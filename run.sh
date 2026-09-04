#!/usr/bin/env bash
cd "$(dirname "$0")"
python3 -c "import flask, PIL, numpy, pydub" 2>/dev/null || {
  echo "Installing Python dependencies…"
  pip install -r requirements.txt
}
command -v ffmpeg >/dev/null || echo "!! ffmpeg not found — install it (macOS: brew install ffmpeg)"
python3 app.py
