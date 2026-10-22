"""Render a BF4 player overview as a 960x600 PNG.

Presentation only: no database or HTTP access. Callers supply verified statistics
and optionally the bytes of the site's existing fancy equipment artwork.
"""
from __future__ import annotations

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH, HEIGHT = 960, 600
BG = "#20242b"
PANEL = "#30353e"
TILE = "#252a32"
WHITE = "#f4f5f7"
MUTED = "#b8bec8"
ORANGE = "#ed8b31"


def _font(size: int, bold: bool = False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(name, size)


def _text(draw, xy, value, size=20, fill=WHITE, bold=False, max_chars=None):
    value = str(value if value is not None else "—")
    if max_chars and len(value) > max_chars:
        value = value[:max_chars - 1] + "…"
    draw.text(xy, value, font=_font(size, bold), fill=fill)


def render_overview(stats: dict, artwork: bytes | None = None) -> bytes:
    """Return PNG bytes; missing artwork and missing stats are supported."""
    im = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 8, HEIGHT), fill=ORANGE)
    d.rectangle((24, 20, 936, 115), fill=PANEL)
    _text(d, (44, 33), "BATTLEFIELD 4  /  PLAYER OVERVIEW", 18, ORANGE, True)
    _text(d, (44, 62), stats.get("name", "Unknown soldier"), 31, WHITE, True, 29)
    _text(d, (650, 43), stats.get("platform", "—"), 20, MUTED)
    _text(d, (650, 75), stats.get("hours", "—") + " HOURS", 20, WHITE, True)

    tiles = [
        ("KILLS", "kills"), ("DEATHS", "deaths"), ("K/D RATIO", "kd"),
        ("ACCURACY", "accuracy"), ("BEST STREAK", "streak"), ("KILLS / MIN", "kpm"),
        ("SCORE / MIN", "spm"), ("WIN RATE", "win_rate"), ("BEST CLASS", "best_class"),
    ]
    for i, (label, key) in enumerate(tiles):
        x = 24 + (i % 3) * 207
        y = 130 + (i // 3) * 120
        d.rounded_rectangle((x, y, x + 194, y + 108), radius=7, fill=TILE)
        _text(d, (x + 15, y + 16), label, 15, MUTED, True)
        _text(d, (x + 15, y + 51), stats.get(key, "—"), 23, WHITE, True, 12)

    d.rounded_rectangle((652, 130, 936, 476), radius=8, fill=PANEL)
    _text(d, (670, 149), "SIGNATURE EQUIPMENT", 16, ORANGE, True)
    if artwork:
        try:
            source = Image.open(BytesIO(artwork)).convert("RGBA")
            source.thumbnail((258, 188), Image.Resampling.LANCZOS)
            im.paste(source, (794 - source.width // 2, 190 + (188 - source.height) // 2), source)
        except (OSError, ValueError):
            pass
    d = ImageDraw.Draw(im)
    _text(d, (669, 392), stats.get("equipment_name", "Not collected"), 19, WHITE, True, 22)
    _text(d, (669, 426), stats.get("equipment_kills", "—") + " kills", 18, MUTED)
    d.rectangle((24, 508, 936, 510), fill="#4a515b")
    _text(d, (28, 531), "BF4 PLAYER STATS", 17, ORANGE, True)
    _text(d, (320, 533), stats.get("collected", "Collection time unavailable"), 16, MUTED)
    _text(d, (28, 568), "Statistics collected by BF4PS • Refresh subject to cooldown", 14, MUTED)
    output = BytesIO()
    im.save(output, format="PNG", optimize=True)
    return output.getvalue()
