"""Redraw the bottom-right clock from the cover into the icon files.

Pillow is a build tool (requirements-build.txt), not a runtime dependency.
"""

from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets"
BG = (43, 49, 59, 255)
CREAM = (246, 241, 230, 255)
GOLD = (245, 180, 0, 255)


def draw(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw_ctx = ImageDraw.Draw(image)
    radius = int(size * 0.22)
    draw_ctx.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=BG)
    cx = cy = size / 2
    outer = size * 0.30
    # Gold wedge from 12 o'clock clockwise to about 4:30, under the ring.
    box = (cx - outer, cy - outer, cx + outer, cy + outer)
    draw_ctx.pieslice(box, start=270, end=405, fill=GOLD)
    stroke = max(2, int(size * 0.055))
    draw_ctx.ellipse(box, outline=CREAM, width=stroke)
    hub = size * 0.045
    draw_ctx.ellipse((cx - hub, cy - hub, cx + hub, cy + hub), fill=CREAM)
    return image


def write_icns(pngs: dict[bytes, bytes], path: Path) -> None:
    chunks = []
    for ostype, data in pngs.items():
        chunks.append(ostype + struct.pack(">I", 8 + len(data)) + data)
    body = b"".join(chunks)
    path.write_bytes(b"icns" + struct.pack(">I", 8 + len(body)) + body)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    master = draw(1024)
    master.save(OUT / "icon-1024.png")
    master.save(OUT / "icon.png")
    icon_512 = master.resize((512, 512), Image.Resampling.LANCZOS)
    icon_512.save(OUT / "icon-512.png")
    pngs: dict[bytes, bytes] = {}
    for size, ostype in (
        (32, b"ic11"),
        (64, b"ic12"),
        (128, b"ic07"),
        (256, b"ic08"),
        (512, b"ic09"),
        (1024, b"ic10"),
    ):
        pngs[ostype] = _png(master, size)
    write_icns(pngs, OUT / "icon.icns")
    ico = master.resize((256, 256), Image.Resampling.LANCZOS)
    ico.save(
        OUT / "icon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


def _png(master: Image.Image, size: int) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    master.resize((size, size), Image.Resampling.LANCZOS).save(buffer, format="PNG")
    return buffer.getvalue()


if __name__ == "__main__":
    main()
