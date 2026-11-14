"""Парсер электронных билетов РЖД/ФПК (регулярные выражения).

Используется как «быстрый путь» в гибридном распознавании: если текст похож на
электронный билет РЖД и парсер уверенно извлёк все поля — LLM не вызывается.
Сумма извлекается с флагом уверенности; при неуверенности она уточняется через LLM.

Возвращает ту же схему, что и LLM: {"tickets": [...], "checks": [], "refunds": []}.
Если файл разобрать не удалось (или не тот формат) — возвращает None.
"""
import re
from datetime import datetime

HEADER = "ЭЛЕКТРОННЫЙ БИЛЕТ. КОНТРОЛЬНЫЙ КУПОН"


def looks_like_rzd(text):
    """True, если текст похож на электронный билет РЖД (может содержать несколько купонов)."""
    return HEADER in (text or "")


def _split_coupons(text):
    parts = text.split(HEADER)
    return [p for p in parts if p.strip()]


def _to_number(s):
    """'2 480,00' → 2480.0; None, если не число."""
    s = (s or "").replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date_ru(s):
    """'05.11.2026' → '2026-11-05'; None, если не дата."""
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", (s or "").strip())
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _extract_amount(text):
    """Извлекает сумму «Итого» и флаг уверенности.

    Возвращает (amount, confident). amount — float|None.
    Спорным считаем, если: «Итого» нет/несколько; число не парсится/<=0;
    или перекрёстная проверка по компонентам не сходится.
    """
    m = re.search(r"Итого[^\d]*?(\d[\d\s]*,\d{2})\s*₽", text)
    amount = _to_number(m.group(1)) if m else None

    n_itogo = len(re.findall(r"Итого", text))
    if n_itogo != 1 or amount is None or amount <= 0:
        return amount, False

    # перекрёстная проверка: сумма какой-либо пары компонентов до «Итого» == итог
    money = [(mm.start(), _to_number(mm.group(1)))
             for mm in re.finditer(r"(\d[\d\s]*,\d{2})\s*₽", text)]
    itogo_pos = text.find("Итого")
    comps = [v for pos, v in money if pos < itogo_pos and v is not None]
    if len(comps) >= 2:
        ok = any(abs(comps[i] + comps[j] - amount) <= 0.02
                 for i in range(len(comps)) for j in range(i + 1, len(comps)))
        if not ok:
            return amount, False

    return amount, True


def _parse_coupon(text):
    """Разбирает один контрольный купон. Возвращает dict или None."""
    # 1. Номер билета
    m = re.search(r"№\s*(\d[\d \xa0]*\d)", text)
    if not m:
        return None
    number = re.sub(r"[\s\xa0]+", "", m.group(1))
    if len(number) < 13:
        return None

    # 2. ФИО (верхний регистр). Кириллицу разбираем сразу; латиницу (загранпаспорт)
    #    помечаем флагом — транслитерацию сделает LLM (при этом остальные поля уже
    #    извлечены регулярками).
    m = re.search(r"(?:ЗАГРАНИЧНЫЙ\s+)?ПАСПОРТ\s+РФ\s*\d+\s*\n"
                  r"\s*[\d.]+\s+RUS\s*[МЖ]\s*\n"
                  r"\s*([A-ZА-ЯЁ]+(?:\s+[A-ZА-ЯЁ]+){1,2})", text)
    if not m:
        return None
    raw_fio = " ".join(m.group(1).split())
    parts = raw_fio.split()
    surname = parts[0].title()
    name = parts[1].title()
    patronymic = parts[2].title() if len(parts) > 2 else ""
    fio_needs_llm = not any('А' <= ch <= 'Я' or ch == 'Ё' for ch in raw_fio)

    # 3. Маршрут — из строки-сводки «… <ОТПРАВЛЕНИЕ> - <ПРИБЫТИЕ> ПН|ЗП…»
    route = None
    for line in text.splitlines():
        if " - " in line and re.search(r"(?:ПН|ЗП)\d{6,}", line):
            rm = re.search(r"\s([А-ЯЁA-Z][А-ЯЁA-Z0-9\-\s]*?)\s+-\s+"
                           r"([А-ЯЁA-Z][А-ЯЁA-Z0-9\-\s]*?)\s+(?:ПН|ЗП)\d", line)
            if rm:
                dep = re.sub(r"\s+", " ", rm.group(1).strip()).title()
                arr = re.sub(r"\s+", " ", rm.group(2).strip()).title()
                route = f"{dep} → {arr}"
                break
    if route is None:
        return None

    # 4. Дата оформления (issue_date)
    m = re.search(r"Оформлен:\s*\n\s*(\d{2}\.\d{2}\.\d{4})", text)
    issue_date = _parse_date_ru(m.group(1)) if m else None

    # 5. Сумма
    amount, amount_confident = _extract_amount(text)

    return {
        "passenger_surname": surname,
        "passenger_name": name,
        "passenger_patronymic": patronymic,
        "ticket_number": number,
        "issue_date": issue_date or "",
        "route": route,
        "ticket_type": "rail",
        "amount": amount,
        "amount_confident": amount_confident,
        "currency": "RUB",
        "fio_needs_llm": fio_needs_llm,
        "_raw_fio": raw_fio,
        "_text": text,
    }


def parse(text):
    """Разбирает текст (возможно, несколько купонов). Возвращает схему LLM или None."""
    coupons = _split_coupons(text)
    if not coupons:
        return None
    tickets = []
    for cup in coupons:
        t = _parse_coupon(cup)
        if t is None:
            return None  # не уверены в файле целиком → отдаём LLM
        tickets.append(t)
    return {"tickets": tickets, "checks": [], "refunds": []}
