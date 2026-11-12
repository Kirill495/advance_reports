import sys, os, json, base64, hashlib, argparse
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import log_config
log_config.setup(os.environ.get("RUN_LOG"))
import requests
from requests.auth import HTTPBasicAuth
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import registry
import config_reader

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(BASE, "config")
TEMP = os.path.join(BASE, "temp")
EMPTY = "00000000-0000-0000-0000-000000000000"
FILE_TYPE = "StandardODATA.Catalog_АвансовыйОтчетПрисоединенныеФайлы"

def norm(s):
    return (s or "").replace("ё", "е").replace("Ё", "Е").strip().lower()

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def _write_result(documents, not_found):
    with open(os.path.join(TEMP, "run_result.json"), "w", encoding="utf-8") as f:
        json.dump({"documents": documents, "not_found": not_found}, f, ensure_ascii=False, indent=2)

def main():
    ap = argparse.ArgumentParser(description="Запись распознанных билетов в 1С + отметка в реестре")
    ap.add_argument("folder", help="Папка с PDF-билетами")
    ap.add_argument("--dry-run", action="store_true", help="Ничего не писать в 1С, только показать план")
    args = ap.parse_args()
    folder = os.path.abspath(args.folder)

    cred = config_reader.one_s_config()
    cfg = config_reader.advance_reports_config()
    recog = load(os.path.join(TEMP, "recognition.json"))
    reg = registry.load()

    base = cred["base_url"].strip().rstrip("/") + "/"
    auth = HTTPBasicAuth(cred["login"], cred["password"])
    JH = {"Accept": "application/json", "Content-Type": "application/json"}

    def get(path, params=None):
        return requests.get(base + path, auth=auth, headers={"Accept": "application/json"}, params=params, timeout=60)
    def post(path, data):
        return requests.post(base + path, auth=auth, headers=JH, json=data, timeout=180)
    def patch(path, data):
        return requests.patch(base + path, auth=auth, headers=JH, json=data, timeout=180)

    documents = []
    not_found = []

    new_files = [f for f in sorted(os.listdir(folder))
                 if f.lower().endswith(".pdf") and not registry.is_processed(reg, os.path.join(folder, f))]
    if not new_files:
        print("Нет новых файлов — записывать нечего.")
        _write_result(documents, not_found)
        return
    new_set = set(new_files)
    print(f"Новых файлов: {len(new_set)}")

    tickets = [t for t in recog["tickets"] if t.get("source_file") in new_set]
    checks = [c for c in recog["checks"] if c.get("source_file") in new_set]
    if not tickets:
        print("Среди новых файлов нет билетов (только чеки/возвраты).")
        _write_result(documents, not_found)
        return

    # ---- сопоставление ФИО (точный фильтр + fallback) ----
    def fix_yo(s):
        return (s or "").replace("ё", "е").replace("Ё", "Е")

    def fetch_eq(surname, name):
        raw = (f"{base}Catalog_ФизическиеЛица?$format=json"
               f"&$filter=Фамилия eq '{fix_yo(surname)}' and Имя eq '{fix_yo(name)}'"
               f"&$select=Ref_Key,ФИО,Фамилия,Имя,Отчество,DeletionMark")
        r = requests.get(raw, auth=auth, headers={"Accept": "application/json"}, timeout=60)
        return [x for x in r.json().get("value", []) if not x.get("DeletionMark")] if r.status_code == 200 else []

    def fetch_startswith(surname):
        raw = (f"{base}Catalog_ФизическиеЛица?$format=json"
               f"&$filter=startswith(Description, '{fix_yo(surname)}')"
               f"&$select=Ref_Key,ФИО,Фамилия,Имя,Отчество,DeletionMark")
        r = requests.get(raw, auth=auth, headers={"Accept": "application/json"}, timeout=60)
        return [x for x in r.json().get("value", []) if not x.get("DeletionMark")] if r.status_code == 200 else []

    tkt_to_check = {}
    for c in recog["checks"]:
        for n in c["tkt_numbers"]:
            tkt_to_check[n] = c
            if len(n) == 14:
                tkt_to_check[n[:13]] = c  # авиа-чек: 13 знаков + контрольная цифра

    tkt_to_refund = {}
    for r in recog.get("refunds", []):
        for it in r.get("items", []):
            n = it.get("tkt_number", "")
            info = {
                "amount": it.get("amount", 0) or 0,
                "fd": r.get("fd", ""),
                "date": r.get("date", ""),
            }
            tkt_to_refund[n] = info
            if len(n) == 14:
                tkt_to_refund[n[:13]] = info

    def person(t):
        ms = fetch_eq(t["passenger_surname"], t["passenger_name"])
        if not ms:
            ms = [x for x in fetch_startswith(t["passenger_surname"]) if norm(x.get("Имя")) == norm(t["passenger_name"])]
        surname, patronymic, status = t["passenger_surname"], t.get("passenger_patronymic") or "", "not_found"
        if len(ms) == 1:
            m = ms[0]
            surname = (m.get("ФИО") or "").split()[0] or surname
            patronymic = m.get("Отчество") or patronymic
            status = "ok"
        elif len(ms) > 1:
            status = "ambiguous"
        initials = t["passenger_name"][0] + "."
        if patronymic:
            initials += patronymic[0] + "."
        return surname, initials, status

    from collections import defaultdict
    rows_by_event = defaultdict(list)
    for t in tickets:
        surname, initials, status = person(t)
        if status == "not_found":
            not_found.append({
                "surname": t["passenger_surname"],
                "name": t["passenger_name"],
                "source_file": t["source_file"],
                "event": t["event"],
            })
        route = t["route"].replace(" → ", "-")
        content = f"{surname} {initials} {t['ticket_number']}, {route}"
        chk = tkt_to_check.get(t["ticket_number"])
        refund = tkt_to_refund.get(t["ticket_number"])
        refund_amt = refund["amount"] if refund else 0
        amount = round((t["amount"] or 0) - refund_amt, 2)
        if refund:
            # входящий документ — чек возврата; в содержании ссылаемся на исходный чек
            incoming_type = "Кассовый чек"
            incoming_number = refund["fd"]
            incoming_date = refund["date"]
            if chk:
                content += f", ВОЗВРАТ; Исходный чек: {chk['fd']}"
        else:
            incoming_type = "Кассовый чек" if chk else "Билет"
            incoming_number = chk["fd"] if chk else t["ticket_number"]
            incoming_date = chk["date"] if chk else t["issue_date"]
        rows_by_event[t["event"]].append({
            "content": content, "surname": surname,
            "ticket_type": t["ticket_type"],
            "amount": amount, "ticket_number": t["ticket_number"],
            "incoming_type": incoming_type,
            "incoming_number": incoming_number,
            "incoming_date": incoming_date,
            "source_file": t["source_file"],
        })

    attach_by_event = defaultdict(list)
    for f in new_files:
        parts = f.split(" - ")
        if len(parts) >= 2:
            attach_by_event[parts[1].strip()].append(f)

    print("\nПлан записи:")
    for ev, rows in sorted(rows_by_event.items()):
        print(f"  {ev}: {len(rows)} строк, {len(attach_by_event[ev])} вложений")

    if args.dry_run:
        print("\n(dry-run) В 1С ничего не записано.")
        return

    for ev, rows in sorted(rows_by_event.items()):
        rep = reg["reports"].get(ev)
        action = "updated" if (rep and rep.get("ref")) else "created"
        doc_number = ""
        if rep and rep.get("ref"):
            doc_key = rep["ref"]
            doc_number = rep.get("number", "")
            print(f"\n[{ev}] дополняю существующий отчёт {doc_number} ({doc_key[:8]}…)")
        else:
            doc = {"Date": "2026-10-01T00:00:00", "ВидОперации": cfg["ВидОперации"],
                   "ВалютаДокумента_Key": cfg["Валюта"], "Организация_Key": cfg["Организация"],
                   "ФизЛицо_Key": cfg["ПодотчетноеЛицо"], "НазначениеАванса": ev,
                   "Комментарий": "", "НДСНеВыделять": True,
                   "КурсДокумента": 1, "КратностьДокумента": 1, "Posted": False}
            r = post("Document_АвансовыйОтчет", doc)
            if r.status_code not in (200, 201):
                print(f"  ОШИБКА создания документа {ev}: {r.status_code} {r.text[:300]}"); continue
            doc_key = r.json()["Ref_Key"]
            num = r.json().get("Number", "")
            doc_number = num
            reg["reports"][ev] = {"ref": doc_key, "number": num}
            print(f"[{ev}] создан документ {num} ({doc_key[:8]}…)")

        documents.append({"event": ev, "number": doc_number, "ref": doc_key, "action": action})

        new_rows = []
        for i, rr in enumerate(rows):
            new_rows.append({
                "LineNumber": i + 1,
                "Номенклатура_Key": cfg["Номенклатура"]["АВИА" if rr["ticket_type"] == "air" else "ЖД"],
                "Сумма": rr["amount"], "СтавкаНДС": "БезНДС", "СуммаНДС": 0,
                "СчетЗатрат_Key": cfg["Счет_26"],
                "Субконто1": cfg["Субконто1"]["Key"], "Субконто1_Type": "StandardODATA." + cfg["Субконто1"]["Тип"],
                "Субконто2": cfg["Субконто2"]["Key"], "Субконто2_Type": "StandardODATA." + cfg["Субконто2"]["Тип"],
                "Субконто3": EMPTY, "Субконто3_Type": "StandardODATA.ChartOfAccounts_Хозрасчетный",
                "Содержание": rr["content"],
                "ВидДокВходящий": rr["incoming_type"], "НомерВходящегоДокумента": rr["incoming_number"],
                "ДатаВходящегоДокумента": rr["incoming_date"] + "T00:00:00",
                "БланкСтрогойОтчетности": False, "СпособУчетаНДС": "Списывается",
            })
        r = patch(f"Document_АвансовыйОтчет(guid'{doc_key}')", {"Прочее": new_rows})
        print(f"  строк Прочее: {r.status_code}")

        ok = 0
        for f in attach_by_event[ev]:
            p = os.path.join(folder, f)
            raw = open(p, "rb").read()
            try:
                r1 = post("Catalog_АвансовыйОтчетПрисоединенныеФайлы", {
                    "Description": f[:-4], "ВладелецФайла_Key": doc_key,
                    "Расширение": "pdf", "Размер": str(len(raw)), "ТипХраненияФайла": "ВИнформационнойБазе"})
                file_ref = r1.json()["Ref_Key"]
                r2 = post("Catalog_ХранилищеДвоичныхДанных", {
                    "Размер": str(len(raw)), "Хеш": base64.b64encode(hashlib.sha256(raw).digest()).decode(),
                    "ДвоичныеДанные_Type": "application/octet-stream",
                    "ДвоичныеДанные_Base64Data": base64.b64encode(raw).decode()})
                bin_ref = r2.json()["Ref_Key"]
                r3 = post("InformationRegister_ХранилищеФайлов", {
                    "Файл": file_ref, "Файл_Type": FILE_TYPE, "ХранилищеДвоичныхДанных_Key": bin_ref})
                if r3.status_code in (200, 201):
                    ok += 1
            except Exception as ex:
                print(f"  ВЛОЖЕНИЕ FAIL {f}: {ex}")
        print(f"  вложения: {ok}/{len(attach_by_event[ev])}")

        r = get(f"Document_АвансовыйОтчет(guid'{doc_key}')/Прочее")
        total = sum(e.get("Сумма", 0) for e in r.json().get("value", [])) if r.status_code == 200 else 0
        patch(f"Document_АвансовыйОтчет(guid'{doc_key}')", {"СуммаДокумента": round(total, 2)})
        surnames = list(dict.fromkeys(rr["surname"] for rr in rows))
        patch(f"Document_АвансовыйОтчет(guid'{doc_key}')", {"Комментарий": ", ".join(surnames)})

        for f in attach_by_event[ev]:
            p = os.path.join(folder, f)
            registry.mark_processed(reg, f, sha256(open(p, "rb").read()), ev,
                                    registry.kind_of(f), "done",
                                    advance_report_number=reg["reports"][ev].get("number"),
                                    advance_report_ref=doc_key)

    registry.save(reg)
    print("\nРеестр обновлён.")
    _write_result(documents, not_found)

if __name__ == "__main__":
    main()
