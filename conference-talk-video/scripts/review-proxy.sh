#!/usr/bin/env bash
# Small review copy of a cut: the first N seconds, 1 s of black, the last N seconds.
# 540p, low bitrate, plays anywhere (phone, Slack, browser). Fast: seeks, never decodes the middle.
# A cut no longer than 2xN seconds comes back whole. Works with or without an audio track.
# Usage: review-proxy.sh <talk.mp4> [seconds=45] [out.mp4]
set -euo pipefail
IN="$1"; N="${2:-45}"; OUT="${3:-${IN%.*}-review.mp4}"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$IN")
HAS_A=$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$IN" | head -1)
FIT="scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1,format=yuv420p"
ENC=(-c:v libx264 -preset veryfast -crf 28 -movflags +faststart)
if [[ -n "$HAS_A" ]]; then ENC+=(-c:a aac -b:a 96k); fi
if ! awk -v d="$DUR" -v n="$N" 'BEGIN{exit !(d > 2*n)}'; then   # short cut: send the whole thing, small
  if [[ -n "$HAS_A" ]]; then M=(-map 0:v:0 -map 0:a:0); else M=(-map 0:v:0 -an); fi
  ffmpeg -v error -y -i "$IN" -vf "$FIT" "${M[@]}" "${ENC[@]}" "$OUT"
  echo "$OUT  (whole cut, $(printf %.0f "$DUR")s — shorter than 2x${N}s)"; exit 0
fi
if [[ -n "$HAS_A" ]]; then
  ffmpeg -v error -y -t "$N" -i "$IN" -sseof "-$N" -i "$IN" \
    -f lavfi -t 1 -i "color=black:s=960x540:r=30" -f lavfi -t 1 -i "anullsrc=r=48000:cl=stereo" \
    -filter_complex "[0:v]$FIT[h];[0:a]aresample=48000,aformat=channel_layouts=stereo[ha];\
[1:v]$FIT[t];[1:a]aresample=48000,aformat=channel_layouts=stereo[ta];[2:v]format=yuv420p,setsar=1[b];\
[h][ha][b][3:a][t][ta]concat=n=3:v=1:a=1[v][a]" -map "[v]" -map "[a]" "${ENC[@]}" "$OUT"
else
  ffmpeg -v error -y -t "$N" -i "$IN" -sseof "-$N" -i "$IN" -f lavfi -t 1 -i "color=black:s=960x540:r=30" \
    -filter_complex "[0:v]$FIT[h];[1:v]$FIT[t];[2:v]format=yuv420p,setsar=1[b];[h][b][t]concat=n=3:v=1:a=0[v]" \
    -map "[v]" "${ENC[@]}" "$OUT"
fi
echo "$OUT  (start = 0:00–0:$(printf %02d "$N"), end = last ${N}s of a $(printf %.0f "$DUR")s talk)"
