import math
import os
import random
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageEnhance, ImageChops

W, H = 1280, 720
FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Lohit-Devanagari.ttf")

_font_cache = {}


def font(size):
    if size not in _font_cache:
        _font_cache[size] = ImageFont.truetype(FONT_PATH, size)
    return _font_cache[size]


# ---------------------------------------------------------------- background

def build_background():
    img = Image.new("RGB", (W, H), (20, 10, 20))
    top = (96, 56, 104)
    bottom = (238, 148, 78)
    for y in range(H):
        t = y / H
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        ImageDraw.Draw(img).line([(0, y), (W, y)], fill=(r, g, b))
    img = img.convert("RGBA")
    d = ImageDraw.Draw(img)

    # soft glow sun/moon
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dg = ImageDraw.Draw(glow)
    dg.ellipse([W * 0.5 - 260, H * 0.14, W * 0.5 + 260, H * 0.14 + 520], fill=(255, 224, 160, 150))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    img.alpha_composite(glow)

    # ground
    d.rectangle([0, H * 0.78, W, H], fill=(92, 60, 34, 255))
    d.rectangle([0, H * 0.76, W, H * 0.80], fill=(120, 82, 46, 255))

    # bunting flags across the top
    colors = [(230, 90, 70), (240, 190, 60), (90, 150, 110), (230, 130, 170), (90, 130, 190)]
    n = 15
    xs = [W * (0.03 + i * (0.94 / (n - 1))) for i in range(n)]
    sag = 46
    for i in range(n - 1):
        x0, x1 = xs[i], xs[i + 1]
        y0 = H * 0.06 + math.sin(i * 0.6) * 6
        y1 = H * 0.06 + math.sin((i + 1) * 0.6) * 6
        # string
        d.line([(x0, y0), ((x0 + x1) / 2, y0 + sag), (x1, y1)], fill=(60, 40, 30, 200), width=3)
        midx = (x0 + x1) / 2
        midy = y0 + sag * 0.75
        c = colors[i % len(colors)]
        d.polygon([(midx - 20, midy - 10), (midx + 20, midy - 10), (midx, midy + 34)], fill=c + (255,))

    # signboard banner
    bx0, by0, bx1, by1 = W * 0.5 - 210, H * 0.03, W * 0.5 + 210, H * 0.145
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=14, fill=(64, 38, 22, 255), outline=(255, 210, 140, 255), width=5)
    txt = "पंचायत"  # पंचायत
    f = font(56)
    tb = d.textbbox((0, 0), txt, font=f)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    d.text(((bx0 + bx1) / 2 - tw / 2, (by0 + by1) / 2 - th / 2 - tb[1]), txt, font=f, fill=(255, 225, 160, 255))

    # simple lantern posts either side
    for sx in (0.06, 0.94):
        px = W * sx
        d.line([(px, H * 0.30), (px, H * 0.80)], fill=(50, 34, 22, 255), width=10)
        d.ellipse([px - 22, H * 0.24, px + 22, H * 0.24 + 60], fill=(250, 200, 90, 230), outline=(90, 60, 20, 255), width=3)

    # gentle corner vignette only (center of frame stays bright/clear)
    vign = Image.new("L", (W, H), 0)
    dv = ImageDraw.Draw(vign)
    dv.ellipse([W * 0.10, H * 0.02, W * 0.90, H * 1.10], fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(160))
    vlayer = Image.new("RGBA", (W, H), (8, 4, 10, 0))
    vlayer.putalpha(vign.point(lambda p: int((255 - p) * 0.42)))
    img.alpha_composite(vlayer)

    return img.convert("RGB")


# --------------------------------------------------------------------- torso

def _sequin_scatter(draw, mask_box, n, rng, rmin=3, rmax=6, color=(255, 255, 255), alpha=190):
    x0, y0, x1, y1 = mask_box
    for _ in range(n):
        x = rng.uniform(x0, x1)
        y = rng.uniform(y0, y1)
        r = rng.uniform(rmin, rmax)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color + (alpha,))


def build_torso(character, width=900, height=460):
    """Kathputli-style costume: teal sequined jacket + rainbow cummerbund
    for Bansi; red velvet bodice + gold trim + beads for Phoolwati."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rng = random.Random(11 if character == "bansi" else 12)

    if character == "bansi":
        base = (30, 120, 118)
        base2 = (22, 90, 92)
    else:
        base = (150, 18, 34)
        base2 = (110, 10, 26)

    body_box = [width * 0.05, -20, width * 0.95, height]
    d.rounded_rectangle(body_box, radius=90, fill=base + (255,))
    # vertical shading
    shade = Image.new("L", (width, height), 0)
    ds = ImageDraw.Draw(shade)
    ds.rounded_rectangle(body_box, radius=90, fill=60)
    shade = shade.filter(ImageFilter.GaussianBlur(24))
    dark = Image.new("RGBA", (width, height), base2 + (255,))
    dark.putalpha(shade.point(lambda p: int(p * 0.55)))
    img.alpha_composite(dark)

    body_mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(body_mask).rounded_rectangle(body_box, radius=90, fill=255)

    if character == "bansi":
        collar = (247, 240, 220)
        gold = (230, 190, 90)
        # sequins scattered across the jacket
        seq_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ds2 = ImageDraw.Draw(seq_layer)
        _sequin_scatter(ds2, (width * 0.08, 0, width * 0.92, height * 0.62), 140, rng,
                         rmin=3, rmax=6, color=(220, 245, 240), alpha=150)
        seq_layer.putalpha(ImageChops.multiply(seq_layer.split()[3], body_mask))
        img.alpha_composite(seq_layer)

        # mandarin collar (small, hugging the neckline) + placket
        d.polygon([(width * 0.5, height * 0.00), (width * 0.44, height * 0.07), (width * 0.56, height * 0.07)],
                   fill=collar + (255,))
        d.line([(width * 0.5, height * 0.02), (width * 0.5, height * 0.50)], fill=gold + (255,), width=6)
        for i in range(4):
            cy = height * (0.12 + i * 0.09)
            d.ellipse([width * 0.5 - 7, cy - 7, width * 0.5 + 7, cy + 7], fill=gold + (255,))

        # rainbow-striped cummerbund across the waist
        cb_top, cb_bot = height * 0.60, height * 0.86
        stripe_colors = [(210, 60, 60), (230, 150, 40), (220, 200, 60), (60, 140, 90),
                          (50, 90, 160), (140, 70, 150)]
        n = len(stripe_colors)
        band = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        db = ImageDraw.Draw(band)
        for i, c in enumerate(stripe_colors):
            y0 = cb_top + (cb_bot - cb_top) * i / n
            y1 = cb_top + (cb_bot - cb_top) * (i + 1) / n
            db.rectangle([width * 0.06, y0, width * 0.94, y1], fill=c + (255,))
        band.putalpha(ImageChops.multiply(band.split()[3], body_mask))
        img.alpha_composite(band)
        d.rectangle([width * 0.06, cb_top - 6, width * 0.94, cb_top], fill=gold + (255,))
        d.rectangle([width * 0.06, cb_bot, width * 0.94, cb_bot + 6], fill=gold + (255,))

    else:
        trim = (230, 195, 110)
        # sequins across the bodice
        seq_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ds2 = ImageDraw.Draw(seq_layer)
        _sequin_scatter(ds2, (width * 0.08, 0, width * 0.92, height * 0.7), 110, rng,
                         rmin=3, rmax=5, color=(255, 225, 180), alpha=140)
        seq_layer.putalpha(ImageChops.multiply(seq_layer.split()[3], body_mask))
        img.alpha_composite(seq_layer)

        # neckline trim
        d.arc([width * 0.30, -height * 0.08, width * 0.70, height * 0.32], start=15, end=165,
              fill=trim + (255,), width=16)
        d.arc([width * 0.34, -height * 0.02, width * 0.66, height * 0.24], start=15, end=165,
              fill=(255, 255, 255, 130), width=4)

        # multi-row bead necklaces
        for row, (ry, spread, csz) in enumerate([(0.16, 0.30, 7), (0.24, 0.36, 6), (0.32, 0.42, 5)]):
            beads_y = height * ry
            cols = [(240, 200, 70), (215, 35, 45)] if row < 2 else [(230, 195, 110)]
            for i in range(11):
                t = i / 10
                bx = width * 0.5 + (t - 0.5) * width * spread
                by = beads_y + math.sin(t * math.pi) * 22
                d.ellipse([bx - csz, by - csz, bx + csz, by + csz], fill=cols[i % len(cols)] + (255,))

        # gold waistband
        wb_top, wb_bot = height * 0.66, height * 0.80
        d.rectangle([width * 0.06, wb_top, width * 0.94, wb_bot], fill=trim + (255,))
        for i in range(10):
            gx = width * (0.10 + i * 0.084)
            d.ellipse([gx - 8, (wb_top + wb_bot) / 2 - 8, gx + 8, (wb_top + wb_bot) / 2 + 8],
                      fill=(215, 35, 45, 255))

    return img


def build_arm(character, width=170, height=400):
    """A single hanging sleeve + hand + bangles, drawn facing 'outward'
    (i.e. as the character's right arm); mirror the image for the left."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if character == "bansi":
        sleeve = (30, 120, 118)
        cuff = (230, 190, 90)
        skin = SKIN if "SKIN" in globals() else (233, 181, 84)
    else:
        sleeve = (150, 18, 34)
        cuff = (230, 195, 110)
        skin = (233, 181, 84)

    d.rounded_rectangle([width * 0.15, 0, width * 0.85, height * 0.72], radius=int(width * 0.32),
                         fill=sleeve + (255,))
    # slight shading
    d.rounded_rectangle([width * 0.15, 0, width * 0.46, height * 0.72], radius=int(width * 0.32),
                         fill=tuple(max(0, c - 25) for c in sleeve) + (140,))
    # cuff
    d.ellipse([width * 0.10, height * 0.60, width * 0.90, height * 0.80], fill=cuff + (255,))
    # hand
    d.ellipse([width * 0.22, height * 0.72, width * 0.78, height * 1.00], fill=skin + (255,))
    if character == "phoolwati":
        for i, ry in enumerate([0.66, 0.70, 0.74]):
            d.ellipse([width * 0.14, height * ry, width * 0.86, height * (ry + 0.05)],
                      outline=(215, 35, 45, 255), width=4)
    return img


# ------------------------------------------------------------------ cutaways

def _card_base(bg_color=(40, 22, 40)):
    img = Image.new("RGBA", (W, H), bg_color + (255,))
    d = ImageDraw.Draw(img)
    for i in range(0, W, 46):
        d.line([(i, 0), (i + H, H)], fill=(255, 255, 255, 10), width=2)
    vign = Image.new("L", (W, H), 0)
    dv = ImageDraw.Draw(vign)
    dv.ellipse([-W * 0.2, -H * 0.2, W * 1.2, H * 1.2], fill=90)
    vign = vign.filter(ImageFilter.GaussianBlur(140))
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    dark.putalpha(ImageOps.invert(vign))
    img.alpha_composite(dark)
    return img


def _fit_font(d, text, max_w, start_size, min_size=28):
    """Shrink the font until the text fits the given width."""
    size = start_size
    while size > min_size:
        f = font(size)
        tb = d.textbbox((0, 0), text, font=f)
        if tb[2] - tb[0] <= max_w:
            return f
        size -= 4
    return font(min_size)


def cutaway_card(text, subtext="", style="reveal"):
    """A cutaway insert card with caller-supplied text, so the app can
    drive cutaways from the script instead of hardcoded copy."""
    if style == "title":
        img = _card_base((30, 34, 60))
        accent = (255, 240, 210)
        sub_accent = (255, 210, 140)
        stroke = (40, 20, 60)
    else:
        img = _card_base((52, 18, 44))
        accent = (255, 225, 120)
        sub_accent = (255, 200, 150)
        stroke = (60, 20, 20)

    d = ImageDraw.Draw(img)
    text = (text or "").strip()
    subtext = (subtext or "").strip()

    main_y = H * 0.42 if subtext else H * 0.46
    if text:
        f1 = _fit_font(d, text, W * 0.84, 78)
        tb = d.textbbox((0, 0), text, font=f1)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        d.text((W / 2 - tw / 2, main_y - th / 2 - tb[1]), text, font=f1, fill=accent + (255,),
               stroke_width=6, stroke_fill=stroke + (255,))

    if subtext:
        f2 = _fit_font(d, subtext, W * 0.76, 46)
        tb2 = d.textbbox((0, 0), subtext, font=f2)
        d.text((W / 2 - (tb2[2] - tb2[0]) / 2, H * 0.58), subtext, font=f2, fill=sub_accent + (255,))

    if style == "reveal":
        # magnifying-glass doodle
        gx, gy = W * 0.5, H * 0.76
        d.ellipse([gx - 40, gy - 40, gx + 40, gy + 40], outline=accent + (255,), width=9)
        d.line([(gx + 28, gy + 28), (gx + 68, gy + 68)], fill=accent + (255,), width=12)
    else:
        # simple decorative rule
        d.line([(W * 0.34, H * 0.72), (W * 0.66, H * 0.72)], fill=accent + (200,), width=5)

    return img.convert("RGB")


# ------------------------------------------------------------------ subtitle

def draw_subtitle(base_img, text):
    img = base_img.convert("RGBA")
    d = ImageDraw.Draw(img)
    f = font(40)
    max_w = W * 0.86

    words = text.split(" ")
    lines, cur = [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        tb = d.textbbox((0, 0), trial, font=f)
        if tb[2] - tb[0] > max_w and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = trial
    if cur:
        lines.append(cur)
    lines = lines[-2:]  # keep it to 2 lines max

    line_h = 50
    block_h = line_h * len(lines) + 26
    y0 = H - block_h - 26
    d.rounded_rectangle([W * 0.05, y0, W * 0.95, H - 26], radius=16, fill=(10, 8, 10, 165))

    y = y0 + 14
    for ln in lines:
        tb = d.textbbox((0, 0), ln, font=f)
        tw = tb[2] - tb[0]
        d.text((W / 2 - tw / 2, y), ln, font=f, fill=(255, 250, 235, 255),
               stroke_width=3, stroke_fill=(20, 10, 10, 255))
        y += line_h
    return img.convert("RGB")


def scene_card(title, kicker=""):
    """A chapter/episode title card for a scene transition.

    Deliberately unlike `cutaway_card`: cutaways are a gag interrupting the
    action, whereas this reads as the show announcing a new section, so it
    gets a curtain-warm ground, a small kicker line ("Scene 1") over a large
    title, and rules top and bottom to frame it.
    """
    img = _card_base((92, 42, 30))
    accent = (255, 236, 190)
    kick = (240, 176, 96)
    rule = (200, 140, 70)
    stroke = (52, 20, 12)

    d = ImageDraw.Draw(img)
    title = (title or "").strip()
    kicker = (kicker or "").strip()

    if kicker:
        fk = _fit_font(d, kicker, W * 0.6, 40, min_size=22)
        tb = d.textbbox((0, 0), kicker, font=fk)
        d.text((W / 2 - (tb[2] - tb[0]) / 2, H * 0.33), kicker, font=fk, fill=kick + (255,))

    if title:
        ft = _fit_font(d, title, W * 0.82, 76, min_size=34)
        tb = d.textbbox((0, 0), title, font=ft)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        ty = H * 0.53
        d.text((W / 2 - tw / 2, ty - th / 2 - tb[1]), title, font=ft,
               fill=accent + (255,), stroke_width=6, stroke_fill=stroke + (255,))

    for y in (H * 0.43, H * 0.66):
        d.line([(W * 0.30, y), (W * 0.70, y)], fill=rule + (220,), width=4)
        d.ellipse([W * 0.5 - 6, y - 6, W * 0.5 + 6, y + 6], fill=accent + (230,))

    return img.convert("RGB")
