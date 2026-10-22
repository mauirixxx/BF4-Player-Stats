"""Render the top-nine weapon/vehicle card with BF4 artwork and readable overlays."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .overview_card import ACCENTS, WHITE, MUTED, ORANGE

WIDTH, HEIGHT = 1200, 675
BACKGROUND = Path(__file__).with_name("assets") / "bf4_ranking_background.jpg"


def font(size: int, bold=False):
    return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)


def text_fit(draw, xy, value, max_width, size, fill=WHITE, bold=True, min_size=15):
    value = str(value or "—")
    while size > min_size and draw.textbbox((0, 0), value, font=font(size, bold))[2] > max_width:
        size -= 1
    if draw.textbbox((0, 0), value, font=font(size, bold))[2] > max_width:
        while value and draw.textbbox((0, 0), value + "…", font=font(size, bold))[2] > max_width:
            value = value[:-1]
        value += "…"
    draw.text(xy, value, font=font(size, bold), fill=fill)


def render_ranking(stats: dict, entries: list[dict], artwork: dict[str, bytes] | None = None) -> bytes:
    """Produce a self-contained 1200x675 PNG; every data value is supplied by caller."""
    artwork = artwork or {}
    accent = ACCENTS.get(stats.get("platform"), ORANGE)
    try:
        with Image.open(BACKGROUND) as source:
            # Center crop keeps the soldier and armored vehicle visible.
            base = ImageOps.fit(source.convert("RGB"), (WIDTH, HEIGHT),
                                method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    except (OSError, ValueError):
        base = Image.new("RGB", (WIDTH, HEIGHT), "#263442")
    im = base.convert("RGBA")
    # Subdue the bright artwork across the whole card without losing the scene.
    im = Image.alpha_composite(im, Image.new("RGBA", (WIDTH, HEIGHT), (8, 13, 20, 105)))
    # Header/footer bands add contrast for text over bright portions of the scene.
    veil = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    vd = ImageDraw.Draw(veil)
    vd.rectangle((0, 0, WIDTH, 128), fill=(10, 15, 22, 192))
    vd.rectangle((0, 624, WIDTH, HEIGHT), fill=(10, 15, 22, 200))
    im = Image.alpha_composite(im, veil)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 8, HEIGHT), fill=accent)
    heading = "TOP WEAPONS" if stats.get("view") == "weapons" else "TOP VEHICLES"
    text_fit(d, (32, 18), "BATTLEFIELD 4  /  " + heading, 680, 24, accent, True)
    text_fit(d, (32, 52), stats.get("name", "Unknown soldier"), 500, 37, WHITE, True)
    d.text((35, 97), f'{stats.get("platform", "—")}  |  {stats.get("hours", "—")} HOURS',
           font=font(17), fill=WHITE)
    try:
        with Image.open(Path(__file__).with_name("assets") / "battlefield4_wordmark_commons.png") as logo:
            logo = logo.convert("RGBA")
            logo.thumbnail((268, 51), Image.Resampling.LANCZOS)
            im.alpha_composite(logo, (WIDTH - 28 - logo.width, 26))
    except (OSError, ValueError):
        pass
    d = ImageDraw.Draw(im)

    left, top, gap_x, gap_y = 28, 151, 13, 12
    tile_w, tile_h = 372, 143
    for i in range(9):
        x = left + (i % 3) * (tile_w + gap_x)
        y = top + (i // 3) * (tile_h + gap_y)
        # Individual semi-transparent dark tiles: background remains visible.
        layer = Image.new("RGBA", (tile_w, tile_h), (16, 21, 29, 225))
        ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle((0, 0, tile_w - 1, tile_h - 1), radius=8,
                             outline=(177, 192, 205, 100), width=2)
        im.alpha_composite(layer, (x, y))
        d = ImageDraw.Draw(im)
        if i >= len(entries):
            continue
        item = entries[i]
        d.text((x + 15, y + 9), str(i + 1), font=font(27, True), fill=accent)
        text_fit(d, (x + 49, y + 12), item.get("name"), 302, 21, WHITE, True)
        d.text((x + 17, y + 54), f'{item.get("kills", 0):,} kills',
               font=font(29, True), fill=WHITE)
        kpm = item.get("kpm")
        hours = item.get("hours")
        details = (f"{kpm:.2f} KPM" if kpm is not None else "— KPM") + "  |  " + (
            f"{hours:,.1f} hours" if hours is not None else "— hours")
        text_fit(d, (x + 17, y + 111), details, 337, 17, MUTED, False)
        key = item.get("key")
        if key and key in artwork:
            try:
                with Image.open(BytesIO(artwork[key])) as source:
                    icon = source.convert("RGBA")
                    # Battlelog fancy PNGs often contain substantial transparent padding.
                    # Crop to the actual visible silhouette before scaling.
                    alpha = icon.getchannel("A")
                    bounds = alpha.point(lambda a: 255 if a > 12 else 0).getbbox()
                    if bounds:
                        icon = icon.crop(bounds)
                        icon.thumbnail((181, 88), Image.Resampling.LANCZOS)
                        # Anchor artwork to the right; keep the KPM line unobstructed.
                        im.alpha_composite(icon, (x + tile_w - 12 - icon.width,
                                                  y + 27 + (88 - icon.height) // 2))
            except (OSError, ValueError):
                pass
    d = ImageDraw.Draw(im)
    d.line((28, 628, 1172, 628), fill=(204, 214, 224, 175), width=2)
    d.text((32, 635), "BF4 PLAYER STATS", font=font(18, True), fill=accent)
    d.text((230, 640), "Statistics collected by BF4PS", font=font(14), fill=WHITE)
    stamp = stats.get("collected", "Collection time unavailable")
    width = d.textbbox((0, 0), stamp, font=font(15))[2]
    d.text((1172 - width, 640), stamp, font=font(15), fill=WHITE)
    out = BytesIO()
    im.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()
