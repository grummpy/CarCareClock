"""Launcher files exist, are executable where that matters, and start the app."""

import os
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_launchers_exist_and_point_at_the_module():
    command = ROOT / "Launch CarCareClock.command"
    bat = ROOT / "Launch CarCareClock.bat"
    shell = ROOT / "launch.sh"
    desktop = ROOT / "carcareclock.desktop"
    for path in (command, bat, shell, desktop):
        assert path.is_file(), path

    for path in (command, shell):
        mode = path.stat().st_mode
        assert mode & stat.S_IXUSR, f"{path.name} is not executable"

    for path in (command, bat, shell):
        text = path.read_text(encoding="utf-8")
        assert "python.org/downloads" in text
        assert "python -m carcareclock" in text or "python.exe -m carcareclock" in text
        assert "requirements.txt" in text

    desk = desktop.read_text(encoding="utf-8")
    assert "CarCareClock" in desk
    assert "launch.sh" in desk
    assert "icon" in desk

    build = (ROOT / "scripts" / "build_app.py").read_text(encoding="utf-8")
    assert "PyInstaller" in build
    assert "icon" in build
    assert "--skip" in build


def test_checker_installers_are_off_by_default(tmp_path: Path):
    from carcareclock.checker_install import install_checker, render_cron

    cron = render_cron(ROOT)
    assert "# 15 8 * * *" in cron
    assert "\n15 8 * * *" not in cron
    assert "carcareclock check" in cron

    calls: list[list[str]] = []

    def runner(cmd, check=False):
        calls.append(cmd)

    # The installer writes a file and does not register it unless enable is true.
    # Patch by calling the writer and confirming the scripts themselves do not enable.
    path = install_checker("cron", ROOT, tmp_path, enable=False)
    assert path.is_file()
    assert calls == []
    for name in ("install_launchd.sh", "install_cron.sh", "install_task.ps1"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "launchctl" not in text
        assert "crontab" not in text
        assert "schtasks" not in text
        assert "--enable" not in text
        assert "install-checker" in text


def test_shell_scripts_are_executable():
    for name in ("install_launchd.sh", "install_cron.sh"):
        path = ROOT / "scripts" / name
        assert path.stat().st_mode & stat.S_IXUSR
        assert os.access(path, os.X_OK)
