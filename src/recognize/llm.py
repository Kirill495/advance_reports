"""Вызов LLM для распознавания и уточнения суммы."""
import os, json, re
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT_DIR = os.path.join(HERE, "resources")
TICKET_PROMPT_FILE = os.path.join(PROMPT_DIR, "ticket_recognize_prompt.txt")
AMOUNT_PROMPT_FILE = os.path.join(PROMPT_DIR, "amount_recognize_prompt.txt")
FIO_PROMPT_FILE = os.path.join(PROMPT_DIR, "fio_transliterate_prompt.txt")

def load_prompt(filename):
    with open(filename, encoding="utf-8") as f:
        return f.read().strip()

SYSTEM_PROMPT = load_prompt(TICKET_PROMPT_FILE)
AMOUNT_PROMPT = load_prompt(AMOUNT_PROMPT_FILE)
FIO_PROMPT = load_prompt(FIO_PROMPT_FILE)

def _post(messages, cfg):
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    payload = {"model": cfg["model"], "messages": messages, "temperature": 0}
    try:
        payload["response_format"] = {"type": "json_object"}
    except Exception:
        pass
    # verify=False: в окружении корпоративный прокси с самоподписанным сертификатом
    r = requests.post(url, headers=headers, json=payload, timeout=180, verify=False)
    if r.status_code != 200:
        raise RuntimeError(f"LLM {r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"]


def call_llm(text, cfg):
    """Полное распознавание. Возвращает dict {"tickets": [...], "checks": [...], "refunds": [...]}."""
    content = _post([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ], cfg)
    return json.loads(content)


def verify_amount(text, cfg):
    """Уточнение суммы через LLM. Возвращает float или None."""
    try:
        content = _post([
            {"role": "system", "content": AMOUNT_PROMPT},
            {"role": "user", "content": text},
        ], cfg)
    except Exception:
        return None
    s = content.replace(" ", "").replace("\xa0", "").replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def transliterate_fio(latin_name, cfg):
    """Транслитерация латинского ФИО → {'surname','name','patronymic'} или None."""
    try:
        content = _post([
            {"role": "system", "content": FIO_PROMPT},
            {"role": "user", "content": latin_name},
        ], cfg)
        data = json.loads(content)
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("surname"):
        return None
    return {
        "surname": str(data.get("surname", "")).strip(),
        "name": str(data.get("name", "")).strip(),
        "patronymic": str(data.get("patronymic", "")).strip(),
    }
