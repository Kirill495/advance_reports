import smtplib, ssl, sys, os, json, uuid
from email.message import EmailMessage
from email.utils import make_msgid
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import log_config
log_config.setup(os.environ.get("RUN_LOG"))
import config_reader

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP = os.path.join(BASE, "temp")

SUBJECT = "Формирование отчетов завершено"

def odata_ref_to_1c(ref):
    """Ref_Key (UUID OData) → 1С-формат GUID для навигационной ссылки."""
    b = uuid.UUID(ref).bytes
    return (b[3::-1] + b[5:3:-1] + b[7:5:-1] + b[8:]).hex()

def nav_link(web_base, ref):
    return f"{web_base}#e1cib/data/Документ.АвансовыйОтчет?ref={odata_ref_to_1c(ref)}"

def main():
    cfg = config_reader.mail_config()
    if not cfg["login"] or not cfg["password"] or not cfg["to"]:
        print("Пропускаю отправку: не заданы MAIL_LOGIN / MAIL_PASSWD / MAIL_TO.")
        return

    for field in ("login", "password", "to"):
        try:
            cfg[field].encode("ascii")
        except UnicodeEncodeError:
            print(f"ОШИБКА: поле «{field}» содержит не-ASCII символы: {cfg[field]!r}")
            sys.exit(1)

    result_path = os.path.join(TEMP, "run_result.json")
    result = json.load(open(result_path, encoding="utf-8")) if os.path.exists(result_path) else {}
    documents = result.get("documents", [])
    not_found = result.get("not_found", [])
    excel = result.get("excel", "")

    web_base = config_reader.one_s_web_base()

    # HTML-тело письма
    h = ["<html><body style='font-family:Arial,sans-serif;font-size:14px'>"]
    h.append("<h3>Формирование отчетов завершено</h3>")

    if documents:
        h.append("<p><b>Документы в 1С:</b></p><ul>")
        for d in documents:
            label = f"{d['event']} — {d['number']}" + (" (создан)" if d.get("action") == "created" else " (дополнен)")
            link = nav_link(web_base, d["ref"])
            h.append(f'<li><a href="{link}">{label}</a></li>')
        h.append("</ul>")
    else:
        h.append("<p>Новые документы не создавались.</p>")

    if not_found:
        h.append("<p><b>Не найдены в справочнике «ФизическиеЛица»:</b></p><ul>")
        for n in not_found:
            h.append(f"<li>{n['surname']} {n['name']} — файл {n['source_file']}</li>")
        h.append("</ul>")

    h.append("</body></html>")
    html = "".join(h)

    msg = EmailMessage()
    msg["From"] = cfg["login"]
    msg["To"] = cfg["to"]
    msg["Subject"] = SUBJECT
    msg["Message-ID"] = make_msgid()
    msg.set_content(html, subtype="html", charset="utf-8")

    if excel and os.path.exists(excel):
        with open(excel, "rb") as f:
            data = f.read()
        msg.add_attachment(data, maintype="application",
                           subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           filename=os.path.basename(excel))

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=context, timeout=30) as server:
            server.login(cfg["login"], cfg["password"])
            server.send_message(msg)
    except Exception as ex:
        print(f"ОШИБКА отправки письма: {ex}")
        sys.exit(1)

    attach = os.path.basename(excel) if (excel and os.path.exists(excel)) else "нет"
    print(f"Письмо отправлено: {cfg['to']} | документов {len(documents)}, не найдено {len(not_found)}, вложение: {attach}")

if __name__ == "__main__":
    main()
