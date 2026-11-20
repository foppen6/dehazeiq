#!/bin/bash
# Dubbelklicka för att starta DeHazeIQ på macOS.
cd "$(dirname "$0")" || exit 1

if ! command -v ffmpeg >/dev/null 2>&1 && [ ! -x /opt/homebrew/bin/ffmpeg ] && [ ! -x /usr/local/bin/ffmpeg ]; then
  echo "FFmpeg saknas. Installera det med Homebrew:"
  echo "  brew install ffmpeg"
  echo
  read -r -p "Tryck Enter för att stänga."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 saknas. Installera med: brew install python"
  read -r -p "Tryck Enter för att stänga."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Förbereder första start (skapar .venv och installerar paket) …"
  python3 -m venv .venv || exit 1
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -r requirements.txt || exit 1
fi

exec ./.venv/bin/python -m dehazeiq "$@"
