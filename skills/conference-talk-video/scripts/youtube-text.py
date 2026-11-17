#!/usr/bin/env python3
"""Write and check the YouTube text for one talk: title, description with chapters, tags.

Suggest chapter points from the cut's own transcript (you then name them):
  youtube-text.py suggest talk.srt [--n 8]

Build talk.youtube.md (and check it against YouTube's rules):
  youtube-text.py build talk.mp4 --title "Shipping robots weekly" --speaker "Dana Reyes" \
      --company "Acme Robotics" --event "Example Summit 2026" \
      --link "Slides: https://example.com/slides" --summary "Two or three sentences." \
      --chapters chapters.txt [--tags "extra, tags"] [--srt talk.srt] [-o talk.youtube.md]

chapters.txt: one chapter per line, "m:ss Title" (the first must be 0:00).

Rules checked: title <= 100 characters; description <= 5,000 characters and no < or >;
at least 3 chapters, the first at 0:00, in order, each at least 10 s long, titles <= 45 characters;
tags <= 500 characters in total. Problems are listed and the exit code is 1.
"""
import argparse, os, re, subprocess, sys

TS = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})")


def secs(t):
    s = 0.0
    for p in str(t).split(":"):
        s = s * 60 + float(p)
    return s


def clock(x):
    x = int(round(x)); h, r = divmod(x, 3600); m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def read_srt(path):
    cues = []
    for block in re.split(r"\n\s*\n", open(path, encoding="utf-8").read().replace("\r\n", "\n").strip()):
        lines = block.split("\n")
        i = next((k for k, l in enumerate(lines) if "-->" in l), None)
        if i is None:
            continue
        a, b = lines[i].split("-->")
        f = lambda t: (lambda h, m, s, ms: h * 3600 + m * 60 + s + ms / 1000)(*map(int, TS.match(t.strip()).groups()))
        cues.append((f(a), f(b.split()[0]), " ".join(lines[i + 1:]).strip()))
    return cues


def duration(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True, check=True).stdout
        return float(out.strip())
    except Exception:
        return None


def suggest(cues, n=8):
    """Pick n chapter starts near even intervals, preferring cues that follow a long pause."""
    if not cues:
        return []
    end = cues[-1][1]
    picks = [0.0]
    for k in range(1, n):
        target, half = k * end / n, end / n / 3
        best, bestgap = None, -1
        for i, (a, _, _) in enumerate(cues):
            if abs(a - target) <= half and a - picks[-1] >= 10:
                gap = a - cues[i - 1][1] if i else 0
                if gap > bestgap:
                    best, bestgap = a, gap
        if best is not None:
            picks.append(best)
    return [(p, next(t for a, _, t in cues if a >= p - 0.001)) for p in picks]


def read_chapters(path):
    ch = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"(\d+(?::\d{1,2}){1,2})\s*[-–—]?\s*(.+)", line)
        if not m:
            raise SystemExit(f"chapters: can't read line: {line!r} (want 'm:ss Title')")
        ch.append((secs(m.group(1)), m.group(2).strip()))
    return ch


def check(title, desc, chapters, tags, dur=None):
    p = []
    if len(title) > 100:
        p.append(f"title is {len(title)} characters (max 100)")
    if len(desc) > 5000:
        p.append(f"description is {len(desc)} characters (max 5,000)")
    if "<" in desc or ">" in desc or "<" in title or ">" in title:
        p.append("YouTube rejects < and > in titles and descriptions")
    if len(chapters) < 3:
        p.append(f"{len(chapters)} chapters (YouTube needs at least 3)")
    if chapters and chapters[0][0] != 0:
        p.append("the first chapter must start at 0:00")
    ends = [c[0] for c in chapters[1:]] + ([dur] if dur else [])
    for (a, t), b in zip(chapters, ends):
        if b - a < 10:
            p.append(f"chapter '{t}' at {clock(a)} is {b - a:.0f}s long (min 10s)")
    for i in range(1, len(chapters)):
        if chapters[i][0] <= chapters[i - 1][0]:
            p.append(f"chapter at {clock(chapters[i][0])} is out of order")
    if dur and chapters and chapters[-1][0] >= dur:
        p.append(f"last chapter {clock(chapters[-1][0])} is past the end of the video ({clock(dur)})")
    for _, t in chapters:
        if len(t) > 45:
            p.append(f"chapter title over 45 characters: {t!r}")
    if len(",".join(tags)) > 500:
        p.append(f"tags total {len(','.join(tags))} characters (max 500)")
    return p


def build(a):
    chapters = read_chapters(a.chapters)
    dur = duration(a.video)
    who = a.speaker + (f" ({a.company})" if a.company else "")
    title = f"{a.title} — {who}"
    lines = []
    if a.link:
        lines += [a.link, ""]
    if a.summary:
        lines += [a.summary.strip(), ""]
    lines += [f"Speaker: {who}" + (f" at {a.event}" if a.event else ""), "", "Chapters:"]
    lines += [f"{clock(t)} {name}" for t, name in chapters]
    desc = "\n".join(lines)
    tags = [a.speaker] + ([a.company] if a.company else []) + ([a.event] if a.event else [])
    tags += [t.strip() for t in (a.tags or "").split(",") if t.strip()]
    tags = list(dict.fromkeys(tags))
    srt = a.srt or os.path.splitext(a.video)[0] + ".srt"
    out = a.out or os.path.splitext(a.video)[0] + ".youtube.md"
    md = (f"# YouTube text: {os.path.basename(a.video)}\n\n## Title\n{title}\n\n## Description\n{desc}\n\n"
          f"## Tags\n{', '.join(tags)}\n\n## Captions\n{os.path.basename(srt)}"
          f"{'' if os.path.exists(srt) else '  (NOT FOUND: run transcribe.sh on this exact file)'}\n"
          "Upload as a caption track: Subtitles → Upload file → With timing.\n")
    open(out, "w", encoding="utf-8").write(md)
    problems = check(title, desc, chapters, tags, dur)
    print(out)
    for q in problems:
        print("  PROBLEM:", q)
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("suggest"); s.add_argument("srt"); s.add_argument("--n", type=int, default=8)
    b = sub.add_parser("build"); b.add_argument("video")
    for f in ("title", "speaker", "chapters"):
        b.add_argument(f"--{f}", required=True)
    for f in ("company", "event", "link", "summary", "tags", "srt"):
        b.add_argument(f"--{f}")
    b.add_argument("-o", "--out")
    a = ap.parse_args(argv)
    if a.cmd == "suggest":
        for t, text in suggest(read_srt(a.srt), a.n):
            print(f"{clock(t):>8}  {text[:80]}")
        print("\nName each point (<= 45 characters, sentence case) and save as chapters.txt: 'm:ss Title' per line.")
        return 0
    return build(a)


if __name__ == "__main__":
    sys.exit(main())
