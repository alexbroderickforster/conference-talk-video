#!/usr/bin/env python3
"""Local transcript with word timings (whisper.cpp; free, about 30x real time on an Apple-silicon Mac).

  transcribe.py <video> [start_s] [length_s]

Writes <video>.srt (captions draft) and <video>.json (word timings for words.py). With start/length it
transcribes only that window (fast boundary checks): the SRT is then on the window's clock, while the
JSON carries clock_offset_s so words.py prints times on the video's clock.

Gap repair: whisper sometimes skips a stretch of speech, typically right after applause or music
(the captions jump ahead 20-30 s). After the main pass this finds caption gaps longer than GAP_S
(default 6) that still contain sound, transcribes each gap again on its own and merges the result.
REPAIR=0 turns it off.

Needs ffmpeg, whisper.cpp (whisper-cli, or set WHISPER_BIN) and WHISPER_MODEL. Run doctor.sh to check.
"""
import json, os, re, shutil, subprocess, sys, tempfile


def die(msg):
    print(msg, file=sys.stderr); sys.exit(1)


def whisper_bin():
    for c in (os.environ.get("WHISPER_BIN"), "whisper-cli", "whisper-cpp"):
        if c and shutil.which(c):
            return c
    die("whisper.cpp not found (brew install whisper-cpp, or set WHISPER_BIN). Run doctor.sh.")


def run_whisper(wav, model, outbase):
    threads = str(os.cpu_count() or 4)
    r = subprocess.run([whisper_bin(), "-m", model, "-l", "en", "-t", threads, "-f", wav, "-ojf", "-of", outbase],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(outbase + ".json"):
        die(r.stderr[-2000:] + "\nwhisper failed (run doctor.sh)")
    return json.load(open(outbase + ".json"))["transcription"]


def ts(ms):
    ms = int(max(0, ms)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def shift(segs, ms):
    for s in segs:
        s["offsets"] = {"from": s["offsets"]["from"] + ms, "to": s["offsets"]["to"] + ms}
        s["timestamps"] = {"from": ts(s["offsets"]["from"]), "to": ts(s["offsets"]["to"])}
        for t in s.get("tokens", []):
            if "offsets" in t:
                t["offsets"] = {"from": t["offsets"]["from"] + ms, "to": t["offsets"]["to"] + ms}
    return segs


def spoken(seg):
    t = seg.get("text", "").strip()
    return bool(t) and not re.fullmatch(r"[\[(].*[\])]", t)


def quiet_seconds(wav, a, b):
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", wav,
                        "-af", "silencedetect=noise=-35dB:d=0.3", "-f", "null", "-"], capture_output=True, text=True)
    return sum(float(x) for x in re.findall(r"silence_duration: ([\d.]+)", r.stderr))


def caption_gaps(segs, dur, gap_s):
    edges = [0.0] + [x for s in segs if spoken(s) for x in (s["offsets"]["from"] / 1000, s["offsets"]["to"] / 1000)] + [dur]
    return [(edges[i], edges[i + 1]) for i in range(0, len(edges) - 1, 2) if edges[i + 1] - edges[i] >= gap_s]


def retranscribe(wav, a, b, dur, model, tmp, tag):
    lo, hi = max(0.0, a - 0.5), min(dur, b + 0.5)
    part = os.path.join(tmp, f"gap{tag}.wav")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{lo:.3f}", "-t", f"{hi - lo:.3f}", "-i", wav,
                    "-c:a", "pcm_s16le", part], check=True)
    new = [s for s in shift(run_whisper(part, model, os.path.join(tmp, f"gap{tag}")), int(lo * 1000)) if spoken(s)]
    mid = lambda s: (s["offsets"]["from"] + s["offsets"]["to"]) / 2000
    return [s for s in new if a <= mid(s) <= b]       # keep lines centred in the gap (edges overlap 0.5 s)


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def dedupe_seams(segs, recovered):
    """A recovered line can end with the words the next line starts with (the slices overlap). Drop them."""
    ids = {id(s) for s in recovered}
    for i in range(len(segs) - 1):
        r, e = segs[i], segs[i + 1]
        if id(r) not in ids or e["offsets"]["from"] > r["offsets"]["to"] + 1500:
            continue
        rw, ew = r["text"].split(), e["text"].split()
        rn, en = [norm(w) for w in rw], [norm(w) for w in ew]
        done = False
        for k in range(min(6, len(rw) - 1), 1, -1):          # 2+ words repeated near the start of the next line
            for j in range(0, 3):
                if rn[-k:] == en[j:j + k]:
                    r["text"] = " " + " ".join(rw[:-k]); done = True; break
            if done:
                break


def repair(segs, wav, dur, model, tmp):
    """Re-transcribe caption gaps that still contain sound. Up to 4 passes; a gap that yields nothing
    is split in half (whisper also skips speech that follows applause inside the gap)."""
    gap_s = float(os.environ.get("GAP_S", "6"))
    todo, tried, n, recovered = caption_gaps(segs, dur, gap_s), set(), 0, []
    for _ in range(4):
        nxt = []
        for a, b in todo:
            key = (round(a, 1), round(b, 1))
            if key in tried or (b - a) - quiet_seconds(wav, a, b) < 2.0:
                continue
            tried.add(key); n += 1
            new = retranscribe(wav, a, b, dur, model, tmp, n)
            if new:
                segs.extend(new); recovered.extend(new)
                print(f"  caption gap {a:.1f}-{b:.1f}s: recovered {len(new)} lines", file=sys.stderr)
            elif b - a >= 4:
                m = (a + b) / 2; nxt += [(a, m + 0.5), (m - 0.5, b)]
        segs.sort(key=lambda s: s["offsets"]["from"])
        nxt += [g for g in caption_gaps(segs, dur, gap_s) if (round(g[0], 1), round(g[1], 1)) not in tried]
        if not nxt:
            break
        todo = nxt
    dedupe_seams(segs, recovered)
    left = [g for g in caption_gaps(segs, dur, gap_s) if (g[1] - g[0]) - quiet_seconds(wav, *g) >= 2.0]
    for a, b in left:
        print(f"  WARNING: no captions for {a:.1f}-{b:.1f}s but there is sound (applause/music, or missed speech): check it", file=sys.stderr)


def main(argv=None):
    a = argv if argv is not None else sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return 0
    video, ss = a[0], float(a[1]) if len(a) > 1 else 0.0
    length = float(a[2]) if len(a) > 2 else None
    model = os.environ.get("WHISPER_MODEL") or die("set WHISPER_MODEL to a ggml model file (doctor.sh --get-model small.en)")
    base = os.path.splitext(video)[0] + (f".at{int(ss)}" if length else "")
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(ss)] + (["-t", str(length)] if length else []) + \
              ["-i", video, "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav]
        subprocess.run(cmd, check=True)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav],
                                   capture_output=True, text=True).stdout.strip())
        segs = run_whisper(wav, model, os.path.join(tmp, "out"))
        if os.environ.get("REPAIR", "1") != "0":
            repair(segs, wav, dur, model, tmp)
    json.dump({"clock_offset_s": ss, "transcription": segs}, open(base + ".json", "w"))
    with open(base + ".srt", "w", encoding="utf-8") as f:
        for n, s in enumerate([s for s in segs if spoken(s)], 1):
            f.write(f"{n}\n{ts(s['offsets']['from'])} --> {ts(s['offsets']['to'])}\n{s['text'].strip()}\n\n")
    print(f"{base}.srt  {base}.json  (word times = file clock; offset {ss:g}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
