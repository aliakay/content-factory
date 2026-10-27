"""Viral Radar command line.

  python -m radar.cli run        search YouTube, verify, store, snapshot, write report
  python -m radar.cli snapshot   re-measure tracked videos (for growth acceleration)
  python -m radar.cli report     score stored candidates and write the report only
  add a profile name to any command: `python -m radar.cli run travel` (default: psychology)
"""
import os, sys
from datetime import datetime, timezone

from . import db
from .config import DB_PATH, REPORT_DIR, SearchProfile, WEIGHTS, get_profile, load_env
from .pipeline import enrich, load_candidates, refresh_snapshots, run_youtube
from .scoring import shortlist
from .youtube import ConnectorError, YouTube

SOURCES_NOT_AUTOMATED = {
    "tiktok": "not searched: Creative Center is a manual workflow (Research API needs approved researcher access)",
    "instagram": "not searched: Graph API hashtag connector not configured",
    "google_trends": "not used: no topic signals recorded",
}


def fmt_int(n):
    return "—" if n is None else f"{n:,}"


def write_report(cands, profile, summary=None, top=30):
    os.makedirs(REPORT_DIR, exist_ok=True)
    start, end = profile.window()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    path = os.path.join(REPORT_DIR, f"radar_{profile.name}_{stamp}.md")
    L = [f"# Viral Radar — {profile.topic}", "",
         f"Window: {start:%Y-%m-%d %H:%M} → {end:%Y-%m-%d %H:%M} UTC · duration < {profile.max_duration_s:g}s · "
         f"market: {'global' if not profile.region else profile.region} · languages: {', '.join(profile.languages)}", "",
         "## Sources", ""]
    if summary:
        L.append(f"- **youtube**: {summary['status']} · {summary['searches']} searches · {summary['ids']} ids · "
                 f"{summary['verified_short']} verified < {profile.max_duration_s:g}s · rejected ≥{profile.max_duration_s:g}s: "
                 f"{summary['rejected_duration']} · outside window: {summary['rejected_window']} · "
                 f"quota used: {summary.get('quota_units', 0)} units")
        for e in summary["errors"]:
            L.append(f"  - error: {e}")
    else:
        L.append("- **youtube**: scored from stored data (no new search this run)")
    for k, v in SOURCES_NOT_AUTOMATED.items():
        L.append(f"- **{k}**: {v}")
    L += ["", f"Weights: " + ", ".join(f"{k} {int(v * 100)}%" for k, v in WEIGHTS.items()) +
          ". Missing components are left out and the rest renormalized. "
          "Growth acceleration needs ≥3 daily snapshots, so early scores are provisional.", "",
          f"## Top {min(top, len(cands))} of {len(cands)} candidates", "",
          "| # | Score | Conf. | Views | Age | Views/h | vs creator | Subs | Icahn | Dur | Subtopics | Title | Link |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, c in enumerate(cands[:top], 1):
        ratio = f"{c['views'] / c['channel_median']:.1f}×" if c.get("channel_median") and c.get("views") else "—"
        title = (c.get("title") or "").replace("|", "/")[:70]
        L.append(f"| {i} | {c['viral_score'] if c['viral_score'] is not None else '—'} | {c['confidence']} | "
                 f"{fmt_int(c.get('views'))} | {c['age_h'] / 24:.1f}d | {fmt_int(round(c['velocity_raw'])) if c['velocity_raw'] else '—'} | "
                 f"{ratio} | {fmt_int(c.get('subscribers'))} | {'✓' if c.get('icahn') else ('—' if c.get('icahn') is None else '')} | {c['duration_s']:g}s | {', '.join(c['subtopics']) or '—'} | {title} | "
                 f"[{c['channel_title'] or 'link'}]({c['url']}) |")
    L += ["", "## Analysis shortlist (max 2 per creator, mixed subtopics)", ""]
    for i, c in enumerate(shortlist(cands), 1):
        L.append(f"{i}. **{c['viral_score']}** · {c['duration_s']:g}s · {fmt_int(c.get('views'))} views · "
                 f"{', '.join(c['subtopics']) or 'unclassified'} · {(c.get('title') or '')[:80]} · {c['url']}")
    L += ["", "Missing per candidate is listed in the database; a `—` means the platform did not provide the value "
              "(e.g. hidden likes), never an estimate."]
    open(path, "w").write("\n".join(L) + "\n")
    return path


def main(argv=None):
    args = argv or sys.argv[1:] or ["report"]
    cmd = args[0]
    profile = get_profile(args[1] if len(args) > 1 else "psychology")
    con = db.connect(DB_PATH)
    summary = None
    if cmd in ("run", "snapshot", "enrich"):
        try:
            yt = YouTube(load_env().get("YOUTUBE_API_KEY"))
        except ConnectorError as e:
            db.log_run(con, "youtube", "not_configured", str(e))
            print(f"youtube: {e}")
            return 1
        if cmd == "run":
            summary = run_youtube(con, yt, profile)
            print({k: v for k, v in summary.items() if k != "errors"}, "errors:", len(summary["errors"]))
        elif cmd == "enrich":
            print("enriched · quota used:", enrich(con, yt, profile))
        else:
            print("snapshots refreshed:", refresh_snapshots(con, yt, profile), "quota used:", yt.used)
            return 0
    cands = load_candidates(con, profile)
    path = write_report(cands, profile, summary)
    print(f"{len(cands)} candidates · report: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
