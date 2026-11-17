#!/usr/bin/env python3
"""Snap a rough cut point to the real gap in the audio.

Whisper's word times can be off by a second or more, worst right after a silence (it often puts the
first word at the start of the quiet). This listens to the audio itself (ffmpeg silencedetect)
and moves the cut into the actual quiet stretch.

  snap.py start <video> <approx>   approx = where words.py says the first kept word starts.
                                   Prints a time just before speech resumes (0.25 s of room tone kept).
  snap.py end   <video> <approx>   approx = where the last kept word (or the applause) ends.
                                   Prints a time just into the next quiet stretch (which must begin
                                   within 5 s of approx).
  snap.py list  <video> <from> <to>  Lists the quiet stretches in a range.

Env: NOISE=-35dB (raise toward -30dB for a noisy room), MIN_SILENCE=0.3 (seconds).
If no quiet stretch is found nearby it says so and exits 1: then cut from words.py's pause instead.
"""
import os, re, subprocess, sys


def secs(t):
    s = 0.0
    for p in str(t).split(":"):
        s = s * 60 + float(p)
    return s


def silences(video, lo, hi):
    lo = max(0.0, lo)
    noise, mind = os.environ.get("NOISE", "-35dB"), os.environ.get("MIN_SILENCE", "0.3")
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-ss", f"{lo:.3f}", "-t", f"{hi - lo:.3f}", "-i", video,
                        "-vn", "-af", f"silencedetect=noise={noise}:d={mind}", "-f", "null", "-"],
                       capture_output=True, text=True)
    out, start = [], None
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1))) + lo
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            out.append((start, float(m.group(1)) + lo)); start = None
    if start is not None:
        out.append((start, hi))
    return out


def snap_start(video, approx, early=1.0, late=0.5):
    """The quiet stretch the first kept word comes out of. Whisper's estimate can be early (it puts the
    word at the start of the quiet), so the stretch may end after approx; but it must START by
    approx + late, or it is a pause inside the speech and cutting there would drop the opening words."""
    for a, b in silences(video, approx - 20, approx + 20):
        if b >= approx - early and a <= approx + late:
            return max(a, b - 0.25)
    return None


def snap_end(video, approx, early=0.3, late=5.0):
    """The first quiet stretch that begins after the last kept word (or applause) ends. A stretch that
    begins more than `late` seconds later is not this boundary: refuse rather than keep the next speaker."""
    for a, b in silences(video, approx - 5, approx + late + 5):
        if a >= approx - early:
            return min(b, a + 0.3) if a <= approx + late else None
    return None


def main(argv=None):
    a = argv if argv is not None else sys.argv[1:]
    if len(a) < 3 or a[0] not in ("start", "end", "list"):
        print(__doc__); return 2
    if a[0] == "list":
        for s, e in silences(a[1], secs(a[2]), secs(a[3])):
            print(f"{s:9.2f} – {e:9.2f}  ({e - s:.2f}s quiet)")
        return 0
    t = (snap_start if a[0] == "start" else snap_end)(a[1], secs(a[2]))
    if t is None:
        print(f"no quiet stretch near {a[2]}s (try NOISE=-30dB, or cut from words.py's pause)", file=sys.stderr)
        return 1
    print(f"{t:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
