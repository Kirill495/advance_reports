"""
Календарь — собственный (без tkcalendar): надёжно переключает месяцы/годы на любой ОС.
"""
import calendar
from datetime import date

import tkinter as tk

MONTH_NAMES = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
               "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

class DatePicker(tk.Toplevel):
    """Модальное окно выбора даты (собственный календарь)."""

    def __init__(self, master, initial, on_ok):
        super().__init__(master)
        self.transient(master)
        self.title("Выберите дату")
        self.resizable(False, False)
        self._on_ok = on_ok
        self._sel = initial
        self._shown = date(initial.year, initial.month, 1)

        self._build()
        self._render()
        self._center(master)

        self.wait_visibility()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window(self)

    def _build(self):
        header = tk.Frame(self)
        header.pack(fill="x", padx=10, pady=(10, 4))
        tk.Button(header, text="«", width=2, relief="flat",
                  command=lambda: self._shift(year=-1)).pack(side="left")
        tk.Button(header, text="‹", width=2, relief="flat",
                  command=lambda: self._shift(month=-1)).pack(side="left")
        self._title = tk.Label(header, text="", width=20, font=("Segoe UI", 10, "bold"))
        self._title.pack(side="left", padx=4)
        tk.Button(header, text="›", width=2, relief="flat",
                  command=lambda: self._shift(month=1)).pack(side="left")
        tk.Button(header, text="»", width=2, relief="flat",
                  command=lambda: self._shift(year=1)).pack(side="left")

        grid = tk.Frame(self)
        grid.pack(padx=10, pady=(0, 10))
        for c, name in enumerate(DAY_NAMES):
            tk.Label(grid, text=name, width=4, anchor="center",
                     font=("Segoe UI", 8)).grid(row=0, column=c, padx=1, pady=1)
        self._cells = []
        for r in range(6):
            row = []
            for c in range(7):
                b = tk.Button(grid, text="", width=4, relief="flat")
                b.grid(row=r + 1, column=c, padx=1, pady=1)
                row.append(b)
            self._cells.append(row)
        self._default_bg = self._cells[0][0].cget("bg")

    def _shift(self, year=0, month=0):
        y = self._shown.year + year
        m = self._shown.month + month
        y += (m - 1) // 12
        m = (m - 1) % 12 + 1
        self._shown = date(y, m, 1)
        self._render()

    def _render(self):
        self._title.config(text=f"{MONTH_NAMES[self._shown.month - 1]} {self._shown.year}")
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(self._shown.year, self._shown.month)
        for r in range(6):
            for c in range(7):
                b = self._cells[r][c]
                if r < len(weeks) and weeks[r][c]:
                    d = weeks[r][c]
                    this = date(self._shown.year, self._shown.month, d)
                    b.config(text=str(d), state="normal",
                             command=lambda this=this: self._pick(this))
                    if this == self._sel:
                        b.config(bg="#cde6ff", relief="sunken")
                    else:
                        b.config(bg=self._default_bg, relief="flat")
                else:
                    b.config(text="", state="disabled", bg=self._default_bg, relief="flat")
    def _pick(self, d):
        self._on_ok(d)
        self.destroy()

    def _center(self, master):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = master.winfo_rootx() + (master.winfo_width() - w) // 2
        y = master.winfo_rooty() + (master.winfo_height() - h) // 2
        self.geometry("+%d+%d" % (max(0, x), max(0, y)))
