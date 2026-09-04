# Puppet Show Studio

A local web app that turns a written script into an animated Hindi puppet
show — two original kathputli-style marionettes, real ElevenLabs voices,
lip-synced mouths, laughter tracks, scene cards, a 1970s village-film
treatment, and optional music — exported as a single MP4 you download from
the browser.

Everything runs on your own machine. The only thing that ever leaves it is
one request per spoken line to ElevenLabs.

---

## Setup (one time)

**1. Install Python packages**

A virtual environment is recommended so this doesn't touch your system
Python:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**2. Install ffmpeg** (used for audio conversion and video encoding)

| OS | Command |
|---|---|
| macOS | `brew install ffmpeg` |
| Ubuntu/Debian | `sudo apt install ffmpeg` |
| Windows | https://ffmpeg.org/download.html |

---

## Run it

```bash
.venv/bin/python app.py
```

Then open **http://127.0.0.1:5050** in your browser.

(macOS/Linux shortcut: `./run.sh` — Windows: `run.bat`)

Set `PUPPETSHOW_PORT` to use a different port. Note the app does **not**
auto-reload: after editing any source file, restart it.

---

## Settings

Open **Settings**, top right.

- Paste your **ElevenLabs API key** and hit Save. It's stored in
  `config.json` next to the app, on your machine only. Copy
  `config.example.json` if you'd rather start from a template.
- Set a voice for each character. The field takes a voice ID directly, so
  you can paste one at any time; **Load my voices** additionally fills a
  dropdown of your voices by name.
  - **Bansi** — stately village elder (checkered turban, big moustache)
  - **Phoolwati** — warm gossipy aunty (jeweled veil, bindi row)
- Voices actually trained on Hindi sound the most natural, though the
  multilingual model handles Devanagari on most voices.

> Your key needs the **`text_to_speech`** permission to generate audio, and
> **`voices_read`** for *Load my voices* to work. A key missing a scope
> fails with a 401 that names the permission it wants.
>
> Free ElevenLabs plans cannot use **library voices** via the API — those
> return `402 paid_plan_required`. Voices in your own account work fine.

---

## Writing a script

Two layouts are accepted, and you can mix them freely.

**Speaker and line together:**

```
Bansi: गाँववालों! आज पंचायत में एक सीरियस केस आया है। [sfx_before:dholak_hit]
Phoolwati: कुछ तो राज़ है! [laugh:big] [cutaway:कुछ तो राज़ है...?]
```

**Speaker on its own line** (dialogue may be quoted):

```
Bansi:
"फूलवती, ये टिक्की ग्रुप का बड़ा नाम सुना है।"
Phoolwati:
"बिल्कुल!"
[LIGHT LAUGHTER]
```

Mixed Devanagari and English is not just allowed but encouraged — it's how
people actually speak, and ElevenLabs reads each script with the right
accent:

```
Phoolwati:
"अरे बंसी, बड़ा mast group है। हर festival, हर birthday…"
```

> **Write the dialogue in Devanagari** (देवनागरी) wherever you can. Fully
> romanized "Hinglish" gets read with an English accent. Devanagari is also
> slightly cheaper, since it encodes the same words in fewer characters.

### Speakers

| Label | Meaning |
|---|---|
| `Bansi:` / `बंसी:` | the elder |
| `Phoolwati:` / `फूलवती:` | the aunty |
| `Both:` / `Bansi & Phoolwati together:` | said by both — synthesized in each voice and stacked, with both puppets' mouths moving |
| `Phoolwati, imitating Abhay:` | trailing stage business is ignored; the line is Phoolwati's |

`Pradhanji:` and `Madhuri:` still work — the characters were renamed and
the old labels are kept as aliases.

### Scene headings

A line on its own with no speaker label and no opening quote is a scene
heading. It becomes a chapter card in front of the line that follows it:

```
Scene 1 — Tikki Group & Memory
```

The part before the dash becomes the small kicker, the part after it the
large title; a heading with no dash is all title. Use `#` at the start of a
line for a comment you *don't* want turned into a card.

### Tags

Any line may end with these:

| Tag | Meaning |
|---|---|
| `[sfx:rimshot]` | sound effect after the line |
| `[sfx_before:dholak_hit]` | sound effect before the line |
| `[laugh:big]` | laughter after the line (see below) |
| `[hold:1.0]` | seconds of silence **before** the line |
| `[pause:0.6]` | reaction pause in seconds after the line |
| `[cutaway:some text]` | cut away to a card with this text |
| `[cutaway_sub:smaller text]` | second line on the cutaway card |
| `[cutaway_style:title]` | title-card style instead of the reveal style |

Sound effects: `dholak_hit`, `tadaa`, `dun_dun_duun`, `rimshot`, `whoosh`.

### Laughter and the held beat

Four sizes, each of which brings its own setup silence:

| `[laugh:…]` | Also written as | Hold before the line |
|---|---|---|
| `chuckle` | `[LIGHT LAUGHTER]` | 0.2s |
| `medium` | `[LAUGHTER]` | 0.5s |
| `big` | `[BIG LAUGHTER]` | **1.0s** |
| `applause` | `[MUSIC STING / APPLAUSE]` | **1.0s** |

The bracketed forms go on a line of their own and attach to the line just
spoken. The silence before a punchline does more work than the laugh after
it, so it is applied automatically — override with `[hold:1.4]`, or
`[hold:0]` to remove it.

Both puppets shake along while the audience laughs.

Click **Parse script** and everything lands in an editable table, where you
can set speaker, text, sound effect, laughter, hold, pause and cutaway per
line without touching tag syntax. **Load sample** fills in a working
example.

---

## Music

Optional, in the **Generate** panel. Point *Open with a song* at any audio
file on your machine and the show gets:

- an **intro** — the first N seconds, with both puppets dancing to it
- a **sting** on every scene card
- an **outro** after the last line, puppets dancing out

The dance is driven by the music itself: per-frame loudness scales how big
the movement is, and the bounce lands on a beat found by autocorrelating
the onset strength, so it follows the actual tempo rather than a fixed
rhythm.

Intro length is set in the UI. The sting and outro windows are start/end
times in seconds, set in `config.json`:

```json
"sting": { "enabled": true, "start": 22.0, "end": 24.0 },
"outro": { "enabled": true, "start": 185.0, "end": 202.0 }
```

Both are cut from the same file as the intro. A scene card holds for
exactly as long as its sting.

---

## The 1970s look

On by default, with a strength slider in the **Generate** panel. It applies
per frame, in the order a real print would have picked the artifacts up:
faded grade with lifted blacks and amber highlights, halation around bright
areas, gate weave, animated grain, dust and the occasional scratch,
vignette, and exposure flicker.

The soundtrack is aged to match — village ambience (crickets, a distant
crowd, wind) underneath, then the whole mix band-limited and lightly
distorted like an optical soundtrack through a courtyard horn speaker.

This roughly **doubles render time**, since it runs on every frame. Set the
strength to 0 to skip it entirely while you iterate.

---

## Generating

- **Burn in subtitles** — on by default.
- **Export at 1080p** — upscaled from the 720p render; 720p is usually fine
  for a projector and renders faster.
- **Preview mode** — builds the whole video with a local placeholder voice
  instead of calling ElevenLabs. Use it to check timing, laughter, scene
  cards and subtitles without spending API credits.

Hit **Generate video**, watch the progress bar, then play it inline and
click **Download MP4**.

Rendering takes a few minutes — every frame is composited in Python. That's
expected; let it finish.

> Credits are roughly one per character of dialogue, and there is **no
> caching**: every render re-synthesizes every line, even ones you didn't
> change. Use Preview mode while iterating and save the API calls for the
> final pass.

---

## Notes

- Generated videos are kept under `jobs/<job-id>/` along with their raw
  audio. Delete that folder any time — it grows quickly.
- The job list lives in memory, so **restarting the app clears it** and old
  download links stop working. The files themselves are still on disk.
- `config.json` holds your API key in plain text and is git-ignored. If
  you'd rather not store it, leave the key blank in the UI and set
  `ELEVENLABS_API_KEY` in the environment before launching.
- The puppets, backdrop, costumes, sound effects, cutaway cards and chapter
  cards are all generated in code (`pipeline/puppets.py`,
  `pipeline/scene.py`, `pipeline/sfx.py`) — no external art.
- **Laughter** is different: `assets/laughs/*.wav` are recorded audience
  files. If any are missing, the app falls back to synthesizing that laugh
  in code (`pipeline/sfx.py`). Drop your own file in as
  `assets/laughs/<slot>.wav` to replace one — it gets converted, faded and
  level-matched for its slot automatically.
- **Music is yours to supply.** No audio file ships with this repo, and
  none is committed. Make sure you have the right to use whatever you point
  the intro at.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "ffmpeg not found" badge in the header | Install ffmpeg (above), restart the app |
| Browser says "access denied" / 403 on the app URL | On macOS the AirPlay Receiver holds port 5000 (IPv4 **and** IPv6), so `localhost` resolves to `::1` and hits AirPlay instead of the app. The app therefore runs on **5050**. Override with `PUPPETSHOW_PORT=5060 python3 app.py` |
| Code change seems to do nothing | The app doesn't auto-reload. Restart it — and if the port seems taken, find the real listener with `lsof -nP -iTCP:5050 -sTCP:LISTEN` and kill that PID |
| 401 from ElevenLabs naming a permission | The key is valid but missing that scope. Regenerate it with `text_to_speech` and `voices_read` |
| 402 `paid_plan_required` | That voice is a library voice, which free plans can't use via the API. Pick a voice from your own account or upgrade |
| 422 from ElevenLabs | Usually a bad voice ID — reload voices and re-pick |
| Subtitles show as boxes | The bundled Devanagari font didn't load — make sure `pipeline/fonts/` came along with the rest of the files |
| A stray line became a scene card | Unquoted lines with no speaker label are treated as headings. Prefix comments with `#` |
| Render feels slow | Normal, and the film look roughly doubles it. Use Preview mode while iterating, drop film strength to 0, and only spend API credits on the final pass |
