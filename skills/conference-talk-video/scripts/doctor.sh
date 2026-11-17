#!/usr/bin/env bash
# Check that everything the skill needs is installed, and say exactly how to fix what isn't.
# Usage: doctor.sh                 check only
#        doctor.sh --get-model [small.en]   also download a whisper model to ~/.cache/whisper/
#                                  (tiny.en 75 MB · base.en 142 MB · small.en 466 MB · medium.en 1.5 GB)
set -uo pipefail
OK=0; MAC=0; [[ "$(uname -s)" == Darwin ]] && MAC=1
pass(){ printf '  ok    %s\n' "$1"; }
fail(){ printf '  MISSING  %s\n        fix: %s\n' "$1" "$2"; OK=1; }
inst(){ if [[ $MAC == 1 ]]; then echo "brew install $1"; else echo "$2"; fi; }

echo "conference-talk-video: checking tools"
for t in ffmpeg ffprobe; do
  if command -v "$t" >/dev/null; then pass "$t ($("$t" -version 2>/dev/null | head -1 | awk '{print $3}'))"
  else fail "$t" "$(inst ffmpeg 'sudo apt install ffmpeg')"; fi
done
if command -v python3 >/dev/null; then pass "python3 ($(python3 -V 2>&1 | awk '{print $2}'))"
else fail python3 "$(inst python 'sudo apt install python3')"; fi

WB="${WHISPER_BIN:-}"
if [[ -z "$WB" ]]; then for c in whisper-cli whisper-cpp; do command -v "$c" >/dev/null && { WB="$c"; break; }; done; fi
if [[ -n "$WB" ]] && command -v "$WB" >/dev/null; then pass "whisper.cpp ($WB)"
else fail "whisper.cpp (whisper-cli)" "$(inst whisper-cpp 'build it: https://github.com/ggml-org/whisper.cpp#quick-start, then set WHISPER_BIN=/path/to/whisper-cli')"; fi

if [[ "${1:-}" == --get-model ]]; then
  M="${2:-small.en}"; DEST="$HOME/.cache/whisper/ggml-$M.bin"
  if [[ -s "$DEST" ]]; then echo "  model already at $DEST"
  else
    mkdir -p "$(dirname "$DEST")"
    echo "  downloading ggml-$M.bin from huggingface.co/ggerganov/whisper.cpp ..."
    curl -fL --progress-bar -o "$DEST.part" "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$M.bin" \
      && mv "$DEST.part" "$DEST" || { rm -f "$DEST.part"; fail "model download" "check the model name (tiny.en, base.en, small.en, medium.en)"; }
  fi
  [[ -s "$DEST" ]] && { echo "  now run:  export WHISPER_MODEL=$DEST"; export WHISPER_MODEL="$DEST"; }
fi

if [[ -n "${WHISPER_MODEL:-}" && -s "${WHISPER_MODEL}" ]]; then pass "WHISPER_MODEL ($(basename "$WHISPER_MODEL"))"
elif [[ -n "${WHISPER_MODEL:-}" ]]; then fail "WHISPER_MODEL points at a missing file: $WHISPER_MODEL" "$0 --get-model small.en"
else
  FOUND=$(ls "$HOME"/.cache/whisper/ggml-*.bin 2>/dev/null | head -1)
  if [[ -n "$FOUND" ]]; then fail "WHISPER_MODEL not set" "export WHISPER_MODEL=$FOUND"
  else fail "a whisper model" "$0 --get-model small.en   (then export WHISPER_MODEL as it says)"; fi
fi

if command -v ffmpeg >/dev/null; then
  HW=none
  for e in h264_videotoolbox h264_nvenc h264_qsv; do
    ffmpeg -nostdin -v error -f lavfi -i color=s=256x256:d=0.1 -frames:v 1 -c:v "$e" -f null - 2>/dev/null && { HW=$e; break; }
  done
  [[ $HW == none ]] && pass "hardware encoder: none (FAST=1 falls back to a quick software encode)" || pass "hardware encoder: $HW (FAST=1 uses it)"
fi
[[ $OK == 0 ]] && echo "All set." || echo "Fix the MISSING items above, then run this again."
exit $OK
