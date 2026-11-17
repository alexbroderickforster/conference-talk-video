#!/usr/bin/env bash
# Run the whole pipeline on the synthetic sample, without Claude, so you can see every step work.
# In real use Claude makes the judgment calls (where a talk ends, chapter names, the summary);
# here simple rules stand in for it so the run is repeatable.
# Usage: WHISPER_MODEL=... run-sample.sh [out_dir=examples/out]
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); S="$HERE/../skills/conference-talk-video/scripts"
OUT="${1:-$HERE/out}"; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
step(){ printf '\n== %s\n' "$1"; }

step "0. Check tools";            "$S/doctor.sh"
step "Make the sample recording"; "$HERE/make-sample.sh" "$OUT"
REC="$OUT/sample-recording.mp4"
step "2. Transcribe";             "$S/transcribe.sh" "$REC"
step "3. Find each talk";         "$S/find-talks.py" "$OUT/sample-recording.srt" "$OUT/schedule.txt"
"$S/find-talks.py" "$OUT/sample-recording.srt" "$OUT/schedule.txt" --json > "$OUT/found.json"

# Boundaries. In real use Claude reads the transcript and decides (SKILL.md step 3). The sample has a
# few seconds of quiet between talks (the next speaker walking up), so two fixed rules stand in here:
#   start = the host's intro (find-talks hint), snapped to the quiet just before speech resumes
#   end   = the first quiet stretch of 1.5 s+ after the talk is under way (the applause has ended)
: > "$OUT/cuts.tsv"
python3 -c "
import json,sys
for t in json.load(open(sys.argv[1])):
    if t['start_hint'] is None: sys.exit('no intro found for '+t['speaker'])
    print('\t'.join([t['speaker'].lower().replace(' ','-'), str(t['start_hint']), t['speaker'], t['company'], t['title']]))
" "$OUT/found.json" > "$OUT/plan.tsv"
while IFS=$'\t' read -r slug hint speaker company title <&3; do
  start=$(MIN_SILENCE=1.5 "$S/snap.py" start "$REC" "$hint")
  end=$(MIN_SILENCE=1.5 "$S/snap.py" list "$REC" "$(awk -v s="$start" 'BEGIN{print s+10}')" 100000 | awk 'NR==1{printf "%.2f", $1+0.3}')
  [[ -n "$end" ]] || { echo "no quiet stretch after $speaker's talk"; exit 1; }
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$slug" "$start" "$end" "$speaker" "$company" "$title" >> "$OUT/cuts.tsv"
  echo "  $speaker: intro near ${hint}s -> cut ${start}s .. ${end}s"
done 3< "$OUT/plan.tsv"

while IFS=$'\t' read -r slug start end speaker company title <&3; do
  T="$OUT/$slug.mp4"
  step "4. Cut: $speaker";          "$S/cut.sh" "$REC" "$start" "$end" "$T"
  step "5. Review copy";            "$S/review-proxy.sh" "$T" 15
  step "6. YouTube text";           "$S/transcribe.sh" "$T" >/dev/null
  "$S/youtube-text.py" suggest "$OUT/$slug.srt" --n 4 | tee "$OUT/$slug.suggest.txt"
  # Claude would name these; the demo uses each point's first few words.
  python3 - "$OUT/$slug.suggest.txt" > "$OUT/$slug.chapters.txt" <<'PY'
import re, sys
for line in open(sys.argv[1]):
    m = re.match(r"\s*(\d+(?::\d+)+)\s+(.+)", line)
    if m:
        w = re.sub(r"[^\w' ]", "", m.group(2)).split()[:5]
        print(m.group(1), (" ".join(w) or "Intro").capitalize()[:45])
PY
  "$S/youtube-text.py" build "$T" --title "$title" --speaker "$speaker" --company "$company" \
    --event "Example Summit" --link "Slides: https://example.com/$slug" \
    --summary "A short demo talk from the synthetic sample recording." --chapters "$OUT/$slug.chapters.txt"
  step "7. Upload (dry run: nothing is sent)"; "$S/upload.py" "$T" --dry-run | head -8
done 3< "$OUT/cuts.tsv"
printf '\nDone. Open %s: each talk has .mp4, -review.mp4, .srt and .youtube.md\n' "$OUT"
