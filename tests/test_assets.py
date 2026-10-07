"""Icon files exist at the sizes the launchers and the web UI use."""

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def test_icon_files():
    svg = (ASSETS / "icon.svg").read_text(encoding="utf-8")
    assert "<svg" in svg
    assert "#F5B400" in svg
    assert _png_size(ASSETS / "icon.png") == (1024, 1024)
    assert _png_size(ASSETS / "icon-512.png") == (512, 512)
    assert _png_size(ASSETS / "icon-1024.png") == (1024, 1024)
    ico = (ASSETS / "icon.ico").read_bytes()
    assert ico[:4] == b"\x00\x00\x01\x00"
    icns = (ASSETS / "icon.icns").read_bytes()
    assert icns.startswith(b"icns")
    assert b"ic09" in icns
    assert b"ic10" in icns
    cover = ROOT / "docs" / "cover.jpg"
    assert cover.is_file()
    assert cover.stat().st_size > 10000
    assert cover.read_bytes()[:3] == b"\xff\xd8\xff"
