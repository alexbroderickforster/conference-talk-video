#!/usr/bin/env python3
"""Move captions onto a new clock, so they match the exact file being uploaded.

  shift-srt.py <in.srt> --by -12.5 [-o out.srt]
      Shift every cue (e.g. you trimmed 12.5 s off the head of a cut: --by -12.5).
  shift-srt.py <in.srt> --window <start> <end> [-o out.srt]
      Keep only the cues inside [start, end] of a longer recording and restart the clock at start,
      i.e. the captions for a talk you cut from start..end.

Times are seconds, m:ss or h:mm:ss(.ms). Cues pushed before 0:00 are dropped; cues straddling an edge
are clipped. Numbering is redone. Writes to stdout unless -o is given.
"""
import argparse, re, sys

TS = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})")


def secs(t):
    s = 0.0
    for p in str(t).split(":"):
        s = s * 60 + float(p)
    return s


def parse_ts(t):
    h, m, s, ms = map(int, TS.match(t.strip()).groups())
    return h * 3600 + m * 60 + s + ms / 1000


def fmt_ts(x):
    ms = int(round(max(0.0, x) * 1000))
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def read_srt(text):
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = block.split("\n")
        i = next((k for k, l in enumerate(lines) if "-->" in l), None)
        if i is None:
            continue
        a, b = lines[i].split("-->")
        body = "\n".join(lines[i + 1:]).strip()
        if body:
            cues.append([parse_ts(a), parse_ts(b.split()[0]), body])
    return cues


def write_srt(cues):
    return "".join(f"{n}\n{fmt_ts(a)} --> {fmt_ts(b)}\n{t}\n\n" for n, (a, b, t) in enumerate(cues, 1))


def shift(cues, by=0.0, lo=None, hi=None):
    out = []
    for a, b, t in cues:
        if lo is not None and b <= lo:
            continue
        if hi is not None and a >= hi:
            continue
        if lo is not None:
            a = max(a, lo)
        if hi is not None:
            b = min(b, hi)
        a, b = a + by, b + by
        if b <= 0.05:
            continue
        out.append([max(0.0, a), b, t])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("srt")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--by", help="seconds to add (negative = earlier)")
    g.add_argument("--window", nargs=2, metavar=("START", "END"))
    ap.add_argument("-o", "--out")
    a = ap.parse_args(argv)
    cues = read_srt(open(a.srt, encoding="utf-8").read())
    if a.by is not None:
        by = -secs(a.by[1:]) if a.by.startswith("-") else secs(a.by)
        res = shift(cues, by)
    else:
        lo, hi = secs(a.window[0]), secs(a.window[1])
        res = shift(cues, -lo, lo, hi)
    text = write_srt(res)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
        print(f"{a.out}  ({len(res)} cues)", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
