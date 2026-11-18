#!/usr/bin/env python3
"""List stretches of a video that have sound but no captions: usually applause or music, sometimes
speech whisper skipped (it can jump 20-30 s ahead right after applause).

  caption-gaps.py <video> <captions.srt> [--min 6]

Run it on any SRT before uploading. A listed gap with speech in it means: re-transcribe that file with
transcribe.py (which repairs these gaps) or fix the SRT by hand. Exit 1 when a gap with sound is found.
Env: NOISE=-35dB (quiet threshold for silencedetect).
"""
import os, re, subprocess, sys


def cues(path):
    t = open(path, encoding="utf-8").read()
    pat = r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)"
    sec = lambda h, m, s, ms: int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    return [(sec(*x[:4]), sec(*x[4:])) for x in re.findall(pat, t)]


def uncovered(intervals, dur, min_len):
    """Stretches of at least min_len seconds that no cue covers. Cues are merged first, so a long cue
    with shorter ones nested inside it leaves no false gap. Cue times are clamped to the media length,
    so a cue past the end never makes nonexistent audio count as sound."""
    merged = []
    for a, b in sorted((min(a, dur), min(b, dur)) for a, b in intervals):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    gaps, t = [], 0.0
    for a, b in merged:
        if a - t >= min_len:
            gaps.append((t, a))
        t = max(t, b)
    if dur - t >= min_len:
        gaps.append((t, dur))
    return gaps


def quiet(video, a, b):
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", video, "-vn",
                        "-af", f"silencedetect=noise={os.environ.get('NOISE', '-35dB')}:d=0.3", "-f", "null", "-"],
                       capture_output=True, text=True)
    return sum(float(x) for x in re.findall(r"silence_duration: ([\d.]+)", r.stderr))


def main(argv=None):
    a = argv if argv is not None else sys.argv[1:]
    if len(a) < 2:
        print(__doc__); return 2
    video, srt = a[0], a[1]
    mn = float(a[a.index("--min") + 1]) if "--min" in a else 6.0
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                               capture_output=True, text=True).stdout.strip())
    bad = 0
    for g0, g1 in uncovered(cues(srt), dur, mn):
        sound = (g1 - g0) - quiet(video, g0, g1)
        if sound >= 2.0:
            bad += 1
            print(f"{g0:8.1f}-{g1:8.1f}s  {g1 - g0:5.1f}s without captions, {sound:4.1f}s of it has sound: listen")
    print(f"{bad} gap(s) with sound" if bad else "no caption gaps with sound")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
