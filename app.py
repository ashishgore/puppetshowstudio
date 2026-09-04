#!/usr/bin/env python3
"""
Puppet Show Studio -- a local web app that turns a script into an animated
Hindi puppet video with real ElevenLabs voices.

Run:
    python3 app.py
Then open http://127.0.0.1:5000 in your browser.
"""
import json
import os
import re
import shutil
import threading
import traceback
import uuid
from datetime import datetime

from flask import (Flask, jsonify, render_template, request,
                   send_file, send_from_directory)

from pipeline import audio as audio_mod
from pipeline import render as render_mod
from pipeline import voices as voices_mod

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.path.join(BASE_DIR, "jobs")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

os.makedirs(JOBS_DIR, exist_ok=True)

app = Flask(__name__)

JOBS = {}
JOBS_LOCK = threading.Lock()

CHARACTERS = [
    {"id": "bansi", "name": "Bansi", "blurb": "Stately village elder — checkered turban, big moustache"},
    {"id": "phoolwati", "name": "Phoolwati", "blurb": "Warm gossipy aunty — jeweled veil, bindi row"},
    # spoken by both puppets at once; borrows their two voices, has none of its own
    {"id": "both", "name": "Both together", "blurb": "Both puppets speak the line", "voice": False},
]

DEFAULT_CONFIG = {
    "api_key": "",
    "voice_ids": {"bansi": "", "phoolwati": ""},
    "model_id": voices_mod.DEFAULT_MODEL,
    "stability": 0.45,
    "similarity": 0.8,
    "style": 0.35,
    "intro": {"enabled": False, "path": "", "seconds": 13},
    # both cut from the intro's audio file; times are seconds into it
    "sting": {"enabled": True, "start": 22.0, "end": 24.0},
    "outro": {"enabled": True, "start": 185.0, "end": 202.0},
    "film": {"enabled": True, "strength": 0.85},
    "laugh_files": {},
}


# --------------------------------------------------------------------- config

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    cfg["voice_ids"] = dict(DEFAULT_CONFIG["voice_ids"])
    cfg["intro"] = dict(DEFAULT_CONFIG["intro"])
    cfg["film"] = dict(DEFAULT_CONFIG["film"])
    for k in ("sting", "outro"):
        cfg[k] = dict(DEFAULT_CONFIG[k])
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                saved = json.load(f)
            cfg.update({k: v for k, v in saved.items() if k not in ("voice_ids", "intro", "film", "sting", "outro")})
            cfg["voice_ids"].update(saved.get("voice_ids", {}))
            cfg["intro"].update(saved.get("intro", {}))
            cfg["film"].update(saved.get("film", {}))
            for k in ("sting", "outro"):
                cfg[k].update(saved.get(k, {}))
        except Exception:  # noqa: BLE001
            pass
    # env var wins if the file has no key (handy for people who prefer env vars)
    if not cfg.get("api_key"):
        cfg["api_key"] = os.environ.get("ELEVENLABS_API_KEY", "")
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ---------------------------------------------------------------- script parse

SPEAKER_ALIASES = {
    "bansi": "bansi", "b": "bansi",
    "phoolwati": "phoolwati", "phool": "phoolwati", "ph": "phoolwati",
    # the characters used to be called Pradhanji and Madhuri -- keep the old
    # names working so scripts written before the rename still parse
    "pradhanji": "bansi", "pradhan": "bansi", "ashish": "bansi", "p": "bansi",
    "madhuri": "phoolwati", "m": "phoolwati",
    # Devanagari speaker labels, for scripts written entirely in Hindi
    "बंसी": "bansi", "बंशी": "bansi",
    "फूलवती": "phoolwati", "फुलवती": "phoolwati",
}

DIRECTIVE_RE = re.compile(r"\[([a-zA-Z_]+)\s*:\s*([^\]]*)\]")


LAUGH_ALIASES = {
    "chuckle": "laugh_chuckle", "light": "laugh_chuckle", "small": "laugh_chuckle",
    "medium": "laugh_medium", "laugh": "laugh_medium", "audience": "laugh_medium",
    "big": "laugh_big", "huge": "laugh_big",
    "applause": "laugh_applause", "clap": "laugh_applause",
}
LAUGH_ALIASES.update({k: k for k in audio_mod.LAUGH_LABELS})


QUOTES = "\u201c\u201d\u2018\u2019\"'\u00ab\u00bb"

# A bracketed line on its own -- [BIG LAUGHTER], [MUSIC STING / APPLAUSE] --
# is a stage direction for the audience, not dialogue. It belongs to the line
# just spoken, so it is folded back onto it as that line's laughter.
STAGE_RE = re.compile(r"^\[([^\]]+)\]$")


def stage_to_laugh(inner):
    """Map a free-text stage direction onto one of the four laugh sizes."""
    t = inner.upper()
    if "APPLAUSE" in t or "CLAP" in t or "OVATION" in t:
        return "laugh_applause"
    if "BIG" in t or "HUGE" in t or "ROAR" in t:
        return "laugh_big"
    if "LIGHT" in t or "SMALL" in t or "CHUCKLE" in t or "TITTER" in t:
        return "laugh_chuckle"
    if "LAUGH" in t:
        return "laugh_medium"
    return None


BOTH_WORDS = ("both", "dono", "together", "sab", "\u0926\u094b\u0928\u094b\u0902", "\u0926\u094b\u0928\u094b")

# split a speaker label into bare words, dropping punctuation, so
# "Phoolwati, imitating Abhay" and "Bansi & Phoolwati together" both tokenize
TOKEN_RE = re.compile(r"[^\w\u0900-\u097f]+")


def split_heading(raw):
    """'Scene 1 - Tikki Group & Memory' -> ('Tikki Group & Memory', 'Scene 1').

    The part before the dash becomes the small kicker line, the part after
    it the large title. A heading with no separator is all title.
    """
    t = raw.strip()
    for sep in ("\u2014", "\u2013", " - ", ":"):
        if sep in t:
            before, after = t.split(sep, 1)
            if before.strip() and after.strip():
                return after.strip(), before.strip()
    return t, ""


def resolve_speaker(head):
    """Resolve a speaker label to a character id.

    Handles 'Bansi', 'Both', 'Phoolwati, imitating Abhay' (punctuation and
    trailing stage business ignored) and 'Bansi & Phoolwati together' (two
    distinct characters named -> they speak it together).
    """
    key = head.strip().lower().strip(":").strip()
    if not key or len(key) > 60:
        return None
    if key in SPEAKER_ALIASES:
        return SPEAKER_ALIASES[key]

    words = [w for w in TOKEN_RE.split(key) if w]
    if any(w in BOTH_WORDS for w in words):
        return "both"

    # names that are actually ours -- someone the script only imitates
    # (Abhay, Neha) is not a speaker and must not count
    found = []
    for w in words:
        who = SPEAKER_ALIASES.get(w)
        if who and who not in found:
            found.append(who)
    if len(found) > 1:
        return "both"
    return found[0] if found else None


def unquote(text):
    """Strip only *matched* outer quote pairs, so quotes nested inside the
    line (a character quoting someone else) survive intact."""
    t = text.strip()
    while len(t) >= 2 and t[0] in QUOTES and t[-1] in QUOTES:
        t = t[1:-1].strip()
    return t


def parse_script(raw):
    """Parse a script into structured lines.

    Two layouts are accepted and may be mixed freely:

        Bansi: text [sfx:rimshot] [pause:0.5]      speaker and line together
        Bansi:                                     speaker on its own line,
        "text"                                     dialogue on the next

    Dialogue may be wrapped in straight or curly quotes. A bracketed line on
    its own is treated as an audience direction and attached to the previous
    line rather than becoming dialogue of its own.
    """
    lines = []
    pending_speaker = None
    pending_scene = None

    for raw_line in (raw or "").splitlines():
        s = raw_line.strip()
        if not s or s.startswith("#"):
            continue

        # audience direction -> laughter on the line just spoken
        m = STAGE_RE.match(s)
        if m:
            laugh = stage_to_laugh(m.group(1))
            if laugh and lines:
                lines[-1]["laugh"] = laugh
                lines[-1]["hold_before"] = lines[-1].get("hold_before")
            continue

        # A line arriving when no speaker is pending, carrying no label and no
        # opening quote, is structural -- a scene heading or act break. It is
        # not spoken; it becomes a chapter card in front of the next line.
        if pending_speaker is None and ":" not in s and s[0] not in QUOTES:
            pending_scene = split_heading(s)
            continue

        speaker = None
        if ":" in s:
            head, rest = s.split(":", 1)
            found = resolve_speaker(head)
            if found:
                speaker = found
                s = rest.strip()
                if not s:
                    # bare "Bansi:" -- the dialogue is on the following line
                    pending_speaker = speaker
                    continue

        if speaker is None:
            speaker = pending_speaker or (lines[-1]["speaker"] if lines else "bansi")
        pending_speaker = None

        directives = {}
        for m in DIRECTIVE_RE.finditer(s):
            directives[m.group(1).lower()] = m.group(2).strip()
        text = unquote(DIRECTIVE_RE.sub("", s))
        if not text:
            continue

        try:
            pause = float(directives.get("pause", 0.25))
        except ValueError:
            pause = 0.25

        laugh = LAUGH_ALIASES.get(directives.get("laugh", "").lower(), "")

        hold = None
        if "hold" in directives:
            try:
                hold = max(0.0, float(directives["hold"]))
            except ValueError:
                hold = None

        scene_title, scene_kicker = pending_scene or ("", "")
        pending_scene = None

        lines.append({
            "speaker": speaker,
            "text": text,
            "scene_title": scene_title,
            "scene_kicker": scene_kicker,
            "sfx_before": directives.get("sfx_before", ""),
            "sfx_after": directives.get("sfx", directives.get("sfx_after", "")),
            "pause_after": pause,
            "laugh": laugh,
            "hold_before": hold,
            "cutaway_text": directives.get("cutaway", ""),
            "cutaway_subtext": directives.get("cutaway_sub", ""),
            "cutaway_style": directives.get("cutaway_style", "reveal"),
        })
    return lines


# ------------------------------------------------------------------- job model

def new_job():
    job_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    job = {
        "id": job_id,
        "status": "queued",
        "pct": 0,
        "message": "Queued…",
        "log": [],
        "error": None,
        "video": None,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
    return job


def job_progress(job, message, pct=None):
    with JOBS_LOCK:
        job["message"] = message
        if pct is not None:
            job["pct"] = max(job["pct"], min(100, int(pct)))
        job["log"].append(message)
        job["log"] = job["log"][-200:]


def run_job(job, lines, settings, options):
    job_dir = os.path.join(JOBS_DIR, job["id"])
    os.makedirs(job_dir, exist_ok=True)
    try:
        with JOBS_LOCK:
            job["status"] = "running"

        job_progress(job, "Starting…", 2)
        timeline = audio_mod.build_audio(
            job_dir, lines, settings,
            progress=lambda m, p=None: job_progress(job, m, p),
            offline=options.get("offline", False),
        )
        video = render_mod.render_video(
            job_dir, timeline,
            fps=int(options.get("fps", 24)),
            upscale_1080=bool(options.get("upscale_1080", False)),
            subtitles=bool(options.get("subtitles", True)),
            film=settings.get("film"),
            progress=lambda m, p=None: job_progress(job, m, p),
        )
        with JOBS_LOCK:
            job["video"] = video
            job["status"] = "done"
            job["pct"] = 100
            job["message"] = "Done — your video is ready."
    except Exception as e:  # noqa: BLE001
        with JOBS_LOCK:
            job["status"] = "error"
            job["error"] = str(e)
            job["message"] = f"Failed: {e}"
            job["log"].append(traceback.format_exc()[-1500:])


# ---------------------------------------------------------------------- routes

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config", methods=["GET"])
def api_get_config():
    cfg = load_config()
    return jsonify({
        "api_key_set": bool(cfg.get("api_key")),
        "api_key_hint": (cfg["api_key"][:4] + "…" + cfg["api_key"][-4:]) if cfg.get("api_key") else "",
        "voice_ids": cfg.get("voice_ids", {}),
        "model_id": cfg.get("model_id"),
        "stability": cfg.get("stability"),
        "similarity": cfg.get("similarity"),
        "style": cfg.get("style"),
        "intro": cfg.get("intro", {}),
        "film": cfg.get("film", {}),
        "sting": cfg.get("sting", {}),
        "outro": cfg.get("outro", {}),
        "characters": CHARACTERS,
        "sfx": [{"id": k, "label": v} for k, v in audio_mod.SFX_LABELS.items()],
        "laughs": [{"id": k, "label": v, "hold": audio_mod.AUTO_HOLD.get(k, 0.0)}
                   for k, v in audio_mod.LAUGH_LABELS.items()],
    })


@app.route("/api/config", methods=["POST"])
def api_save_config():
    body = request.get_json(force=True) or {}
    cfg = load_config()
    if body.get("api_key"):
        cfg["api_key"] = body["api_key"].strip()
    if body.get("clear_api_key"):
        cfg["api_key"] = ""
    if "voice_ids" in body:
        cfg["voice_ids"].update({k: (v or "").strip() for k, v in body["voice_ids"].items()})
    if "intro" in body:
        intro = body["intro"] or {}
        if "path" in intro:
            cfg["intro"]["path"] = (intro["path"] or "").strip()
        if "enabled" in intro:
            cfg["intro"]["enabled"] = bool(intro["enabled"])
        if intro.get("seconds") not in (None, ""):
            cfg["intro"]["seconds"] = max(1.0, min(60.0, float(intro["seconds"])))
    if "laugh_files" in body:
        cfg.setdefault("laugh_files", {}).update(
            {k: (v or "").strip() for k, v in (body["laugh_files"] or {}).items()})
    for blk in ("sting", "outro"):
        if blk in body:
            v = body[blk] or {}
            if "enabled" in v:
                cfg[blk]["enabled"] = bool(v["enabled"])
            for f in ("start", "end"):
                if v.get(f) not in (None, ""):
                    cfg[blk][f] = max(0.0, float(v[f]))
    if "film" in body:
        fl = body["film"] or {}
        if "enabled" in fl:
            cfg["film"]["enabled"] = bool(fl["enabled"])
        if fl.get("strength") not in (None, ""):
            cfg["film"]["strength"] = max(0.0, min(1.0, float(fl["strength"])))
    for k in ("model_id", "stability", "similarity", "style"):
        if k in body and body[k] not in (None, ""):
            cfg[k] = body[k]
    save_config(cfg)
    return jsonify({"ok": True})


@app.route("/api/voices", methods=["GET"])
def api_voices():
    cfg = load_config()
    try:
        return jsonify({"ok": True, "voices": voices_mod.list_voices(cfg.get("api_key"))})
    except voices_mod.VoiceError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/parse", methods=["POST"])
def api_parse():
    body = request.get_json(force=True) or {}
    return jsonify({"ok": True, "lines": parse_script(body.get("script", ""))})


@app.route("/api/generate", methods=["POST"])
def api_generate():
    body = request.get_json(force=True) or {}
    lines = body.get("lines") or parse_script(body.get("script", ""))
    lines = [l for l in lines if (l.get("text") or "").strip()]
    if not lines:
        return jsonify({"ok": False, "error": "The script is empty."}), 400

    options = body.get("options") or {}
    cfg = load_config()

    if not options.get("offline"):
        if not cfg.get("api_key"):
            return jsonify({"ok": False, "error": "No ElevenLabs API key saved. Add one in Settings, "
                                                  "or tick Preview mode to test without API calls."}), 400
        needed = set()
        for l in lines:
            needed.update(audio_mod.BOTH_SPEAKERS if l["speaker"] == "both" else [l["speaker"]])
        missing = [c for c in needed if not cfg["voice_ids"].get(c)]
        if missing:
            names = ", ".join(c.title() for c in missing)
            return jsonify({"ok": False, "error": f"No voice selected for: {names}."}), 400

    intro = cfg.get("intro") or {}
    if intro.get("enabled"):
        if not intro.get("path"):
            return jsonify({"ok": False, "error": "Opening song is switched on but no file is set."}), 400
        if not os.path.exists(intro["path"]):
            return jsonify({"ok": False, "error": f"Opening song file not found: {intro['path']}"}), 400

    job = new_job()
    t = threading.Thread(target=run_job, args=(job, lines, cfg, options), daemon=True)
    t.start()
    return jsonify({"ok": True, "job_id": job["id"]})


@app.route("/api/status/<job_id>")
def api_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"ok": False, "error": "Unknown job."}), 404
        return jsonify({
            "ok": True,
            "status": job["status"],
            "pct": job["pct"],
            "message": job["message"],
            "log": job["log"][-12:],
            "error": job["error"],
            "has_video": bool(job["video"]),
        })


@app.route("/api/video/<job_id>")
def api_video(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or not job.get("video"):
        return jsonify({"ok": False, "error": "No video for that job."}), 404
    return send_file(job["video"], mimetype="video/mp4", conditional=True)


@app.route("/api/download/<job_id>")
def api_download(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or not job.get("video"):
        return jsonify({"ok": False, "error": "No video for that job."}), 404
    return send_file(job["video"], mimetype="video/mp4", as_attachment=True,
                     download_name=f"puppet_show_{job_id}.mp4")


@app.route("/api/jobs")
def api_jobs():
    with JOBS_LOCK:
        items = [{"id": j["id"], "status": j["status"], "created": j["created"],
                  "has_video": bool(j["video"])}
                 for j in sorted(JOBS.values(), key=lambda x: x["created"], reverse=True)]
    return jsonify({"ok": True, "jobs": items[:20]})


@app.route("/api/health")
def api_health():
    return jsonify({
        "ok": True,
        "ffmpeg": shutil.which("ffmpeg") is not None,
    })


# Port 5000 is not safe to use on macOS: the AirPlay Receiver in Control
# Centre binds *:5000 on both IPv4 and IPv6. Flask can still take the IPv4
# loopback, but a browser resolving "localhost" hits ::1 first, lands on
# AirPlay instead, and shows a 403 "access denied" that looks like our bug.
DEFAULT_PORT = 5050


def main():
    if shutil.which("ffmpeg") is None:
        print("\n!! ffmpeg was not found on your PATH.")
        print("   macOS:  brew install ffmpeg")
        print("   Ubuntu: sudo apt install ffmpeg")
        print("   Windows: https://ffmpeg.org/download.html\n")

    port = int(os.environ.get("PUPPETSHOW_PORT", DEFAULT_PORT))

    print("Warming up puppet art…")
    render_mod.warm_up()
    print(f"\n  Puppet Show Studio is running:  http://127.0.0.1:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
