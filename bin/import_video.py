#!/usr/bin/env python3
"""Add a finished video made outside the Studio's lines to the Studio (factory/imports.py).

  import_video.py <video.mp4> --title "..." --channel <channel id> [--series <id> --episode <n>]
                  [--url <published link>] [--thumb cover.jpg ...] [--note "..."]

Example (episode 1 of The Unopened Letter):
  import_video.py out/unopened_ep1/the_unopened_letter_ep1_full.mp4 --channel hikaye-en --series 1 --episode 1 \\
      --title "The Unopened Letter · Episode 1: The Tin Box" --url https://youtu.be/pn26qVpJ5cM
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from factory import imports  # noqa: E402
from factory.config import ROOT  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--title", required=True)
    ap.add_argument("--channel", required=True)
    ap.add_argument("--series", type=int)
    ap.add_argument("--episode", type=int)
    ap.add_argument("--url")
    ap.add_argument("--thumb", action="append", default=[])
    ap.add_argument("--note", default="")
    ap.add_argument("--db", default=os.path.join(ROOT, "data", "factory.db"))
    a = ap.parse_args(argv)
    con = sqlite3.connect(a.db, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        pid = imports.import_video(con, a.video, a.title, a.channel, a.series, a.episode, a.url, a.thumb, note=a.note)
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"production {pid} added (open it in the Studio: #/p/{pid})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
