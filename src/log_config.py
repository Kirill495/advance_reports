import os, sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE, "log")

class _TimestampedFile:
    """Обёртка над файлом: добавляет метку времени к началу каждой строки."""
    def __init__(self, file):
        self._file = file
        self._at_line_start = True

    def _ts(self):
        # до миллисекунд
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " "

    def write(self, data):
        if not data:
            return
        out = []
        i, n = 0, len(data)
        while i < n:
            if self._at_line_start:
                out.append(self._ts())
                self._at_line_start = False
            nl = data.find("\n", i)
            if nl == -1:
                out.append(data[i:])
                i = n
            else:
                out.append(data[i:nl + 1])
                i = nl + 1
                self._at_line_start = True
        self._file.write("".join(out))
        self._file.flush()

    def flush(self):
        self._file.flush()

class _Tee:
    """Пишет в консоль (без меток) и в файл лога (с метками времени)."""
    def __init__(self, console, timestamped_file):
        self._console = console
        self._file = timestamped_file

    def write(self, data):
        try:
            self._console.write(data)
            self._console.flush()
        except Exception:
            pass
        try:
            self._file.write(data)
        except Exception:
            pass

    def flush(self):
        try:
            self._console.flush()
        except Exception:
            pass
        try:
            self._file.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._console, name)

def setup(log_file=None):
    """Перенаправляет stdout/stderr в консоль И в файл лога (с метками времени). Возвращает путь к логу."""
    os.makedirs(LOG_DIR, exist_ok=True)
    if log_file is None:
        log_file = os.path.join(LOG_DIR, "run_" + datetime.now().strftime("%Y-%m-%d") + ".log")
    try:
        fh = open(log_file, "a", encoding="utf-8")
    except Exception as ex:
        print(f"[log] не удалось открыть {log_file}: {ex}")
        return log_file
    tfile = _TimestampedFile(fh)
    sys.stdout = _Tee(sys.stdout, tfile)
    sys.stderr = _Tee(sys.stderr, tfile)
    return log_file
