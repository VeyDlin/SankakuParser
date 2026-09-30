from pathlib import Path
from Sankaku.Config import load_config
from Sankaku.Tui import SankakuApp
import sys


ROOT: Path = Path(__file__).resolve().parent


def main() -> int:
    try:
        config = load_config(ROOT)
    except (OSError, ValueError) as err:
        print(f'Cannot read config: {err}', file=sys.stderr)
        return 1

    SankakuApp(config).run()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
