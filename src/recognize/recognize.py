"""Распознавание документов: texts.json → recognition.json.

Гибрид: для электронных билетов РЖД (TEXT) сначала пробуем быстрый regex-парсер
(recognize.rzd); если парсер не уверен — вызываем LLM. Сумма при спорных случаях
уточняется отдельным запросом к LLM.
"""
import os, sys, json, time
SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # app/src
sys.path.insert(0, SRC)  # для log_config, registry, config_reader
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import log_config
log_config.setup(os.environ.get("RUN_LOG"))

import registry
import config_reader
from recognize import rzd, llm, translit

BASE = os.path.dirname(SRC)  # корень проекта (app/)
TEMP = os.path.join(BASE, "temp")
TEXTS_JSON = os.path.join(TEMP, "texts.json")
RECOGNITION_JSON = os.path.join(TEMP, "recognition.json")


def recognize_file(text, method, llm_cfg):
    """Возвращает (res, method_used, llm_used_for).

    method_used: 'regex' | 'LLM'.
    llm_used_for: список подзадач, для которых при regex-разборе привлекался LLM
                  (например ['ФИО', 'сумма']).
    """
    if method == "TEXT" and rzd.looks_like_rzd(text):
        res = rzd.parse(text)
        if res is not None:
            used_fio_llm = used_amount = False
            for t in res["tickets"]:
                # латинское ФИО (загранпаспорт) — детерминированная транслитерация,
                # LLM только как фолбэк
                if t.get("fio_needs_llm"):
                    raw = t.get("_raw_fio") or ""
                    fio = translit.to_cyrillic_fio(raw)
                    if fio is None:
                        fio = llm.transliterate_fio(raw, llm_cfg)
                        if fio:
                            used_fio_llm = True
                    if fio:
                        t["passenger_surname"] = fio["surname"]
                        t["passenger_name"] = fio["name"]
                        t["passenger_patronymic"] = fio.get("patronymic", "")
                # спорная сумма — уточнение отдельным запросом
                if not t.get("amount_confident", True):
                    amt = llm.verify_amount(t.get("_text") or text, llm_cfg)
                    if amt is not None:
                        t["amount"] = amt
                    used_amount = True
                t.pop("amount_confident", None)
                t.pop("fio_needs_llm", None)
                t.pop("_raw_fio", None)
                t.pop("_text", None)
            llm_used_for = []
            if used_fio_llm:
                llm_used_for.append("ФИО")
            if used_amount:
                llm_used_for.append("сумма")
            return res, "regex", llm_used_for
    return llm.call_llm(text, llm_cfg), "LLM", []


def _apply_qr(check, qr):
    """Номер (fd), дата и сумма чека — эталонно из QR, а не из LLM."""
    check["fd"] = qr["fd"] or check.get("fd", "")
    check["date"] = qr["date"] or check.get("date", "")
    check["amount"] = qr["sum"]
    check["fn"] = qr["fn"]
    check["fp"] = qr["fp"]


def _merge_qr(res, qr_entries):
    """Вливает данные QR ФФД в распознанные чеки.

    Номер (fd), дата и сумма чека берутся эталонно из QR; привязку к билетам
    (tkt_numbers) оставляет LLM, т.к. в QR их нет. Возвращает (res, примечание).
    """
    checks = res.get("checks", [])
    if not checks:
        return res, "QR найден, но чек не распознан (нет tkt_numbers) — QR пропущен"

    if len(qr_entries) == 1 and len(checks) == 1:
        q = qr_entries[0]
        _apply_qr(checks[0], q)
        return res, f"QR эталон: fd={q['fd']}, дата={q['date']}, сумма={q['sum']}"

    # Несколько QR/чеков — сопоставляем по fd (если LLM его распознал верно).
    by_fd = {q["fd"]: q for q in qr_entries}
    matched = 0
    for c in checks:
        q = by_fd.get(c.get("fd") or "")
        if q:
            _apply_qr(c, q)
            matched += 1
    return res, f"QR: сопоставлено по fd {matched}/{len(checks)}"


def main():
    texts = json.load(open(TEXTS_JSON, encoding="utf-8")) if os.path.exists(TEXTS_JSON) else {}
    if not texts:
        print("Нет новых файлов — распознавать нечего.")
        return

    llm_cfg = config_reader.llm_config()
    recog = json.load(open(RECOGNITION_JSON, encoding="utf-8")) if os.path.exists(RECOGNITION_JSON) \
        else {"tickets": [], "checks": [], "refunds": []}
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

    print(f"Распознаю {len(todo)} файлов (модель {llm_cfg.get('model')})...")
    added_t = added_c = added_r = 0
    for i, f in enumerate(todo, 1):
        qr_entries = texts[f].get("qr", [])
        hint = "regex" if (texts[f].get("method") == "TEXT"
                           and rzd.looks_like_rzd(texts[f]["text"])) else "LLM"
        if qr_entries:
            hint += "+QR"
        print(f"[{i}/{len(todo)}] {f} - начат разбор [{hint}]")
        t0 = time.time()
        try:
            res, method_used, llm_used_for = recognize_file(
                texts[f]["text"], texts[f].get("method", ""), llm_cfg)
        except Exception as ex:
            print(f"  ОШИБКА: {ex}")
            continue
        dt = time.time() - t0

        qr_note = ""
        if qr_entries:
            res, qr_note = _merge_qr(res, qr_entries)

        ev = os.environ.get("RUN_EVENT") or config_reader.event_of(f)
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

        if llm_used_for:
            print(f"  (привлечён LLM для: {', '.join(llm_used_for)})")
        if qr_note:
            print(f"  ({qr_note})")
        print(f"  OK разбор завершён ({dt:.1f}с): "
              f"+{len(res.get('tickets', []))} билетов, "
              f"+{len(res.get('checks', []))} чеков, "
              f"+{len(res.get('refunds', []))} возвратов")

    with open(RECOGNITION_JSON, "w", encoding="utf-8") as fh:
        json.dump(recog, fh, ensure_ascii=False, indent=2)
    print(f"\nРаспознавание завершено: билетов {added_t}, чеков {added_c}, возвратов {added_r}. "
          f"Сохранено в {RECOGNITION_JSON}")


if __name__ == "__main__":
    main()
