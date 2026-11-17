# conference-talk-video

[![test](https://github.com/alexbroderickforster/conference-talk-video/actions/workflows/test.yml/badge.svg)](https://github.com/alexbroderickforster/conference-talk-video/actions/workflows/test.yml)

A Claude Code skill that turns conference recordings into publish-ready YouTube talks. You give it the
AV team's files; it finds each talk, cuts it cleanly, hands a person a short preview to approve, and
writes the YouTube title, description, chapters and captions. Everything runs on your laptop.

Built for and used on IT Revolution's Enterprise AI Summit recordings (Charlotte and Bletchley Park, 2026).

## Install

In Claude Code:

    /plugin marketplace add alexbroderickforster/conference-talk-video
    /plugin install conference-talk-video@conference-talk-video

(On Claude Code 2.1.275 or later, one step: `/plugin install conference-talk-video --marketplace alexbroderickforster/conference-talk-video`.)

Then the tools. On a Mac:

    brew install ffmpeg whisper-cpp

On Linux, install ffmpeg and [build whisper.cpp](https://github.com/ggml-org/whisper.cpp#quick-start),
then set `WHISPER_BIN` to its `whisper-cli`. Then ask Claude to "check the video tools". It runs
`doctor.sh`, which checks everything and downloads a whisper model if you need one.

Without the plugin system: copy `skills/conference-talk-video/` into `~/.claude/skills/`.

## Use

In Claude Code:

> Here are today's recordings in ~/event/day1, and the schedule is in schedule.txt.
> Cut the talks and make review copies.

You get, per talk:
- `talk.mp4`, cut at the host's intro and after the applause, with soft fades;
- `talk-review.mp4`, the first and last 45 seconds at 540p, to watch on your phone;
- `talk.srt` captions and `talk.youtube.md` with the title, description, chapters and tags, ready to paste.

A person watches each preview and uploads in YouTube Studio. Optionally, the AI uploads as private
via the API. Nothing is ever made public without a person.

## Try it in two minutes, no footage needed

    WHISPER_MODEL=~/.cache/whisper/ggml-small.en.bin examples/run-sample.sh

This builds a synthetic recording (a test pattern, with a host and two speakers made from text-to-speech)
and runs every step on it. The tests check that the cuts land within a fraction of a second of the
real talk boundaries.

## The scripts

They work without Claude too.

| Script | What it does |
|---|---|
| `doctor.sh` | Checks the tools and model and says how to fix what's missing; `--get-model` downloads one |
| `reencode.sh` | Shrinks a huge file to H.264 1080p (`FAST=1` uses a hardware encoder if there is one) |
| `transcribe.sh` | Local transcript with word timings, for a whole file or a window; repairs whisper's skipped stretches |
| `find-talks.py` | Finds each scheduled speaker's intro in the transcript (fuzzy name match) |
| `words.py` | Lists words and pauses between two times, to pick cut points |
| `snap.py` | Moves a rough cut point into the real quiet in the audio |
| `cut.sh` | Cuts one talk with soft fades; optional audio delay and loudness levelling |
| `review-proxy.sh` | 540p preview of the first and last 45 s, for a person to check |
| `caption-gaps.py` | Before upload: lists stretches with sound but no captions |
| `shift-srt.py` | Moves captions after a trim, or extracts one talk's captions from the full recording |
| `youtube-text.py` | Suggests chapter points; builds and checks the title, description, chapters and tags |
| `upload.py` | Optional: uploads as private with captions, thumbnail and playlist (YouTube Data API) |

## What we learned cutting real events

- **Whisper's word times drift after silence.** A whole-file pass can put several words at the same
  instant, or put the first word at the start of the quiet before it. Re-transcribing 40 s around each
  boundary, then snapping to the actual gap in the audio, gives cuts that never clip a word.
- **Whisper skips speech after applause.** It sometimes jumps 20–30 s ahead. `transcribe.sh` finds caption
  gaps that still contain sound and transcribes them again.
- **People review by watching, not reading.** A 90-second start-and-end preview catches bad cuts faster
  than a contact sheet or timestamps.
- **Lip sync differs by day.** Measure it once per day on a close-up: one feed ran 40 ms early on day 1 and 30 ms on day 2.
- **Captions must come from the exact file you upload.** Any trim means re-transcribing or shifting the SRT.

## Tests

    tests/run.sh          # unit tests; plus end-to-end when WHISPER_MODEL is set

CI runs both on Ubuntu and macOS on every push.

## License

MIT
