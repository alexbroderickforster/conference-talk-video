#!/usr/bin/env python3
"""Print words with their times between two points, marking pauses — use it to pick cut points.
Usage: words.py <transcript.json from transcribe.sh> [from] [to] [--json]   times as s, m:ss or h:mm:ss
  --json prints [{"start","end","word"}...] instead, for scripts.
Cut INSIDE a marked pause, just before the first word you keep / just after the last word."""
import json, sys
def secs(t):
    s = 0.0
    for p in str(t).split(":"): s = s * 60 + float(p)
    return s
def hms(s):
    h, r = divmod(s, 3600); m, r = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{r:05.2f}"
AS_JSON = "--json" in sys.argv
sys.argv = [a for a in sys.argv if a != "--json"]
d = json.load(open(sys.argv[1])); off = d.get("clock_offset_s", 0.0)
lo = secs(sys.argv[2]) if len(sys.argv) > 2 else 0; hi = secs(sys.argv[3]) if len(sys.argv) > 3 else 1e9
words = []
for seg in d["transcription"]:
    for tok in seg.get("tokens", []):
        t = tok["text"]
        if t.startswith("[_") or not t.strip(): continue
        a = tok["offsets"]["from"] / 1000 + off; b = tok["offsets"]["to"] / 1000 + off
        b = max(a, b)                                  # whisper sometimes ends a token before it starts
        if words and not t.startswith(" ") and not words[-1][2].endswith("]"):   # sub-word: glue on
            words[-1][1] = max(words[-1][1], b); words[-1][2] += t
        else:
            words.append([a, b, t.strip()])
words = [w for w in words if not (w[2].startswith("[") and w[2].endswith("]"))]   # [BLANK_AUDIO], [Applause]
if AS_JSON:
    print(json.dumps([{"start": round(a, 3), "end": round(b, 3), "word": w} for a, b, w in words if b >= lo and a <= hi]))
    sys.exit(0)
prev = None
for a, b, w in words:
    if b < lo or a > hi: prev = b; continue
    if prev is not None and a - prev >= 0.3:   # only real gaps (overlapping times print no pause)
        print(f"{'':12}  ---- pause {a-prev:.2f}s  (cut here: {hms(prev + (a-prev)/2)})")
    print(f"{hms(a)}  {w}")
    prev = b
