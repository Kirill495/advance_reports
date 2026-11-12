import argparse, os, sys, subprocess
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import log_config
import component_manager

SRC = os.path.dirname(os.path.abspath(__file__))

def run_script(name, *args):
    cmd = [sys.executable, os.path.join(SRC, name), *args]
    print(f"\n===== {name} {' '.join(args)} =====")
    return subprocess.call(cmd)

def main():
    log_file = log_config.setup()
    os.environ["RUN_LOG"] = log_file
    print(f"Лог: {log_file}")

    ap = argparse.ArgumentParser(description="Оркестратор: PDF-билеты → 1С → Excel")
    ap.add_argument("--from", dest="src_dir", required=True, help="Папка с PDF-билетами")
    ap.add_argument("--out", dest="out_dir", required=True, help="Каталог для результатов (Excel)")
    ap.add_argument("--dry-run", action="store_true", help="Не писать в 1С, только показать план")
    args = ap.parse_args()
    src_dir = os.path.abspath(args.src_dir)
    out_dir = os.path.abspath(args.out_dir)

    if run_script("read_pdf.py", src_dir) != 0:
        sys.exit(1)
    if run_script("recognize.py") != 0:
        print("\nРаспознавание не завершено — выполни шаг ИИ/LLM и перезапусти run.py.")
        sys.exit(1)
    extra = ["--dry-run"] if args.dry_run else []
    if run_script("write_1c.py", src_dir, *extra) != 0:
        sys.exit(1)
    if component_manager.is_enabled("make_excel"):
        if run_script("make_excel.py", out_dir) != 0:
            sys.exit(1)
    else:
        print("\nКомпонент make_excel отключён — пропускаю.")

    if args.dry_run:
        print("\n(dry-run) Письмо не отправляется.")
        sys.exit(0)

    if component_manager.is_enabled("send_mail"):
        sys.exit(run_script("send_mail.py"))
    print("\nКомпонент send_mail отключён — пропускаю.")

if __name__ == "__main__":
    main()
