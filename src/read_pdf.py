import argparse, os, sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import log_config
log_config.setup(os.environ.get("RUN_LOG"))

import pymupdf
import registry

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP = os.path.join(BASE, "temp")
TEXTS_JSON = os.path.join(TEMP, "texts.json")

_ocr = None
def get_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr

def readable_ratio(text):
    if not text:
        return 0.0
    good = sum(1 for ch in text if ch.isalnum() or ch.isspace() or ch in ".,:;/-()№\"'₽%*=")
    return good / len(text)

def ocr_pdf(doc, tmp_png):
    parts = []
    for pg in doc:
        pix = pg.get_pixmap(dpi=200)
        pix.save(tmp_png)
        res, _ = get_ocr()(tmp_png)
        parts.append("\n".join(t for _, t, _ in (res or [])))
    return "\n".join(parts)

def extract_text(path):
    doc = pymupdf.open(path)
    text = "\n".join(pg.get_text() for pg in doc)
    cyr = sum(1 for ch in text if 'А' <= ch <= 'я' or ch in 'Ёё')
    if readable_ratio(text) < 0.5 or (cyr < 20 and len(text) > 100):
        tmp = os.path.join(TEMP, "_ocr_tmp.png")
        text = ocr_pdf(doc, tmp)
        if os.path.exists(tmp):
            os.remove(tmp)
        doc.close()
        return text, "OCR"
    doc.close()
    return text, "TEXT"

def main():
    ap = argparse.ArgumentParser(description="Чтение PDF → temp/texts.json")
    ap.add_argument("folder", help="Папка с PDF-билетами")
    args = ap.parse_args()
    folder = os.path.abspath(args.folder)

    os.makedirs(TEMP, exist_ok=True)
    reg = registry.load()
    pdfs = sorted(f for f in os.listdir(folder) if f.lower().endswith(".pdf"))
    new_files = [f for f in pdfs if not registry.is_processed(reg, os.path.join(folder, f))]

    print(f"PDF всего: {len(pdfs)} | новых: {len(new_files)}")
    result = {}
    for f in new_files:
        text, method = extract_text(os.path.join(folder, f))
        result[f] = {"text": text, "method": method}
        print(f"   [{method}] {f} ({len(text)} зн.)")

    with open(TEXTS_JSON, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f"Сохранено: {TEXTS_JSON} ({len(result)} файлов)")

if __name__ == "__main__":
    main()
