"""Locations for the repo, the rules files, and the gitignored data folder."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def repo_root() -> Path:
    """Folder that contains rules/, assets/, and the launchers."""
    override = os.environ.get("CARCARE_ROOT")
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    override = os.environ.get("CARCARE_DATA_DIR")
    path = Path(override).resolve() if override else repo_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    override = os.environ.get("CARCARE_DB")
    if override:
        path = Path(override).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return data_dir() / "carcareclock.sqlite"


def rules_path() -> Path:
    override = os.environ.get("CARCARE_RULES")
    return Path(override).resolve() if override else repo_root() / "rules" / "maryland.yaml"


def defaults_path() -> Path:
    override = os.environ.get("CARCARE_DEFAULTS")
    if override:
        return Path(override).resolve()
    return repo_root() / "rules" / "maintenance_defaults.yaml"


def assets_dir() -> Path:
    return repo_root() / "assets"
