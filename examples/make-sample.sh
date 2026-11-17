#!/usr/bin/env bash
# Build a small fake conference recording to try the skill on: about 2.5 minutes with a host,
# two short "talks" and applause, all synthetic (test-pattern video, text-to-speech voices).
# Usage: make-sample.sh [out_dir=examples/out]
# Writes: sample-recording.mp4, schedule.txt, truth.json (where each talk really starts and ends)
# Needs ffmpeg plus a text-to-speech voice: macOS `say` (built in) or espeak-ng / espeak on Linux.
set -euo pipefail
OUT="${1:-$(dirname "$0")/out}"; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
N=0; LIST="$W/list.txt"; : > "$LIST"; T=0; MARKS="$W/marks"; : > "$MARKS"

# speak <voice: host|a|b> <text>: one line of speech, 48 kHz mono WAV, appended to the program
speak(){
  local f="$W/$(printf %03d $N).wav"; N=$((N+1))
  if command -v say >/dev/null; then
    local v; case $1 in host) v=Daniel;; a) v=Samantha;; *) v=Fred;; esac
    say -v "$v" -r 175 -o "$W/s.aiff" "$2" 2>/dev/null || say -r 175 -o "$W/s.aiff" "$2"
    ffmpeg -nostdin -v error -y -i "$W/s.aiff" -ar 48000 -ac 1 -c:a pcm_s16le "$f"
  else
    local e; e=$(command -v espeak-ng || command -v espeak) || { echo "need say, espeak-ng or espeak" >&2; exit 1; }
    local v; case $1 in host) v=en-gb;; a) v=en-us+f3;; *) v=en-us+m3;; esac
    "$e" -v "$v" -s 165 -w "$W/s.wav" "$2"
    ffmpeg -nostdin -v error -y -i "$W/s.wav" -ar 48000 -ac 1 -c:a pcm_s16le "$f"
  fi
  add "$f"
}
gap(){ local f="$W/$(printf %03d $N).wav"; N=$((N+1))
  ffmpeg -nostdin -v error -y -f lavfi -i "anoisesrc=color=brown:amplitude=0.004:r=48000,aformat=channel_layouts=mono" -t "$1" -c:a pcm_s16le "$f"; add "$f"; }
applause(){ local f="$W/$(printf %03d $N).wav"; N=$((N+1))
  ffmpeg -nostdin -v error -y -f lavfi -i "anoisesrc=color=pink:amplitude=0.25:r=48000,aformat=channel_layouts=mono" \
    -af "tremolo=f=9:d=0.6,afade=t=in:d=0.4,afade=t=out:st=$(awk -v d="$1" 'BEGIN{print d-1}'):d=1" -t "$1" -c:a pcm_s16le "$f"; add "$f"; }
add(){ echo "file '$1'" >> "$LIST"
  T=$(awk -v t="$T" -v d="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$1")" 'BEGIN{printf "%.3f", t+d}'); }
mark(){ echo "$1 $T" >> "$MARKS"; }

gap 3
mark t1_start
speak host "Good morning, and welcome back. Please welcome our first speaker, Dana Reyes from Acme Robotics, on shipping robots every week."
applause 3
speak a "Thank you. Two years ago, we shipped new robot software twice a year."
gap 0.6
speak a "Every release was a big event, and every release broke something in the field."
gap 0.6
speak a "So we asked a simple question. What would it take to ship every single week?"
gap 0.6
speak a "The first answer was testing. We built a simulator that runs every change against a thousand recorded shifts."
gap 0.6
speak a "The second answer was rollout. Every update goes to five robots first, then fifty, then the whole fleet."
gap 0.6
speak a "Today we ship every Tuesday, and field incidents are down by two thirds."
gap 0.6
speak a "The lesson is that small batches are safer, not riskier. Thank you very much."
mark t1_speech_end
applause 4
mark t1_end
gap 3          # the next speaker walks up
mark t2_start
speak host "Our next speaker is Sam Okafor from Northwind, on what we learned from four hundred incidents."
applause 3
speak b "Hello everyone. Over three years, my team wrote up four hundred incidents."
gap 0.6
speak b "We read every one of them again last spring, looking for patterns."
gap 0.6
speak b "Pattern one. Most outages started with a change that nobody thought was risky."
gap 0.6
speak b "Pattern two. The fastest recoveries came from teams who could roll back in one step."
gap 0.6
speak b "Pattern three. Blame made the write ups shorter, and the next incident longer."
gap 0.6
speak b "So we made rollback a button, and we made the write ups blameless."
gap 0.6
speak b "Our time to recover has halved. Thanks for listening."
mark t2_speech_end
applause 4
mark t2_end
gap 3
speak host "That's all for this morning. Lunch is served in the main hall."
gap 2

ffmpeg -nostdin -v error -y -f concat -safe 0 -i "$LIST" -c:a pcm_s16le "$W/program.wav"
ffmpeg -nostdin -v error -y -f lavfi -i "testsrc2=s=1280x720:r=30" -i "$W/program.wav" -shortest \
  -c:v libx264 -preset veryfast -crf 26 -pix_fmt yuv420p -c:a aac -b:a 128k -ac 2 -movflags +faststart \
  "$OUT/sample-recording.mp4"

cat > "$OUT/schedule.txt" <<'EOF'
# One talk per line, in running order: [planned time |] speaker | company | title
9:00 | Dana Reyes | Acme Robotics | Shipping robots every week
9:30 | Sam Okafor | Northwind | What we learned from 400 incidents
EOF
python3 - "$MARKS" > "$OUT/truth.json" <<'PY'
import json, sys
m = dict((k, float(v)) for k, v in (l.split() for l in open(sys.argv[1])))
print(json.dumps({"talks": [
  {"speaker": "Dana Reyes", "start": m["t1_start"], "speech_end": m["t1_speech_end"], "end": m["t1_end"]},
  {"speaker": "Sam Okafor", "start": m["t2_start"], "speech_end": m["t2_speech_end"], "end": m["t2_end"]}]}, indent=2))
PY
echo "$OUT/sample-recording.mp4  ($(printf %.0f "$T")s)  + schedule.txt, truth.json"
