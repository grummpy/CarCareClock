"""Optional PyInstaller build.

Produces a macOS .app or a Windows .exe when run on that system, using the
icon in assets/. On Linux it builds a one-file binary, or skips cleanly:

    python scripts/build_app.py --skip

CI only needs a Linux build, and it may skip packaging. Running the app does
not require this script. Install the extra tools with:

    pip install -r requirements-build.txt
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package CarCareClock with PyInstaller.")
    parser.add_argument(
        "--skip",
        action="store_true",
        help="Exit without building. CI may pass this.",
    )
    args = parser.parse_args(argv)
    if args.skip:
        print("Skipping the PyInstaller build.")
        return 0
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed. pip install -r requirements-build.txt")
        print("Skipping the packaged build.")
        return 0

    system = platform.system()
    icon = ROOT / "assets" / ("icon.icns" if system == "Darwin" else "icon.ico")
    sep = ";" if system == "Windows" else ":"
    bundled = [
        (ROOT / "carcareclock" / "templates", "carcareclock/templates"),
        (ROOT / "carcareclock" / "static", "carcareclock/static"),
        (ROOT / "rules", "rules"),
        (ROOT / "assets", "assets"),
    ]
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "CarCareClock",
        "--paths",
        str(ROOT),
    ]
    if system == "Darwin":
        command.extend(["--windowed", "--icon", str(icon), "--osx-bundle-identifier", "local.carcareclock"])
    elif system == "Windows":
        command.extend(["--onefile", "--icon", str(icon)])
    else:
        command.append("--onefile")
        print("On Linux this builds a one-file binary. A .app and a .exe are built on macOS and Windows.")
    for source, dest in bundled:
        command.extend(["--add-data", f"{source}{sep}{dest}"])
    command.append(str(ROOT / "scripts" / "entry.py"))
    print(" ".join(command))
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
