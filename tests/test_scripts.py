"""Unit tests for the Python helpers. Run: python3 -m unittest discover -s tests"""
import importlib.util, io, json, os, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "conference-talk-video", "scripts")


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


SRT = """1
00:00:00,500 --> 00:00:04,000
Good morning. Please welcome Dana Reyes from Acme.

2
00:00:05,000 --> 00:00:12,000
Thank you. Two years ago we shipped twice a year.

3
00:00:20,000 --> 00:00:31,000
Thanks Dana. Our next speaker is Sam Okerfor from Northwind.

4
00:00:32,000 --> 00:00:45,000
Hello everyone, over three years we wrote up incidents.
"""


class ShiftSrt(unittest.TestCase):
    def setUp(self):
        self.m = load("shift-srt"); self.cues = self.m.read_srt(SRT)

    def test_window_restarts_clock_and_clips(self):
        out = self.m.shift(self.cues, -10, 10, 33)
        self.assertEqual([round(c[0], 2) for c in out], [0.0, 10.0, 22.0])
        self.assertEqual(round(out[0][1], 2), 2.0)          # cue 2 clipped at the window start
        self.assertEqual(round(out[-1][1], 2), 23.0)        # cue 4 clipped at the window end

    def test_shift_back_drops_cues_before_zero(self):
        out = self.m.shift(self.cues, -13)
        self.assertEqual(len(out), 2)
        self.assertEqual(round(out[0][0], 2), 7.0)

    def test_roundtrip_format(self):
        text = self.m.write_srt(self.cues)
        self.assertIn("00:00:20,000 --> 00:00:31,000", text)
        self.assertEqual(len(self.m.read_srt(text)), 4)


class FindTalks(unittest.TestCase):
    def test_fuzzy_names_in_order(self):
        m = load("find-talks")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.srt"); open(p, "w").write(SRT)
            cues = m.read_srt(p)
        talks = [{"speaker": "Dana Reyes", "company": "", "title": ""}, {"speaker": "Sam Okafor", "company": "", "title": ""}]
        res = m.find(cues, talks)
        self.assertEqual(res[0]["start_hint"], 0.5)
        self.assertEqual(res[1]["start_hint"], 20.0)       # "Okerfor": whisper's spelling still matches

    def test_garbled_surname_still_found(self):
        m = load("find-talks")
        self.assertGreaterEqual(m.score("Dana Reyes", "welcome Dana Raised from Acme Robotics", "Acme Robotics"), 0.8)
        self.assertGreaterEqual(m.score("Sam Okafor", "Our next speaker is Samokafa from Northwind", "Northwind"), 0.8)
        self.assertLess(m.score("Dana Reyes", "Thank you, Dana.", "Acme Robotics"), 0.8)
        self.assertLess(m.score("Sam Okafor", "Today we ship every Tuesday", "Northwind"), 0.8)

    def test_schedule_parsing(self):
        m = load("find-talks")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sched.txt")
            open(p, "w").write("# c\n9:05 | Dana Reyes | Acme | Robots\nSam Okafor | Northwind\n")
            t = m.read_schedule(p)
        self.assertEqual([x["speaker"] for x in t], ["Dana Reyes", "Sam Okafor"])
        self.assertEqual(t[1]["title"], "")


class YoutubeText(unittest.TestCase):
    def setUp(self):
        self.m = load("youtube-text")

    def test_good_text_passes(self):
        ch = [(0, "Intro"), (60, "Testing"), (120, "Rollout")]
        self.assertEqual(self.m.check("A talk — Dana Reyes (Acme)", "desc", ch, ["a"], dur=300), [])

    def test_rules(self):
        ch = [(5, "x" * 50), (8, "Too soon"), (7, "Out of order")]
        p = " | ".join(self.m.check("t" * 101, "<b>", ch, ["t" * 501], dur=300))
        for want in ("title is 101", "< and >", "start at 0:00", "min 10s", "out of order", "over 45", "tags total"):
            self.assertIn(want, p)

    def test_too_few_chapters(self):
        self.assertTrue(any("at least 3" in x for x in self.m.check("t", "d", [(0, "a"), (30, "b")], [], 100)))

    def test_suggest_starts_at_zero_and_spaces_out(self):
        cues = [(i * 5.0, i * 5.0 + 4, f"line {i}") for i in range(40)]
        s = self.m.suggest(cues, 4)
        self.assertEqual(s[0][0], 0.0)
        self.assertTrue(all(b[0] - a[0] >= 10 for a, b in zip(s, s[1:])))
        self.assertGreaterEqual(len(s), 3)


class Words(unittest.TestCase):
    def test_glue_filter_and_json(self):
        d = {"clock_offset_s": 100.0, "transcription": [{"tokens": [
            {"text": "[_BEG_]", "offsets": {"from": 0, "to": 0}},
            {"text": " Hel", "offsets": {"from": 0, "to": 200}},
            {"text": "lo", "offsets": {"from": 200, "to": 400}},
            {"text": " world", "offsets": {"from": 1500, "to": 1200}},     # end before start: clamped
            {"text": " [BLANK_AUDIO]", "offsets": {"from": 2000, "to": 3000}}]}]}
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "t.json"); json.dump(d, open(p, "w"))
            out = subprocess.run([sys.executable, os.path.join(SCRIPTS, "words.py"), p, "--json"],
                                 capture_output=True, text=True, check=True).stdout
            txt = subprocess.run([sys.executable, os.path.join(SCRIPTS, "words.py"), p],
                                 capture_output=True, text=True, check=True).stdout
        w = json.loads(out)
        self.assertEqual([x["word"] for x in w], ["Hello", "world"])
        self.assertEqual(w[0]["start"], 100.0)
        self.assertEqual(w[1]["end"], 101.5)
        self.assertIn("pause 1.10s", txt)


def seg(a, b, text, tokens=None):
    return {"offsets": {"from": int(a * 1000), "to": int(b * 1000)}, "text": " " + text,
            "tokens": tokens if tokens is not None else [{"text": " " + w} for w in text.split()]}


class Transcribe(unittest.TestCase):
    """Regression tests for the code-review findings on the gap repair (2026-11-17)."""
    def setUp(self):
        self.m = load("transcribe")

    def test_dedupe_trims_text_and_tokens_where_lines_meet(self):
        r, e = seg(25, 30.4, "the fastest came from teams who"), seg(30.0, 33, "The teams who could roll back")
        self.m.dedupe_seams([r, e], [r])
        self.assertEqual(r["text"].strip(), "the fastest came from")
        self.assertEqual([t["text"].strip() for t in r["tokens"]], ["the", "fastest", "came", "from"])

    def test_dedupe_keeps_real_repeats_a_second_apart(self):          # finding 4
        r, e = seg(6, 8, "Please sit down."), seg(9, 10, "Sit down now.")
        self.m.dedupe_seams([r, e], [r])
        self.assertEqual(r["text"].strip(), "Please sit down.")

    def test_split_halves_do_not_duplicate_a_line(self):             # finding 3
        first = self.m.keep_new([seg(9, 11, "one spoken line")], 0, 10.5)
        second = self.m.keep_new([seg(9, 11, "one spoken line")], 9.5, 20, have=first)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        twice = self.m.keep_new([seg(9, 11, "one spoken line"), seg(9, 11, "one spoken line")], 0, 20)
        self.assertEqual(len(twice), 1)

    def test_recovered_noise_and_echoes_are_dropped(self):
        have = [seg(47, 52.0, "safer, not riskier. Thank you very much.")]
        got = self.m.keep_new([seg(51.5, 52.6, "Thank you very much."), seg(52.6, 53.4, "March."),
                               seg(54, 58, "Our next speaker is here.")], 52.0, 59, have=have)
        self.assertEqual([g["text"].strip() for g in got], ["Our next speaker is here."])

    def test_negative_window_is_clamped(self):                        # finding 5
        self.assertEqual(self.m.clamp_window(-10, 40), (0.0, 30))
        self.assertEqual(self.m.clamp_window(5, 40), (5, 40))
        self.assertEqual(self.m.clamp_window(-3, None), (0.0, None))

    def test_whole_file_run_never_silently_replaces_captions(self):  # finding 6
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "talk.mp4"); open(v, "w").close()
            srt = os.path.join(d, "talk.srt")
            with open(srt, "w") as f:
                f.write("1\n00:00:00,000 --> 00:00:02,000\nHand-fixed name\n")
            os.environ["WHISPER_MODEL"] = os.environ.get("WHISPER_MODEL") or "/nonexistent.bin"
            with self.assertRaises(SystemExit):
                self.m.main([v])
            with open(srt) as f:
                self.assertIn("Hand-fixed", f.read())

    def test_gaps_use_the_union_of_cues(self):                        # finding 7 (same logic as caption-gaps)
        nested = [seg(0, 25, "a"), seg(10, 12, "b"), seg(20, 22, "c")]
        self.assertEqual(self.m.caption_gaps(nested, 25, 6), [])
        self.assertEqual(self.m.caption_gaps([seg(0, 5, "a"), seg(30, 31, "b")], 40, 6), [(5, 30), (31, 40)])

    def test_shift_moves_tokens(self):
        s = self.m.shift([{"offsets": {"from": 0, "to": 1000}, "tokens": [{"offsets": {"from": 10, "to": 20}}]}], 5000)
        self.assertEqual(s[0]["timestamps"]["from"], "00:00:05,000")
        self.assertEqual(s[0]["tokens"][0]["offsets"]["from"], 5010)


class CaptionGaps(unittest.TestCase):
    def test_nested_cues_are_not_a_gap(self):                         # finding 7
        m = load("caption-gaps")
        self.assertEqual(m.uncovered([(0, 25), (10, 12), (20, 22)], 25, 6), [])
        self.assertEqual(m.uncovered([(0, 5.7), (30, 33)], 52, 6), [(5.7, 30), (33, 52)])


class Snap(unittest.TestCase):
    def setUp(self):
        self.m = load("snap")

    def fake(self, quiet):
        self.m.silences = lambda video, lo, hi: [q for q in quiet if q[1] >= lo and q[0] <= hi]

    def test_start_never_uses_a_pause_inside_the_speech(self):        # finding 1
        self.fake([(110, 111)])
        self.assertIsNone(self.m.snap_start("v", 100))

    def test_start_uses_the_quiet_before_an_early_estimate(self):
        self.fake([(0, 3.01), (4.9, 5.3)])          # whisper said 0.0 s; speech starts at 3.0 s
        self.assertAlmostEqual(self.m.snap_start("v", 0), 2.76)

    def test_end_takes_the_pause_right_after_the_last_word(self):     # finding 2
        self.fake([(100.05, 100.75), (110, 111)])
        self.assertAlmostEqual(self.m.snap_end("v", 100), 100.35)

    def test_end_refuses_a_far_pause(self):
        self.fake([(110, 111)])
        self.assertIsNone(self.m.snap_end("v", 100))


class Upload(unittest.TestCase):
    def test_dry_run_is_private_and_parses_text(self):
        m = load("upload")
        with tempfile.TemporaryDirectory() as d:
            v = os.path.join(d, "talk.mp4"); open(v, "w").close()
            open(os.path.join(d, "talk.youtube.md"), "w").write(
                "# YouTube text\n\n## Title\nA talk — Dana\n\n## Description\nLine 1\n\nChapters:\n0:00 Intro\n\n"
                "## Tags\nDana, Acme\n\n## Captions\ntalk.srt\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                m.main([v, "--dry-run"])
        plan = json.loads(buf.getvalue())
        self.assertEqual(plan["body"]["status"]["privacyStatus"], "private")
        self.assertEqual(plan["body"]["snippet"]["title"], "A talk — Dana")
        self.assertEqual(plan["body"]["snippet"]["tags"], ["Dana", "Acme"])
        self.assertIn("Chapters:", plan["body"]["snippet"]["description"])


if __name__ == "__main__":
    unittest.main()
