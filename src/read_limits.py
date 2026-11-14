"""Чтение уточняющего реестра (Excel) → temp/limits.json.

Excel-файл «Уточняющий реестр» содержит лист «Реестр_знач» с уточнёнными суммами
возмещения за проезд по каждому судье. Колонки ищем не по буквам, а по содержимому
заголовков: «ФИО судьи» и «Сумма возмещения расходов за проезд (руб.)».

Результат пишется в temp/limits.json:
  {"readable": bool, "reason": str, "limits": {нормализованная_фамилия: сумма}}

Если файл не указан/не найден/не читаем — readable=false и reason с причиной
(суммы тогда берутся чисто из билетов/чеков).
"""
import os, sys, json, argparse
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import log_config
log_config.setup(os.environ.get("RUN_LOG"))

from openpyxl import load_workbook

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP = os.path.join(BASE, "temp")
LIMITS_JSON = os.path.join(TEMP, "limits.json")

FIO_HEADER = "фио судьи"
AMOUNT_HEADER = "сумма возмещения расходов за проезд"


def norm(s):
    return (s or "").replace("ё", "е").replace("Ё", "Е").strip().lower()


def parse_amount(v):
    """Число или строка вида '0,00' / '6183,7' → float."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("\xa0", " ").replace(" ", "").replace("р.", "").replace("руб.", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def find_header(ws, needle):
    """Вернуть (row, col) первой ячейки, чьё значение содержит needle (без учёта регистра/ё)."""
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and needle in norm(cell.value):
                return cell.row, cell.column
    return None, None


def write_result(result):
    os.makedirs(TEMP, exist_ok=True)
    with open(LIMITS_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser(description="Чтение уточняющего реестра (Excel) → temp/limits.json")
    ap.add_argument("excel", nargs="?", default="", help="Путь к xlsx-файлу уточняющего реестра")
    args = ap.parse_args()

    result = {"readable": False, "reason": "", "limits": {}}

    if not args.excel:
        result["reason"] = "файл не указан"
        print("[Уточняющий реестр] файл не указан — суммы берутся из билетов/чеков.")
        write_result(result)
        return
    if not os.path.exists(args.excel):
        result["reason"] = f"файл не найден: {args.excel}"
        print(f"[Уточняющий реестр] файл не читаем: {result['reason']} — суммы берутся из билетов/чеков.")
        write_result(result)
        return

    print(f"[Уточняющий реестр] читаю: {args.excel}")
    try:
        wb = load_workbook(args.excel, data_only=True)
    except Exception as ex:
        result["reason"] = f"не удалось открыть файл ({type(ex).__name__}: {ex})"
        print(f"[Уточняющий реестр] файл не читаем: {result['reason']} — суммы берутся из билетов/чеков.")
        write_result(result)
        return

    try:
        if "Реестр_знач" not in wb.sheetnames:
            result["reason"] = "нет листа «Реестр_знач»"
            print(f"[Уточняющий реестр] файл не читаем: {result['reason']} — суммы берутся из билетов/чеков.")
            write_result(result)
            return

        ws = wb["Реестр_знач"]
        fio_row, fio_col = find_header(ws, FIO_HEADER)
        amt_row, amt_col = find_header(ws, AMOUNT_HEADER)

        if fio_col is None or amt_col is None:
            missing = []
            if fio_col is None:
                missing.append("«ФИО судьи»")
            if amt_col is None:
                missing.append("«Сумма возмещения расходов за проезд (руб.)»")
            result["reason"] = "не найдена колонка " + " и ".join(missing)
            print(f"[Уточняющий реестр] файл не читаем: {result['reason']} — суммы берутся из билетов/чеков.")
            write_result(result)
            return

        start = max(fio_row, amt_row) + 1
        # группируем по полному ФИО (на случай нескольких строк на человека)
        by_fio = {}
        for r in range(start, ws.max_row + 1):
            fio = ws.cell(row=r, column=fio_col).value
            amt = ws.cell(row=r, column=amt_col).value
            if fio is None or not str(fio).strip() or amt is None:
                continue  # пустые строки / строка «Итого» / подпись
            key = norm(str(fio))
            by_fio[key] = round(by_fio.get(key, 0.0) + parse_amount(amt), 2)

        # фамилия → сумма (ключ для сопоставления с билетами)
        limits = {}
        collisions = []
        for fio_norm, amount in by_fio.items():
            surname = fio_norm.split()[0] if fio_norm.split() else ""
            if not surname:
                continue
            if surname in limits:
                collisions.append(surname)
                limits[surname] = round(limits[surname] + amount, 2)
            else:
                limits[surname] = amount
        if collisions:
            print(f"  (внимание: несколько судей с одинаковой фамилией {collisions} — суммы сложены)")

        result["readable"] = True
        result["reason"] = ""
        result["limits"] = limits
        print(f"[Уточняющий реестр] прочитано судей: {len(by_fio)} (с ненулевой суммой: {sum(1 for a in limits.values() if a > 0)})")
    finally:
        wb.close()

    write_result(result)


if __name__ == "__main__":
    main()
