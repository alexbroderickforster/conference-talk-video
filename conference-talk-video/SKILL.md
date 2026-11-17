---
name: conference-talk-video
description: Turn conference recordings into publish-ready YouTube talks — shrink huge files, transcribe locally with word timings, cut each talk at clean word boundaries with soft fades, make a small start/end review copy for a person to watch, and draft the YouTube title, description, chapters, tags and captions. Use when someone hands you event recordings (one file with several talks, or one per talk) and wants talks ready to upload.
---

# Conference talk video

You take recordings from the AV team and hand a person finished talks to approve and upload.
A person approves every talk before it goes public. You never publish on your own.

Tools: `ffmpeg`, `whisper-cpp` (`brew install ffmpeg whisper-cpp`) and a whisper model
(`ggml-small.en.bin` from the whisper.cpp model list; set `WHISPER_MODEL` to its path).
Everything runs locally, so there are no per-minute transcription costs. The scripts are in `scripts/`.

## Who does what
| Step | Who |
|---|---|
| Record + hand off the program recording | AV team |
| 1. Shrink, 2. transcribe, 3. find talks, 4. cut | **AI** (you) |
| 5. Review the start and end of each talk | **Person** watches the review copy |
| 6. Title, description, chapters, tags, captions | **AI** drafts, person skims |
| 7. Upload in YouTube Studio, set public | **Person** (or AI via the API, if set up) |

## 1. Shrink if needed
If a file is ProRes or very large (hundreds of GB), re-encode it first: `scripts/reencode.sh in.mov`
(`FAST=1` uses the Mac hardware encoder). For anything you publish, use crf 14–18 at preset medium.
"veryfast" encodes looked soft on YouTube.

## 2. Transcribe
`scripts/transcribe.sh recording.mp4` writes `recording.srt` and `recording.json`, which holds the word timings.
It runs at about 30× real time on Apple silicon.

## 3. Find each talk
Read the SRT to find where each talk begins and ends. A file may hold one talk or several.
- **Start:** where the host starts introducing the speaker. Keep the host's intro.
- **End:** after the speaker's last line, plus the start of the applause. Keep a host's closing
  remark only when it is complete and on topic. If you're unsure, end at the applause and ask.
- **Word-level check:** for each boundary, re-transcribe about 40 s around it:
  `scripts/transcribe.sh recording.mp4 <start-20> 40`.
  A whole-file pass can give several words the same time, while a short window gets each word's time right. Then
  run `scripts/words.py recording.at<N>.json`. It prints every word with its time and marks each pause
  with a suggested cut time. Cut inside the pause just before the first word you keep, and inside the pause just
  after the last word. Never cut on a segment's start time: that leaves fragments like
  "…more frequently. All right" at the head.

## 4. Cut
`scripts/cut.sh recording.mp4 <start> <end> talk.mp4` makes a 0.5 s fade in and out on both picture and sound.
- `LOUDNORM=1` levels the sound to −16 LUFS.
- `AUDIO_DELAY_MS=40` fixes audio that runs early. Measure sync once per day of the event by checking lip
  movement on a close-up: one of our AV feeds ran 40 ms early on day 1 and 30 ms on day 2.

## 5. Review copy (person watches)
Run `scripts/review-proxy.sh talk.mp4`. It makes a 540p file of the first 45 s, one second of black, then the last 45 s,
small enough to watch on a phone. Send it to the reviewer with one line per talk: speaker, title and
length. Fix any cut they flag, then re-check the new edge with `words.py`.

## 6. YouTube text (AI drafts)
Draft these from the cut's own transcript. Re-run `transcribe.sh talk.mp4` so the times match the file.
- **Title:** the talk title, then " — Speaker Name (Company)". Keep it under 100 characters.
- **Description:** line 1 is the one link you most want clicked (slides, a paper, next year's event).
  Then a 2–3 sentence summary, the speaker line and the chapter list.
- **Chapters:** 7–10 of them, the first at `0:00`, titles under 45 characters, in sentence case. Each needs to be at least 10 s long.
- **Tags:** speakers, company, event, city, organizer.
- **Captions:** `talk.srt` with names and product terms fixed (make a glossary per event).
  Upload it as a real caption track, never left to auto-captions. Captions must come from the
  exact file being uploaded. If you trim again, re-transcribe or shift the SRT by the trim.
Write all of it to `talk.youtube.md` for the person to paste into Studio.

## 7. Upload
- **Simple:** a person with Editor or Manager access on the channel uploads in YouTube Studio. They paste the
  text, upload the SRT (Subtitles → Upload file → With timing), add the thumbnail and playlist, set
  "not made for kids", and publish. Uploads done by hand have no API quota.
- **Automated (optional):** this needs YouTube Data API v3, a Google Cloud project, an OAuth client and a
  channel manager's consent. The quota is 10,000 units/day: an upload costs 1,600 and a caption track
  400, so about 5 talks a day. Upload as private, wait for processing to finish (edits are
  ignored while it's processing), add captions, check everything, then make it public.
- Pinned comments, cards, end screens and thumbnail A/B tests are Studio-only; there's no API for them.
- YouTube can't swap a video's file. A fixed cut means a new upload and a new link, so review first.

## Rules
- Never publish or make anything public without a person's OK, talk by talk.
- Keep a hold list of talks that must not go out (speaker or sponsor approval) and check it each time.
- Never delete originals. Keep the recording, the cut, the SRT and the YouTube text together per talk.
- Look before the person does: play the start and end yourself (`words.py` on the cut) before
  sending the review copy.
