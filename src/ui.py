"""UI-режим (Tkinter): мероприятие + дата документа + папка с файлами + лог обработки.

Использует тот же конвейер, что и CLI (pipeline.run_pipeline), запуская его в фоновом
потоке и стримя вывод в текстовое поле. Лог по-прежнему пишется в log/run_YYYY-MM-DD.log.


"""
import os, sys, queue, threading, shutil, uuid, json
from datetime import datetime, date
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox

import pipeline
import config_reader
import log_config

from util.date_picker import DatePicker

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP = os.path.join(BASE, "temp")
SETTINGS_FILE = os.path.join(TEMP, "ui-settings.json")

class App:
    def __init__(self, root):
        self.root = root
        root.title("Авансовые отчёты — обработка документов")
        root.geometry("760x620")

        self.event_var = tk.StringVar()
        self.date_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="folder")
        self.path_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.limits_var = tk.StringVar()
        self._files = []
        self.dry_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Готово")

        self._build()
        self._load_settings()

    def _build(self):
        pad = {"padx": 8, "pady": 4}
        root = self.root

        form = ttk.Frame(root)
        form.pack(fill="x", **pad)
        form.columnconfigure(1, weight=1)

        # 1. Мероприятие
        ttk.Label(form, text="Мероприятие:").grid(row=0, column=0, sticky="w", **pad)
        events = config_reader.events()
        combo = ttk.Combobox(form, textvariable=self.event_var, values=events)
        combo.grid(row=0, column=1, columnspan=2, sticky="ew", **pad)
        ttk.Label(form, text="(пусто = автоопределение из events.json)", foreground="#666") \
            .grid(row=0, column=3, sticky="w", **pad)

        # 2. Дата документа
        ttk.Label(form, text="Дата документа:").grid(row=1, column=0, sticky="w", **pad)
        self.date_var.set(datetime.now().strftime("%Y-%m-%d"))
        dframe = ttk.Frame(form)
        dframe.grid(row=1, column=1, sticky="w", **pad)
        self.date_entry = ttk.Entry(dframe, textvariable=self.date_var, width=14, state="readonly")
        self.date_entry.pack(side="left")
        ttk.Button(dframe, text="Выбрать…", command=self._open_calendar).pack(side="left", padx=(6, 0))

        # 3. Источник: папка или отдельные файлы
        ttk.Label(form, text="Источник:").grid(row=2, column=0, sticky="w", **pad)
        mode_frame = ttk.Frame(form)
        mode_frame.grid(row=2, column=1, columnspan=2, sticky="w", **pad)
        ttk.Radiobutton(mode_frame, text="Папка", variable=self.mode_var, value="folder",
                        command=self._on_mode_change).pack(side="left")
        ttk.Radiobutton(mode_frame, text="Файлы", variable=self.mode_var, value="files",
                        command=self._on_mode_change).pack(side="left", padx=(12, 0))

        # 4. Папка / файлы
        ttk.Label(form, text="Папка/Файлы:").grid(row=3, column=0, sticky="w", **pad)
        ttk.Entry(form, textvariable=self.path_var).grid(row=3, column=1, sticky="ew", **pad)
        ttk.Button(form, text="Обзор…", command=self._pick_path).grid(row=3, column=2, **pad)

        # 5. Каталог результата (Excel)
        ttk.Label(form, text="Каталог результата:").grid(row=4, column=0, sticky="w", **pad)
        ttk.Entry(form, textvariable=self.out_var).grid(row=4, column=1, sticky="ew", **pad)
        ttk.Button(form, text="Обзор…", command=self._pick_out).grid(row=4, column=2, **pad)

        # 6. Уточняющий реестр (необязательный)
        ttk.Label(form, text="Уточняющий реестр:").grid(row=5, column=0, sticky="w", **pad)
        ttk.Entry(form, textvariable=self.limits_var).grid(row=5, column=1, sticky="ew", **pad)
        ttk.Button(form, text="Обзор…", command=self._pick_limits).grid(row=5, column=2, **pad)

        # dry-run
        ttk.Checkbutton(form, text="Dry-run (не писать в 1С, не отправлять письмо)",
                        variable=self.dry_var).grid(row=6, column=1, columnspan=2, sticky="w", **pad)

        # Кнопки
        btns = ttk.Frame(root)
        btns.pack(fill="x", **pad)
        self.run_btn = ttk.Button(btns, text="Запустить", command=self._start)
        self.run_btn.pack(side="left", **pad)
        ttk.Button(btns, text="Очистить лог", command=self._clear_log).pack(side="left", **pad)
        ttk.Label(btns, textvariable=self.status_var).pack(side="right", **pad)

        # Лог (только для чтения, но с возможностью выделения и копирования)
        self.log = scrolledtext.ScrolledText(root, wrap="word", height=20)
        self.log.pack(fill="both", expand=True, **pad)
        self._make_log_readonly()

    def _load_settings(self):
        """Загружает сохранённые настройки формы (temp/ui-settings.json)."""
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                s = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return
        if s.get("event"):
            self.event_var.set(s["event"])
        if s.get("date"):
            self.date_var.set(s["date"])
        mode = s.get("mode")
        if mode in ("folder", "files"):
            self.mode_var.set(mode)
        if s.get("out"):
            self.out_var.set(s["out"])
        if s.get("limits"):
            self.limits_var.set(s["limits"])
        if "dry_run" in s:
            self.dry_var.set(bool(s["dry_run"]))
        self._files = list(s.get("files") or [])
        if mode == "files":
            self.path_var.set(f"Выбрано файлов: {len(self._files)}" if self._files else "")
        elif s.get("path"):
            self.path_var.set(s["path"])

    def _save_settings(self):
        """Сохраняет настройки формы в temp/ui-settings.json."""
        os.makedirs(TEMP, exist_ok=True)
        s = {
            "event": self.event_var.get(),
            "date": self.date_var.get(),
            "mode": self.mode_var.get(),
            "path": self.path_var.get(),
            "out": self.out_var.get(),
            "limits": self.limits_var.get(),
            "dry_run": bool(self.dry_var.get()),
            "files": list(self._files),
        }
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(s, f, ensure_ascii=False, indent=2)
        except OSError as ex:
            print(f"[настройки] не удалось сохранить {SETTINGS_FILE}: {ex}")

    def _open_calendar(self):
        try:
            initial = datetime.strptime(self.date_var.get(), "%Y-%m-%d").date()
        except ValueError:
            initial = date.today()
        DatePicker(self.root, initial, self._on_date_picked)

    def _on_date_picked(self, d):
        self.date_var.set(d.strftime("%Y-%m-%d"))

    def _on_mode_change(self):
        self.path_var.set("")
        self._files = []

    def _dinit(self, value):
        """Возвращает dict с initialdir по текущему значению поля (или пустой dict).

        Если поле указывает на существующий каталог/файл — открываем диалог в его
        каталоге. Иначе initialdir не задаётся, и ОС использует «последний выбранный».
        """
        v = (value or "").strip()
        if not v:
            return {}
        if os.path.isdir(v):
            return {"initialdir": v}
        parent = os.path.dirname(v)
        return {"initialdir": parent} if parent and os.path.isdir(parent) else {}

    def _pick_path(self):
        if self.mode_var.get() == "files":
            files = filedialog.askopenfilenames(
                title="Выберите файлы (PDF или изображения)",
                filetypes=[("Документы", "*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"),
                           ("Все файлы", "*.*")],
                **self._dinit(self._files[0] if self._files else ""))
            if files:
                self._files = list(files)
                self.path_var.set(f"Выбрано файлов: {len(self._files)}")
                if not self.out_var.get().strip():
                    self.out_var.set(os.path.normpath(
                        os.path.join(os.path.dirname(self._files[0]), "результат")))
        else:
            d = filedialog.askdirectory(
                title="Выберите папку с документами",
                **self._dinit(self.path_var.get()))
            if d:
                self._files = []
                self.path_var.set(d)
                if not self.out_var.get().strip():
                    self.out_var.set(os.path.normpath(os.path.join(d, "результат")))

    def _stage_files(self, files):
        os.makedirs(TEMP, exist_ok=True)
        staging = os.path.join(TEMP, "selected_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:6])
        os.makedirs(staging, exist_ok=True)
        for f in files:
            shutil.copy2(f, os.path.join(staging, os.path.basename(f)))
        return staging

    def _cleanup_staging(self, staging):
        if staging:
            try:
                shutil.rmtree(staging, ignore_errors=True)
            except Exception:
                pass

    def _pick_out(self):
        d = filedialog.askdirectory(
            title="Выберите каталог для результата (Excel)",
            **self._dinit(self.out_var.get()))
        if d:
            self.out_var.set(d)

    def _pick_limits(self):
        f = filedialog.askopenfilename(
            title="Выберите уточняющий реестр (xlsx)",
            filetypes=[("Excel", "*.xlsx"), ("Все файлы", "*.*")],
            **self._dinit(self.limits_var.get()))
        if f:
            self.limits_var.set(f)

    def _clear_log(self):
        self.log.delete("1.0", "end")

    def _append(self, text):
        self.log.insert("end", text)
        self.log.see("end")

    def _make_log_readonly(self):
        """Лог только для чтения, но текст можно выделять и копировать (Ctrl+C / ПКМ)."""
        nav = {"Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
               "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
               "Caps_Lock", "Num_Lock", "Scroll_Lock"}

        def on_key(event):
            if event.state & 0x4:  # Ctrl — всё блокируем, кроме явных Ctrl+C/Ctrl+A
                return "break"
            if event.keysym in nav:
                return None
            return "break"  # блокируем печать, BackSpace, Delete, Enter, вставку

        self.log.bind("<Key>", on_key)
        self.log.bind("<Control-c>", self._copy_log)
        self.log.bind("<Control-a>", self._select_all_log)

        menu = tk.Menu(self.log, tearoff=0)
        menu.add_command(label="Копировать", command=self._copy_log)
        menu.add_command(label="Выделить всё", command=self._select_all_log)
        menu.add_separator()
        menu.add_command(label="Очистить лог", command=self._clear_log)

        def show_menu(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        self.log.bind("<Button-3>", show_menu)

    def _copy_log(self, event=None):
        try:
            sel = self.log.selection_get()
            self.log.clipboard_clear()
            self.log.clipboard_append(sel)
        except tk.TclError:
            pass
        return "break"

    def _select_all_log(self, event=None):
        self.log.tag_add("sel", "1.0", "end-1c")
        self.log.mark_set("insert", "1.0")
        self.log.see("insert")
        return "break"

    def _start(self):
        self._save_settings()
        out = self.out_var.get().strip()
        event = self.event_var.get().strip()
        staging = None
        files = []

        if self.mode_var.get() == "files":
            files = [f for f in self._files if os.path.isfile(f)]
            if not files:
                messagebox.showerror("Ошибка", "Выберите файлы для обработки (кнопка «Обзор…»).")
                return
            src = self._stage_files(files)
            staging = src
        else:
            src = self.path_var.get().strip()
            if not src:
                messagebox.showerror("Ошибка", "Укажите папку с файлами.")
                return
            if not os.path.isdir(src):
                messagebox.showerror("Ошибка", f"Папка не найдена:\n{src}")
                return
            if not out:
                out = os.path.normpath(os.path.join(src, "результат"))
                self.out_var.set(out)

        if not out:
            out = os.path.normpath(os.path.join(BASE, "out"))
            self.out_var.set(out)

        try:
            date_val = self._get_date()
        except ValueError as ex:
            self._cleanup_staging(staging)
            messagebox.showerror("Ошибка", str(ex))
            return

        self.run_btn.config(state="disabled")
        self.status_var.set("Выполняется…")
        self._append(f"\n===== Запуск: {datetime.now().strftime('%H:%M:%S')} =====\n")
        src_label = f"Файлы: {len(files)}" if self.mode_var.get() == "files" else src
        self._append(f"Источник: {src_label}\nМероприятие: {event or '(авто)'}\nДата: {date_val}\n")

        q = queue.Queue()

        def worker():
            sink, log_path = log_config.setup_stream(q)
            try:
                rc = pipeline.run_pipeline(
                    src, out,
                    dry_run=self.dry_var.get(),
                    event=event or None,
                    doc_date=date_val,
                    sink=sink,
                    persist_registry=False,
                    limits_xlsx=self.limits_var.get().strip() or None,
                )
                q.put(("done", rc, log_path))
            except Exception as ex:
                q.put(("error", f"{type(ex).__name__}: {ex}", log_path))
            finally:
                self._cleanup_staging(staging)

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(80, self._poll, q)

    def _get_date(self):
        raw = self.date_var.get().strip()
        datetime.strptime(raw, "%Y-%m-%d")  # выбросит ValueError при неверном формате
        return raw

    def _poll(self, q):
        try:
            while True:
                item = q.get_nowait()
                if isinstance(item, tuple) and item[0] in ("done", "error"):
                    kind, val, log_path = item
                    if kind == "error":
                        self._append(f"\n[ОШИБКА] {val}\n")
                        self.status_var.set("Ошибка")
                    else:
                        self._append(f"\nЗавершено (код {val}). Лог: {log_path}\n")
                        self.status_var.set("Готово" if val == 0 else "Завершено с ошибкой")
                    self.run_btn.config(state="normal")
                    return
                self._append(item)
        except queue.Empty:
            pass
        self.root.after(80, self._poll, q)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
