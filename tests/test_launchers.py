"""Launcher files exist, are executable where that matters, and start the app."""

import os
import stat
import subprocess
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


def test_cron_enable_and_disable_preserve_other_entries(monkeypatch, tmp_path: Path):
    from carcareclock import checker_install

    current = "MAILTO=household@example.test\n0 6 * * * /usr/local/bin/backup\n"
    writes: list[str] = []

    def fake_run(cmd, **kwargs):
        if cmd == ["crontab", "-l"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=current, stderr="")
        assert cmd == ["crontab", "-"]
        writes.append(kwargs["input"])
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(checker_install.subprocess, "run", fake_run)
    checker_install.install_checker("cron", ROOT, tmp_path, enable=True)
    assert len(writes) == 1
    assert "MAILTO=household@example.test" in writes[0]
    assert "/usr/local/bin/backup" in writes[0]
    assert "# BEGIN CarCareClock checker (managed)" in writes[0]
    assert "\n15 8 * * * cd " in writes[0]
    assert "# 15 8 * * *" not in writes[0]

    current = writes[-1]
    checker_install.install_checker("cron", ROOT, tmp_path, enable=True)
    assert len(writes) == 1, "enabling an installed checker must be idempotent"

    checker_install.install_checker("cron", ROOT, tmp_path, disable=True)
    assert len(writes) == 2
    assert "MAILTO=household@example.test" in writes[-1]
    assert "/usr/local/bin/backup" in writes[-1]
    assert "CarCareClock checker" not in writes[-1]

    current = writes[-1]
    checker_install.install_checker("cron", ROOT, tmp_path, disable=True)
    assert len(writes) == 2, "disabling an absent checker must be idempotent"


def test_cron_does_not_write_when_crontab_cannot_be_read(monkeypatch, tmp_path: Path):
    from carcareclock import checker_install

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="permission denied")

    monkeypatch.setattr(checker_install.subprocess, "run", fake_run)
    try:
        checker_install.install_checker("cron", ROOT, tmp_path, enable=True)
    except OSError as exc:
        assert "could not read" in str(exc)
    else:
        raise AssertionError("expected crontab read failure")
    assert calls == [["crontab", "-l"]]


def test_cron_quotes_paths_with_spaces(monkeypatch):
    from carcareclock import checker_install

    root = Path("/Users/Example User/Car Care Clock")
    monkeypatch.setattr(
        checker_install, "_python", lambda _root: "/Users/Example User/Python/bin/python"
    )
    line = checker_install._active_cron_line(root)
    assert "cd '/Users/Example User/Car Care Clock'" in line
    assert "'/Users/Example User/Python/bin/python'" in line
    assert "/path/to/carcareclock.cron" in checker_install.render_cron(root)


def test_shell_scripts_are_executable():
    for name in ("install_launchd.sh", "install_cron.sh"):
        path = ROOT / "scripts" / name
        assert path.stat().st_mode & stat.S_IXUSR
        assert os.access(path, os.X_OK)
