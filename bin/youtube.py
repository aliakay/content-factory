#!/usr/bin/env python3
"""Upload videos to a YouTube channel (factory/youtube_upload.py).

  youtube.py auth <account>              sign in once: prints a code to enter at google.com/device
  youtube.py whoami <account>            show the channel this account uploads to
  youtube.py check <spec.json>           validate an upload spec without uploading
  youtube.py upload <account> <spec.json>

<account> is just a local name for the stored sign-in (e.g. troia). Needs YOUTUBE_CLIENT_ID and
YOUTUBE_CLIENT_SECRET in .env (OAuth client: "Desktop app" or "TVs and Limited Input devices").
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from factory import youtube_upload as yt  # noqa: E402


def _progress(done, total):
    print(f"\r  {done / total * 100:5.1f}%  {done / 1e6:7.1f} / {total / 1e6:.1f} MB", end="", flush=True)
    if done >= total:
        print()


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    try:
        if cmd == "auth" and len(argv) == 2:
            client = yt.Client.from_env()
            dev = yt.start_device(client)
            print(f"Open {dev.get('verification_url') or dev.get('verification_uri')} and enter: {dev['user_code']}")
            print("Waiting for approval ...", flush=True)
            path = yt.save_token(argv[1], yt.poll_device(client, dev))
            ch = yt.Session(argv[1], client).channel()
            print(f"Signed in. Channel: {ch['snippet']['title']} ({ch['id']}). Saved to {path}")
        elif cmd == "whoami" and len(argv) == 2:
            ch = yt.Session(argv[1]).channel()
            print(f"{ch['snippet']['title']}  https://www.youtube.com/channel/{ch['id']}")
        elif cmd == "check" and len(argv) == 2:
            spec = yt.Spec.load(argv[1])
            bad = spec.problems()
            print("\n".join(bad) if bad else "ok")
            return 1 if bad else 0
        elif cmd == "upload" and len(argv) == 3:
            spec = yt.Spec.load(argv[2])
            out = yt.publish(yt.Session(argv[1]), spec, progress=_progress)
            print(json.dumps(out, indent=1, ensure_ascii=False))
        else:
            print(__doc__)
            return 2
    except yt.YouTubeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
