"""1970s Indian-village-film treatment.

Everything here is applied per rendered frame, on top of the clean
composite, to sell the idea that this show was shot on faded stock and
projected on a bedsheet in a village courtyard. The pieces, in the order
a real print would have acquired them:

  grade    faded Eastmancolor -- lifted (never black) blacks, warm
           amber highlights, cyan-ish shadows, low saturation
  halation the glow old stock blooms around bright areas
  weave    the whole frame drifting a pixel or two, as film does when
           the sprockets are worn
  grain    animated silver-halide noise
  dirt     dust specks and the occasional vertical scratch
  vignette corners falling off, as a cheap projector lens does
  flicker  frame-to-frame exposure wobble

Cost matters: this runs on every frame, so the tone curve is baked into
a lookup table once, the vignette and grain are precomputed, and the
halation pass works on a quarter-size image.
"""
import numpy as np
from PIL import Image, ImageFilter

_CACHE = {}

# how many distinct grain fields to cycle through -- enough that the eye
# never catches the loop, few enough to stay in memory
GRAIN_FIELDS = 12


def _tone_luts(strength):
    """Per-channel 256-entry curves: lift the blacks, roll the highlights
    off early (old stock never reached true white), and push the whole
    thing amber."""
    x = np.linspace(0, 1, 256, dtype=np.float32)
    luts = []
    # r, g, b: warm the highlights, cool the shadows slightly
    for lift, gain, gamma, tint in (
        (0.055, 0.98, 0.92, 1.045),   # red   -- strongest
        (0.048, 0.95, 0.96, 1.000),   # green -- reference
        (0.070, 0.88, 1.06, 0.945),   # blue  -- lifted but weak
    ):
        y = np.clip(x, 0, 1) ** gamma
        y = y * gain * tint + lift
        # shoulder: compress the top so highlights bloom instead of clip
        y = np.where(y > 0.75, 0.75 + (y - 0.75) * 0.55, y)
        y = x * (1 - strength) + y * strength
        luts.append(np.clip(y * 255.0, 0, 255).astype(np.uint8))
    return luts


def _vignette(w, h, strength):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2.0, h / 2.0
    r = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2) / 1.414
    v = 1.0 - strength * np.clip(r, 0, 1) ** 2.1
    return v.astype(np.float32)[..., None]


def _grain_fields(w, h, rng):
    """Grain is luminance noise, slightly blurred so it reads as silver
    grain rather than digital salt-and-pepper."""
    fields = []
    for _ in range(GRAIN_FIELDS):
        n = rng.normal(0, 1, (h // 2, w // 2)).astype(np.float32)
        img = Image.fromarray(np.clip(n * 40 + 128, 0, 255).astype(np.uint8))
        img = img.filter(ImageFilter.GaussianBlur(0.6)).resize((w, h), Image.BILINEAR)
        fields.append((np.asarray(img, dtype=np.float32) - 128.0)[..., None] / 128.0)
    return fields


def prepare(w, h, strength=1.0, seed=7):
    """Build (once) every lookup the per-frame pass needs."""
    key = (w, h, round(strength, 3), seed)
    if key in _CACHE:
        return _CACHE[key]
    rng = np.random.default_rng(seed)
    state = dict(
        luts=_tone_luts(strength),
        vignette=_vignette(w, h, 0.42 * strength),
        grain=_grain_fields(w, h, rng),
        rng=np.random.default_rng(seed + 1),
        strength=strength,
        w=w, h=h,
    )
    _CACHE[key] = state
    return state


_GLOW_TINT = np.array([1.0, 0.78, 0.5], dtype=np.float32)


def _halation(f, strength):
    """Bleed a warm glow out of the bright areas.

    The mask is built from a decimated copy rather than the full frame --
    the glow is heavily blurred anyway, so sampling every 4th pixel costs
    nothing visually and turns the most expensive stage into a cheap one.
    """
    h, w = f.shape[:2]
    small = f[::4, ::4]
    bright = np.clip((small.max(axis=2) - 0.62) * (1.0 / 0.38), 0, 1)
    img = Image.fromarray((bright * 255).astype(np.uint8))
    img = img.filter(ImageFilter.GaussianBlur(6)).resize((w, h), Image.BILINEAR)
    glow = np.asarray(img, dtype=np.float32)[..., None] * (_GLOW_TINT / 255.0)
    glow *= 0.32 * strength
    # screen blend, in place
    np.subtract(1.0, f, out=f)
    np.subtract(1.0, glow, out=glow)
    np.multiply(f, glow, out=f)
    np.subtract(1.0, f, out=f)
    return f


def apply_frame(rgb, state, frame_index):
    """Run one clean RGB frame (uint8 HxWx3) through the whole chain."""
    s = state["strength"]
    rng = state["rng"]

    # -- gate weave: the print drifting in the projector gate
    if s > 0:
        dx = int(round(np.sin(frame_index * 0.31) * 1.6 * s + rng.normal(0, 0.35) * s))
        dy = int(round(np.sin(frame_index * 0.17 + 1.1) * 1.2 * s + rng.normal(0, 0.3) * s))
        if dx or dy:
            rgb = np.roll(np.roll(rgb, dx, axis=1), dy, axis=0)

    # -- tone curve + warmth, straight out of the baked LUTs
    lut_r, lut_g, lut_b = state["luts"]
    graded = np.empty_like(rgb)
    graded[..., 0] = lut_r[rgb[..., 0]]
    graded[..., 1] = lut_g[rgb[..., 1]]
    graded[..., 2] = lut_b[rgb[..., 2]]

    f = graded.astype(np.float32)
    f *= 1.0 / 255.0

    # One luminance pass, reused twice below -- computing it per channel and
    # summing costs noticeably more than three scaled adds.
    lum = f[..., 0] * 0.299
    lum += f[..., 1] * 0.587
    lum += f[..., 2] * 0.114
    lum = lum[..., None]

    # -- desaturate: dye layers fade unevenly and the print goes muddy
    np.subtract(f, lum, out=f)
    np.multiply(f, 1.0 - 0.28 * s, out=f)
    np.add(f, lum, out=f)

    f = _halation(f, s)

    # -- grain, cycling through the precomputed fields. Weighted by the
    # luminance we already have: strongest in the midtones, barely there
    # in the blacks, which is how silver grain actually reads.
    grain = state["grain"][frame_index % GRAIN_FIELDS]
    weight = np.abs(lum - 0.5)
    np.multiply(weight, -1.3, out=weight)
    np.add(weight, 1.0, out=weight)
    f += grain * (0.055 * s) * weight

    # -- vignette and per-frame exposure flicker, folded into one multiply
    flicker = 1.0 + rng.normal(0, 0.011) * s
    np.multiply(f, state["vignette"], out=f)
    np.multiply(f, flicker, out=f)

    # -- dirt: a few dust specks most frames, a scratch now and then
    h, w = f.shape[:2]
    for _ in range(rng.poisson(2.2 * s)):
        y = rng.integers(0, h)
        x = rng.integers(0, w)
        r = int(rng.integers(1, 3))
        dark = rng.random() < 0.65
        f[max(0, y - r):y + r, max(0, x - r):x + r] = 0.06 if dark else 0.92
    if rng.random() < 0.10 * s:
        x = int(rng.integers(int(w * 0.05), int(w * 0.95)))
        y0 = int(rng.integers(0, h // 2))
        y1 = int(rng.integers(h // 2, h))
        f[y0:y1, x:x + 1] = np.clip(f[y0:y1, x:x + 1] * 1.5 + 0.12, 0, 1)

    return np.clip(f * 255.0, 0, 255).astype(np.uint8)
