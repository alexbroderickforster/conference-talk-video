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

# Boundaries. Claude reads the transcript and decides; this demo uses fixed rules instead:
#   start = the host's intro (find-talks hint), snapped to the real quiet just before speech (snap.py)
#   end   = the speaker's last word before the long gap (applause), snapped to the quiet after it
"$S/words.py" "$OUT/sample-recording.json" --json > "$OUT/words.json"
python3 - "$OUT/found.json" "$OUT/words.json" > "$OUT/plan.tsv" <<'PY2'
import json, sys
found, words = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
for i, t in enumerate(found):
    if t["start_hint"] is None:
        sys.exit(f"no intro found for {t['speaker']}")
    nxt = found[i + 1]["start_hint"] if i + 1 < len(found) else 1e9
    span = [k for k, w in enumerate(words[:-1]) if t["start_hint"] <= w["start"] < nxt]
    last = [k for k in span if words[k + 1]["start"] - words[k]["end"] >= 2.5]
    if not last:
        sys.exit(f"can't find where {t['speaker']} stops talking")
    slug = t["speaker"].lower().replace(" ", "-")
    print("\t".join([slug, f"{t['start_hint']:.2f}", f"{words[last[-1]]['end'] + 1.0:.2f}", t["speaker"], t["company"], t["title"]]))
PY2
: > "$OUT/cuts.tsv"
while IFS=$'\t' read -r slug hint last speaker company title <&3; do
  start=$("$S/snap.py" start "$REC" "$hint"); end=$("$S/snap.py" end "$REC" "$last")
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
