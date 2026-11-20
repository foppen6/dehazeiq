#!/bin/bash
# Hämtar en fristående FFmpeg/FFprobe för Apple Silicon till packaging/ffmpeg.
# Försöker först statiska byggen; faller annars tillbaka till Homebrew + dylibbundler.
set -uo pipefail
cd "$(dirname "$0")"
rm -rf ffmpeg && mkdir -p ffmpeg && cd ffmpeg

static_ok=1
for tool in ffmpeg ffprobe; do
  if curl -fsSL --retry 3 -o "$tool.zip" \
       "https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/$tool.zip"; then
    unzip -oq "$tool.zip" && rm -f "$tool.zip"
  else
    static_ok=0
  fi
done
chmod +x ffmpeg ffprobe 2>/dev/null

if [ "$static_ok" = 1 ] && ./ffmpeg -hide_banner -version >/dev/null 2>&1 && ./ffprobe -hide_banner -version >/dev/null 2>&1; then
  echo "Använder statiska FFmpeg-byggen"
else
  echo "Statiska byggen saknas – använder Homebrew + dylibbundler"
  rm -rf ./*
  brew install ffmpeg dylibbundler >/dev/null
  cp "$(brew --prefix)/bin/ffmpeg" "$(brew --prefix)/bin/ffprobe" .
  chmod u+w ffmpeg ffprobe
  dylibbundler -cd -of -b -x ./ffmpeg -x ./ffprobe -d ./libs -p @executable_path/libs/
  codesign --force -s - ./libs/*.dylib ./ffmpeg ./ffprobe
fi

./ffmpeg -hide_banner -version | head -1 || exit 1
./ffprobe -hide_banner -version | head -1 || exit 1
if ./ffmpeg -hide_banner -encoders 2>/dev/null | grep -q h264_videotoolbox; then
  echo "VideoToolbox: finns"
else
  echo "VARNING: VideoToolbox saknas i detta FFmpeg-bygge"
fi
