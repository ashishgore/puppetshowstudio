"""Builds the narration + reaction pauses + SFX into one mix, and emits a
millisecond-accurate timeline the renderer uses to drive mouth movement,
subtitles and cutaways."""
import json
import os
import shutil
import subprocess

from pydub import AudioSegment

from . import sfx as sfx_mod
from . import voices as voices_mod

# the two puppets that a "Both:" line is split across
BOTH_SPEAKERS = ("bansi", "phoolwati")

# how long a scene/chapter card holds on screen, whoosh included
SCENE_CARD_MS = 2200

SFX_BUILDERS = {
    "dholak_hit": lambda: sfx_mod.dholak_hit(),
    "tadaa": lambda: sfx_mod.tadaa_chime(),
    "dun_dun_duun": lambda: sfx_mod.dun_dun_duun(),
    "rimshot": lambda: sfx_mod.rimshot_tss(),
    "whoosh": lambda: sfx_mod.whoosh(),
}

LAUGH_BUILDERS = {
    "laugh_chuckle": lambda: sfx_mod.laugh_chuckle(),
    "laugh_medium": lambda: sfx_mod.laugh_medium(),
    "laugh_big": lambda: sfx_mod.laugh_big(),
    "laugh_applause": lambda: sfx_mod.laugh_applause(),
}

LAUGH_LABELS = {
    "laugh_chuckle": "Light chuckle",
    "laugh_medium": "Audience laugh",
    "laugh_big": "Big laugh",
    "laugh_applause": "Big laugh + applause",
}

# The beat of silence before a punchline does more work than the laugh
# after it -- it tells the room something is coming. Bigger the laugh you
# are going for, longer you hold. These are defaults only: an explicit
# [hold:...] on the line always wins, including [hold:0] to kill it.
AUTO_HOLD = {
    "laugh_big": 1.0,
    "laugh_applause": 1.0,
    "laugh_medium": 0.5,
    "laugh_chuckle": 0.2,
}

SFX_LABELS = {
    "dholak_hit": "Dholak hit (scene opener)",
    "tadaa": "Ta-daa chime (reveal)",
    "dun_dun_duun": "Dun-dun-duun (suspense)",
    "rimshot": "Ba-dum-tss (punchline)",
    "whoosh": "Whoosh (transition)",
}


# Recorded laughter beats anything synthesized, so real files win when they
# are present. Levels are matched per slot rather than across the board --
# normalizing all four to one loudness would flatten the whole point of
# having four sizes.
LAUGH_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               os.pardir, "assets", "laughs")

LAUGH_LUFS = {
    "laugh_chuckle": -26,
    "laugh_medium": -21,
    "laugh_big": -18,
    "laugh_applause": -17,
}


def import_laugh(src, dest, lufs=-20):
    """Bring an arbitrary audio file into the pipeline's format: mono
    44.1k, topped and tailed so it cannot click, levelled for its slot."""
    af = ("afade=t=in:st=0:d=0.01,areverse,afade=t=in:st=0:d=0.15,areverse,"
          f"loudnorm=I={lufs}:TP=-2:LRA=9")
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-af", af,
         "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", dest],
        check=True, capture_output=True,
    )
    return dest


def _resolve_laugh(name, laugh_files):
    """Where this laugh should come from, best source first: a file the
    user pointed at, then the bundled asset, then synthesis."""
    custom = (laugh_files or {}).get(name) or ""
    if custom and os.path.exists(custom):
        return custom, True
    asset = os.path.join(LAUGH_ASSET_DIR, f"{name}.wav")
    if os.path.exists(asset):
        return asset, False
    return None, False


def ensure_sfx(sfx_dir, laugh_files=None):
    os.makedirs(sfx_dir, exist_ok=True)
    for name, builder in SFX_BUILDERS.items():
        path = os.path.join(sfx_dir, f"{name}.wav")
        if not os.path.exists(path):
            sfx_mod.write_wav(path, builder())

    for name, builder in LAUGH_BUILDERS.items():
        path = os.path.join(sfx_dir, f"{name}.wav")
        if os.path.exists(path):
            continue
        src, needs_import = _resolve_laugh(name, laugh_files)
        if src is None:
            sfx_mod.write_wav(path, builder())          # synthesized fallback
        elif needs_import:
            import_laugh(src, path, LAUGH_LUFS.get(name, -20))
        else:
            shutil.copyfile(src, path)                  # already in our format


def music_cut(path, start, dur, out_wav, lufs=-16, fade_in=0.4, fade_out=1.0):
    """Cut `dur` seconds out of an audio file starting at `start`, faded at
    both ends so it never pops in or stops mid-bar, levelled for its slot."""
    fade_out = min(fade_out, dur / 3.0)
    af = (f"afade=t=in:st=0:d={fade_in:.2f},"
          f"afade=t=out:st={max(0.0, dur - fade_out):.2f}:d={fade_out:.2f},"
          f"loudnorm=I={lufs}:TP=-2:LRA=9")
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", path,
         "-af", af, "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", out_wav],
        check=True, capture_output=True,
    )
    return out_wav


def build_intro(job_dir, intro_cfg):
    """Trim the opening seconds of a user-supplied music file into the
    intro bed: mono 44.1k, faded at both ends so it neither pops in nor
    cuts off mid-bar, and levelled a touch louder than the narration."""
    path = (intro_cfg.get("path") or "").strip()
    seconds = float(intro_cfg.get("seconds") or 13)
    if not path or not os.path.exists(path):
        raise ValueError(f"Intro song file not found: {path}")

    audio_dir = os.path.join(job_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    out_wav = os.path.join(audio_dir, "intro.wav")

    fade = min(1.5, seconds / 4.0)
    af = (f"afade=t=in:st=0:d=0.4,"
          f"afade=t=out:st={max(0.0, seconds - fade):.2f}:d={fade:.2f},"
          "loudnorm=I=-16:TP=-2:LRA=9")
    subprocess.run(
        ["ffmpeg", "-y", "-ss", "0", "-t", f"{seconds:.3f}", "-i", path,
         "-af", af, "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", out_wav],
        check=True, capture_output=True,
    )
    return out_wav


def _process_line(raw_mp3, proc_wav):
    """Format-convert and level-match. Real voices need no de-robotifying,
    just consistent loudness so no line jumps out."""
    af = ("acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120,"
          "loudnorm=I=-18:TP=-2:LRA=7")
    subprocess.run(
        ["ffmpeg", "-y", "-i", raw_mp3, "-af", af,
         "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", proc_wav],
        check=True, capture_output=True,
    )


def _period_sound(mix, job_dir, strength=1.0):
    """Age the finished mix. First the village settles in underneath,
    then the whole thing is squeezed into the band an optical soundtrack
    actually carried and pushed through a courtyard horn speaker: no deep
    bass, no air on top, a little distortion, a short hard reflection."""
    audio_dir = os.path.join(job_dir, "audio")
    dur = len(mix) / 1000.0

    amb_path = os.path.join(audio_dir, "ambience.wav")
    sfx_mod.write_wav(amb_path, sfx_mod.village_ambience(dur))
    bed = AudioSegment.from_wav(amb_path) - (28 - 6 * strength)
    mixed = mix.overlay(bed)

    raw = os.path.join(audio_dir, "pre_film.wav")
    mixed.export(raw, format="wav")

    out = os.path.join(audio_dir, "full_mix.wav")
    lo = 150 + int(40 * strength)     # roll the bass off
    hi = 7000 - int(1800 * strength)  # and the air
    af = (
        f"highpass=f={lo},lowpass=f={hi},"
        "acompressor=threshold=-18dB:ratio=3:attack=10:release=200,"
        f"asoftclip=type=atan:param={0.15 + 0.25 * strength:.2f},"
        f"aecho=0.9:0.85:{18 + int(10 * strength)}:{0.10 * strength:.2f},"
        "loudnorm=I=-17:TP=-2:LRA=8"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", raw, "-af", af,
         "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", out],
        check=True, capture_output=True,
    )
    return out


def build_audio(job_dir, lines, settings, progress=None, offline=False):
    """lines: [{speaker, text, sfx_before, sfx_after, pause_after,
               cutaway_text, cutaway_subtext, cutaway_style}]
    Returns the timeline dict (also written to <job_dir>/audio/timeline.json).
    """
    def report(msg, pct=None):
        if progress:
            progress(msg, pct)

    audio_dir = os.path.join(job_dir, "audio")
    raw_dir = os.path.join(audio_dir, "lines_raw")
    proc_dir = os.path.join(audio_dir, "lines_proc")
    sfx_dir = os.path.join(audio_dir, "sfx")
    for d in (audio_dir, raw_dir, proc_dir, sfx_dir):
        os.makedirs(d, exist_ok=True)

    ensure_sfx(sfx_dir, settings.get("laugh_files"))

    api_key = settings.get("api_key", "")
    voice_ids = settings.get("voice_ids", {})
    model_id = settings.get("model_id") or voices_mod.DEFAULT_MODEL

    timeline = []
    cursor = 0
    mix = AudioSegment.silent(duration=0)

    intro_cfg = settings.get("intro") or {}
    if intro_cfg.get("enabled") and intro_cfg.get("path"):
        report("Preparing the opening song…", 3)
        intro_seg = AudioSegment.from_wav(build_intro(job_dir, intro_cfg))
        mix += intro_seg
        timeline.append(dict(type="intro", start_ms=0, end_ms=len(intro_seg)))
        cursor += len(intro_seg)
        # a beat of quiet so the song doesn't collide with the first line
        settle = AudioSegment.silent(duration=300)
        mix += settle
        cursor += len(settle)

    lead_in = AudioSegment.silent(duration=150)
    mix += lead_in
    cursor += len(lead_in)

    # the scene-transition sting, cut once and reused for every card
    sting_wav = None
    sting_cfg = settings.get("sting") or {}
    music_path = (intro_cfg.get("path") or "").strip()
    if sting_cfg.get("enabled") and music_path and os.path.exists(music_path):
        st = float(sting_cfg.get("start", 0))
        en = float(sting_cfg.get("end", st + 2))
        if en > st:
            sting_wav = music_cut(music_path, st, en - st,
                                  os.path.join(audio_dir, "sting.wav"),
                                  lufs=-17, fade_in=0.12, fade_out=0.5)

    n = len(lines)
    for i, line in enumerate(lines):
        speaker = line.get("speaker", "bansi")
        text = (line.get("text") or "").strip()
        if not text:
            continue

        report(f"Generating voice line {i+1} of {n} ({speaker})…", 5 + int(35 * i / max(1, n)))

        # a scene card comes first of all -- it is the transition into this
        # line, so it precedes even the punchline hold
        scene_title = (line.get("scene_title") or "").strip()
        if scene_title:
            card_start = cursor
            if sting_wav:
                # a musical sting carries the transition; the card holds for
                # exactly as long as the sting runs
                bed = AudioSegment.from_wav(sting_wav)
                mix += bed
                cursor += len(bed)
            else:
                whoosh = AudioSegment.from_wav(os.path.join(sfx_dir, "whoosh.wav"))
                mix += whoosh
                cursor += len(whoosh)
                rest = SCENE_CARD_MS - len(whoosh)
                if rest > 0:
                    mix += AudioSegment.silent(duration=rest)
                    cursor += rest
            timeline.append(dict(
                type="scene", title=scene_title,
                kicker=(line.get("scene_kicker") or "").strip(),
                start_ms=card_start, end_ms=cursor,
            ))

        # the held beat before a punchline, ahead of everything else on this line
        laugh = (line.get("laugh") or "").strip()
        hold = line.get("hold_before")
        if hold in (None, ""):
            hold = AUTO_HOLD.get(laugh, 0.0)
        hold_ms = int(max(0.0, float(hold)) * 1000)
        if hold_ms > 0:
            mix += AudioSegment.silent(duration=hold_ms)
            timeline.append(dict(type="hold", start_ms=cursor, end_ms=cursor + hold_ms))
            cursor += hold_ms

        raw_mp3 = os.path.join(raw_dir, f"line{i}.mp3")
        proc_wav = os.path.join(proc_dir, f"line{i}.wav")

        tts_kw = dict(
            model_id=model_id,
            stability=float(settings.get("stability", 0.45)),
            similarity=float(settings.get("similarity", 0.8)),
            style=float(settings.get("style", 0.35)),
        )
        if offline:
            voices_mod.offline_tts_to_file(text, raw_mp3, character=speaker)
        elif speaker == "both":
            # a chorus line: say it in each character's own voice and stack
            # them, which reads as two puppets together rather than one
            stacked = None
            for ch in BOTH_SPEAKERS:
                part = os.path.join(raw_dir, f"line{i}_{ch}.mp3")
                voices_mod.tts_to_file(api_key, voice_ids.get(ch), text, part, **tts_kw)
                seg = AudioSegment.from_file(part)
                stacked = seg if stacked is None else stacked.overlay(seg)
            stacked.export(raw_mp3, format="mp3")
        else:
            voices_mod.tts_to_file(api_key, voice_ids.get(speaker), text, raw_mp3, **tts_kw)
        _process_line(raw_mp3, proc_wav)
        seg = AudioSegment.from_wav(proc_wav)

        if line.get("sfx_before"):
            s = AudioSegment.from_wav(os.path.join(sfx_dir, f"{line['sfx_before']}.wav"))
            start = cursor
            mix += s
            cursor += len(s)
            timeline.append(dict(type="sfx", name=line["sfx_before"], start_ms=start, end_ms=cursor))
            gap = AudioSegment.silent(duration=120)
            mix += gap
            cursor += len(gap)

        start = cursor
        mix += seg
        cursor += len(seg)
        line_end = cursor
        timeline.append(dict(
            type="line", index=i, speaker=speaker,
            start_ms=start, end_ms=line_end, text=text,
        ))

        cutaway_start = None
        if line.get("sfx_after"):
            gap = AudioSegment.silent(duration=100)
            mix += gap
            cursor += len(gap)
            cutaway_start = cursor
            s = AudioSegment.from_wav(os.path.join(sfx_dir, f"{line['sfx_after']}.wav"))
            start_sfx = cursor
            mix += s
            cursor += len(s)
            timeline.append(dict(type="sfx", name=line["sfx_after"], start_ms=start_sfx, end_ms=cursor))

        if laugh in LAUGH_BUILDERS:
            gap = AudioSegment.silent(duration=80)   # land on the tail of the line
            mix += gap
            cursor += len(gap)
            lg = AudioSegment.from_wav(os.path.join(sfx_dir, f"{laugh}.wav"))
            start_lg = cursor
            mix += lg
            cursor += len(lg)
            timeline.append(dict(type="laugh", name=laugh, start_ms=start_lg, end_ms=cursor))
            if cutaway_start is None:
                cutaway_start = start_lg

        pause_ms = int(float(line.get("pause_after") or 0.2) * 1000)
        if pause_ms > 0:
            gap = AudioSegment.silent(duration=pause_ms)
            mix += gap
            cursor += pause_ms
            timeline.append(dict(type="pause", start_ms=cursor - pause_ms, end_ms=cursor))

        cutaway_text = (line.get("cutaway_text") or "").strip()
        if cutaway_text:
            timeline.append(dict(
                type="cutaway",
                text=cutaway_text,
                subtext=(line.get("cutaway_subtext") or "").strip(),
                style=line.get("cutaway_style") or "reveal",
                start_ms=cutaway_start if cutaway_start is not None else line_end,
                end_ms=cursor,
            ))

    if cursor == 0:
        raise ValueError("No usable script lines were provided.")

    outro_cfg = settings.get("outro") or {}
    if outro_cfg.get("enabled") and music_path and os.path.exists(music_path):
        st = float(outro_cfg.get("start", 0))
        en = float(outro_cfg.get("end", st + 10))
        if en > st:
            report("Cutting the closing music…", 39)
            gap = AudioSegment.silent(duration=400)
            mix += gap
            cursor += len(gap)
            outro_wav = music_cut(music_path, st, en - st,
                                  os.path.join(audio_dir, "outro.wav"),
                                  lufs=-16, fade_in=0.5, fade_out=2.0)
            seg = AudioSegment.from_wav(outro_wav)
            start_o = cursor
            mix += seg
            cursor += len(seg)
            timeline.append(dict(type="outro", start_ms=start_o, end_ms=cursor))

    tail = AudioSegment.silent(duration=250)
    mix += tail
    cursor += len(tail)

    mix = mix.set_frame_rate(44100).set_channels(1)

    film_cfg = settings.get("film") or {}
    if film_cfg.get("enabled"):
        report("Aging the soundtrack…", 40)
        _period_sound(mix, job_dir, float(film_cfg.get("strength", 1.0)))
    else:
        mix.export(os.path.join(audio_dir, "full_mix.wav"), format="wav")

    data = dict(total_ms=cursor, segments=timeline)
    with open(os.path.join(audio_dir, "timeline.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    report(f"Narration assembled ({cursor/1000:.1f}s).", 42)
    return data
