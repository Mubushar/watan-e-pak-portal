"""
Build the Watan-e-Pak app icons from assets/logo.png.

The launcher icon is the logo's line work in white with gold accents, drawn bold and outlined in
dark grey, with the Urdu name وطن پاک in gold beneath it, on the brand green inside a gold ring.
assets/urdu-wordmark.png is the Urdu name rendered in Noto Nastaliq Urdu (Pillow can't shape
Urdu, so it was drawn once in a browser canvas). Writes:

* Android adaptive icon layers (mipmap-*/ic_launcher_foreground.png, ic_launcher_background.png)
  and the legacy square / round icons (ic_launcher.png, ic_launcher_round.png)
* iOS AppIcon (1024 x 1024, no transparency)
* Electron icon (build-resources/icon.png)
* assets/app-icon-preview.png (what a launcher shows) for review

Run from portable/:  python scripts/make_app_icon.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "android" / "app" / "src" / "main" / "res"

GREEN_CENTER = (31, 138, 87)    # brand-500
GREEN_EDGE = (9, 58, 38)        # brand-900
SHADOW = (4, 32, 22)            # brand-950
OUTLINE = (46, 50, 48)          # dark grey around the white and gold line work
WHITE = (255, 255, 255)
GOLD_TOP = (242, 221, 143)      # gold-200
GOLD_BOTTOM = (220, 177, 58)    # gold-400

CANVAS = 1728                   # working size of the 108 dp adaptive canvas (16 px per dp)
GLYPH_WIDTH_DP = 54             # the logo's width on the 108 dp canvas (visible area is ~72 dp)
GLYPH_TOP_DP = 25               # top of the logo; the Urdu name sits below it
URDU_HEIGHT_DP = 14             # height of وطن پاک
STROKE_DP = 0.75                # extra line weight added around every stroke
OUTLINE_DP = 0.8                # dark grey outline width


def _glyph_masks(width: int) -> tuple[Image.Image, Image.Image]:
    """The logo split into a white layer (everything but gold) and a gold layer, bolded."""
    logo = Image.open(ROOT / "assets" / "logo.png").convert("RGBA")
    logo = logo.crop(logo.getbbox())
    logo = logo.resize((width, round(logo.height * width / logo.width)), Image.LANCZOS)
    rgb = np.asarray(logo.convert("RGB"), dtype=np.float32) / 255
    alpha = np.asarray(logo.getchannel("A"), dtype=np.float32) / 255
    hsv = np.asarray(logo.convert("HSV"), dtype=np.float32) / 255
    hue, sat, val = hsv[..., 0] * 360, hsv[..., 1], hsv[..., 2]
    gold = (hue > 25) & (hue < 65) & (sat > 0.3)
    pale = (sat < 0.22) & (val > 0.7) & (rgb.min(axis=-1) > 0.6)   # the snowy mountains
    white_a = np.where(gold, 0, np.where(pale, np.clip(alpha * 2.2 - 0.25, 0, 1), alpha))
    gold_a = np.where(gold, alpha, 0)
    grow = max(3, round(STROKE_DP * CANVAS / 108)) | 1
    to_img = lambda a: Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "L")
    return to_img(white_a).filter(ImageFilter.MaxFilter(grow)), to_img(gold_a).filter(ImageFilter.MaxFilter(grow))


def _gold_fill(size: tuple[int, int]) -> Image.Image:
    """A vertical gold gradient (light at the top) for the gold layer."""
    t = np.linspace(0, 1, size[1], dtype=np.float32)[:, None, None]
    top, bottom = np.array(GOLD_TOP, np.float32), np.array(GOLD_BOTTOM, np.float32)
    grad = np.broadcast_to(top + (bottom - top) * t, (size[1], size[0], 3))
    return Image.fromarray(grad.astype(np.uint8), "RGB")


def _outlined(layer: Image.Image, parts: list[tuple[Image.Image, Image.Image, tuple[int, int]]]) -> None:
    """Draw each (fill, mask, position) with one shared dark grey outline and a soft shadow."""
    union = Image.new("L", layer.size, 0)
    for _, mask, pos in parts:
        union.paste(Image.fromarray(np.maximum(np.asarray(union.crop((*pos, pos[0] + mask.width, pos[1] + mask.height))),
                                                np.asarray(mask)), "L"), pos)
    grow = max(3, round(OUTLINE_DP * 2 * CANVAS / 108)) | 1
    outline_mask = union.filter(ImageFilter.MaxFilter(grow))
    shadow = Image.new("RGBA", layer.size, SHADOW + (0,))
    shadow.putalpha(outline_mask.point(lambda v: v * 0.45).filter(ImageFilter.GaussianBlur(CANVAS / 120)))
    layer.alpha_composite(shadow, (0, CANVAS // 140))
    outline = Image.new("RGBA", layer.size, OUTLINE + (0,))
    outline.putalpha(outline_mask)
    layer.alpha_composite(outline)
    for fill, mask, pos in parts:
        fill = fill.copy()
        fill.putalpha(mask)
        layer.alpha_composite(fill, pos)


def _urdu_mask(height: int) -> Image.Image:
    urdu = Image.open(ROOT / "assets" / "urdu-wordmark.png").getchannel("A")
    return urdu.resize((round(urdu.width * height / urdu.height), height), Image.LANCZOS)


def foreground() -> Image.Image:
    """Transparent 108 dp layer: the logo, with وطن پاک below it, centred inside the ring."""
    dp = CANVAS / 108
    width = round(GLYPH_WIDTH_DP * dp)
    white_mask, gold_mask = _glyph_masks(width)
    urdu = _urdu_mask(round(URDU_HEIGHT_DP * dp))
    layer = Image.new("RGBA", (CANVAS, CANVAS))
    pos = ((CANVAS - width) // 2, round(GLYPH_TOP_DP * dp))
    urdu_pos = ((CANVAS - urdu.width) // 2, pos[1] + white_mask.height + round(1.2 * dp))
    _outlined(layer, [
        (Image.new("RGBA", white_mask.size, WHITE + (255,)), white_mask, pos),
        (_gold_fill(gold_mask.size).convert("RGBA"), gold_mask, pos),
        (_gold_fill(urdu.size).convert("RGBA"), urdu, urdu_pos),
    ])
    return layer


def background() -> Image.Image:
    """Brand green, lighter in the middle, with a thin gold ring inside the visible area."""
    yy, xx = np.mgrid[0:CANVAS, 0:CANVAS].astype(np.float32)
    r = np.hypot(xx - CANVAS / 2, yy - CANVAS / 2) / (CANVAS / 2)
    t = np.clip(r, 0, 1)[..., None] ** 1.4
    c0, c1 = np.array(GREEN_CENTER, np.float32), np.array(GREEN_EDGE, np.float32)
    img = Image.fromarray((c0 + (c1 - c0) * t).astype(np.uint8), "RGB").convert("RGBA")
    draw = ImageDraw.Draw(img)
    dp = CANVAS / 108
    for radius, width, colour in ((35.0, 1.1, GOLD_BOTTOM + (255,)), (33.7, 0.35, WHITE + (200,))):
        box = [CANVAS / 2 - radius * dp, CANVAS / 2 - radius * dp, CANVAS / 2 + radius * dp, CANVAS / 2 + radius * dp]
        draw.ellipse(box, outline=colour, width=max(1, round(width * dp)))
    return img


def _scaled(img: Image.Image, px: int) -> Image.Image:
    return img.resize((px, px), Image.LANCZOS)


def _masked(img: Image.Image, round_icon: bool) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    if round_icon:
        d.ellipse([0, 0, img.width - 1, img.height - 1], fill=255)
    else:
        d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=img.width * 0.22, fill=255)
    out = img.copy()
    out.putalpha(mask)
    return out


def main() -> None:
    fg, bg = foreground(), background()
    full = bg.copy()
    full.alpha_composite(fg)
    dp = CANVAS / 108

    def crop(visible_dp: float) -> Image.Image:
        m = round((108 - visible_dp) / 2 * dp)
        return full.crop((m, m, CANVAS - m, CANVAS - m))

    densities = {"ldpi": 0.75, "mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
    legacy = crop(74)
    for name, scale in densities.items():
        folder = RES / f"mipmap-{name}"
        _scaled(fg, round(108 * scale)).save(folder / "ic_launcher_foreground.png", optimize=True)
        _scaled(bg, round(108 * scale)).save(folder / "ic_launcher_background.png", optimize=True)
        icon = _scaled(legacy, round(48 * scale))
        _masked(icon, False).save(folder / "ic_launcher.png", optimize=True)
        _masked(icon, True).save(folder / "ic_launcher_round.png", optimize=True)

    ios = ROOT / "ios" / "App" / "App" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon-512@2x.png"
    _scaled(crop(80), 1024).convert("RGB").save(ios, optimize=True)

    desktop = Image.new("RGBA", (1024, 1024))
    desktop.alpha_composite(_masked(_scaled(crop(80), 896), False), (64, 64))
    desktop.save(ROOT / "build-resources" / "icon.png", optimize=True)

    preview = _masked(_scaled(crop(72), 512), False)
    preview.save(ROOT / "assets" / "app-icon-preview.png", optimize=True)
    print("icons written; preview: assets/app-icon-preview.png")


if __name__ == "__main__":
    main()
