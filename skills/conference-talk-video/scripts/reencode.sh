#!/usr/bin/env bash
# Shrink a huge recording (ProRes, high-bitrate MOV/MP4) to a YouTube-ready H.264 1080p MP4.
# Usage: reencode.sh <in> [out.mp4]
#   FAST=1 uses a hardware encoder if one works here (Mac VideoToolbox, NVIDIA NVENC, Intel QSV):
#   much faster, slightly larger. With none available it falls back to a quick software encode.
set -euo pipefail
IN="$1"; OUT="${2:-${IN%.*}-h264.mp4}"
V=(-c:v libx264 -preset medium -crf 16)   # crf 14-18 for anything you publish; "veryfast" looked soft on YouTube
if [[ "${FAST:-0}" == 1 ]]; then
  V=(-c:v libx264 -preset veryfast -crf 18); HW=""
  for e in h264_videotoolbox h264_nvenc h264_qsv; do   # listed != usable, so try one frame first
    ffmpeg -nostdin -v error -f lavfi -i color=s=256x256:d=0.1 -frames:v 1 -c:v "$e" -f null - 2>/dev/null && { HW=$e; break; }
  done
  if [[ -n "$HW" ]]; then V=(-c:v "$HW" -b:v 12M -maxrate 16M); echo "FAST: using $HW" >&2
  else echo "FAST: no hardware encoder here, using libx264 veryfast" >&2; fi
fi
ffmpeg -nostdin -v warning -stats -y -i "$IN" -vf "scale=-2:'min(1080,ih)'" "${V[@]}" -pix_fmt yuv420p \
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart "$OUT"
echo "$OUT"
