"""Write launchd, Task Scheduler, and cron checker files. Off unless --enable.

The launchers never call this. Running it without --enable only writes a file
under the data directory and prints how to turn the checker on.
"""

from __future__ import annotations

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


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
    python = _python(root)
    return (
        "# CarCareClock background check is OFF by default.\n"
        "# The schedule line is commented out. Uncomment it, then run:\n"
        f"#   crontab {root / 'data' / 'checkers' / 'carcareclock.cron'}\n"
        f"# 15 8 * * * cd {root} && {python} -m carcareclock check\n"
    )


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


def install_checker(kind: str, root: Path, data: Path, enable: bool = False) -> Path:
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
        if enable:
            subprocess.run(["crontab", str(path)], check=False)
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
