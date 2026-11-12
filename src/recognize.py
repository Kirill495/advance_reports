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
    '{"tickets": [...], "checks": [...], "refunds": [...]}\n\n'
    "Ticket fields (each object in tickets):\n"
    '- "ticket_type": "air" | "rail" | "bus" (infer from the text: flight → air, train → rail, bus → bus)\n'
    '- "carrier": string — any company name (airline / railway / bus operator / ferry, ...)\n'
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
    '- "tkt_numbers": array of ticket numbers, digits only. AIR: the ticket number is 13 digits, but the receipt often prints 13 digits + 1 trailing check digit = 14 digits — take ONLY the first 13 digits (drop the trailing check digit). RAIL (ФПК/РЖД): the number is 14 digits, take all 14. In a line like "1. TKT - 65521029281131 шт" the number is "6552102928113" and "1 шт" is the quantity — never merge the quantity.\n'
    '- "date": "YYYY-MM-DD" (receipt date)\n\n'
    "Refund fields (one object in refunds, only for a REFUND receipt \"Возврат прихода\"):\n"
    '- "fd": FD number\n'
    '- "date": "YYYY-MM-DD"\n'
    '- "items": array of {"tkt_number": "13-digit ticket number (drop the trailing check digit)", "amount": refunded amount for this ticket}\n\n'
    "Rules:\n"
    "- A single PDF/image may contain SEVERAL documents at once — e.g. a ticket (or several tickets) AND a cash receipt. Recognize and return ALL of them (tickets and checks together), never just one.\n"
    "- A TICKET is any travel document that has a passenger name AND a ticket/document number (a long digit string, often labeled \"Билет №\", \"Номер билета\", \"Ticket number\", \"№\") AND a route (from → to). It can be air, rail, bus, ferry, etc. — do not rely on a specific carrier or layout.\n"
    "- If the text contains several tickets (several passengers) return several objects in tickets.\n"
    "- A CASH RECEIPT is a document with \"Кассовый чек\", \"ФД\", \"ИТОГО\", and/or \"TKT - <number>\" lines — return it in checks.\n"
    '- A REFUND ("Возврат прихода") — return it in refunds (items from the "TKT - <number>" lines).\n'
    "- Do not confuse issue_date with flight/travel date.\n"
    '- Take TOTAL amount (labels "Итого", "Total", "Сумма платежа"), not the taxes sum.\n'
    "- Translate months to numbers: января→01, окт.→10, Oct→10, SEP→09, ...\n"
    '- If a field is missing use null (numbers) or "" (strings).'
)

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
    recog = json.load(open(RECOGNITION_JSON, encoding="utf-8")) if os.path.exists(RECOGNITION_JSON) else {"tickets": [], "checks": [], "refunds": []}
    recog.setdefault("tickets", [])
    recog.setdefault("checks", [])
    recog.setdefault("refunds", [])

    known = ({t.get("source_file") for t in recog["tickets"]}
             | {c.get("source_file") for c in recog["checks"]}
             | {r.get("source_file") for r in recog["refunds"]})
    todo = [f for f in texts if f not in known]

    if not todo:
        print("Все новые файлы уже распознаны.")
        return

    print(f"Распознаю {len(todo)} файлов (модель {llm.get('model')})...")
    added_t = added_c = added_r = 0
    for f in todo:
        try:
            res = call_llm(texts[f]["text"], llm)
        except Exception as ex:
            print(f"  FAIL {f}: {ex}")
            continue
        ev = config_reader.event_of(f)
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
        for r in res.get("refunds", []):
            r["source_file"] = f
            r["event"] = ev
            recog["refunds"].append(r)
            added_r += 1
        print(f"  OK {f}: +{len(res.get('tickets', []))} билетов, +{len(res.get('checks', []))} чеков, +{len(res.get('refunds', []))} возвратов")

    with open(RECOGNITION_JSON, "w", encoding="utf-8") as fh:
        json.dump(recog, fh, ensure_ascii=False, indent=2)
    print(f"\nРаспознавание завершено: билетов {added_t}, чеков {added_c}, возвратов {added_r}. Сохранено в {RECOGNITION_JSON}")

if __name__ == "__main__":
    main()
