#!/usr/bin/env bash
# Run all tests. Unit tests always; the end-to-end run on the synthetic sample when ffmpeg,
# whisper.cpp and WHISPER_MODEL are available (or E2E=1 to insist).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
echo "== unit tests"
python3 -W ignore::ResourceWarning -m unittest discover -s "$ROOT/tests" -v 2>&1 | tail -n 25

if [[ -z "${WHISPER_MODEL:-}" || ! -s "${WHISPER_MODEL:-/nonexistent}" ]]; then
  [[ "${E2E:-0}" == 1 ]] && { echo "E2E=1 but WHISPER_MODEL is not set"; exit 1; }
  echo "== end-to-end: skipped (set WHISPER_MODEL to run it)"; exit 0
fi

echo "== end-to-end on the synthetic sample"
OUT="$ROOT/tests/out"; rm -rf "$OUT"
"$ROOT/examples/run-sample.sh" "$OUT" > "$OUT.log" 2>&1 || { tail -40 "$OUT.log"; exit 1; }
python3 - "$OUT" <<'PY'
import json, os, re, subprocess, sys
out = sys.argv[1]; fails = []
truth = json.load(open(f"{out}/truth.json"))["talks"]
cuts = [l.rstrip("\n").split("\t") for l in open(f"{out}/cuts.tsv")]
def probe(p, *a):
    return subprocess.run(["ffprobe", "-v", "error", *a, "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip()
for t, c in zip(truth, cuts):
    slug, start, end = c[0], float(c[1]), float(c[2])
    if not (t["start"] - 1.5 <= start <= t["start"] + 0.05):
        fails.append(f"{slug}: start {start:.2f} not just before the host's first word at {t['start']:.2f}")
    if end < t["speech_end"] + 0.5:
        fails.append(f"{slug}: end {end:.2f} cuts into the speaker (last word ends {t['speech_end']:.2f})")
    nxt = [x for x in truth if x["start"] > t["start"]]
    if nxt and end > nxt[0]["start"]:
        fails.append(f"{slug}: end {end:.2f} runs into the next talk ({nxt[0]['start']:.2f})")
    for f in (".mp4", "-review.mp4", ".srt", ".youtube.md"):
        if not os.path.getsize(f"{out}/{slug}{f}") > 0:
            fails.append(f"missing {slug}{f}")
    wh = probe(f"{out}/{slug}-review.mp4", "-select_streams", "v:0", "-show_entries", "stream=width,height")
    if wh != "960,540":
        fails.append(f"{slug}-review.mp4 is {wh}, expected 960,540")
    md = open(f"{out}/{slug}.youtube.md").read()
    if not re.search(r"^0:00 ", md, re.M):
        fails.append(f"{slug}.youtube.md has no 0:00 chapter")
    srt = open(f"{out}/{slug}.srt").read()
    times = [int(h) * 3600 + int(m) * 60 + int(s) for h, m, s in re.findall(r"(\d+):(\d+):(\d+),\d+ -->", srt)]
    gaps = [b - a for a, b in zip(times, times[1:])]
    if gaps and max(gaps) > 15:
        fails.append(f"{slug}.srt has a {max(gaps)}s hole in the captions")
    texts = [re.sub(r"\W+", " ", t).strip().lower() for t in re.findall(r"-->[^\n]*\n(.+)", srt)]
    if any(a == b for a, b in zip(texts, texts[1:])):
        fails.append(f"{slug}.srt repeats a caption line")
    print(f"  {slug}: cut {start:.2f}-{end:.2f}s (truth {t['start']:.2f}-{t['end']:.2f}s)")
log = open(out + ".log").read()
if "PROBLEM:" in log:
    fails += [l.strip() for l in log.splitlines() if "PROBLEM:" in l]
if fails:
    print("FAIL\n  " + "\n  ".join(fails)); sys.exit(1)
print("  all end-to-end checks passed")
PY
