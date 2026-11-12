import os, json, re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(BASE, "config")

def _load_properties():
    """Загружает единый файл настроек properties.json."""
    p = os.path.join(CONFIG, "properties.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}

def _section(name):
    return _load_properties().get(name, {})

def one_s_config():
    """Конфиг 1С. Приоритет: переменные окружения → properties.json (раздел one_s)."""
    cfg = _section("one_s")
    base_url = cfg.get("base_url", "")
    base_id = os.environ.get("ONE_S_BASE_ID")
    if base_id:
        # подставляем номер базы в URL из конфига, не трогая путь и суффикс
        base_url = re.sub(r"/(\d+)/odata/", f"/{base_id}/odata/", base_url)
    return {
        "base_url": base_url,
        "login": os.environ.get("ONE_S_LOGIN", cfg.get("login", "")),
        "password": os.environ.get("ONE_S_PASSWD", cfg.get("password", "")),
    }

def one_s_web_base():
    """Префикс веб-клиента 1С (до /odata/) — для навигационных ссылок."""
    base_url = one_s_config()["base_url"]
    return base_url.split("/odata/")[0].rstrip("/") + "/"

def llm_config():
    """Конфиг LLM. Приоритет: переменные окружения → properties.json (раздел llm)."""
    cfg = _section("llm")
    return {
        "base_url": os.environ.get("LLM_URL", cfg.get("base_url", "https://api.deepseek.com")),
        "api_key": os.environ.get("LLM_API_KEY", cfg.get("api_key", "")),
        "model": cfg.get("model", "deepseek-flash"),
    }

def mail_config():
    """Конфиг почты (SMTP). Приоритет: переменные окружения → properties.json (раздел mail)."""
    cfg = _section("mail")
    return {
        "host": os.environ.get("MAIL_HOST", cfg.get("host", "smtp.yandex.ru")),
        "port": int(os.environ.get("MAIL_PORT", cfg.get("port", 465))),
        "login": os.environ.get("MAIL_LOGIN", cfg.get("login", "")),
        "password": os.environ.get("MAIL_PASSWD", cfg.get("password", "")),
        "to": os.environ.get("MAIL_TO", cfg.get("to", "")),
    }

def advance_reports_config():
    """GUID-ы для авансовых отчётов (несекретные, раздел advance_reports)."""
    return _section("advance_reports")

def components():
    """Раздел components: {имя_скрипта: true/false}."""
    return _section("components")

UNRECOGNIZED_EVENT = "Нераспознано"

def events():
    """Список известных мероприятий из config/events.json."""
    p = os.path.join(CONFIG, "events.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return data.get("events", [])
    return []

def event_of(name):
    """Мероприятие по имени файла (по списку events.json). Не найдено → "Нераспознано"."""
    name_tokens = re.findall(r"\w+", name.lower())
    for ev in events():
        ev_tokens = re.findall(r"\w+", ev.lower())
        if not ev_tokens:
            continue
        n = len(ev_tokens)
        for i in range(len(name_tokens) - n + 1):
            if name_tokens[i:i + n] == ev_tokens:
                return ev
    return UNRECOGNIZED_EVENT
