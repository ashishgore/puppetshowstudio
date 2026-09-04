"""Extract a smoothed loudness envelope from a WAV file, used to drive
puppet mouth-open amount (classic 'flap to the amplitude' puppeteering,
not phoneme-accurate visemes)."""
import math
import wave

import numpy as np


def read_wav_mono(path):
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
        sampwidth = wf.getsampwidth()
        ch = wf.getnchannels()
    if sampwidth != 2:
        raise ValueError("expected 16-bit PCM")
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


def mouth_states_for_line(path, fps, n_frames_hint=None):
    """Return an array of mouth states (0,1,2) with one entry per video
    frame for the duration of this line's audio."""
    data, sr = read_wav_mono(path)
    dur = len(data) / sr
    n_frames = n_frames_hint or max(1, int(round(dur * fps)))
    hop = len(data) / n_frames

    rms = np.zeros(n_frames)
    for i in range(n_frames):
        a = int(i * hop)
        b = int(min(len(data), a + hop))
        seg = data[a:b]
        rms[i] = np.sqrt(np.mean(seg ** 2)) if len(seg) else 0.0

    if rms.max() > 0:
        norm = rms / (np.percentile(rms, 92) + 1e-6)
        norm = np.clip(norm, 0, 1)
    else:
        norm = rms

    # light smoothing so mouth doesn't chatter frame-to-frame
    kernel = np.array([0.2, 0.6, 0.2])
    if len(norm) >= 3:
        padded = np.pad(norm, (1, 1), mode="edge")
        norm = np.convolve(padded, kernel, mode="valid")

    states = np.zeros(n_frames, dtype=int)
    states[norm > 0.16] = 1
    states[norm > 0.45] = 2

    # avoid single-frame flicker: require state to hold >=2 frames
    for i in range(1, len(states) - 1):
        if states[i] != states[i - 1] and states[i] != states[i + 1]:
            states[i] = states[i - 1]

    return states, dur


def _estimate_beat_period(onset, fps, bpm_lo=60, bpm_hi=180, bpm_pref=120.0):
    """Autocorrelate the onset strength to find the most likely beat
    spacing, in frames, within a plausible tempo range.

    Raw autocorrelation peaks just as hard at 2x and 4x the true beat, so
    a slow song can come back as half-time and the puppets end up bobbing
    once a bar. Scores are weighted by a log-Gaussian prior around
    `bpm_pref` to break that ambiguity toward a danceable tempo.
    """
    lo = max(2, int(round(fps * 60.0 / bpm_hi)))
    hi = min(len(onset) - 1, int(round(fps * 60.0 / bpm_lo)))
    if hi <= lo:
        return max(2, int(round(fps * 0.5)))
    x = onset - onset.mean()
    best_lag, best_score = lo, -1e18
    for lag in range(lo, hi + 1):
        bpm = fps * 60.0 / lag
        prior = math.exp(-0.5 * (math.log2(bpm / bpm_pref) / 0.9) ** 2)
        score = float(np.dot(x[:-lag], x[lag:])) * prior
        if score > best_score:
            best_lag, best_score = lag, score
    return best_lag


def dance_track(path, fps, n_frames):
    """Per-frame drive for puppets dancing to a music bed.

    Returns `energy` (0..~1.4, how hard to move right now) and `phase`
    (0..1 within the current beat), so the bounce lands on the beat
    instead of on an arbitrary sine wave.
    """
    data, sr = read_wav_mono(path)
    n_frames = max(1, n_frames)
    hop = len(data) / n_frames

    rms = np.zeros(n_frames)
    for i in range(n_frames):
        a = int(i * hop)
        b = int(min(len(data), a + hop))
        seg = data[a:b]
        rms[i] = np.sqrt(np.mean(seg ** 2)) if len(seg) else 0.0

    energy = np.clip(rms / (np.percentile(rms, 90) + 1e-6), 0, 1.4)
    if n_frames >= 5:
        k = np.array([0.15, 0.2, 0.3, 0.2, 0.15])
        energy = np.convolve(np.pad(energy, (2, 2), mode="edge"), k, mode="valid")

    onset = np.clip(np.diff(rms, prepend=rms[0]), 0, None)
    period = _estimate_beat_period(onset, fps)

    # lock phase 0 to the loudest onset so the first bounce hits a real beat
    anchor = int(np.argmax(onset)) if onset.max() > 0 else 0
    phase = ((np.arange(n_frames) - anchor) % period) / float(period)

    return dict(energy=energy, phase=phase, period=int(period))
