from pathlib import Path
from Sankaku.Config import load_config
from Sankaku.Tui import SankakuApp
import sys


# A release build keeps data/ and .config/ next to the executable, not in its
# temporary unpack folder.
ROOT: Path = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent


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
