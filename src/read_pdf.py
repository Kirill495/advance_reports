import argparse, os, sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import log_config
log_config.setup(os.environ.get("RUN_LOG"))

import pymupdf
import registry
import qr_ffd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP = os.path.join(BASE, "temp")
TEXTS_JSON = os.path.join(TEMP, "texts.json")

PDF_EXTS = (".pdf",)
IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")
DOC_EXTS = PDF_EXTS + IMG_EXTS

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

def extract(path):
    """Извлекает текст документа. PDF — текстовый слой (+OCR-фолбэк), изображение — OCR."""
    ext = os.path.splitext(path)[1].lower()
    if ext in IMG_EXTS:
        res, _ = get_ocr()(path)
        return "\n".join(t for _, t, _ in (res or [])), "OCR"
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
    ap = argparse.ArgumentParser(description="Чтение документов (PDF/изображения) → temp/texts.json")
    ap.add_argument("folder", help="Папка с документами (PDF, PNG, JPG, ...)")
    args = ap.parse_args()
    folder = os.path.abspath(args.folder)

    os.makedirs(TEMP, exist_ok=True)
    reg = registry.load()
    docs = sorted(f for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in DOC_EXTS)
    new_files = [f for f in docs if not registry.is_processed(reg, os.path.join(folder, f))]

    print(f"Документов всего: {len(docs)} | новых: {len(new_files)}")
    result = {}
    for f in new_files:
        path = os.path.join(folder, f)
        text, method = extract(path)
        qr = qr_ffd.extract_checks(path)
        result[f] = {"text": text, "method": method, "qr": qr}
        qr_note = f", QR-чеков: {len(qr)}" if qr else ""
        print(f"   [{method}] {f} ({len(text)} зн.{qr_note})")

    with open(TEXTS_JSON, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f"Сохранено: {TEXTS_JSON} ({len(result)} файлов)")

if __name__ == "__main__":
    main()
