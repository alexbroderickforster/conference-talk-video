#!/usr/bin/env python3
"""Find where each scheduled talk starts in a recording, by spotting the speaker's name in the transcript.

  find-talks.py <recording.srt> <schedule.txt> [--json]

schedule.txt has one talk per line, in running order (lines starting with # are ignored):
    9:05 | Dana Reyes | Acme Robotics | Shipping robots weekly
    Sam Okafor | Northwind | What we learned from 400 incidents
The time is optional and is only a hint (the program's planned start, not the file's clock).

For each speaker it prints the cues that mention their name (whisper often misspells names, so
matching is fuzzy) and the best candidate for where the host starts introducing them: the first
mention after the previous talk's candidate. Treat the output as a lead to check with
transcribe.sh + words.py, never as the final cut point.
"""
import difflib, re, sys

TS = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})")


def ts(t):
    h, m, s, ms = map(int, TS.match(t.strip()).groups())
    return h * 3600 + m * 60 + s + ms / 1000


def hms(x):
    h, r = divmod(x, 3600); m, r = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{r:05.2f}"


def read_srt(path):
    cues = []
    for block in re.split(r"\n\s*\n", open(path, encoding="utf-8").read().replace("\r\n", "\n").strip()):
        lines = block.split("\n")
        i = next((k for k, l in enumerate(lines) if "-->" in l), None)
        if i is None:
            continue
        a, b = lines[i].split("-->")
        cues.append((ts(a), ts(b.split()[0]), " ".join(lines[i + 1:]).strip()))
    return cues


def read_schedule(path):
    talks = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if re.fullmatch(r"\d{1,2}:\d{2}", parts[0]):
            parts = parts[1:]
        parts += [""] * (3 - len(parts))
        talks.append({"speaker": parts[0], "company": parts[1], "title": parts[2]})
    return talks


def words(s):
    return re.findall(r"[a-z0-9']+", s.lower())


def score(name, text, company=""):
    """How well a cue matches the speaker, 0..1. Whisper often garbles surnames ("Reyes" -> "Raised"),
    so an exact first name, or the company named in the same line, also counts."""
    parts = [p for p in words(name) if len(p) > 2] or words(name)
    if not parts:
        return 0.0
    tw = words(text)
    def best(p):
        return max((difflib.SequenceMatcher(None, p, w).ratio() for w in tw), default=0.0)
    last = best(parts[-1])
    first = best(parts[0]) if len(parts) > 1 else last
    joined = "".join(parts)                      # "Samokafa": whisper glued first name and surname
    glued = max((difflib.SequenceMatcher(None, joined, w).ratio() for w in tw if len(w) >= len(joined) - 3), default=0.0)
    sc = max(last, glued, 0.6 * first + 0.4 * last if first >= 0.9 else 0.0)
    cw = [w for w in words(company) if len(w) > 2 and w not in ("inc", "ltd", "llc", "the", "and")]
    if cw and max(best(w) for w in cw) >= 0.85:
        sc = min(1.0, sc + 0.15)
    return sc


def find(cues, talks, threshold=0.8):
    results, after = [], -1.0
    for t in talks:
        hits = [(a, b, txt, score(t["speaker"], txt, t.get("company", ""))) for a, b, txt in cues]
        hits = [h for h in hits if h[3] >= threshold]
        later = [h for h in hits if h[0] > after]
        cand = later[0][0] if later else None
        if cand is not None:
            after = cand
        results.append({**t, "start_hint": cand, "mentions": hits})
    return results


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    as_json = "--json" in argv
    argv = [x for x in argv if x != "--json"]
    if len(argv) != 2:
        print(__doc__); sys.exit(2)
    cues, talks = read_srt(argv[0]), read_schedule(argv[1])
    res = find(cues, talks)
    if as_json:
        import json
        print(json.dumps([{k: r[k] for k in ("speaker", "company", "title", "start_hint")} for r in res], indent=2))
        return
    for n, r in enumerate(res, 1):
        head = f"{n}. {r['speaker']}" + (f" ({r['company']})" if r["company"] else "") + (f": {r['title']}" if r["title"] else "")
        print(head)
        if r["start_hint"] is None:
            print("   no mention found: look for the host's intro by reading the SRT around the expected time")
        else:
            print(f"   likely intro starts near {hms(r['start_hint'])}")
        for a, _, txt, sc in r["mentions"][:6]:
            print(f"     {hms(a)}  ({sc:.2f})  {txt[:90]}")
    print("\nCheck each start with: transcribe.sh <recording> <start-20> 40, then words.py")


if __name__ == "__main__":
    main()
