"""Write launchd, Task Scheduler, and cron checker files. Off unless --enable.

The launchers never call this. Running it without --enable only writes a file
under the data directory and prints how to turn the checker on.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CRON_BEGIN = "# BEGIN CarCareClock checker (managed)"
CRON_END = "# END CarCareClock checker (managed)"


def checker_dir(data: Path) -> Path:
    path = data / "checkers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _python(root: Path) -> str:
    venv = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if venv.exists():
        return str(venv)
    return sys.executable


def render_launchd_plist(root: Path) -> str:
    python = _python(root)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.carcareclock.checker</string>
    <key>Comment</key>
    <string>CarCareClock background check. Not loaded until you enable it.</string>
    <key>WorkingDirectory</key>
    <string>{root}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>carcareclock</string>
        <string>check</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>15</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{root / "data" / "checkers" / "check.log"}</string>
    <key>StandardErrorPath</key>
    <string>{root / "data" / "checkers" / "check.log"}</string>
</dict>
</plist>
"""


def render_cron(root: Path) -> str:
    return (
        "# CarCareClock background check is OFF by default.\n"
        "# The schedule line is commented out. Uncomment it, then run:\n"
        "#   crontab /path/to/carcareclock.cron\n"
        f"# {_active_cron_line(root)}\n"
    )


def _active_cron_line(root: Path) -> str:
    return f"15 8 * * * cd {shlex.quote(str(root))} && {shlex.quote(_python(root))} -m carcareclock check"


def _without_managed_cron(text: str) -> str:
    """Remove only this application's complete managed blocks.

    A dangling marker is intentionally retained: deleting through EOF could
    silently erase another application's cron entries.
    """
    lines = text.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        if lines[index] != CRON_BEGIN:
            kept.append(lines[index])
            index += 1
            continue
        try:
            end = lines.index(CRON_END, index + 1)
        except ValueError:
            kept.append(lines[index])
            index += 1
        else:
            index = end + 1
    return "\n".join(kept).rstrip("\n")


def _read_crontab() -> str:
    result = subprocess.run(["crontab", "-l"], check=False, capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout
    # POSIX cron uses exit status 1 when the user has no crontab. Other
    # failures must be shown to the caller instead of overwriting blindly.
    if result.returncode == 1 and "no crontab" in result.stderr.lower():
        return ""
    raise OSError(f"could not read the current crontab: {result.stderr.strip() or result.returncode}")


def _write_crontab(text: str) -> None:
    result = subprocess.run(
        ["crontab", "-"], input=text, check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise OSError(f"could not update the crontab: {result.stderr.strip() or result.returncode}")


def update_cron_checker(root: Path, *, enable: bool) -> None:
    """Add or remove only CarCareClock's managed cron block.

    The operation is idempotent and deliberately reads the existing crontab
    before writing it back, so unrelated entries survive unchanged.
    """
    existing = _read_crontab()
    remaining = _without_managed_cron(existing)
    if enable:
        managed = f"{CRON_BEGIN}\n{_active_cron_line(root)}\n{CRON_END}"
        updated = f"{remaining}\n{managed}" if remaining else managed
    else:
        updated = remaining
    if updated != existing.rstrip("\n"):
        _write_crontab(f"{updated}\n" if updated else "")


def render_task_xml(root: Path) -> str:
    python = _python(root)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>CarCareClock background check. Not registered until you enable it.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T08:15:00</StartBoundary>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Actions>
    <Exec>
      <Command>{python}</Command>
      <Arguments>-m carcareclock check</Arguments>
      <WorkingDirectory>{root}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def install_checker(
    kind: str, root: Path, data: Path, enable: bool = False, disable: bool = False
) -> Path:
    """Write the installer file. `enable` is false unless the user passes --enable."""
    folder = checker_dir(data)
    if kind == "launchd":
        path = folder / "com.carcareclock.checker.plist"
        path.write_text(render_launchd_plist(root), encoding="utf-8")
        if enable:
            if sys.platform != "darwin":
                raise OSError("launchd --enable only works on macOS. The plist was written.")
            subprocess.run(
                ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)],
                check=False,
            )
        return path
    if kind == "cron":
        path = folder / "carcareclock.cron"
        path.write_text(render_cron(root), encoding="utf-8")
        if enable or disable:
            update_cron_checker(root, enable=enable)
        return path
    if kind == "task":
        path = folder / "CarCareClockChecker.xml"
        path.write_text(render_task_xml(root), encoding="utf-8")
        ET.fromstring(path.read_text(encoding="utf-8"))
        if enable:
            if sys.platform != "win32":
                raise OSError("Task Scheduler --enable only works on Windows. The XML was written.")
            subprocess.run(
                ["schtasks", "/Create", "/TN", "CarCareClock", "/XML", str(path), "/F"],
                check=False,
            )
        return path
    raise ValueError(f"unknown checker kind {kind}")
