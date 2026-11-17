---
name: conference-talk-video
description: Turn conference recordings into publish-ready YouTube talks — shrink huge files, transcribe locally with word timings, find and cut each talk at clean word boundaries with soft fades, make a small start/end review copy for a person to watch, and draft the YouTube title, description, chapters, tags and captions. Use when someone hands you event recordings (one file with several talks, or one per talk) and wants talks ready to upload.
---

# Conference talk video

You take recordings from the AV team and hand a person finished talks to approve and upload.
A person approves every talk before it goes public. You never publish on your own.

The scripts are in this skill's `scripts/` folder. Everything runs locally, so there are no per-minute
transcription costs. **Start with `scripts/doctor.sh`**: it checks ffmpeg, whisper.cpp and the
whisper model and prints the exact fix for anything missing (`doctor.sh --get-model small.en`
downloads a model).

## Who does what
| Step | Who |
|---|---|
| Record + hand off the program recording (plus the schedule, if there is one) | AV team / organizer |
| 1. Shrink, 2. transcribe, 3. find talks, 4. cut | **AI** (you) |
| 5. Review the start and end of each talk | **Person** watches the review copy |
| 6. Title, description, chapters, tags, captions | **AI** writes them, person skims |
| 7. Upload, set public | **Person** in YouTube Studio (or AI uploads as private via the API, if set up) |

## 1. Shrink if needed
If a file is ProRes or very large (hundreds of GB), re-encode it first: `scripts/reencode.sh in.mov`.
`FAST=1` uses a hardware encoder if the machine has one. For anything you publish, keep crf 14–18
at preset medium: "veryfast" encodes looked soft on YouTube.

## 2. Transcribe
`scripts/transcribe.sh recording.mp4` writes `recording.srt` and `recording.json`, which holds the word timings.
It runs at about 30× real time on Apple silicon.
It also **repairs caption gaps**: whisper sometimes skips 20–30 s of speech right after applause or
music. Long caption gaps that still contain sound get transcribed again and merged in. Any gap it
can't fix is printed as a WARNING. Look at those spots: they're usually applause, sometimes missed speech.

## 3. Find each talk
If you have the schedule, save it as `schedule.txt` (`speaker | company | title`, one talk per line,
in running order) and run `scripts/find-talks.py recording.srt schedule.txt`. It spots each speaker's
name in the host's intro (fuzzy, since whisper misspells names) and gives a likely start. Otherwise read the SRT.
- **Start:** where the host starts introducing the speaker. Keep the host's intro.
- **End:** after the speaker's last line, plus the start of the applause. Keep a host's closing
  remark only when it is complete and on topic. If you're unsure, end at the applause and ask.
- **Word-level check, every boundary:**
  1. Re-transcribe about 40 s around it: `scripts/transcribe.sh recording.mp4 <start-20> 40`. A whole-file pass
     can give several words the same time; a short window gets them right.
  2. Run `scripts/words.py recording.at<N>.json`. It prints every word with its time and marks pauses
     with a suggested cut time.
  3. Whisper's times can still be a second off, worst right after a silence. Snap to the real gap in the
     audio: `scripts/snap.py start recording.mp4 <first kept word's time>` and
     `scripts/snap.py end recording.mp4 <last kept word or applause end>`. (`snap.py list` shows
     the quiet stretches. In a noisy room, try `NOISE=-30dB`.)
  Never cut on a segment's start time: that leaves fragments like "…more frequently. All right" at the head.

## 4. Cut
`scripts/cut.sh recording.mp4 <start> <end> talk.mp4` makes a 0.5 s fade in and out on both picture and sound.
- `LOUDNORM=1` levels the sound to −16 LUFS.
- `AUDIO_DELAY_MS=40` fixes audio that runs early. Measure sync once per day of the event by checking lip
  movement on a close-up: one AV feed we used ran 40 ms early on day 1 and 30 ms on day 2.

## 5. Review copy (person watches)
Run `scripts/review-proxy.sh talk.mp4`. It makes a 540p file of the first 45 s, one second of black, then the last 45 s,
small enough to watch on a phone. Send it to the reviewer with one line per talk: speaker, title and
length. Fix any cut they flag, then re-check the new edge with `words.py` and `snap.py`.

## 6. YouTube text (AI writes)
1. Transcribe the cut itself (`scripts/transcribe.sh talk.mp4`) so the captions and chapters match the file
   being uploaded. After a trim, re-transcribe, or move existing captions with
   `scripts/shift-srt.py talk.srt --by -<seconds trimmed>`; `--window START END` extracts a talk's
   captions from the full recording's SRT.
2. Fix names and product terms in `talk.srt` (keep a glossary per event). A later whole-file
   `transcribe.sh` refuses to replace a `talk.srt` that already exists; `--force` replaces it and keeps
   the old one as `talk.srt.bak`.
   Before uploading, run `scripts/caption-gaps.py talk.mp4 talk.srt`: it lists stretches with sound but
   no captions. Listen to each: applause is fine; speech means re-transcribe or fix the SRT.
3. Chapters, done automatically: `scripts/youtube-text.py suggest talk.srt` proposes points at natural breaks.
   Read the transcript and name each one (7–10 for a 20–40 min talk; under 45 characters, sentence case).
   Save them as `chapters.txt` with one `m:ss Title` per line, the first at `0:00`.
4. Build and check: `scripts/youtube-text.py build talk.mp4 --title … --speaker … --company … --event …
   --link "<the one link you most want clicked>" --summary "<2–3 sentences>" --chapters chapters.txt`.
   It writes `talk.youtube.md` and flags anything YouTube would reject: title over 100 characters,
   fewer than 3 chapters, chapters under 10 s, `<` or `>` in the text, tags over 500 characters.

## 7. Upload
- **Simple:** a person with Editor or Manager access on the channel uploads in YouTube Studio. They paste from
  `talk.youtube.md`, upload the SRT (Subtitles → Upload file → With timing), add the thumbnail and
  playlist, set "not made for kids", and publish. Uploads done by hand use no API quota.
- **Automated (optional):** `scripts/upload.py talk.mp4 --dry-run` shows what would be sent. Without `--dry-run`
  it uploads as **private** with the text, captions, thumbnail and playlist, and never makes anything public.
  Setup is in `upload.py --help`: a Google Cloud project with YouTube Data API v3, a Desktop OAuth client,
  and a channel manager's consent. Quota is 10,000 units/day (upload 1,600 + captions 400), about 5 talks a day.
- Pinned comments, cards, end screens and thumbnail A/B tests are Studio-only; there's no API for them.
- YouTube can't swap a video's file. A fixed cut means a new upload and a new link, so review first.

## Rules
- Never publish or make anything public without a person's OK, talk by talk.
- Keep a hold list of talks that must not go out (speaker or sponsor approval) and check it each time.
- Never delete originals. Keep the recording, the cut, the SRT and the YouTube text together per talk.
- Look before the person does: check each cut's first and last words (`words.py` on the cut) before
  sending the review copy.

## Try it without real footage
`examples/run-sample.sh` (in the plugin repo) builds a 2-minute synthetic recording, with a host and
two talks made from text-to-speech, and runs every step above on it.
