#!/usr/bin/env bash
# Local transcript with word timings (whisper.cpp; free, runs ~30x real time on an Apple-silicon Mac).
# Usage: transcribe.sh <video> [start_s] [length_s]
#   Writes <video>.srt (captions draft) and <video>.json (word timings for words.py).
#   With start/length, transcribes only that window (fast boundary checks); times stay on the video's clock.
# Needs: brew install whisper-cpp ffmpeg; WHISPER_MODEL=path to ggml-small.en.bin (or medium.en)
set -euo pipefail
IN="$1"; SS="${2:-0}"; LEN="${3:-}"
M="${WHISPER_MODEL:?set WHISPER_MODEL to a ggml model file, e.g. ggml-small.en.bin}"
BASE="${IN%.*}"; [[ -n "$LEN" ]] && BASE="${BASE}.at${SS%.*}"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
ffmpeg -v error -y -ss "$SS" ${LEN:+-t "$LEN"} -i "$IN" -vn -ar 16000 -ac 1 -c:a pcm_s16le "$TMP/a.wav"
whisper-cli -m "$M" -l en -t 8 -f "$TMP/a.wav" -osrt -ojf -of "$TMP/out" >/dev/null 2>&1
python3 - "$TMP/out.json" "$SS" > "$BASE.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); off=float(sys.argv[2])
d["clock_offset_s"]=off
print(json.dumps(d))
PY
cp "$TMP/out.srt" "$BASE.srt"
echo "$BASE.srt  $BASE.json  (word times = file clock; offset ${SS}s)"
