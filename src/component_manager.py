import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import config_reader

def is_enabled(name):
    """True, если компонент включён. Отсутствующий или false → выключен."""
    comps = config_reader.components()
    return bool(comps.get(name, False))

def main():
    if len(sys.argv) < 2:
        print("Использование: component_manager.py <имя_компонента>")
        sys.exit(1)
    name = sys.argv[1]
    if is_enabled(name):
        print(f"{name}: enabled")
        sys.exit(0)
    print(f"{name}: disabled")
    sys.exit(1)

if __name__ == "__main__":
    main()
