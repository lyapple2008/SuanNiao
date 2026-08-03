#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CACHE_DIR="${TMPDIR:-/tmp}/suanniao-manim-cache"
mkdir -p "$CACHE_DIR"

cd "$SCRIPT_DIR"
XDG_CACHE_HOME="$CACHE_DIR" manim \
  --config_file manim.cfg \
  --renderer cairo \
  -r 1920,1080 \
  --fps 30 \
  -o beam-search-core-raw \
  beam_search_core.py BeamSearchCore

RAW_OUTPUT="$(find media -type f -name 'beam-search-core-raw.mp4' -print -quit)"
if [[ -z "$RAW_OUTPUT" ]]; then
  echo "Rendered MP4 not found" >&2
  exit 1
fi

ffmpeg -y -v warning \
  -i "$RAW_OUTPUT" \
  -t 75.000 \
  -an \
  -c:v libx264 \
  -preset medium \
  -crf 18 \
  -pix_fmt yuv420p \
  -movflags +faststart \
  "$SCRIPT_DIR/beam-search-core-1080p.mp4"

echo "$SCRIPT_DIR/beam-search-core-1080p.mp4"
