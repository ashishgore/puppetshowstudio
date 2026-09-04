"""
Original Rajasthani "kathputli"-style string-marionette characters for the
"Panchayat" comedy bits. Styled after traditional painted-wood kathputli
dolls (bold flat-painted face, thick black eyeliner/brows, ornate turban or
jeweled veil, sequined/embroidered costume, visible strings) -- an original
design, not a copy of any copyrighted character:

  - Bansi (Ashish): stately village-elder host. Checkered red/cream
    turban, black painted moustache + full beard, red tilak, teal
    sequined jacket.
  - Phoolwati: warm gossipy-aunty co-host. Jeweled silver headdress with a
    red zari-edged veil, red velvet bodice, bindi row.

Each character is built as layered PIL RGBA images so mouth shape
(closed/mid/open) and eye state (open/blink) can be swapped per frame for
simple amplitude-driven "puppet flap" mouth animation + blinking.
"""
import math
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

random.seed(7)

CANVAS = (900, 1150)  # working resolution per head asset

SKIN = (233, 181, 84)        # painted-wood gold face
SKIN_SHADE = (196, 142, 58)


def _felt_texture(size, base_color, seed=0, strength=10):
    """Very subtle painted-wood grain (much softer than the old felt noise)."""
    rng = np.random.default_rng(seed)
    w, h = size
    noise = rng.normal(0, 1, (h, w))
    img = Image.fromarray(((noise - noise.min()) / (np.ptp(noise)) * 255).astype(np.uint8))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    arr = np.array(img).astype(np.float32) / 255.0
    base = np.array(Image.new("RGB", size, base_color)).astype(np.float32)
    variation = (arr[..., None] - 0.5) * strength
    out = np.clip(base + variation, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="RGB")


def _mask_from_points(size, pts, blur=3):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    if blur:
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
    return mask


def _carved_head_mask(size, jitter_seed=1):
    """A more geometric, symmetric 'carved wooden mask' silhouette --
    wide cheekbones, a defined chin, much less organic than a felt blob."""
    w, h = size
    cx = w / 2
    rng = random.Random(jitter_seed)
    # key vertical fractions (as % of h) and half-widths (as % of w)
    profile = [
        (0.00, 0.30), (0.06, 0.365), (0.16, 0.40), (0.30, 0.415),
        (0.46, 0.40), (0.60, 0.365), (0.72, 0.30), (0.84, 0.205),
        (0.94, 0.11), (1.00, 0.045),
    ]
    left = []
    right = []
    for t, hw in profile:
        jitter = 1 + rng.uniform(-0.015, 0.015)
        y = h * t
        x = hw * w * jitter
        left.append((cx - x, y))
        right.append((cx + x, y))
    pts = left + right[::-1]
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(2.5))
    mask = mask.point(lambda p: 255 if p > 120 else int(p * 1.2))
    return mask


def make_eye(open_=True, size=140, wing=True):
    """Bold kathputli eye: white sclera, thick black outline, dark iris,
    a winged eyeliner flick, and a graphic painted brow above it (brow is
    added separately so it can be repositioned per character)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy = size * 0.52
    if open_:
        eye_box = [size * 0.04, cy - size * 0.22, size * 0.86, cy + size * 0.22]
        d.ellipse(eye_box, fill=(255, 252, 240, 255))
        d.ellipse(eye_box, outline=(15, 10, 8, 255), width=7)
        r = size * 0.185
        icx, icy = size * 0.46, cy + size * 0.02
        d.ellipse([icx - r, icy - r, icx + r, icy + r], fill=(35, 20, 12, 255))
        pr = r * 0.4
        d.ellipse([icx - pr, icy - pr, icx + pr, icy + pr], fill=(5, 3, 2, 255))
        d.ellipse([icx - r * 0.5, icy - r * 0.7, icx - r * 0.05, icy - r * 0.25], fill=(255, 255, 255, 220))
        if wing:
            wx, wy = size * 0.86, cy - size * 0.10
            d.line([(size * 0.62, cy - size * 0.20), (wx, wy), (wx + size * 0.14, wy - size * 0.10)],
                   fill=(15, 10, 8, 255), width=8, joint="curve")
    else:
        d.line([(size * 0.04, cy), (size * 0.86, cy - size * 0.02)], fill=(15, 10, 8, 255), width=8)
        if wing:
            wx, wy = size * 0.86, cy - size * 0.10
            d.line([(size * 0.66, cy - size * 0.02), (wx + size * 0.14, wy - size * 0.06)],
                   fill=(15, 10, 8, 255), width=7)
    return img


def make_mouth(state, size=(280, 190), tone="bansi"):
    """Flat painted mouth (bold outline, solid fill) -- state 0 closed,
    1 mid, 2 open."""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w, h = size
    lip = (150, 30, 40, 255)
    inner = (70, 12, 18, 255)

    if state == 0:
        d.line([(w * 0.20, h * 0.48), (w * 0.5, h * 0.58), (w * 0.80, h * 0.48)],
               fill=lip, width=11, joint="curve")
    elif state == 1:
        d.ellipse([w * 0.28, h * 0.34, w * 0.72, h * 0.60], fill=inner, outline=lip, width=9)
    else:
        d.ellipse([w * 0.20, h * 0.16, w * 0.80, h * 0.84], fill=inner, outline=lip, width=12)
        d.rectangle([w * 0.30, h * 0.20, w * 0.70, h * 0.32], fill=(250, 245, 232, 255))
        d.pieslice([w * 0.32, h * 0.44, w * 0.68, h * 0.84], start=0, end=180, fill=(200, 70, 80, 255))
    return img


def _checker_turban(w, h, base=(190, 40, 34), check=(250, 240, 222)):
    """Red/cream checkered safa (Rajasthani turban), wrapped dome + a
    peak-fan fold on one side, brooch at the front."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    dome_mask = Image.new("L", (w, h), 0)
    dm = ImageDraw.Draw(dome_mask)
    dm.ellipse([w * 0.05, h * 0.02, w * 0.95, h * 0.92], fill=255)
    dome_mask = dome_mask.filter(ImageFilter.GaussianBlur(2))

    xs, ys = np.meshgrid(np.arange(w), np.arange(h))
    period = h * 0.11
    # diagonal check pattern (two crossing stripe sets)
    a = (np.floor((xs * 0.6 + ys) / period) % 2)
    b = (np.floor((xs * -0.6 + ys) / period) % 2)
    is_check = ((a == 0) ^ (b == 0)).astype(np.float32)
    cloth = np.zeros((h, w, 3), dtype=np.float32)
    for c in range(3):
        cloth[..., c] = base[c] * (1 - is_check) + check[c] * is_check
    yy = ys / h
    cloth *= (1.0 - 0.18 * yy)[..., None]
    cloth_img = Image.fromarray(np.clip(cloth, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    cloth_img.putalpha(dome_mask)
    img.alpha_composite(cloth_img)

    d = ImageDraw.Draw(img)
    # wrap seams
    for i in range(3):
        y0 = h * (0.18 + i * 0.20)
        d.arc([w * 0.10, y0, w * 0.90, y0 + h * 0.42], start=195, end=345,
              fill=(120, 18, 16, 130), width=6)
    d.arc([w * 0.08, h * 0.28, w * 0.92, h * 0.98], start=12, end=168, fill=(80, 10, 10, 170), width=10)

    # side fan/plume fold (kathputli signature peak)
    fan = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    df = ImageDraw.Draw(fan)
    df.polygon([(w * 0.66, h * 0.10), (w * 0.94, h * -0.14), (w * 0.86, h * 0.30), (w * 0.62, h * 0.30)],
               fill=base + (255,))
    for i in range(4):
        xa = w * (0.66 + i * 0.065)
        df.line([(xa, h * 0.28), (xa + w * 0.05, h * -0.06)], fill=check + (230,), width=5)
    img.alpha_composite(fan)

    cx, cy = w * 0.5, h * 0.56
    d.ellipse([cx - 26, cy - 22, cx + 26, cy + 22], fill=(240, 200, 60, 255), outline=(255, 250, 220, 255), width=4)
    d.ellipse([cx - 10, cy - 8, cx + 10, cy + 8], fill=(200, 30, 40, 255))
    return img


def _jeweled_veil(w, h, veil=(190, 30, 40), trim=(225, 195, 100)):
    """Ornate silver/gold tiara band along the hairline + a flowing red
    zari-edged veil draped over the head."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    dome_mask = Image.new("L", (w, h), 0)
    dm = ImageDraw.Draw(dome_mask)
    dm.ellipse([w * 0.04, h * 0.02, w * 0.96, h * 0.98], fill=255)
    dome_mask = dome_mask.filter(ImageFilter.GaussianBlur(2))

    xs, ys = np.meshgrid(np.arange(w), np.arange(h))
    t = np.clip(ys / (h * 0.9), 0, 1)
    cloth = np.zeros((h, w, 3), dtype=np.float32)
    dark = tuple(max(0, c - 55) for c in veil)
    for c in range(3):
        cloth[..., c] = veil[c] * (1 - t * 0.4) + dark[c] * (t * 0.4)
    cloth_img = Image.fromarray(np.clip(cloth, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    cloth_img.putalpha(dome_mask)
    img.alpha_composite(cloth_img)

    d = ImageDraw.Draw(img)
    # zari (metallic) trim band along the front hairline edge -- thick and bright
    d.arc([w * 0.05, h * 0.28, w * 0.95, h * 1.02], start=12, end=168, fill=trim + (255,), width=20)
    d.arc([w * 0.08, h * 0.33, w * 0.92, h * 0.94], start=12, end=168, fill=(255, 255, 235, 160), width=4)
    d.arc([w * 0.05, h * 0.28, w * 0.95, h * 1.02], start=12, end=168, fill=(140, 40, 20, 255), width=3)
    # tiara jewels along the band, alternating ruby/emerald for richness
    jewel_colors = [(210, 30, 40), (30, 120, 80)]
    for i in range(9):
        a = math.radians(14 + i * (152 / 8))
        ex = w * 0.5 - math.cos(a) * w * 0.43
        ey = h * 0.70 - math.sin(a) * h * 0.40
        jc = jewel_colors[i % 2]
        d.ellipse([ex - 11, ey - 11, ex + 11, ey + 11], fill=jc + (255,), outline=trim + (255,), width=3)
        d.ellipse([ex - 4, ey - 4, ex + 4, ey + 4], fill=(255, 255, 255, 160))
    # central jewel centerpiece (maang-tikka style)
    cx, cy = w * 0.5, h * 0.64
    d.ellipse([cx - 34, cy - 30, cx + 34, cy + 30], fill=(215, 35, 45, 255), outline=trim + (255,), width=6)
    d.ellipse([cx - 14, cy - 12, cx + 14, cy + 12], fill=(255, 235, 190, 255))
    d.line([(cx, cy - 30), (cx, h * 0.30)], fill=trim + (255,), width=5)
    d.ellipse([cx - 8, h * 0.30 - 8, cx + 8, h * 0.30 + 8], fill=trim + (255,))

    # soft veil fold to the side (subtle, not a big dark disc)
    fold = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    df = ImageDraw.Draw(fold)
    dark = tuple(max(0, c - 55) for c in veil)
    df.ellipse([w * 0.72, h * 0.46, w * 0.98, h * 0.88], fill=dark + (140,))
    fold = fold.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(Image.composite(fold, Image.new("RGBA", (w, h), (0, 0, 0, 0)), dome_mask))

    # small chain danglers either side of the face
    for sx in (-1, 1):
        bx = w * 0.5 + sx * w * 0.36
        by = h * 0.66
        d.line([(bx, by), (bx + sx * 6, by + 30)], fill=trim + (230,), width=3)
        d.ellipse([bx + sx * 6 - 7, by + 30 - 7, bx + sx * 6 + 7, by + 30 + 7], fill=(210, 30, 40, 255),
                  outline=trim + (255,), width=2)
    return img


def _eyebrow(w, h, color=(15, 10, 8)):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.line([(4, h * 0.66), (w * 0.46, h * 0.10), (w - 4, h * 0.42)], fill=color + (255,), width=17, joint="curve")
    return img


def _moustache(w, h, color=(18, 12, 10)):
    """Bold curled handlebar moustache, lying flat along the upper lip
    and curling up at the tips -- not two tall 'ears'."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = w / 2
    base_y = h * 0.42
    for side in (-1, 1):
        d.polygon([
            (cx, base_y + h * 0.10),
            (cx + side * w * 0.06, base_y - h * 0.06),
            (cx + side * w * 0.22, base_y - h * 0.02),
            (cx + side * w * 0.36, base_y + h * 0.04),
            (cx + side * w * 0.46, base_y - h * 0.10),
            (cx + side * w * 0.50, base_y - h * 0.24),
            (cx + side * w * 0.42, base_y - h * 0.20),
            (cx + side * w * 0.34, base_y + h * 0.10),
            (cx + side * w * 0.18, base_y + h * 0.16),
        ], fill=color + (255,))
    return img


def _chin_beard(w, h, color=(18, 12, 10)):
    """Beard framing the jaw and chin ONLY (a horseshoe shape) -- the
    mouth sits in the open gap above it, so it stays visible/animatable."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = w / 2
    outer = [
        (cx - w * 0.50, h * 0.00), (cx - w * 0.50, h * 0.30),
        (cx - w * 0.40, h * 0.62), (cx - w * 0.20, h * 0.88),
        (cx, h * 1.00), (cx + w * 0.20, h * 0.88),
        (cx + w * 0.40, h * 0.62), (cx + w * 0.50, h * 0.30),
        (cx + w * 0.50, h * 0.00),
    ]
    inner = [
        (cx + w * 0.30, h * 0.00), (cx + w * 0.28, h * 0.20),
        (cx + w * 0.14, h * 0.42), (cx, h * 0.50),
        (cx - w * 0.14, h * 0.42), (cx - w * 0.28, h * 0.20),
        (cx - w * 0.30, h * 0.00),
    ]
    mask = Image.new("L", (w, h), 0)
    dm = ImageDraw.Draw(mask)
    dm.polygon(outer, fill=255)
    dm.polygon(inner, fill=0)
    solid = Image.new("RGBA", (w, h), color + (255,))
    img.paste(solid, (0, 0), mask)
    return img


def build_head(character, mouth_state=0, blink=False):
    """Returns the full head+headwear composited on the CANVAS-sized
    transparent sheet."""
    W, H = CANVAS
    TOP = int(H * 0.22)
    HW, HH = W, H - TOP

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    face = Image.new("RGBA", (HW, HH), (0, 0, 0, 0))

    mask = _carved_head_mask((HW, HH), jitter_seed=1 if character == "bansi" else 2)
    tex = _felt_texture((HW, HH), SKIN, seed=5 if character == "bansi" else 9, strength=9)
    head_rgba = Image.new("RGBA", (HW, HH), (0, 0, 0, 0))
    head_rgba.paste(tex, (0, 0), mask)
    face.alpha_composite(head_rgba)

    # simple painted shading down each side (carved-wood contour, flat not fuzzy)
    shade = Image.new("L", (HW, HH), 0)
    ds = ImageDraw.Draw(shade)
    ds.ellipse([HW * 0.10, HH * 0.05, HW * 0.90, HH * 1.02], fill=70)
    shade = shade.filter(ImageFilter.GaussianBlur(50))
    shadow_alpha = ImageOps.invert(shade).point(lambda p: int(p * 0.30))
    shadow_alpha = Image.composite(shadow_alpha, Image.new("L", (HW, HH), 0), mask)
    shadow_layer = Image.new("RGBA", (HW, HH), (0, 0, 0, 0))
    shadow_layer.putalpha(shadow_alpha)
    face.alpha_composite(shadow_layer)

    # cheek blush (painted circles)
    cheek = Image.new("RGBA", (HW, HH), (0, 0, 0, 0))
    dc = ImageDraw.Draw(cheek)
    blush = (205, 90, 70)
    dc.ellipse([HW * 0.14, HH * 0.52, HW * 0.32, HH * 0.64], fill=blush + (90,))
    dc.ellipse([HW * 0.68, HH * 0.52, HW * 0.86, HH * 0.64], fill=blush + (90,))
    cheek = cheek.filter(ImageFilter.GaussianBlur(12))
    face.alpha_composite(cheek)

    eye_y = int(HH * 0.36)
    eye_dx = int(HW * 0.175)
    eye = make_eye(open_=not blink)
    ew = eye.size[0]
    # left eye mirrored so both wings point outward
    eye_l = ImageOps.mirror(eye)
    face.alpha_composite(eye_l, (int(HW / 2 - eye_dx - ew / 2), eye_y))
    face.alpha_composite(eye, (int(HW / 2 + eye_dx - ew / 2), eye_y))

    brow = _eyebrow(180, 90)
    brow_l = ImageOps.mirror(brow)
    face.alpha_composite(brow_l, (int(HW / 2 - eye_dx - 90), eye_y - 66))
    face.alpha_composite(brow, (int(HW / 2 + eye_dx - 90), eye_y - 66))

    # simple painted nose: a small soft triangle + two nostril dots
    nose = Image.new("RGBA", (HW, HH), (0, 0, 0, 0))
    dn = ImageDraw.Draw(nose)
    nx = HW / 2
    ny0, ny1 = HH * 0.44, HH * 0.555
    dn.polygon([(nx, ny0), (nx - 16, ny1), (nx + 16, ny1)], fill=SKIN_SHADE + (160,))
    dn.ellipse([nx - 15, ny1 - 6, nx - 5, ny1 + 4], fill=SKIN_SHADE + (200,))
    dn.ellipse([nx + 5, ny1 - 6, nx + 15, ny1 + 4], fill=SKIN_SHADE + (200,))
    nose = nose.filter(ImageFilter.GaussianBlur(1.2))
    face.alpha_composite(nose)
    d = ImageDraw.Draw(face)

    if character == "bansi":
        # red tilak mark, centred forehead
        tx, ty = HW / 2, HH * 0.20
        d.line([(tx, ty - 30), (tx, ty + 16)], fill=(190, 20, 30, 255), width=10)
        d.ellipse([tx - 7, ty - 40, tx + 7, ty - 26], fill=(190, 20, 30, 255))
    else:
        # bindi row across the forehead + a larger central bindi
        by = HH * 0.24
        for i in range(7):
            bx = HW * (0.30 + i * 0.40 / 6)
            d.ellipse([bx - 5, by - 5, bx + 5, by + 5], fill=(190, 20, 30, 255))
        d.ellipse([HW / 2 - 11, eye_y - 34 - 11, HW / 2 + 11, eye_y - 34 + 11],
                   fill=(200, 30, 40, 255), outline=(230, 190, 100, 255), width=3)

    mouth_y = int(HH * 0.62)
    mouth_tone = "bansi" if character == "bansi" else "phoolwati"
    mouth = make_mouth(mouth_state, tone=mouth_tone)
    mouth_pos = (int(HW / 2 - mouth.size[0] / 2), mouth_y)
    face.alpha_composite(mouth, mouth_pos)

    if character == "bansi":
        beard = _chin_beard(320, 280)
        face.alpha_composite(beard, (int(HW / 2 - 160), mouth_y + 30))
        must = _moustache(280, 130)
        face.alpha_composite(must, (int(HW / 2 - 140), mouth_y - 78))

    canvas.alpha_composite(face, (0, TOP))

    if character == "bansi":
        turb = _checker_turban(int(W * 0.94), int(H * 0.40), base=(190, 40, 34))
        canvas.alpha_composite(turb, (int(W * 0.03), int(TOP * 0.02)))
    else:
        veil = _jeweled_veil(int(W * 1.00), int(H * 0.42))
        canvas.alpha_composite(veil, (0, int(TOP * -0.02)))

    return canvas


if __name__ == "__main__":
    import os
    os.makedirs("assets", exist_ok=True)
    for ch in ("bansi", "phoolwati"):
        for ms in (0, 1, 2):
            img = build_head(ch, mouth_state=ms, blink=False)
            img.save(f"assets/{ch}_mouth{ms}.png")
        blink_img = build_head(ch, mouth_state=0, blink=True)
        blink_img.save(f"assets/{ch}_blink.png")
    print("done")
