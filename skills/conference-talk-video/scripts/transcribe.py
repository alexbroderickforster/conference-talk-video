#!/usr/bin/env python3
"""Local transcript with word timings (whisper.cpp; free, about 30x real time on an Apple-silicon Mac).

  transcribe.py <video> [start_s] [length_s] [--force]

Writes <video>.srt (captions draft) and <video>.json (word timings for words.py). With start/length it
transcribes only that window (fast boundary checks): the SRT is then on the window's clock, while the
JSON carries clock_offset_s so words.py prints times on the video's clock. A window that starts before
0:00 is clamped to 0:00. A whole-file run refuses to replace an existing <video>.srt (it may hold hand
fixes) unless you pass --force, which keeps the old one as <video>.srt.bak. Window runs always overwrite.
A window with nothing left in it (`-40 40`, or a length of 0) is an error.

Gap repair: whisper sometimes skips a stretch of speech, typically right after applause or music
(the captions jump ahead 20-30 s). After the main pass this finds caption gaps longer than GAP_S
(default 6) that still contain sound, transcribes each gap again on its own and merges the result.
REPAIR=0 turns it off.

Needs ffmpeg, whisper.cpp (whisper-cli, or set WHISPER_BIN) and WHISPER_MODEL. Run doctor.sh to check.
"""
import json, os, re, shutil, subprocess, sys, tempfile


def die(msg):
    print(msg, file=sys.stderr); sys.exit(1)


class WhisperFailed(Exception):
    pass


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
        raise WhisperFailed(r.stderr[-2000:] + "\nwhisper failed (run doctor.sh)")
    try:
        return json.load(open(outbase + ".json"))["transcription"]
    except (ValueError, KeyError) as e:
        raise WhisperFailed(f"whisper wrote unreadable output ({e}); run doctor.sh")


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


def covered(intervals):
    """Union of (start, end) intervals, sorted and merged (nested or overlapping cues count once)."""
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def uncovered(intervals, dur, min_len):
    """Gaps of at least min_len s; cue times are clamped to the media length first."""
    gaps, t = [], 0.0
    for a, b in covered([(min(a, dur), min(b, dur)) for a, b in intervals]):
        if a - t >= min_len:
            gaps.append((t, a))
        t = max(t, b)
    if dur - t >= min_len:
        gaps.append((t, dur))
    return gaps


def caption_gaps(segs, dur, gap_s):
    return uncovered([(s["offsets"]["from"] / 1000, s["offsets"]["to"] / 1000) for s in segs if spoken(s)], dur, gap_s)


def retranscribe(wav, a, b, dur, model, tmp, tag, have=()):
    lo, hi = max(0.0, a - 0.5), min(dur, b + 0.5)
    part = os.path.join(tmp, f"gap{tag}.wav")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{lo:.3f}", "-t", f"{hi - lo:.3f}", "-i", wav,
                    "-c:a", "pcm_s16le", part], check=True)
    new = shift(run_whisper(part, model, os.path.join(tmp, f"gap{tag}")), int(lo * 1000))
    return keep_new(new, a, b, have)


def keep_new(new, a, b, have=()):
    """Recovered lines worth adding: spoken, centred in the gap (the slice overlaps its edges by 0.5 s),
    and not already captioned (the two halves of a split gap can both hear the same line)."""
    mid = lambda s: (s["offsets"]["from"] + s["offsets"]["to"]) / 2000
    # One word heard in applause or music is usually invented ("March." over clapping): drop it.
    new = [s for s in new if spoken(s) and a <= mid(s) <= b and len(s["text"].split()) >= 2]
    out = []
    for s in new:
        prior = list(have) + out
        if any(overlap(s, h) > 0.5 for h in prior) or repeats_tail(s, prior):
            continue
        out.append(s)
    return out


def repeats_tail(s, prior, abut_ms=300):
    """True when s only repeats the last words of a line it overlaps (or starts within 0.3 s of): the
    re-transcribed slice starts 0.5 s early and can hear the speaker's last words ("Thank you very
    much.") again. Decided by time first, never by text alone: the same words said later are real."""
    words = [norm(w) for w in s["text"].split()]
    for h in prior:
        if s["offsets"]["from"] <= h["offsets"]["to"] + abut_ms and s["offsets"]["to"] > h["offsets"]["from"]:
            tail = [norm(w) for w in h["text"].split()][-len(words):]
            if words and tail == words:
                return True
    return False


def overlap(s, h):
    """Share of s's duration that overlaps h."""
    a, b = s["offsets"]["from"], s["offsets"]["to"]
    o = min(b, h["offsets"]["to"]) - max(a, h["offsets"]["from"])
    return max(0, o) / max(1, b - a)


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def drop_last_words(seg, k):
    """Remove the last k words from a segment's text and its tokens (words start with a space)."""
    seg["text"] = " " + " ".join(seg["text"].split()[:-k])
    toks, n = seg.get("tokens", []), 0
    while toks and n < k:
        t = toks.pop()
        if t.get("text", "").startswith(" ") and not t["text"].strip().startswith("[_"):
            n += 1


def dedupe_seams(segs, recovered):
    """A recovered line can end with the words the next line starts with, because the re-transcribed
    slice runs 0.5 s past the gap. Only lines whose times actually overlap (the recovered one ends after
    the next one starts) are trimmed; the same words in lines that don't overlap are real speech."""
    ids = {id(s) for s in recovered}
    for i in range(len(segs) - 1):
        r, e = segs[i], segs[i + 1]
        if id(r) not in ids or r["offsets"]["to"] <= e["offsets"]["from"]:
            continue
        rw, ew = r["text"].split(), e["text"].split()
        rn, en = [norm(w) for w in rw], [norm(w) for w in ew]
        done = False
        for k in range(min(6, len(rw) - 1), 1, -1):          # 2+ words repeated near the start of the next line
            for j in range(0, 3):
                if rn[-k:] == en[j:j + k]:
                    drop_last_words(r, k); done = True; break
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
            try:
                new = retranscribe(wav, a, b, dur, model, tmp, n, have=[x for x in segs if spoken(x)])
            except (WhisperFailed, subprocess.CalledProcessError, OSError) as e:
                # The main pass is good: keep it. The gap stays open and is reported below.
                print(f"  WARNING: retry of caption gap {a:.1f}-{b:.1f}s failed: {str(e).strip()[-300:]}", file=sys.stderr)
                continue
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


def clamp_window(ss, length):
    """A window starting before 0:00 (e.g. boundary 10 s, `-10 40`) starts at 0:00 and keeps its end.
    ffmpeg would read from 0 anyway, so recording the negative offset would shift every word."""
    if ss < 0:
        return 0.0, (None if length is None else max(0.0, length + ss))
    return ss, length


def main(argv=None):
    a = argv if argv is not None else sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return 0
    force = "--force" in a
    a = [x for x in a if x != "--force"]
    video, ss = a[0], float(a[1]) if len(a) > 1 else 0.0
    length = float(a[2]) if len(a) > 2 else None
    ss, length = clamp_window(ss, length)
    if length is not None and length <= 0:
        die(f"nothing to transcribe: the window {a[1]} {a[2]} is empty once it is clamped to the start of the file")
    model = os.environ.get("WHISPER_MODEL") or die("set WHISPER_MODEL to a ggml model file (doctor.sh --get-model small.en)")
    base = os.path.splitext(video)[0] + (f".at{int(ss)}" if length else "")
    if not length and not force and os.path.exists(base + ".srt"):
        die(f"{base}.srt already exists and may hold hand fixes (names, terms). Move it aside, or pass --force "
            f"to replace it (the old one is kept as {os.path.basename(base)}.srt.bak).")
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(ss)] + (["-t", str(length)] if length else []) + \
              ["-i", video, "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav]
        subprocess.run(cmd, check=True)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav],
                                   capture_output=True, text=True).stdout.strip())
        try:
            segs = run_whisper(wav, model, os.path.join(tmp, "out"))
        except WhisperFailed as e:
            die(str(e))
        if os.environ.get("REPAIR", "1") != "0":
            repair(segs, wav, dur, model, tmp)
    if not length and os.path.exists(base + ".srt"):
        shutil.copy2(base + ".srt", base + ".srt.bak")
    with open(base + ".json", "w") as f:
        json.dump({"clock_offset_s": ss, "transcription": segs}, f)
    with open(base + ".srt", "w", encoding="utf-8") as f:
        for n, s in enumerate([s for s in segs if spoken(s)], 1):
            f.write(f"{n}\n{ts(s['offsets']['from'])} --> {ts(s['offsets']['to'])}\n{s['text'].strip()}\n\n")
    print(f"{base}.srt  {base}.json  (word times = file clock; offset {ss:g}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
