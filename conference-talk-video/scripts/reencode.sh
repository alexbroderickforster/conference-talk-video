#!/usr/bin/env bash
# Shrink a huge recording (ProRes, high-bitrate MOV/MP4) to a YouTube-ready H.264 1080p MP4.
# Usage: reencode.sh <in> [out.mp4]      FAST=1 uses the Mac hardware encoder (much faster, slightly larger)
set -euo pipefail
IN="$1"; OUT="${2:-${IN%.*}-h264.mp4}"
if [[ "${FAST:-0}" == 1 ]]; then
  V=(-c:v h264_videotoolbox -b:v 12M -maxrate 16M)
else
  V=(-c:v libx264 -preset medium -crf 16)   # crf 14-18 for anything you publish; "veryfast" looked soft on YouTube
fi
ffmpeg -v warning -stats -y -i "$IN" -vf "scale=-2:'min(1080,ih)'" "${V[@]}" -pix_fmt yuv420p \
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart "$OUT"
echo "$OUT"
