@echo off
cd /d "%~dp0"
python -c "import flask, PIL, numpy, pydub" 2>NUL || (
  echo Installing Python dependencies...
  pip install -r requirements.txt
)
where ffmpeg >NUL 2>NUL || echo !! ffmpeg not found - see https://ffmpeg.org/download.html
python app.py
pause
