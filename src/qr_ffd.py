"""Чтение QR-кодов фискальных чеков (ФФД) из файлов документов.

Кассовый чек ККТ содержит QR-код со строкой формата фискальных документов:
    t=YYYYMMDDTHHMM&s=СУММА&fn=ФН&i=ФД&fp=ФП&n=ТИП
где:
    t  — дата/время чека;
    s  — сумма;
    fn — номер фискального накопителя;
    i  — номер фискального документа (в системе это поле чека `fd`);
    fp — фискальный признак;
    n  — тип операции (1 приход, 2 возврат прихода, 3 расход, 4 возврат расхода).

Классификация «чек / не чек» — детерминированная, по наличию ФФД-сигнатуры
(fn + i), без LLM. Не-ФФД QR (ссылки, СБП, промо) отбрасываются.
"""
import io, os, re
from datetime import datetime

IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")

_FFD_DATE = re.compile(r"(\d{8})T?(\d{4})")


def parse_ffd(text):
    """Парсит ФФД-строку в dict {date, sum, fn, fd, fp, op} или None.

    None, если строка не похожа на фискальный QR (нет fn и i).
    Устойчив как к «голой» строке t=…&s=…&fn=…, так и к URL-варианту https://…?t=….
    """
    if not text:
        return None

    def get(key):
        m = re.search(r"(?:^|[&?])" + re.escape(key) + r"=([^&]*)", text)
        return m.group(1) if m else ""

    fn = get("fn")
    fd = get("i")
    if not fn or not fd:
        return None

    date = ""
    m = _FFD_DATE.search(get("t"))
    if m:
        try:
            date = datetime.strptime(m.group(1), "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            date = ""

    amount = None
    s = get("s")
    if s:
        try:
            amount = round(float(s.replace(",", ".")), 2)
        except ValueError:
            amount = None

    return {
        "date": date,
        "sum": amount,
        "fn": fn,
        "fd": fd,
        "fp": get("fp"),
        "op": get("n"),
    }


def decode_qr_texts(image):
    """Список текстов QR-кодов с одного изображения (PIL). Ошибки/нет кодов → []."""
    try:
        import zxingcpp
    except Exception:
        return []
    qr_formats = (zxingcpp.BarcodeFormat.QRCode,
                  zxingcpp.BarcodeFormat.MicroQRCode,
                  zxingcpp.BarcodeFormat.RMQRCode)
    texts = []
    try:
        for b in zxingcpp.read_barcodes(image):
            if b.format in qr_formats:
                texts.append(b.text)
    except Exception:
        pass
    return texts


def _page_images(path):
    """Изображения страниц файла: PDF → рендер каждой страницы, картинка → как есть."""
    from PIL import Image
    ext = os.path.splitext(path)[1].lower()
    if ext in IMG_EXTS:
        return [Image.open(path).convert("RGB")]

    import pymupdf
    doc = pymupdf.open(path)
    images = []
    try:
        for pg in doc:
            pix = pg.get_pixmap(dpi=200)
            images.append(Image.open(io.BytesIO(pix.tobytes("png"))))
    finally:
        doc.close()
    return images


def extract_checks(path):
    """Распознанные чеки из файла: [{date, sum, fn, fd, fp, op}].

    Дедупликация по (fn, fd); не-ФФД QR отбрасываются; ошибки чтения → [].
    """
    checks = []
    seen = set()
    try:
        images = _page_images(path)
    except Exception:
        return checks
    for img in images:
        for text in decode_qr_texts(img):
            parsed = parse_ffd(text)
            if not parsed:
                continue
            key = (parsed["fn"], parsed["fd"])
            if key in seen:
                continue
            seen.add(key)
            checks.append(parsed)
    return checks
