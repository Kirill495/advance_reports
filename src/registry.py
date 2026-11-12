import os, json, hashlib, sys
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_PATH = os.path.join(BASE, "registry.json")

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def kind_of(name):
    n = name.lower()
    if "возрат" in n or "возврат" in n:
        return "refund"
    if "кассовый чек" in n:
        return "check"
    return "ticket"

def event_of(name):
    parts = name.split(" - ")
    return parts[1].strip() if len(parts) >= 2 else ""

def load():
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"reports": {}, "files": {}}

def save(reg):
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)

def is_processed(reg, path):
    """True, если файл уже обработан и его содержимое не менялось."""
    name = os.path.basename(path)
    ent = reg["files"].get(name)
    return bool(ent and ent.get("sha256") == sha256_file(path))

def mark_processed(reg, name, sha, event, kind, status="done", **meta):
    ent = {"sha256": sha, "event": event, "kind": kind, "status": status,
           "processed_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    ent.update(meta)
    reg["files"][name] = ent
