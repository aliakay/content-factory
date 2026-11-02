"""Import the productions of the old system into project folders (read-only on the old data, copies only).

Every old production becomes a project of its line. The old state maps to checkpoints like this:

  published                -> all stages complete (imported), publish approved
  ready                    -> all complete (imported), publish waits at its gate
  preview, voice (explainer) -> every stage pending: the line starts again at research. The later stages read the
                              proposal (look, length, budget), which the old data cannot supply, and the old
                              scene format cannot become the new html scenes. The old script stays in legacy.json.

With archive=True (the creator's choice for the old videos) every row is imported as a read-only archive: all stages
complete, project status "archived", nothing can be run or approved on it, and flags are only reported.

Only artifacts the old data really supports are built (script, publish, compose); research, proposal and
scene_plan are never invented. The whole old row is kept as artifacts/legacy.json. No budget is set, so an imported
project cannot spend credits before the proposal is approved again.

    python -m factory.hat.migrate [--src ROOT] [--dst DIR] [--apply] [--archive] [--force]   (without --apply: dry run)
"""
import argparse, glob, json, os, shutil, sqlite3, sys

from . import manifest, project as P
from ..config import ROOT
from ..store import now

LINE_OF = {"explainer_short": "explainer", "story_vo": "travel_vlog"}
SKIP = object()


def _j(v, default=None):
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v) if v else default
    except (TypeError, ValueError):
        return default


def source_rows(src):
    """Old productions, read-only."""
    con = sqlite3.connect(f"file:{os.path.join(src, 'data', 'factory.db')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute("select * from productions order by prod_id")]
    finally:
        con.close()


def _out_dir(src, row):
    """The old output folder: the recorded name, or for a row without one the folder named after its title."""
    out = row.get("output") or row.get("name")
    if out:
        return out
    word = P.slug(row.get("title") or "").split("-")[0]        # "Kuyt’ın ..." -> "kuytin"; its folder is 116_kuyt
    hits = [os.path.basename(x) for x in glob.glob(os.path.join(src, "out", "[0-9][0-9][0-9]_*"))
            if len(os.path.basename(x)[4:]) >= 4 and word.startswith(os.path.basename(x)[4:])]
    return hits[0] if len(hits) == 1 else None


def _files(src, row):
    """Files of this production found on disk: {role: relative path}."""
    found = {}
    out = _out_dir(src, row)
    if out:
        mp4 = glob.glob(os.path.join(src, "out", out, "*.mp4"))
        cap = os.path.join(src, "out", out, "caption.txt")
        if mp4:
            found["final"] = os.path.relpath(mp4[0], src)
        if os.path.isfile(cap):
            found["caption"] = os.path.relpath(cap, src)
    prev = row.get("preview")
    if prev:
        mp4 = glob.glob(os.path.join(src, prev, "*.mp4")) or glob.glob(os.path.join(src, prev + "*.mp4"))
        if mp4:
            found["preview"] = os.path.relpath(mp4[0], src)
    take = (_j((_j(row.get("data"), {}) or {}).get("voice_take"), {}) or {}).get("file")
    if take and os.path.isfile(os.path.join(src, take)):
        found["voice_take"] = take
    return found


def plan(row, src, archive=False):
    """What would be imported for one old row: the mapped states, the files found, the flags."""
    flags = []
    old = row.get("stage")
    line = LINE_OF.get(row.get("format"))
    if not line:
        return {"prod": row["prod_id"], "skip": f"format '{row.get('format')}' has no line"}
    stage_ids = [s["id"] for s in manifest.get(line)["stages"]]
    files = _files(src, row)
    if archive:
        states = {s: "done" for s in stage_ids}
        if old == "published":
            states[stage_ids[-1]] = "approved"
    elif old in ("ready", "published"):
        states = {s: "done" for s in stage_ids}
        states[stage_ids[-1]] = "approved" if old == "published" else "awaiting_approval"
        if "final" not in files:
            flags.append("state is %s but no final mp4 was found on disk" % old)
    elif old in ("preview", "voice") and line == "explainer":
        states = {s: "pending" for s in stage_ids}
        if files.get("final"):
            flags.append("DB says %s but a final render exists on disk" % old)
    else:
        return {"prod": row["prod_id"], "skip": f"stage '{old}' ({line}) is not imported", "files": files}
    qa = _j(row.get("qa"), {}) or {}
    if old == "ready" and qa.get("pass") is False:
        flags.append("qa did not pass")
    if not row.get("name") and not row.get("output"):
        flags.append("no output name recorded" + (f"; found out/{_out_dir(src, row)}" if _out_dir(src, row) else ""))
    return {"prod": row["prod_id"], "title": row["title"], "line": line, "old_stage": old, "states": states,
            "files": files, "flags": flags}


# ---------------------------------------------------------------- artifacts from real data

def _script(row):
    d = _j(row.get("data"), {}) or {}
    lines = (_j(d.get("voice"), {}) or {}).get("lines") or []
    if len(lines) < 2:
        return None
    ver = {v.get("claim"): v for v in (_j(row.get("verification"), {}) or {}).get("verdicts", []) if isinstance(v, dict)}
    claims = []
    for f in _j(d.get("facts"), []) or []:
        if not isinstance(f, dict) or not f.get("claim"):
            continue
        v = ver.get(f["claim"])
        ok = bool(v and v.get("verdict") == "supported")        # verified only where the old check says supported
        src = f.get("source") or ((v or {}).get("sources") or [{}])[0].get("url")
        claims.append({"text": f["claim"], "verified": ok, **({"source": src} if src else {})})
    post = _j(d.get("post"), {}) or {}
    return {"title": row["title"], "hook": d.get("hook") or lines[0], "lines": lines, "claims": claims,
            "caption": post.get("caption", ""), "imported": True,
            "summary": "Imported from the old production; the fact check marks come from the old verification."}


def _publish(row):
    post = (_j(row.get("data"), {}) or {}).get("post")
    post = _j(post, {}) or {}
    if not post.get("caption"):
        return None
    tags = post.get("hashtags") or ""
    return {"caption": post["caption"], "hashtags": tags.split() if isinstance(tags, str) else list(tags),
            "imported": True, "summary": "Imported from the old production."}


def _copy(src, dst, rel):
    to = os.path.join(dst, os.path.basename(rel))
    os.makedirs(dst, exist_ok=True)
    if os.path.isdir(os.path.join(src, rel)):
        return None
    shutil.copy2(os.path.join(src, rel), to)             # copy, never move or link
    return to


def _topic(title):
    return "-".join(P.slug(title, 80).split("-")[:3])


def migrate(src, dst=None, apply=False, force=False, include_flagged=False, archive=False):
    """Plan (and with apply=True write) every importable production. Returns a report per old row.
    Rows with a flag are held for the creator: they are imported only with include_flagged."""
    report = []
    rows = source_rows(src)
    nums = [_number(r, src) for r in rows]
    existing = {_topic(P.load(i, dst)["title"]): i for i in P.list_ids(dst) if not P.load(i, dst).get("imported_from")}
    for row in rows:
        pl = plan(row, src, archive)
        if "skip" not in pl:
            n = _number(row, src)
            if nums.count(n) > 1:
                pl["flags"].append("number %d is used by %d old productions" % (n, nums.count(n)))
            if _topic(row["title"]) in existing:
                pl["flags"].append("same topic as the new project " + existing[_topic(row["title"])])
        if "skip" in pl:
            report.append(pl)
            continue
        num = _number(row, src)
        pid = f"{num:03d}-{P.slug(row['title'])}"
        pl["project"] = pid
        exists = os.path.exists(P.path(pid, d=dst))
        pl["exists"] = exists
        pl["archive"] = archive
        if apply and pl["flags"] and not (include_flagged or archive):
            pl["result"] = "held (flagged)"
        elif apply and exists and not force:
            pl["result"] = "skipped (already imported)"
        elif apply:
            if exists:
                worked = [e for e in P.tail(pid, n=1000, d=dst) if e.get("kind") not in ("created", "imported")]
                if worked:
                    pl["result"] = "refused: the project has work after the import"
                    report.append(pl)
                    continue
                shutil.rmtree(P.path(pid, d=dst))
            _write(row, pl, src, dst, num)
            pl["result"] = "imported"
        report.append(pl)
    return report


def _number(row, src=None):
    n = (row.get("name") or row.get("output") or (_out_dir(src, row) if src else None) or "")[:3]
    return int(n) if n.isdigit() else 900 + row["prod_id"]


def _write(row, pl, src, dst, num):
    d = _j(row.get("data"), {}) or {}
    p = P.create(pl["line"], row["title"], row.get("brief") or d.get("topic") or "", video_lang=d.get("lang") or "tr",
                 aspect=d.get("aspect") or "9:16", channel=row.get("channel_id"), user="import", d=dst, num=num,
                 extra={"imported_from": {"prod_id": row["prod_id"], "stage": row["stage"], "name": row.get("name"),
                                          "at": now()}, "created_at": row.get("created_at") or now(),
                        **({"status": "archived"} if pl.get("archive") else {})})
    pid = p["id"]
    P.write_artifact(pid, "legacy", row, dst)            # the whole old row, as it was
    stage_of = {s["id"]: s["artifact"] for s in manifest.get(pl["line"])["stages"]}
    built = {"script": _script(row), "publish": _publish(row)}
    for sid, status in pl["states"].items():
        cp = P.checkpoint(pid, sid, dst)
        cp.update(status=status, imported=True,
                  summary="Archived from the old system" if pl.get("archive") else "Imported from the old system")
        art = built.get(stage_of[sid]) if status != "pending" else None
        if art and (status != "pending"):
            P.write_artifact(pid, stage_of[sid], art, dst)
        P._log(cp, "import", "import", f"old stage {row['stage']}")
        P._write_cp(pid, cp, dst)
    files = {}
    for role, rel in pl["files"].items():
        copied = _copy(src, P.path(pid, "renders" if role in ("final", "preview") else "assets", d=dst), rel)
        if copied:
            files[role] = os.path.relpath(copied, ROOT)          # the form every stage artifact uses
    if files.get("final") and "compose" in pl["states"]:
        qa = _j(row.get("qa"), {}) or {}
        P.write_artifact(pid, stage_of["compose"], {"final": files["final"], "qa": qa, "imported": True}, dst)
    P.event(pid, "imported", d=dst, prod_id=row["prod_id"], files=sorted(files))
    return pid


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", default=os.path.expanduser("~/tiktok"), help="the old system's root (read-only)")
    ap.add_argument("--dst", default=None, help="projects directory (default: this repo's projects/)")
    ap.add_argument("--apply", action="store_true", help="write the projects (default is a dry run)")
    ap.add_argument("--include-flagged", action="store_true", help="also import rows that carry a flag")
    ap.add_argument("--archive", action="store_true", help="import every row as a read-only archive")
    ap.add_argument("--force", action="store_true", help="overwrite projects that were imported before")
    a = ap.parse_args(argv)
    rep = migrate(a.src, a.dst, apply=a.apply, force=a.force, include_flagged=a.include_flagged, archive=a.archive)
    for r in rep:
        if "skip" in r:
            print(f"  prod {r['prod']:>3}  SKIP  {r['skip']}")
            continue
        print(f"  prod {r['prod']:>3}  {r['old_stage']:<9} -> {r['project']}  [{r['line']}]  "
              f"{r.get('result', 'dry run')}{'  (exists)' if r['exists'] else ''}")
        print("            states: " + (", ".join(f"{k}={v}" for k, v in r["states"].items() if v != "pending") or "all pending (starts at research)"))
        for role, rel in r["files"].items():
            sz = os.path.getsize(os.path.join(a.src, rel)) if os.path.isfile(os.path.join(a.src, rel)) else 0
            print(f"            file {role}: {rel} ({sz // 1024} KB)")
        for f in r["flags"]:
            print(f"            FLAG: {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
