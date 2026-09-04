"""Frame compositor + encoder. Puppet art is built once and cached at
module level so repeat jobs on the running server start rendering
immediately."""
import json
import math
import os
import random
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from .puppets import build_head
from .scene import (W, H, build_background, build_torso, build_arm, cutaway_card,
                    scene_card, draw_subtitle)
from .envelope import mouth_states_for_line, dance_track
from . import film as film_mod

HEAD_SCALE = 0.40
HEAD_W = int(900 * HEAD_SCALE)
HEAD_H = int(1150 * HEAD_SCALE)
TORSO_W = int(900 * HEAD_SCALE)
TORSO_H = int(460 * HEAD_SCALE)
ARM_W = int(170 * HEAD_SCALE)
ARM_H = int(400 * HEAD_SCALE)

ANCHOR = {
    "bansi": dict(cx=int(W * 0.315), ground_y=int(H * 0.90)),
    "phoolwati": dict(cx=int(W * 0.685), ground_y=int(H * 0.90)),
}

# how hard the puppets shake while the audience is going
LAUGH_SIZE = {
    "laugh_chuckle": 0.35,
    "laugh_medium": 0.65,
    "laugh_big": 1.0,
    "laugh_applause": 1.0,
}

_ASSETS = {}


def _assets():
    """Build (once) and return every static art asset."""
    if _ASSETS:
        return _ASSETS

    heads = {}
    for ch in ("bansi", "phoolwati"):
        for ms in (0, 1, 2):
            heads[(ch, ms, False)] = build_head(ch, mouth_state=ms, blink=False)
        heads[(ch, 0, True)] = build_head(ch, mouth_state=0, blink=True)

    torsos = {ch: build_torso(ch).resize((TORSO_W, TORSO_H), Image.LANCZOS)
              for ch in ("bansi", "phoolwati")}
    arms_r = {ch: build_arm(ch).resize((ARM_W, ARM_H), Image.LANCZOS)
              for ch in ("bansi", "phoolwati")}
    arms_l = {ch: ImageOps.mirror(img) for ch, img in arms_r.items()}

    _ASSETS.update(dict(
        heads=heads, torsos=torsos, arms_l=arms_l, arms_r=arms_r,
        bg=build_background(),
    ))
    return _ASSETS


def warm_up():
    """Pre-build art so the first job doesn't pay the cost mid-render."""
    _assets()


class _Blinker:
    def __init__(self, seed=42):
        self.rng = random.Random(seed)
        self.state = {"bansi": 0, "phoolwati": 0}

    def tick(self, ch, speaking):
        if self.state[ch] > 0:
            self.state[ch] -= 1
            return True
        if not speaking and self.rng.random() < 0.012:
            self.state[ch] = 2
            return True
        return False


def _compose_puppet(A, ch, mouth_state, blink, bob_phase, talk_amt, dim,
                    dx=0, dy=0, lean=0.0, swing_mult=1.0):
    key = (ch, mouth_state if not blink else 0, blink)
    head = A["heads"].get(key, A["heads"][(ch, mouth_state, False)])

    hw = int(HEAD_W * (1 + 0.01 * talk_amt))
    hh = int(HEAD_H * (1 + 0.01 * talk_amt))
    head_s = head.resize((hw, hh), Image.LANCZOS)
    angle = math.sin(bob_phase) * (2.2 + 3.0 * talk_amt) + lean
    head_s = head_s.rotate(angle, resample=Image.BICUBIC, expand=False)

    anchor = ANCHOR[ch]
    cx, ground_y = anchor["cx"], anchor["ground_y"]

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    torso_x = cx - TORSO_W // 2 + dx
    torso_y = ground_y - TORSO_H + dy

    swing = math.sin(bob_phase * 0.8 + 0.6) * (3 + 4 * talk_amt) * swing_mult
    shoulder_y = torso_y + int(TORSO_H * 0.04)
    arm_l_x = torso_x - int(ARM_W * 0.42)
    arm_r_x = torso_x + TORSO_W - int(ARM_W * 0.58)
    layer.alpha_composite(A["arms_l"][ch].rotate(-swing, resample=Image.BICUBIC, expand=False),
                          (arm_l_x, shoulder_y))
    layer.alpha_composite(A["arms_r"][ch].rotate(swing, resample=Image.BICUBIC, expand=False),
                          (arm_r_x, shoulder_y))
    layer.alpha_composite(A["torsos"][ch], (torso_x, torso_y))

    bob_y = int(math.sin(bob_phase) * (3 + 5 * talk_amt))
    head_x = cx - hw // 2 + dx
    head_y = torso_y - hh + int(TORSO_H * 0.22) + bob_y
    layer.alpha_composite(head_s, (head_x, head_y))

    if dim:
        rgb = layer.convert("RGB")
        rgb = ImageEnhance.Brightness(rgb).enhance(0.62)
        rgb = ImageEnhance.Color(rgb).enhance(0.7)
        layer = Image.merge("RGBA", (*rgb.split(), layer.split()[3]))

    anchors = dict(
        head_top=(head_x + hw / 2, head_y + hh * 0.06),
        hand_l=(arm_l_x + ARM_W * 0.5, shoulder_y + ARM_H * 0.86),
        hand_r=(arm_r_x + ARM_W * 0.5, shoulder_y + ARM_H * 0.86),
    )
    return layer, anchors


def _draw_strings(frame, anchors, cx):
    d = ImageDraw.Draw(frame)
    top_y = H * 0.045
    for (ax, ay), (tx, ty) in [
        (anchors["head_top"], (cx, top_y)),
        (anchors["hand_l"], (cx - 46, top_y + 14)),
        (anchors["hand_r"], (cx + 46, top_y + 14)),
    ]:
        d.line([(ax, ay), (tx, ty)], fill=(235, 230, 215, 160), width=2)
        d.ellipse([tx - 4, ty - 4, tx + 4, ty + 4], fill=(90, 62, 30, 230))


def _spotlight(cx, ground_y):
    from PIL import ImageFilter
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    r = 260
    d.ellipse([cx - r, ground_y - r * 1.5, cx + r, ground_y + r * 0.3], fill=(255, 225, 160, 70))
    return layer.filter(ImageFilter.GaussianBlur(50))


def _dance_frame(A, dance, fidx, t_sec, blinker):
    """Both puppets dancing to the opening song. The hop lands on the
    detected beat; sway, lean and arm swing scale with how loud the music
    is right now, so quiet bars settle and loud bars go big. The two
    puppets move a half-cycle apart so they play off each other."""
    e = float(dance["energy"][fidx])
    beat = float(dance["phase"][fidx])
    bounce = abs(math.sin(math.pi * beat))

    frame = A["bg"].copy().convert("RGBA")
    for ch in ("bansi", "phoolwati"):
        frame.alpha_composite(_spotlight(ANCHOR[ch]["cx"], ANCHOR[ch]["ground_y"]))

    for k, ch in enumerate(("bansi", "phoolwati")):
        off = 0.0 if k == 0 else math.pi
        sway = math.sin(t_sec * 2.2 + off)
        dx = int(sway * (18 + 26 * e))
        dy = int(-bounce * (14 + 34 * e))
        lean = sway * (6.0 + 8.0 * e)
        phase = t_sec * 3.0 + off
        blink = blinker.tick(ch, False)
        layer, anchors = _compose_puppet(
            A, ch, 0, blink, phase, 0.0, False,
            dx=dx, dy=dy, lean=lean, swing_mult=3.5 + 3.5 * e,
        )
        _draw_strings(frame, anchors, ANCHOR[ch]["cx"])
        frame.alpha_composite(layer)

    return frame.convert("RGB")


def render_video(job_dir, timeline, fps=24, upscale_1080=False, progress=None,
                 subtitles=True, film=None):
    def report(msg, pct=None):
        if progress:
            progress(msg, pct)

    A = _assets()

    film_state = None
    film_strength = float((film or {}).get("strength", 1.0))
    # at zero strength every stage is a no-op, so skip the pass entirely
    # rather than paying ~50ms a frame to round the image through float
    if film and film.get("enabled") and film_strength > 0:
        report("Preparing the film look…", 43)
        film_state = film_mod.prepare(W, H, strength=film_strength)

    segments = timeline["segments"]
    total_ms = timeline["total_ms"]
    total_frames = max(1, int(math.ceil(total_ms / 1000 * fps)))

    line_segs = [s for s in segments if s["type"] == "line"]
    cut_segs = [s for s in segments if s["type"] == "cutaway"]
    intro_segs = [s for s in segments if s["type"] == "intro"]
    laugh_segs = [s for s in segments if s["type"] == "laugh"]
    scene_segs = [s for s in segments if s["type"] == "scene"]

    outro_segs = [s for s in segments if s["type"] == "outro"]

    # the puppets dance to any music bed -- opening song and closing music
    # alike -- so each gets its own beat analysis
    dances = {}
    for kind, segs in (("intro", intro_segs), ("outro", outro_segs)):
        if not segs:
            continue
        report(f"Finding the beat in the {'opening' if kind == 'intro' else 'closing'} music…", 44)
        seg = segs[0]
        n_dance = max(1, int(round((seg["end_ms"] - seg["start_ms"]) / 1000 * fps)))
        dances[kind] = dance_track(
            os.path.join(job_dir, "audio", f"{kind}.wav"), fps, n_dance)

    report("Analyzing speech for mouth movement…", 45)
    envelopes = {}
    proc_dir = os.path.join(job_dir, "audio", "lines_proc")
    for s in line_segs:
        path = os.path.join(proc_dir, f"line{s['index']}.wav")
        n_frames = max(1, int(round((s["end_ms"] - s["start_ms"]) / 1000 * fps)))
        states, _ = mouth_states_for_line(path, fps, n_frames_hint=n_frames)
        envelopes[s["index"]] = states

    # chapter cards, built once each
    scene_imgs = {}
    for s in scene_segs:
        key = (s.get("title", ""), s.get("kicker", ""))
        if key not in scene_imgs:
            scene_imgs[key] = scene_card(*key)

    # cutaway cards, built once each
    cut_imgs = {}
    for s in cut_segs:
        key = (s.get("text", ""), s.get("subtext", ""), s.get("style", "reveal"))
        if key not in cut_imgs:
            cut_imgs[key] = cutaway_card(*key)

    blinker = _Blinker()

    out_dir = os.path.join(job_dir, "out")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "puppet_show.mp4")
    audio_path = os.path.join(job_dir, "audio", "full_mix.wav")

    vf = ["-vf", "scale=1920:1080:flags=lanczos"] if upscale_1080 else []
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-i", audio_path,
        *vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
        "-c:a", "aac", "-b:a", "160k", "-shortest", out_path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)

    report("Rendering animation frames…", 48)
    try:
        for i in range(total_frames):
            t_ms = i / fps * 1000

            active_line = None
            for s in line_segs:
                if s["start_ms"] <= t_ms < s["end_ms"]:
                    active_line = s
                    break
            active_cut = None
            for s in cut_segs:
                if s["start_ms"] <= t_ms < s["end_ms"]:
                    active_cut = s
                    break

            active_scene = None
            for s in scene_segs:
                if s["start_ms"] <= t_ms < s["end_ms"]:
                    active_scene = s
                    break

            active_music = None
            for kind, segs in (("intro", intro_segs), ("outro", outro_segs)):
                for s in segs:
                    if s["start_ms"] <= t_ms < s["end_ms"]:
                        active_music = (kind, s)
                        break
                if active_music:
                    break

            if active_scene is not None:
                frame = scene_imgs[(active_scene.get("title", ""),
                                    active_scene.get("kicker", ""))].copy()
            elif active_music is not None:
                kind, seg = active_music
                d = dances[kind]
                rel = t_ms - seg["start_ms"]
                fidx = min(len(d["energy"]) - 1, max(0, int(rel / 1000 * fps)))
                frame = _dance_frame(A, d, fidx, t_ms / 1000.0, blinker)
            elif active_cut is not None:
                key = (active_cut.get("text", ""), active_cut.get("subtext", ""),
                       active_cut.get("style", "reveal"))
                frame = cut_imgs[key].copy()
            else:
                frame = A["bg"].copy().convert("RGBA")
                speaking = {"bansi": False, "phoolwati": False}
                mouth = {"bansi": 0, "phoolwati": 0}
                talk = {"bansi": 0.0, "phoolwati": 0.0}

                if active_line is not None:
                    idx = active_line["index"]
                    rel = t_ms - active_line["start_ms"]
                    env = envelopes[idx]
                    fidx = min(len(env) - 1, max(0, int(rel / 1000 * fps)))
                    st = int(env[fidx])
                    spk = active_line["speaker"]
                    # a "Both:" line drives both mouths off the same envelope
                    for ch in (("bansi", "phoolwati") if spk == "both" else (spk,)):
                        speaking[ch] = True
                        mouth[ch] = st
                        talk[ch] = st / 2.0
                        frame.alpha_composite(_spotlight(ANCHOR[ch]["cx"], ANCHOR[ch]["ground_y"]))

                # nobody is dimmed while both are speaking
                active_speaker = active_line["speaker"] if active_line else None
                if active_speaker == "both":
                    active_speaker = None
                t_sec = t_ms / 1000.0

                # both puppets shake along while the audience laughs, easing
                # in and out so it doesn't switch on and off mid-frame
                laugh_amt = 0.0
                for s in laugh_segs:
                    if s["start_ms"] <= t_ms < s["end_ms"]:
                        span = max(1.0, s["end_ms"] - s["start_ms"])
                        rel = (t_ms - s["start_ms"]) / span
                        laugh_amt = (LAUGH_SIZE.get(s["name"], 0.6)
                                     * math.sin(math.pi * min(1.0, max(0.0, rel))))
                        break

                for ch in ("bansi", "phoolwati"):
                    blink = blinker.tick(ch, speaking[ch])
                    phase = t_sec * (2.6 if speaking[ch] else 0.9) + (0 if ch == "bansi" else 1.7)
                    dim = (active_speaker is not None) and (ch != active_speaker)
                    off = 0.0 if ch == "bansi" else 0.9
                    ldy = int(-abs(math.sin(t_sec * 9.0 + off)) * 11 * laugh_amt)
                    llean = math.sin(t_sec * 7.0 + off) * 4.5 * laugh_amt
                    layer, anchors = _compose_puppet(A, ch, mouth[ch], blink, phase, talk[ch], dim,
                                                     dy=ldy, lean=llean)
                    _draw_strings(frame, anchors, ANCHOR[ch]["cx"])
                    frame.alpha_composite(layer)

                frame = frame.convert("RGB")
                if subtitles and active_line is not None:
                    frame = draw_subtitle(frame, active_line["text"])

            arr = np.asarray(frame.convert("RGB"), dtype=np.uint8)
            if film_state is not None:
                arr = film_mod.apply_frame(arr, film_state, i)
            proc.stdin.write(arr.tobytes())

            if i % 24 == 0:
                pct = 48 + int(48 * i / total_frames)
                report(f"Rendering frame {i} of {total_frames}…", pct)
    finally:
        try:
            proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        proc.wait()

    if proc.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError("ffmpeg failed while encoding the video.")

    report("Finished.", 100)
    return out_path
