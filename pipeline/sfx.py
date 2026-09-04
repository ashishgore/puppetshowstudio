"""Small procedurally-synthesized sound-effect library (no external audio
files, so nothing here has licensing concerns). Everything returns a
mono float32 numpy array at SR Hz in range [-1, 1]."""
import numpy as np

SR = 44100


def _t(dur):
    return np.linspace(0, dur, int(SR * dur), endpoint=False)


def _env(n, attack=0.01, release=0.08):
    e = np.ones(n)
    a = int(SR * attack)
    r = int(SR * release)
    if a > 0:
        e[:a] *= np.linspace(0, 1, a)
    if r > 0:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def sine(freq, dur, amp=0.5, decay=None):
    t = _t(dur)
    sig = np.sin(2 * np.pi * freq * t) * amp
    if decay:
        sig *= np.exp(-t / decay)
    return sig.astype(np.float32)


def noise_burst(dur, amp=0.5, lp=None):
    n = int(SR * dur)
    sig = (np.random.rand(n) * 2 - 1) * amp
    if lp:
        # crude one-pole low-pass
        alpha = np.exp(-2 * np.pi * lp / SR)
        out = np.zeros_like(sig)
        prev = 0.0
        for i, s in enumerate(sig):
            prev = (1 - alpha) * s + alpha * prev
            out[i] = prev
        sig = out
    return sig.astype(np.float32)


def _mix(*sigs):
    n = max(len(s) for s in sigs)
    out = np.zeros(n, dtype=np.float32)
    for s in sigs:
        out[: len(s)] += s
    peak = np.max(np.abs(out)) or 1.0
    if peak > 0.98:
        out = out / peak * 0.98
    return out


def dholak_hit():
    """Low thump + crisp tap, like a hand-drum stroke for a scene opener."""
    t = _t(0.35)
    thump = np.sin(2 * np.pi * (140 * np.exp(-t * 10)) * t) * np.exp(-t * 9) * 0.9
    tap = noise_burst(0.05, amp=0.5, lp=3500) * _env(int(SR * 0.05), 0.001, 0.045)
    sig = _mix(thump, np.concatenate([tap, np.zeros(len(thump) - len(tap))]))
    return sig


def tadaa_chime():
    """Bright two-note rising chime for a reveal / good-news beat."""
    n1 = sine(523.25, 0.16, amp=0.35, decay=0.18)
    n2 = sine(659.25, 0.16, amp=0.35, decay=0.18)
    n3 = sine(783.99, 0.34, amp=0.4, decay=0.30)
    sig = np.concatenate([n1, n2 * 0.9, n3])
    return sig


def dun_dun_duun():
    """Descending comedic 'suspense' sting for the raaz/secret line."""
    n1 = sine(220.0, 0.22, amp=0.4, decay=0.18)
    n2 = sine(196.0, 0.22, amp=0.4, decay=0.18)
    n3 = sine(146.83, 0.55, amp=0.45, decay=0.5)
    sig = np.concatenate([n1, n2, n3])
    return sig


def rimshot_tss():
    """'Ba-dum-tss' comedy rimshot for a punchline."""
    d1 = noise_burst(0.05, amp=0.6, lp=1800) * _env(int(SR * 0.05), 0.001, 0.045)
    gap = np.zeros(int(SR * 0.10))
    d2 = noise_burst(0.05, amp=0.6, lp=1800) * _env(int(SR * 0.05), 0.001, 0.045)
    gap2 = np.zeros(int(SR * 0.06))
    tss = noise_burst(0.35, amp=0.3, lp=9000) * _env(int(SR * 0.35), 0.001, 0.32)
    sig = np.concatenate([d1, gap, d2, gap2, tss])
    return sig


def whoosh():
    """Soft whoosh for a cutaway transition."""
    n = int(SR * 0.30)
    sig = noise_burst(0.30, amp=0.35, lp=2000)
    freq_sweep = np.linspace(400, 3000, n)
    t = _t(0.30)
    mod = np.sin(2 * np.pi * freq_sweep * t / SR * SR * 0) # no-op placeholder
    sig *= _env(n, 0.05, 0.2)
    return sig


def to_wav_bytes(sig, sr=SR):
    sig = np.clip(sig, -1, 1)
    pcm = (sig * 32767).astype(np.int16)
    return pcm, sr


def write_wav(path, sig, sr=SR):
    import wave
    pcm, sr = to_wav_bytes(sig, sr)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


if __name__ == "__main__":
    import os
    os.makedirs("audio/sfx", exist_ok=True)
    write_wav("audio/sfx/dholak_hit.wav", dholak_hit())
    write_wav("audio/sfx/tadaa.wav", tadaa_chime())
    write_wav("audio/sfx/dun_dun_duun.wav", dun_dun_duun())
    write_wav("audio/sfx/rimshot.wav", rimshot_tss())
    write_wav("audio/sfx/whoosh.wav", whoosh())
    print("sfx done")


def _one_pole_lp(sig, cutoff):
    alpha = float(np.exp(-2 * np.pi * cutoff / SR))
    out = np.empty_like(sig)
    prev = 0.0
    for i in range(len(sig)):
        prev = (1 - alpha) * sig[i] + alpha * prev
        out[i] = prev
    return out


def village_ambience(dur, seed=11):
    """An evening in the village, synthesized: crickets, a distant dog,
    a low crowd murmur and a breath of wind. Sits far under the dialogue
    -- you should feel it rather than hear it.
    """
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    out = np.zeros(n, dtype=np.float32)

    # --- crickets: short chirp trains around 4.2 kHz, staggered
    for _ in range(int(dur * 2.2)):
        start = int(rng.uniform(0, max(1, n - SR)))
        freq = rng.uniform(3800, 4800)
        train = rng.integers(3, 7)
        for c in range(train):
            clen = int(SR * 0.028)
            off = start + c * int(SR * rng.uniform(0.055, 0.085))
            if off + clen >= n:
                break
            t = np.arange(clen) / SR
            chirp = np.sin(2 * np.pi * freq * t) * np.hanning(clen)
            out[off:off + clen] += chirp.astype(np.float32) * rng.uniform(0.05, 0.11)

    # --- crowd murmur: heavily low-passed noise, slowly breathing
    murmur = _one_pole_lp((rng.random(n).astype(np.float32) * 2 - 1), 420.0)
    breath = 0.55 + 0.45 * np.sin(2 * np.pi * 0.09 * np.arange(n) / SR).astype(np.float32)
    out += murmur * breath * 0.10

    # --- wind: very low noise floor
    out += _one_pole_lp((rng.random(n).astype(np.float32) * 2 - 1), 120.0) * 0.06

    # --- a distant dog, once or twice, if there's room
    for _ in range(int(rng.integers(1, 3))):
        start = int(rng.uniform(0, max(1, n - SR)))
        blen = int(SR * 0.16)
        if start + blen >= n:
            continue
        t = np.arange(blen) / SR
        bark = (np.sin(2 * np.pi * 320 * t) + 0.5 * np.sin(2 * np.pi * 640 * t))
        bark *= np.exp(-t * 14) * np.hanning(blen)
        out[start:start + blen] += bark.astype(np.float32) * 0.05

    peak = float(np.abs(out).max())
    if peak > 0:
        out = out / peak * 0.5
    return out.astype(np.float32)


# ------------------------------------------------------------------ laughter
#
# Laughter is synthesized per-voice and then stacked, rather than looping one
# recorded crowd. Each voice gets its own pitch, syllable rate and entry time,
# which is what makes a room full of people sound like a room rather than a
# copy-paste. Building it this way also means the four sizes are genuinely
# different performances, not the same clip at four volumes.


def _ha_syllable(f0, dur, rng, bright=1.0):
    """One voiced 'ha': a harmonic stack shaped by open-vowel formants,
    under a sharp-attack decay, with breath noise on top."""
    n = max(8, int(SR * dur))
    t = np.arange(n, dtype=np.float32) / SR
    f = f0 * (1.0 - 0.05 * (t / max(dur, 1e-6)))       # pitch sags across the syllable
    phase = (2.0 * np.pi * np.cumsum(f) / SR).astype(np.float32)

    sig = np.zeros(n, dtype=np.float32)
    formants = ((700.0, 1.0), (1220.0, 0.5), (2600.0, 0.22))
    nharm = int(min(38, (SR * 0.45) / max(f0, 1.0)))
    for k in range(1, nharm + 1):
        fk = f0 * k
        amp = 0.0
        for fc, w in formants:
            amp += w * float(np.exp(-0.5 * ((fk - fc) / (fc * 0.6)) ** 2))
        amp *= bright / (k ** 0.7)
        if amp < 2e-3:
            continue
        sig += np.sin(phase * k).astype(np.float32) * amp

    env = np.exp(-t * rng.uniform(9.0, 14.0)).astype(np.float32)
    a = int(SR * 0.006)
    env[:a] *= np.linspace(0, 1, a, dtype=np.float32)
    sig *= env
    sig += (rng.random(n).astype(np.float32) * 2 - 1) * env * 0.10
    return sig


def _laugh_voice(total_dur, rng, f0, rate, gain, start):
    """One person laughing: a run of syllables that falls in pitch and
    fades as they run out of breath."""
    n = int(SR * total_dur)
    out = np.zeros(n, dtype=np.float32)
    syl_dur = rng.uniform(0.10, 0.16)
    variants = [_ha_syllable(f0 * m, syl_dur, rng) for m in (1.0, 0.93, 0.86)]

    n_syl = max(2, int((total_dur - start) * rate * rng.uniform(0.75, 1.0)))
    pos = start
    for i in range(n_syl):
        v = variants[min(len(variants) - 1, int(i * len(variants) / max(1, n_syl)))]
        p = int(SR * pos)
        if p + len(v) >= n:
            break
        out[p:p + len(v)] += v * (gain * float(np.exp(-i * 0.12)) * rng.uniform(0.75, 1.0))
        pos += (1.0 / rate) * rng.uniform(0.85, 1.15)
    return out


def _crowd_laugh(dur, n_voices, rng, spread=0.5, f_lo=95, f_hi=255):
    n = int(SR * dur)
    out = np.zeros(n, dtype=np.float32)
    for _ in range(n_voices):
        out += _laugh_voice(
            dur, rng,
            f0=rng.uniform(f_lo, f_hi),
            rate=rng.uniform(4.5, 7.0),
            gain=rng.uniform(0.5, 1.0),
            start=rng.uniform(0.0, spread),
        )
    # swell in, trail off -- a room doesn't start or stop all at once
    t = np.arange(n, dtype=np.float32) / SR
    swell = np.clip(t / 0.18, 0, 1) * np.clip((dur - t) / (dur * 0.45), 0, 1)
    return out * swell


def _applause(dur, rng, density=780):
    """Hands, not noise: many short bandpassed transients at random times."""
    n = int(SR * dur)
    out = np.zeros(n, dtype=np.float32)
    clap_len = int(SR * 0.013)
    ct = np.arange(clap_len, dtype=np.float32) / SR
    shapes = []
    for _ in range(6):
        c = (rng.random(clap_len).astype(np.float32) * 2 - 1) * np.exp(-ct * rng.uniform(240, 400))
        shapes.append(_one_pole_lp(c, rng.uniform(2200, 4200)))
    for _ in range(int(dur * density)):
        p = int(rng.uniform(0, max(1, n - clap_len)))
        out[p:p + clap_len] += shapes[int(rng.integers(0, len(shapes)))] * rng.uniform(0.25, 1.0)
    t = np.arange(n, dtype=np.float32) / SR
    swell = np.clip(t / 0.25, 0, 1) * np.clip((dur - t) / (dur * 0.5), 0, 1)
    return out * swell


def _finish(sig, peak=0.85):
    m = float(np.abs(sig).max())
    return (sig / m * peak).astype(np.float32) if m > 0 else sig.astype(np.float32)


def laugh_chuckle():
    """A few people who found it mildly funny."""
    rng = np.random.default_rng(21)
    return _finish(_crowd_laugh(1.1, n_voices=3, rng=rng, spread=0.22), 0.5)


def laugh_medium():
    """A proper room laugh."""
    rng = np.random.default_rng(22)
    return _finish(_crowd_laugh(1.8, n_voices=14, rng=rng, spread=0.42), 0.72)


def laugh_big():
    """The whole courtyard goes up, with a couple of high whoops on top."""
    rng = np.random.default_rng(23)
    sig = _crowd_laugh(2.5, n_voices=30, rng=rng, spread=0.5)
    for _ in range(3):                       # whoops ride above the crowd
        sig += _laugh_voice(2.5, rng, f0=rng.uniform(300, 400),
                            rate=rng.uniform(3.0, 4.2), gain=0.5,
                            start=rng.uniform(0.15, 0.7))
    return _finish(sig, 0.92)


def laugh_applause():
    """Big laugh that turns into applause -- for the closer."""
    rng = np.random.default_rng(24)
    dur = 3.4
    sig = _crowd_laugh(dur, n_voices=26, rng=rng, spread=0.45)
    clap = _applause(dur, rng)
    pad = np.zeros(int(SR * 0.45), dtype=np.float32)   # claps start slightly late
    clap = np.concatenate([pad, clap])[:len(sig)]
    sig[:len(clap)] += clap * 0.85
    return _finish(sig, 0.95)
