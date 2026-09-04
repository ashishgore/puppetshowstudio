"""ElevenLabs client (stdlib only -- no extra pip dependency) plus an
offline fallback so the app can be tested without spending API credits."""
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request

BASE = "https://api.elevenlabs.io/v1"
DEFAULT_MODEL = "eleven_multilingual_v2"


class VoiceError(Exception):
    pass


def list_voices(api_key):
    if not api_key:
        raise VoiceError("No ElevenLabs API key set.")
    req = urllib.request.Request(f"{BASE}/voices", headers={"xi-api-key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        if e.code in (401, 403):
            raise VoiceError("ElevenLabs rejected the API key (401/403). Check the key.") from e
        raise VoiceError(f"ElevenLabs error {e.code}: {detail}") from e
    except Exception as e:  # noqa: BLE001
        raise VoiceError(f"Could not reach ElevenLabs: {e}") from e

    out = []
    for v in data.get("voices", []):
        labels = v.get("labels", {}) or {}
        out.append({
            "voice_id": v.get("voice_id"),
            "name": v.get("name"),
            "gender": labels.get("gender", ""),
            "age": labels.get("age", ""),
            "accent": labels.get("accent", ""),
            "description": labels.get("description", ""),
        })
    return out


def tts_to_file(api_key, voice_id, text, out_mp3, model_id=DEFAULT_MODEL,
                stability=0.45, similarity=0.8, style=0.35, retries=2):
    if not api_key:
        raise VoiceError("No ElevenLabs API key set.")
    if not voice_id:
        raise VoiceError("No voice ID set for this character.")

    body = json.dumps({
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity,
            "style": style,
        },
    }).encode("utf-8")

    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            f"{BASE}/text-to-speech/{voice_id}",
            data=body,
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                audio = resp.read()
            if not audio:
                raise VoiceError("ElevenLabs returned an empty audio response.")
            with open(out_mp3, "wb") as f:
                f.write(audio)
            return out_mp3
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code in (401, 403):
                raise VoiceError("ElevenLabs rejected the API key (401/403).") from e
            if e.code == 422:
                raise VoiceError(f"ElevenLabs rejected the request (422) -- usually a bad voice ID. {detail}") from e
            last = f"{e.code}: {detail}"
        except Exception as e:  # noqa: BLE001
            last = str(e)
        if attempt < retries:
            time.sleep(1.5)
    raise VoiceError(f"ElevenLabs call failed after retries -- {last}")


# ---------------------------------------------------------------- offline mode

def _macos_say_voice(character):
    """macOS ships a Hindi voice ('Lekha'); fall back to any default."""
    return "Lekha" if character else "Lekha"


def offline_tts_to_file(text, out_mp3, character="bansi"):
    """Preview mode: generate placeholder narration locally with whatever
    the machine has (macOS `say`, else espeak-ng, else timed silence), so
    the whole pipeline can be tested without spending API credits."""
    tmp_wav = out_mp3.replace(".mp3", "_tmp.aiff")

    if shutil.which("say"):
        try:
            cmd = ["say", "-v", _macos_say_voice(character), "-o", tmp_wav, text]
            subprocess.run(cmd, check=True, capture_output=True)
            subprocess.run(["ffmpeg", "-y", "-i", tmp_wav, out_mp3],
                           check=True, capture_output=True)
            os.remove(tmp_wav)
            return out_mp3
        except Exception:  # noqa: BLE001
            # Hindi voice may not be installed; fall through to the next option
            if os.path.exists(tmp_wav):
                os.remove(tmp_wav)

    if shutil.which("espeak-ng"):
        wav = out_mp3.replace(".mp3", "_tmp.wav")
        rate, pitch = (138, 22) if character == "bansi" else (168, 62)
        subprocess.run(["espeak-ng", "-v", "hi", "-s", str(rate), "-p", str(pitch),
                        "-a", "170", "-w", wav, text], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-i", wav, out_mp3], check=True, capture_output=True)
        os.remove(wav)
        return out_mp3

    # last resort: silence roughly as long as the line would take to say
    seconds = max(1.2, len(text) / 13.0)
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
        "-t", f"{seconds:.2f}", out_mp3,
    ], check=True, capture_output=True)
    return out_mp3
