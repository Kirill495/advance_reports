"""Единый конвейер обработки: read_pdf → recognize → write_1c → make_excel → send_mail.

Используется и CLI (run.py), и UI (ui.py). Разница только в способе вывода:
- sink == None  → как раньше: подскрипты наследуют stdout, каждый сам пишет в лог;
- sink задан    → родитель перехватывает stdout подскриптов построчно и отдаёт в sink
                  (очередь UI + файл лога), а подскриптам запрещено писать в лог самим.
"""
import os, sys, subprocess
import component_manager

SRC = os.path.dirname(os.path.abspath(__file__))


def run_pipeline(src_dir, out_dir, dry_run=False, event=None, doc_date=None, sink=None,
                 persist_registry=True, limits_xlsx=None):
    env = dict(os.environ)
    # stdio подскриптов — в UTF-8 (иначе трейсбеки с кириллицей ломаются при перехвате).
    env["PYTHONIOENCODING"] = "utf-8"
    if event:
        env["RUN_EVENT"] = event
    if doc_date:
        env["RUN_DATE"] = doc_date
    if sink is not None:
        # Родитель владеет логированием — подскрипты не пишут в лог сами.
        env["RUN_LOG"] = ""
        # Живой (построчный) вывод из подскриптов.
        env["PYTHONUNBUFFERED"] = "1"

    def emit(text):
        if sink is not None:
            sink.write(text)
        else:
            sys.stdout.write(text)

    def run_step(name, *args):
        emit(f"\n===== {name} {' '.join(args)} =====\n")
        cmd = [sys.executable, os.path.join(SRC, name), *args]
        if sink is None:
            return subprocess.call(cmd, env=env)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=env, text=True, encoding="utf-8", errors="replace", bufsize=1)
        for line in proc.stdout:
            emit(line)
        return proc.wait()

    if run_step("read_limits.py", limits_xlsx or "") != 0:
        return 1
    if run_step("read_pdf.py", src_dir) != 0:
        return 1
    if run_step(os.path.join("recognize", "recognize.py")) != 0:
        emit("\nРаспознавание не завершено — выполни шаг ИИ/LLM и перезапусти run.py.\n")
        return 1

    extra = ["--dry-run"] if dry_run else []
    if not persist_registry:
        extra.append("--no-registry")
    if run_step("write_1c.py", src_dir, *extra) != 0:
        return 1

    if component_manager.is_enabled("make_excel"):
        if run_step("make_excel.py", out_dir) != 0:
            return 1
    else:
        emit("\nКомпонент make_excel отключён — пропускаю.\n")

    if dry_run:
        emit("\n(dry-run) Письмо не отправляется.\n")
        return 0

    if component_manager.is_enabled("send_mail"):
        return run_step("send_mail.py")

    emit("\nКомпонент send_mail отключён — пропускаю.\n")
    return 0
