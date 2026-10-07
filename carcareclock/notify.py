"""Local desktop notifications. No network. The sender is replaceable in tests."""

from __future__ import annotations

import platform
import shutil
import subprocess
from collections.abc import Callable


def _escape_osascript(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _powershell_literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def desktop_notify(title: str, body: str) -> str:
    """Show a notification with the OS tool, or print it if that tool is missing.

    Returns a short status string: notified, printed, or the tool name that failed.
    """
    system = platform.system()
    title = title.replace("\n", " ")[:120]
    body = body.replace("\n", " ")[:500]
    try:
        if system == "Darwin":
            script = f'display notification "{_escape_osascript(body)}" with title "{_escape_osascript(title)}"'
            subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
            return "notified"
        if system == "Linux" and shutil.which("notify-send"):
            subprocess.run(["notify-send", title, body], check=False, capture_output=True)
            return "notified"
        if system == "Windows":
            command = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "Add-Type -AssemblyName System.Drawing; "
                "$n = New-Object System.Windows.Forms.NotifyIcon; "
                "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                "$n.Visible = $true; "
                f"$n.ShowBalloonTip(8000, {_powershell_literal(title)}, {_powershell_literal(body)}, "
                "[System.Windows.Forms.ToolTipIcon]::Info); "
                "Start-Sleep -Seconds 9; $n.Dispose()"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                check=False,
                capture_output=True,
            )
            return "notified"
    except OSError:
        pass
    print(f"NOTICE: {title}: {body}")
    return "printed"


def deliver(lines: list[str], sender: Callable[[str, str], str] = desktop_notify) -> str | None:
    if not lines:
        return None
    body = " ".join(lines)
    if len(body) > 450:
        body = body[:447] + "..."
    return sender("CarCareClock", body)
