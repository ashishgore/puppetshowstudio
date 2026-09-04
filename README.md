# Puppet Show Studio

A local web app that turns a written script into an animated Hindi puppet
show — two original kathputli-style marionettes, real ElevenLabs voices,
lip-synced mouths, head bob, burned-in subtitles, sound effects, and
cutaway cards — exported as a single MP4 you download from the browser.

Everything runs on your own machine. The only thing that ever leaves it is
one request per line to ElevenLabs.

---

## Setup (one time)

**1. Install Python packages**

```bash
pip install -r requirements.txt
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
python3 app.py
```

Then open **http://127.0.0.1:5050** in your browser.

(macOS/Linux shortcut: `./run.sh` — Windows: `run.bat`)

---

## Using it

**Settings** (top right)

- Paste your **ElevenLabs API key** and hit Save. It's stored in
  `config.json` next to the app, on your machine only.
- Click **Load my voices** to pull your ElevenLabs voice list, then pick
  one for each character from the dropdown:
  - **Bansi** — stately village elder (checkered turban, big moustache)
  - **Phoolwati** — warm gossipy aunty (jeweled veil, bindi row)
- Voices actually trained on Hindi sound the most natural, though the
  multilingual model handles Devanagari on most voices.

**Script**

One spoken line per row, prefixed with the character name:

```
Bansi: गाँववालों! आज पंचायत में एक बहुत ही सीरियस केस आया है। [sfx_before:dholak_hit]
Phoolwati: केस है — नेहा और अभय के पच्चीस साल की शादी का! [sfx:tadaa] [pause:0.35]
Phoolwati: तो पंचायत को लगा... कुछ तो राज़ है! [sfx:dun_dun_duun] [cutaway:कुछ तो राज़ है...?]
```

Optional tags at the end of any line:

| Tag | Meaning |
|---|---|
| `[sfx:rimshot]` | sound effect after the line |
| `[sfx_before:dholak_hit]` | sound effect before the line |
| `[pause:0.6]` | reaction pause in seconds after the line |
| `[cutaway:some text]` | cut away to a card with this text |
| `[cutaway_sub:smaller text]` | second line on the cutaway card |
| `[cutaway_style:title]` | use the title-card style instead of the reveal style |

Available sound effects: `dholak_hit`, `tadaa`, `dun_dun_duun`, `rimshot`, `whoosh`.

Click **Parse script** and everything lands in an editable table — you can
change speaker, text, sound effect, pause and cutaway per line there
without touching the tag syntax. **Load sample** fills in a working example.

> **Write in Devanagari** (देवनागरी) for natural Hindi pronunciation.
> Romanized "Hinglish" gets read with an English accent.

**Generate**

- **Burn in subtitles** — on by default.
- **Export at 1080p** — upscaled from the 720p render; 720p is usually
  fine for a projector and renders faster.
- **Preview mode** — builds the whole video with a local placeholder voice
  instead of calling ElevenLabs. Use it to check timing, subtitles and
  cutaways without spending API credits.

Hit **Generate video**, watch the progress bar, then play it inline and
click **Download MP4**.

Rendering takes a few minutes — every frame is composited in Python
(roughly 24 frames per second of video). That's expected; let it finish.

---

## Notes

- Generated videos are kept under `jobs/<job-id>/` if you want the raw
  audio or to re-download an older run. Delete that folder any time.
- `config.json` holds your API key in plain text. If you'd rather not
  store it, leave the key blank in the UI and set the environment variable
  `ELEVENLABS_API_KEY` before launching instead.
- The puppet designs, backdrop, costumes, sound effects and cutaway cards
  are all generated in code (`pipeline/puppets.py`, `pipeline/scene.py`,
  `pipeline/sfx.py`) — no external art or audio assets, nothing licensed
  from anyone else.

## Troubleshooting

| Problem | Fix |
|---|---|
| "ffmpeg not found" badge in the header | Install ffmpeg (above), restart the app |
| Browser says "access denied" / 403 on the app URL | On macOS the AirPlay Receiver holds port 5000 (IPv4 **and** IPv6), so `localhost` resolves to `::1` and hits AirPlay instead of the app. The app therefore runs on **5050**. Override with `PUPPETSHOW_PORT=5060 python3 app.py` |
| 401 / 403 from ElevenLabs | API key is wrong or expired |
| 422 from ElevenLabs | Usually a bad voice ID — reload voices and re-pick |
| Subtitles show as boxes | The bundled Devanagari font didn't load — make sure `pipeline/fonts/` came along with the rest of the files |
| Render feels slow | Normal. Use Preview mode while iterating on timing, and only spend API credits on the final pass |
