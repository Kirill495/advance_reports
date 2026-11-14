import argparse, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import log_config
import pipeline


def main():
    log_file = log_config.setup()
    os.environ["RUN_LOG"] = log_file
    print(f"Лог: {log_file}")

    ap = argparse.ArgumentParser(description="Оркестратор: документы (PDF/изображения) → 1С → Excel")
    ap.add_argument("--from", dest="src_dir", required=True, help="Папка с документами (PDF, PNG, JPG, ...)")
    ap.add_argument("--out", dest="out_dir", required=True, help="Каталог для результатов (Excel)")
    ap.add_argument("--dry-run", action="store_true", help="Не писать в 1С, только показать план")
    ap.add_argument("--event", dest="event", default=None, help="Принудительное мероприятие (вместо автоопределения)")
    ap.add_argument("--date", dest="doc_date", default=None, help="Дата документа в формате YYYY-MM-DD (по умолчанию сегодня)")
    ap.add_argument("--limits", dest="limits_xlsx", default=None, help="Уточняющий реестр (xlsx) с суммами возмещения")
    args = ap.parse_args()

    src_dir = os.path.abspath(args.src_dir)
    out_dir = os.path.abspath(args.out_dir)

    sys.exit(pipeline.run_pipeline(
        src_dir, out_dir,
        dry_run=args.dry_run,
        event=args.event,
        doc_date=args.doc_date,
        limits_xlsx=args.limits_xlsx,
    ))


if __name__ == "__main__":
    main()
