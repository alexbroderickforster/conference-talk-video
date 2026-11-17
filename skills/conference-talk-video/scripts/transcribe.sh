#!/usr/bin/env bash
# Local transcript with word timings. Thin wrapper: see transcribe.py --help.
# Usage: transcribe.sh <video> [start_s] [length_s]  ->  <video>.srt + <video>.json
exec python3 "$(cd "$(dirname "$0")" && pwd)/transcribe.py" "$@"
