"""PyInstaller entry. The launchers use `python -m carcareclock` instead."""

from carcareclock.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
