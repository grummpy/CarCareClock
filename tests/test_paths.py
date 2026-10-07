"""Persistent mutable paths for packaged applications."""

from pathlib import Path


def test_frozen_app_keeps_resources_and_data_separate(monkeypatch, tmp_path: Path):
    from carcareclock import paths

    bundle = tmp_path / "pyinstaller-extract"
    home = tmp_path / "home"
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("CARCARE_DATA_DIR", raising=False)
    monkeypatch.delenv("CARCARE_DB", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    assert paths.repo_root() == bundle
    first = paths.database_path()
    second = paths.database_path()
    assert first == second == home / ".local/share/CarCareClock/carcareclock.sqlite"
    assert bundle not in first.parents
    assert paths.rules_path() == bundle / "rules/maryland.yaml"


def test_frozen_data_override_is_explicit_and_persistent(monkeypatch, tmp_path: Path):
    from carcareclock import paths

    override = tmp_path / "chosen-data"
    db_override = tmp_path / "elsewhere" / "chosen.sqlite"
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setenv("CARCARE_DATA_DIR", str(override))
    monkeypatch.setenv("CARCARE_DB", str(db_override))

    assert paths.data_dir() == override
    assert paths.database_path() == db_override
    assert db_override.parent.is_dir()
