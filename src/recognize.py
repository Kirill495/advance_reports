import os, sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import log_config
log_config.setup(os.environ.get("RUN_LOG"))
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import registry
import config_reader

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(BASE, "config")
TEMP = os.path.join(BASE, "temp")
TEXTS_JSON = os.path.join(TEMP, "texts.json")
RECOGNITION_JSON = os.path.join(TEMP, "recognition.json")

SYSTEM_PROMPT = (
    "Extract structured data from the text of a travel ticket or cash receipt (text was extracted from a PDF). "
    "Return STRICTLY one JSON object, no prose, no markdown fences:\n"
    '{"tickets": [...], "checks": [...]}\n\n'
    "Ticket fields (each object in tickets):\n"
    '- "ticket_type": "air" | "rail" | "bus"\n'
    '- "carrier": string (SCAT, Aeroflot, RZD, Utair, Pobeda, Ural Airlines, ...)\n'
    '- "passenger_raw": full name exactly as written\n'
    '- "passenger_surname": surname in Cyrillic (transliterate Latin: KALAEV→Калаев, IURII→Юрий, TKACHEV→Ткачёв)\n'
    '- "passenger_name": given name in Cyrillic\n'
    '- "passenger_patronymic": patronymic in Cyrillic ("" if absent)\n'
    '- "ticket_number": ticket number, digits only (strip №/TKT/spaces)\n'
    '- "issue_date": "YYYY-MM-DD" (ticket ISSUE date, not travel date)\n'
    '- "route": "From → To" (all segments joined by " → ", e.g. "Москва → Шымкент → Москва")\n'
    '- "amount": number (TOTAL amount in rubles)\n'
    '- "currency": "RUB"\n\n'
    "Check fields (each object in checks):\n"
    '- "fd": FD number (value after "ФД:" or "№ ФД:")\n'
    '- "tkt_numbers": array of ticket numbers. Air tickets are usually 13 digits, rail (ФПК/РЖД) are 14 digits — take the FULL number as written, never truncate. In a line like "1. TKT - 65521029281131 шт" the number is "6552102928113" and "1 шт" is the quantity — do NOT merge the quantity into the number.\n'
    '- "date": "YYYY-MM-DD" (receipt date)\n\n'
    "Rules:\n"
    "- If the text contains several tickets (several passengers) return several objects in tickets.\n"
    "- If it is a cash receipt return tickets:[] and one object in checks.\n"
    '- If it is a refund ("Возврат прихода") return {"tickets": [], "checks": [], "note": "возврат"}.\n'
    "- Do not confuse issue_date with flight/travel date.\n"
    '- Take TOTAL amount (labels "Итого", "Total", "Сумма платежа"), not the taxes sum.\n'
    "- Translate months to numbers: января→01, окт.→10, Oct→10, SEP→09, ...\n"
    '- If a field is missing use null (numbers) or "" (strings).'
)

def event_of(name):
    parts = name.split(" - ")
    return parts[1].strip() if len(parts) >= 2 else ""

def call_llm(text, llm):
    url = llm["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {llm['api_key']}", "Content-Type": "application/json"}
    payload = {
        "model": llm["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
    }
    try:
        payload["response_format"] = {"type": "json_object"}
    except Exception:
        pass
    # verify=False: в окружении корпоративный прокси с самоподписанным сертификатом
    r = requests.post(url, headers=headers, json=payload, timeout=180, verify=False)
    if r.status_code != 200:
        raise RuntimeError(f"LLM {r.status_code}: {r.text[:300]}")
    content = r.json()["choices"][0]["message"]["content"]
    return json.loads(content)

def main():
    texts = json.load(open(TEXTS_JSON, encoding="utf-8")) if os.path.exists(TEXTS_JSON) else {}
    if not texts:
        print("Нет новых файлов — распознавать нечего.")
        return

    llm = config_reader.llm_config()
    recog = json.load(open(RECOGNITION_JSON, encoding="utf-8")) if os.path.exists(RECOGNITION_JSON) else {"tickets": [], "checks": []}
    recog.setdefault("tickets", [])
    recog.setdefault("checks", [])

    known = {t.get("source_file") for t in recog["tickets"]} | {c.get("source_file") for c in recog["checks"]}
    todo = [f for f in texts if f not in known]

    if not todo:
        print("Все новые файлы уже распознаны.")
        return

    print(f"Распознаю {len(todo)} файлов (модель {llm.get('model')})...")
    added_t = added_c = 0
    for f in todo:
        try:
            res = call_llm(texts[f]["text"], llm)
        except Exception as ex:
            print(f"  FAIL {f}: {ex}")
            continue
        ev = event_of(f)
        for t in res.get("tickets", []):
            t["source_file"] = f
            t["event"] = ev
            recog["tickets"].append(t)
            added_t += 1
        for c in res.get("checks", []):
            c["source_file"] = f
            c["event"] = ev
            recog["checks"].append(c)
            added_c += 1
        note = res.get("note", "")
        print(f"  OK {f}: +{len(res.get('tickets', []))} билетов, +{len(res.get('checks', []))} чеков"
              + (f" [{note}]" if note else ""))

    with open(RECOGNITION_JSON, "w", encoding="utf-8") as fh:
        json.dump(recog, fh, ensure_ascii=False, indent=2)
    print(f"\nРаспознавание завершено: добавлено билетов {added_t}, чеков {added_c}. Сохранено в {RECOGNITION_JSON}")

if __name__ == "__main__":
    main()
