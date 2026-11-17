#!/usr/bin/env python3
"""OPTIONAL: upload one talk to YouTube as PRIVATE, with its text, captions and thumbnail.

A person still checks it in YouTube Studio and makes it public. This script never makes anything public.

  upload.py talk.mp4 [--text talk.youtube.md] [--captions talk.srt] [--thumbnail talk.jpg]
            [--playlist PLAYLIST_ID] [--client-secret client_secret.json] [--dry-run]

Setup, once (needs someone who manages the channel):
  1. In Google Cloud: create a project, enable "YouTube Data API v3", create an OAuth client of type
     "Desktop app" and download its JSON (the client secret file).
  2. pip install google-api-python-client google-auth-oauthlib
  3. The first run opens a browser; sign in as the channel's manager and allow access. The token is
     saved to ~/.config/conference-talk-video/token.json (readable only by you).
     Custom thumbnails need a verified channel; captions need the channel owner/manager.

Quota: 10,000 units a day by default. An upload costs 1,600, a caption track 400, a thumbnail 50,
adding to a playlist 50, so about 5 talks a day. --dry-run shows what would be sent and uses none.
"""
import argparse, json, os, re, sys, time

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]
TOKEN = os.path.expanduser("~/.config/conference-talk-video/token.json")


def parse_text(path):
    sec, cur = {}, None
    for line in open(path, encoding="utf-8").read().split("\n"):
        m = re.match(r"^## (\w+)", line)
        if m:
            cur = m.group(1).lower(); sec[cur] = []
        elif cur:
            sec[cur].append(line)
    get = lambda k: "\n".join(sec.get(k, [])).strip()
    title, desc = get("title"), get("description")
    tags = [t.strip() for t in get("tags").split(",") if t.strip()]
    if not title:
        raise SystemExit(f"{path}: no '## Title' section (make it with youtube-text.py build)")
    return title, desc, tags


def credentials(client_secret):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES) if os.path.exists(TOKEN) else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not client_secret:
            raise SystemExit("first run: pass --client-secret client_secret.json (see the setup notes in --help)")
        creds = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES).run_local_server(port=0)
    os.makedirs(os.path.dirname(TOKEN), exist_ok=True)
    fd = os.open(TOKEN, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(creds.to_json())
    return creds


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--text"); ap.add_argument("--captions"); ap.add_argument("--thumbnail")
    ap.add_argument("--playlist"); ap.add_argument("--client-secret"); ap.add_argument("--language", default="en")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    stem = os.path.splitext(a.video)[0]
    text = a.text or stem + ".youtube.md"
    caps = a.captions or (stem + ".srt" if os.path.exists(stem + ".srt") else None)
    title, desc, tags = parse_text(text)
    body = {"snippet": {"title": title, "description": desc, "tags": tags, "categoryId": "28",
                        "defaultLanguage": a.language, "defaultAudioLanguage": a.language},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}}
    plan = {"upload": a.video, "body": body, "captions": caps, "thumbnail": a.thumbnail, "playlist": a.playlist,
            "quota_units": 1600 + (400 if caps else 0) + (50 if a.thumbnail else 0) + (50 if a.playlist else 0)}
    if a.dry_run:
        print(json.dumps(plan, indent=2, ensure_ascii=False)); return 0
    for p in [a.video] + [x for x in (caps, a.thumbnail) if x]:
        if not os.path.exists(p):
            raise SystemExit(f"missing file: {p}")

    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=credentials(a.client_secret))

    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(a.video, chunksize=16 * 1024 * 1024, resumable=True))
    resp, tries = None, 0
    while resp is None:
        try:
            status, resp = req.next_chunk()
            if status:
                print(f"  uploading {int(status.progress() * 100)}%", end="\r", file=sys.stderr)
        except HttpError as e:
            if e.resp.status not in (500, 502, 503, 504) or tries >= 5:
                raise
            tries += 1; time.sleep(2 ** tries)
    vid = resp["id"]
    print(f"uploaded PRIVATE: https://youtu.be/{vid}  (studio: https://studio.youtube.com/video/{vid}/edit)")

    if caps:
        yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": a.language,
                             "name": "English", "isDraft": False}},
                             media_body=MediaFileUpload(caps, mimetype="application/octet-stream")).execute()
        print(f"  captions: {caps}")
    if a.thumbnail:
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(a.thumbnail)).execute()
        print(f"  thumbnail: {a.thumbnail}")
    if a.playlist:
        yt.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": a.playlist,
                                  "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
        print(f"  added to playlist {a.playlist}")
    print("Next: a person checks it in Studio (processing, captions, chapters) and makes it public.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
