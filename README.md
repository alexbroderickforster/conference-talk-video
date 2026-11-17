# Conference talk video: a Claude Code skill

From IT Revolution's Enterprise AI Summit pipeline (Charlotte and Bletchley Park, 2026).

**Install:** copy `conference-talk-video/` into `~/.claude/skills/` (or into your repo's `.claude/skills/`).
Then install the tools and download a whisper model, for example ggml-small.en.bin from the whisper.cpp model list:
    brew install ffmpeg whisper-cpp
    export WHISPER_MODEL=/path/to/ggml-small.en.bin

**Use:** in Claude Code, ask: "Here are today's recordings in ~/event/day1. Cut the talks and
make review copies." Claude finds each talk, cuts it, and gives you a short start/end preview per
talk to watch, plus a ready-to-paste YouTube description, chapters and captions file.

The scripts also work without Claude:
| Script | What it does |
|---|---|
| reencode.sh | Shrinks a huge file to H.264 1080p |
| transcribe.sh | Local transcript with word timings (whole file or a window) |
| words.py | Lists words and pauses between two times, to pick cut points |
| cut.sh | Cuts one talk with soft fades, with optional audio delay and loudness levelling |
| review-proxy.sh | Makes a 540p preview of the first and last 45 s, for a person to check |
