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

    # Итоговые строки текущей загрузки (write_1c.py → temp/final_rows.json)
    rows_path = os.path.join(TEMP, "final_rows.json")
    rows = json.load(open(rows_path, encoding="utf-8")) if os.path.exists(rows_path) else []

    td_path = os.path.join(TEMP, "travel_dates.json")
    travel_dates = json.load(open(td_path, encoding="utf-8")) if os.path.exists(td_path) else {}

    # Номер авансового отчёта: из свежего run_result.json, иначе из реестра
    result_path = os.path.join(TEMP, "run_result.json")
    run_result = json.load(open(result_path, encoding="utf-8")) if os.path.exists(result_path) else {}
    report_by_event = {d["event"]: d.get("number", "") for d in run_result.get("documents", [])}
    reg = registry.load()

    wb = Workbook()
    ws = wb.active
    ws.title = "Билеты"
    ws.append(["Мероприятие", "ФИО", "Маршрут", "Дата", "Тип", "Сумма", "№ чека", "Дата чека", "Авансовый отчет", "Билет", "Чек"])
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for r in sorted(rows, key=lambda x: (x["event"], x["surname"], x["name"])):
        td = travel_dates.get(r["source_file"])
        travel = datetime.strptime(td, "%Y-%m-%d").date() if td else ""
        chk_date = datetime.strptime(r["chk_date"], "%Y-%m-%d").date() if r.get("chk_date") else ""
        rep_number = report_by_event.get(r["event"], reg["reports"].get(r["event"], {}).get("number", ""))
        ws.append([r["event"], f'{r["surname"]} {r["name"]}', r["route"], travel,
                   TYPE_MAP.get(r["ticket_type"], r["ticket_type"]), float(r["amount"]),
                   r.get("chk_fd", ""), chk_date, rep_number,
                   r.get("source_file", ""), r.get("chk_file", "")])

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
    print(f"Excel сохранён: {path} | строк билетов: {len(rows)}")

    # путь к Excel — в сводку для письма
    result = run_result
    result["excel"] = path
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
