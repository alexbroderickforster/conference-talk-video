#!/usr/bin/env bash
# Cut one talk out of a recording with soft edges: 0.5 s fade in/out on picture and sound.
# Usage: cut.sh <recording> <start> <end> <out.mp4>      (times as s or h:mm:ss.xx, on the recording's clock)
# Env: FADE=0.5   AUDIO_DELAY_MS=0 (positive = delay sound, if the AV feed's audio runs early)
#      LOUDNORM=1 (level to -16 LUFS, YouTube-friendly)
set -euo pipefail
IN="$1"; S="$2"; E="$3"; OUT="$4"; F="${FADE:-0.5}"; DLY="${AUDIO_DELAY_MS:-0}"
toS(){ awk -F: '{s=0; for(i=1;i<=NF;i++) s=s*60+$i; printf "%.3f", s}' <<<"$1"; }
SS=$(toS "$S"); DUR=$(awk -v a="$SS" -v b="$(toS "$E")" 'BEGIN{printf "%.3f", b-a}')
FO=$(awk -v d="$DUR" -v f="$F" 'BEGIN{printf "%.3f", d-f}')
AF="afade=t=in:d=$F,afade=t=out:st=$FO:d=$F"
[[ "$DLY" != 0 ]] && AF="adelay=${DLY}:all=1,$AF"
[[ "${LOUDNORM:-0}" == 1 ]] && AF="$AF,loudnorm=I=-16:TP=-1.5:LRA=11"
ffmpeg -v warning -stats -y -ss "$SS" -i "$IN" -t "$DUR" \
  -vf "fade=t=in:d=$F,fade=t=out:st=$FO:d=$F" -af "$AF" \
  -c:v libx264 -preset medium -crf 16 -pix_fmt yuv420p -c:a aac -b:a 192k -ar 48000 -movflags +faststart "$OUT"
echo "$OUT  ($DUR s)"
