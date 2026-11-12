import os, sys, json, argparse
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import log_config
log_config.setup(os.environ.get("RUN_LOG"))
from openpyxl import Workbook
from openpyxl.styles import Font
import registry

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP = os.path.join(BASE, "temp")
TYPE_MAP = {"air": "Авиа", "rail": "ЖД", "bus": "Автобус"}

def main():
    ap = argparse.ArgumentParser(description="Формирование Excel-сводки")
    ap.add_argument("out_dir", help="Каталог для результата (Excel)")
    args = ap.parse_args()
    out_dir = os.path.abspath(args.out_dir)

    recog = json.load(open(os.path.join(TEMP, "recognition.json"), encoding="utf-8"))
    travel_dates = json.load(open(os.path.join(TEMP, "travel_dates.json"), encoding="utf-8"))
    reg = registry.load()

    tickets = recog["tickets"]
    checks = recog["checks"]

    tkt_to_check = {}
    for c in checks:
        for t in c["tkt_numbers"]:
            tkt_to_check[t] = c

    wb = Workbook()
    ws = wb.active
    ws.title = "Билеты"
    ws.append(["Мероприятие", "ФИО", "Маршрут", "Дата", "Тип", "Сумма", "№ чека", "Дата чека", "Авансовый отчет", "Билет", "Чек"])
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for t in sorted(tickets, key=lambda x: (x["event"], x["passenger_surname"], x["passenger_name"])):
        chk = tkt_to_check.get(t["ticket_number"])
        td = travel_dates.get(t["source_file"])
        travel = datetime.strptime(td, "%Y-%m-%d").date() if td else ""
        chk_date = datetime.strptime(chk["date"], "%Y-%m-%d").date() if (chk and chk.get("date")) else ""
        rep = reg["reports"].get(t["event"], {})
        ws.append([t["event"], f'{t["passenger_surname"]} {t["passenger_name"]}', t["route"], travel,
                   TYPE_MAP.get(t["ticket_type"], t["ticket_type"]), float(t["amount"]),
                   chk["fd"] if chk else "", chk_date, rep.get("number", ""),
                   t.get("source_file", ""), chk["source_file"] if chk else ""])

    for col, w in [("A",14),("B",24),("C",34),("D",12),("E",10),("F",12),("G",12),("H",12),("I",18),("J",60),("K",60)]:
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2, min_col=6, max_col=6):
        for cell in row:
            cell.number_format = "#,##0.00"
    for row in ws.iter_rows(min_row=2, min_col=4, max_col=4):
        for cell in row:
            cell.number_format = "DD.MM.YYYY"
    for row in ws.iter_rows(min_row=2, min_col=8, max_col=8):
        for cell in row:
            cell.number_format = "DD.MM.YYYY"
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    os.makedirs(out_dir, exist_ok=True)
    filename = "uploaded_tickets_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".xlsx"
    path = os.path.join(out_dir, filename)
    wb.save(path)
    print(f"Excel сохранён: {path} | строк билетов: {len(tickets)}")

    # путь к Excel — в сводку для письма
    result_path = os.path.join(TEMP, "run_result.json")
    result = json.load(open(result_path, encoding="utf-8")) if os.path.exists(result_path) else {}
    result["excel"] = path
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
