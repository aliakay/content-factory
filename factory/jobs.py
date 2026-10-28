"""Background jobs for the Content Factory. The web app queues a row and spawns `python -m factory.jobs run <id>`.

Kinds: ingest <album link> · analyze · describe · trends · radar [profile] · ideas <json {n, brief}> · verify <idea_id> ·
render <idea_id> · yt_stats · Studio productions: p_ideas <json {format, n, brief, places}> · p_voice <json {id, approved}> ·
p_preview <id> · p_render <id> · p_revise <json {id, feedback}> · p_verify <id> · p_design <json {id, note}> · p_plan <json {id, feedback}> · p_plan_apply <json {id, steps}>
"""
import json, os, re, subprocess, sys, traceback

from . import discover, ideas, media, styles, productions, qa, refs, sfx, signals, tracking
from .store import ROOT, connect, jload, now

PY = os.path.join(ROOT, ".venv", "bin", "python")
LOGDIR = os.path.join(ROOT, "data", "jobs")


def queue(con, kind, arg="", user=None):
    """Start a job process for `user` (default: whoever is logged in); its Claude steps run on that user's login."""
    from . import accounts
    user = user or accounts.current()
    try:
        con.execute("ALTER TABLE jobs ADD COLUMN user TEXT")
    except Exception:
        pass
    cur = con.execute("INSERT INTO jobs (kind, arg, status, started_at, user) VALUES (?,?,?,?,?)",
                      (kind, arg, "queued", now(), user))
    con.commit()
    jid = cur.lastrowid
    os.makedirs(LOGDIR, exist_ok=True)
    log = os.path.join(LOGDIR, f"{jid}.log")
    con.execute("UPDATE jobs SET log=? WHERE job_id=?", (log, jid))
    con.commit()
    subprocess.Popen([PY, "-m", "factory.jobs", "run", str(jid)], cwd=ROOT, start_new_session=True,
                     stdout=open(log, "a"), stderr=subprocess.STDOUT, env={**os.environ, "FACTORY_USER": user})
    return jid


# ---------- steps ----------
def do_ingest(con, link):
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import icloud_fetch
    res = icloud_fetch.main(link, True)
    con.execute("INSERT OR REPLACE INTO albums VALUES (?,?,COALESCE((SELECT added_at FROM albums WHERE link=?),?),?)",
                (link, res["title"], link, now(), now()))
    con.commit()
    print(f"album {res['title']!r}: {res['items']} items, {len(res['downloaded'])} new")
    do_analyze(con, album=res["title"])
    do_describe(con)


def do_analyze(con, album=None):
    raw = os.path.join(ROOT, "raw")
    known = {r["clip_id"] for r in con.execute("SELECT clip_id FROM clips WHERE analyzed_at IS NOT NULL")}
    for name in sorted(os.listdir(raw)):
        path = os.path.join(raw, name)
        kind = media.kind_of(path)
        if not kind or name in known or name.endswith(".part"):
            continue
        print("analyze", name, flush=True)
        meta = media.probe_video(path) if kind == "video" else media.probe_photo(path)
        sheet = media.contact_sheet(path, name, kind)
        motion = segs = None
        if kind == "video":
            rows = media.motion_profile(path)
            segs = media.best_segments(rows)
            motion = [(t, round(m or 0, 2)) for t, m, _ in rows[::5]]
        day = (meta["captured_at"] or "")[:10]
        place = media.assign_place(con, meta["lat"], meta["lon"], day)
        usable, note = 1, None
        if name.lower().endswith(".png"):
            usable, note = 0, "screenshot — excluded for privacy"
        con.execute("""INSERT OR REPLACE INTO clips (clip_id, path, kind, album, captured_at, lat, lon, duration, fps,
                       width, height, place_id, sheet, motion, segments, usable, note, analyzed_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (name, path, kind, album, meta["captured_at"], meta["lat"], meta["lon"], meta["duration"],
                     meta["fps"], meta["width"], meta["height"], place, sheet, json.dumps(motion),
                     json.dumps(segs), usable, note, now()))
        con.commit()


def do_describe(con, batch=8):
    todo = [dict(r) for r in con.execute(
        "SELECT clip_id, kind, sheet, captured_at, duration FROM clips WHERE described_at IS NULL AND usable=1 "
        "ORDER BY captured_at")]
    for i in range(0, len(todo), batch):
        part = todo[i:i + batch]
        listing = "\n".join(f"- clip_id={c['clip_id']} kind={c['kind']} captured={c['captured_at']} "
                            f"duration={c['duration']} image={c['sheet']}" for c in part)
        prompt = f"""Read each image file below. Video images are strips of frames left→right in time; photo images are
the photo itself. Describe what a viewer would see, for choosing B-roll for short videos.
{listing}
Reply with ONLY JSON: {{"clips": [{{"clip_id": "...", "description": "one or two sentences, concrete",
"tags": ["5-8 lowercase tags"], "mood": "one word", "people": "none|creator|strangers_faces|strangers_far"}}]}}"""
        data, meta = ideas.llm.ask(prompt, tools=("Read",), timeout=900, model="sonnet")
        for d in data.get("clips", []):
            note = "strangers' faces visible — use with care" if d.get("people") == "strangers_faces" else None
            con.execute("UPDATE clips SET description=?, tags=?, mood=?, note=COALESCE(note, ?), described_at=? "
                        "WHERE clip_id=?", (d.get("description"), json.dumps(d.get("tags", [])), d.get("mood"),
                                            note, now(), d.get("clip_id")))
        con.commit()
        print(f"described {len(part)} clips · cost ${meta.get('cost_usd') or 0:.3f}", flush=True)


def gather_signals(con):
    yt = signals.radar_candidates()
    trends, _ = signals.latest_trends(con)
    tt = [dict(r) for r in con.execute("SELECT * FROM tiktok_refs ORDER BY added_at DESC LIMIT 30")]
    return {"youtube": yt, "trends": trends, "tiktok": tt}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", (s or "idea").lower()).strip("_")[:40]


def next_number():
    out = os.path.join(ROOT, "out")
    nums = [int(d[:3]) for d in os.listdir(out) if d[:3].isdigit()] if os.path.isdir(out) else []
    return max(nums, default=0) + 1


def build_montage(con, idea, name):
    mpath = os.path.join(ROOT, "specs", "montage", f"{name}.json")
    mspec = json.dumps(ideas.to_specs(idea, name), indent=1)
    cached = (os.path.exists(mpath) and open(mpath).read() == mspec
              and os.path.exists(os.path.join(ROOT, "work", f"{name}_montage.mp4")))
    open(mpath, "w").write(mspec)
    if cached:
        print("montage unchanged — reusing", flush=True)
    else:
        subprocess.run([PY, os.path.join(ROOT, "bin", "montage.py"), mpath], check=True, cwd=ROOT)
    return mpath, json.load(open(os.path.join(ROOT, "work", f"{name}_montage.json")))


def do_preview(con, idea_id):
    """Style frames before the full render: fast draft + one frame per beat (cover first)."""
    row = con.execute("SELECT * FROM ideas WHERE idea_id=?", (idea_id,)).fetchone()
    idea = json.loads(row["data"])
    name = row["output"] or f"{next_number():03d}_{slug(idea.get('title'))}"
    if not row["output"]:
        con.execute("UPDATE ideas SET output=? WHERE idea_id=?", (name, idea_id))
        con.commit()
    mpath, timing = build_montage(con, idea, name)
    mspec_ = json.load(open(mpath))
    windows = [(timing["starts"][i], timing["starts"][i] + mspec_["shots"][i].get("xd", 0.3))
               for i in range(1, len(timing["starts"]))]
    spec = ideas.render_spec(idea, name, timing["total"], transitions=windows)
    spec.update(preview=True)
    spec.pop("post", None)
    rpath = os.path.join(ROOT, "work", "preview", f"{name}.json")
    os.makedirs(os.path.dirname(rpath), exist_ok=True)
    json.dump(spec, open(rpath, "w"), ensure_ascii=False)
    subprocess.run([PY, os.path.join(ROOT, "bin", "render.py"), rpath], check=True, cwd=ROOT)
    sheet, _ = qa.beat_frames(os.path.join(ROOT, "work", "preview", f"{name}.mp4"), idea.get("beats", []),
                              timing["total"], f"{name}_preview")
    idea["preview_sheet"] = sheet
    con.execute("UPDATE ideas SET data=? WHERE idea_id=?", (json.dumps(idea, ensure_ascii=False), idea_id))
    con.commit()
    print("preview", sheet, flush=True)


def do_render(con, idea_id):
    row = con.execute("SELECT * FROM ideas WHERE idea_id=?", (idea_id,)).fetchone()
    idea = json.loads(row["data"])
    if not idea.get("shots"):
        raise ValueError("idea has no usable shots")
    name = row["output"] or f"{next_number():03d}_{slug(idea.get('title'))}"
    mpath, timing = build_montage(con, idea, name)
    total = timing["total"]
    mspec_ = json.load(open(mpath))
    windows = [(timing["starts"][i], timing["starts"][i] + mspec_["shots"][i].get("xd", 0.3))
               for i in range(1, len(timing["starts"]))]
    spec = ideas.render_spec(idea, name, total, transitions=windows)
    level = idea.get("sfx_level") or ideas.brand().get("sfx_default", "subtle")
    spec["sfx"] = sfx.to_render(sfx.plan(idea, json.load(open(mpath)), timing, level))
    rpath = os.path.join(ROOT, "specs", f"{name}.json")
    json.dump(spec, open(rpath, "w"), ensure_ascii=False, indent=1)
    subprocess.run([PY, os.path.join(ROOT, "bin", "render.py"), rpath], check=True, cwd=ROOT)
    con.execute("UPDATE ideas SET status='rendered', output=? WHERE idea_id=?", (name, idea_id))
    con.commit()
    print("rendered", name, f"· {len(spec['sfx'])} sfx ({level})", flush=True)
    mp4 = os.path.join(ROOT, "out", name, f"{name}.mp4")
    mspec = json.load(open(mpath))
    transitions = [timing["starts"][i] + mspec["shots"][i].get("xd", 0.3) / 2 for i in range(1, len(timing["starts"]))]
    prev = jload(row["qa"], {}) or {}
    report = qa.review(mp4, idea, total, name, transitions=transitions,
                       previous=(prev.get("visual") or {}).get("issues"))
    ledger = idea.get("qa_ledger", []) + [{"at": now(), "pass": report["pass"],
                                           "issues": len(report["visual"].get("issues", [])),
                                           "verification": report["visual"].get("verification", [])}]
    idea["qa_ledger"] = ledger
    con.execute("UPDATE ideas SET qa=?, data=? WHERE idea_id=?",
                (json.dumps(report, ensure_ascii=False), json.dumps(idea, ensure_ascii=False), idea_id))
    con.commit()
    print("QA", "pass" if report["pass"] else "issues", report["technical"].get("problems"),
          [i.get("problem") for i in report["visual"].get("issues", [])], flush=True)


def run_production(con, kind, arg, job_id):
    if kind == "p_ideas":
        o = jload(arg, {})
        ids, meta = productions.generate(con, o["format"], o.get("n", 3), o.get("brief", ""), o.get("places") or None,
                                         o.get("refs") or None, o.get("voice_id"), o.get("aspect", "9:16"), o.get("narrate", "auto"),
                                         o.get("look", "tech"), o.get("channel"), o.get("continues"), o.get("recipe"))
        for pid in ids:  # "auto" look: Opus designs the scenes now, so the creator sees them BEFORE approving voice credits
            if productions.get(con, pid)["data"].get("look_pack") != "auto":
                continue
            q = productions.get(con, pid)
            q["job_id"] = job_id
            productions.save(con, q)
            try:
                os.environ["FACTORY_PROD_ID"] = str(pid)
                productions.design(con, pid)
            except Exception as e:  # the production stays usable; the first preview retries the design
                print(f"design failed for {pid}: {type(e).__name__}: {e}", flush=True)
            finally:
                q = productions.get(con, pid)
                q["job_id"] = None
                productions.save(con, q)
        return f"fikirler {ids}"
    o = jload(arg, None)
    pid = int(o["id"]) if isinstance(o, dict) else int(arg)
    os.environ["FACTORY_PROD_ID"] = str(pid)
    p = productions.get(con, pid)
    p["job_id"] = job_id
    productions.save(con, p)
    try:
        if kind == "p_voice":
            _, cost = productions.make_voice(con, pid, int(o["approved"]))
            productions.preview(con, pid)
            return f"ses {round(cost)} kredi + önizleme"
        if kind == "p_design":
            productions.design(con, pid, o.get("note", "") if isinstance(o, dict) else "")
            p = productions.get(con, pid)
            if p["stage"] == "preview" and p["data"].get("voice_take"):
                productions.preview(con, pid)
            return "hareket tasarımı hazır"
        if kind == "p_direct":
            productions.direct(con, pid, o.get("note", "") if isinstance(o, dict) else "")
            p = productions.get(con, pid)
            fmt_ok = not productions.formats.for_data(p["format"], p["data"])["voice"] or p["data"].get("voice_take")
            if p["stage"] == "preview" and fmt_ok:
                productions.preview(con, pid)
            return "art direction hazır"
        if kind == "p_plates":   # illustrated look / series episode: the scene illustrations, then the motion design
            from . import illustrate, series
            chars, flow = series.cast_for(con, p)
            cost = illustrate.make_plates(con, p, int(o["approved"]), chars, flow)
            productions.save(con, p, "çizimler", f"{round(cost)} kredi")
            if p["data"].get("look_pack") == "illustrated":
                productions.design(con, pid)
            p = productions.get(con, pid)
            if p["stage"] == "preview" and p["data"].get("voice_take"):
                productions.preview(con, pid)
            return f"çizimler {round(cost)} kredi + hareket tasarımı"
        if kind == "p_music":
            _, cost = productions.make_music(con, pid, int(o["approved"]), o.get("prompt"))
            productions.preview(con, pid)
            return f"müzik {round(cost)} kredi + önizleme"
        if kind == "p_preview":
            productions.preview(con, pid)
            return "önizleme hazır"
        if kind == "p_render":
            productions.render(con, pid)
            return "render + QA bitti"
        if kind == "p_revise":
            productions.revise(con, pid, o["feedback"])
            p = productions.get(con, pid)
            if p["data"].get("look_pack") == "auto":  # a new script drops the old design: redesign before anything else
                productions.design(con, pid)
                p = productions.get(con, pid)
            if p["stage"] == "preview":
                productions.preview(con, pid)
            return "revizyon uygulandı"
        if kind == "p_plan":
            productions.plan_edit(con, pid, o["feedback"])
            return "düzenleme planı hazır"
        if kind == "p_plan_apply":
            stage = productions.apply_plan(con, pid, o["steps"])
            if stage == "preview":
                productions.preview(con, pid)
                return "plan uygulandı + önizleme"
            return "plan uygulandı; ses için kredi onayı bekliyor"
        if kind == "p_verify":
            productions.verify(con, pid)
            return "doğrulandı"
        raise ValueError(f"unknown job kind {kind}")
    finally:
        p = productions.get(con, pid)
        p["job_id"] = None
        productions.save(con, p)


def run(job_id):
    con = connect()
    job = con.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    con.execute("UPDATE jobs SET status='running', started_at=? WHERE job_id=?", (now(), job_id))
    con.commit()
    kind, arg, result = job["kind"], job["arg"], ""
    os.environ.update(FACTORY_JOB_ID=str(job_id), FACTORY_JOB_KIND=kind)   # tags Claude calls in llm_usage
    try:
        if kind == "ingest":
            do_ingest(con, arg)
        elif kind == "refs":
            if arg:
                sys.path.insert(0, os.path.join(ROOT, "bin"))
                import icloud_fetch
                res = icloud_fetch.main(arg, False, dest=refs.REFS)
                print(f"refs album {res['title']!r}: {len(res['downloaded'])} new", flush=True)
            refs.analyze(con)
            result = f"{refs.describe(con)} references profiled"
        elif kind == "ref_lib":
            n = refs.scan_library(con)
            m = refs.describe_recipes(con)
            result = f"{n} new references measured, {m} recipes written"
        elif kind == "avatar_check":
            prof_path = os.path.join(ROOT, "data", "eleven_profile.json")
            prof = json.load(open(prof_path))
            from . import eleven
            found = eleven.avatar_node(prof["avatar"]["flow_id"])
            nodes = found.get("avatar_nodes") or []
            prof["avatar"]["node_id"] = nodes[0]["node_id"] if nodes else None
            prof["avatar"]["checked_at"] = now()
            json.dump(prof, open(prof_path, "w"), ensure_ascii=False, indent=1)
            result = f"avatar node: {prof['avatar']['node_id'] or 'yok'}"
        elif kind == "eleven_voices":   # a member's own ElevenLabs connector: read its voices on their Claude login
            from . import accounts, eleven
            acc = accounts.eleven(arg)
            with accounts.as_user(acc["owner"]):
                voices = eleven.list_voices()
            accounts.set_voices(arg, voices)
            result = f"{len(voices)} ses okundu"
        elif kind == "analyze":
            do_analyze(con)
        elif kind == "describe":
            do_describe(con)
        elif kind == "discover":
            rid = discover.scan(con)
            result = f"discovery run {rid}: {discover.cards(con, rid)['run']['cards']} cards"
        elif kind == "plan":   # the composer's planner (factory/planner.py)
            from . import planner
            o = jload(arg, {})
            try:
                pl = planner.think(con, int(o["id"]), o.get("voices"))
            except Exception as e:
                con.execute("UPDATE plans SET status='failed', error=? WHERE plan_id=?", (f"{type(e).__name__}: {e}"[:300], int(o["id"])))
                con.commit()
                raise
            result = f"plan: {pl['kind']} · {pl['format']}" + (" (yedek)" if pl.get("fallback") else "")
        elif kind in ("series_bible", "series_cast", "series_episode"):
            from . import series
            o = jload(arg, {})
            s = series.get(con, int(o["id"]))
            s["job_id"] = job_id
            series.save(con, s)
            try:
                if kind == "series_bible":
                    s = series.write_bible(con, s["series_id"], o.get("feedback"))
                    result = f"seri kitabı: {s['title']}"
                elif kind == "series_cast":
                    from . import accounts
                    cost = series.make_sheets(con, s["series_id"], int(o["approved"]), o.get("account") or accounts.default_eleven())
                    result = f"karakter sayfaları {round(cost)} kredi"
                else:
                    pid = series.write_episode(con, s["series_id"], int(o["n"]), o.get("note", ""))
                    result = f"bölüm {o['n']} → üretim {pid}"
            except Exception:
                s = series.get(con, int(o["id"]))
                if s["status"] == "writing":
                    s["status"] = "failed"
                    series.save(con, s)
                raise
            finally:
                s = series.get(con, int(o["id"]))
                s["job_id"] = None
                series.save(con, s)
        elif kind == "style_extract":
            o = jload(arg, {})
            result = "stil: " + styles.extract(o["files"], o.get("note", ""))
        elif kind == "trends":
            result = f"{signals.fetch_trends(con)} trend items"
        elif kind == "radar":
            subprocess.run([PY, "-m", "radar.cli", "run", *([arg] if arg else [])], check=True, cwd=ROOT)
        elif kind == "yt_stats":
            result = f"{tracking.refresh_youtube(con)} YouTube posts refreshed"
        elif kind == "talk_new":   # a raw talking video -> analysed, cut by Claude, filed as a production
            from . import talk
            o = jload(arg, {})
            pid = talk.create(con, os.path.join(ROOT, o["file"]), o.get("brief", ""), o.get("channel"), o.get("aspect", "9:16"),
                              o.get("recipe"), o.get("lang"))
            result = f"konuşma kurgusu {pid}"
        elif kind.startswith("p_"):
            result = run_production(con, kind, arg, job_id)
        elif kind == "ideas":
            opts = jload(arg, {})
            ids, meta = ideas.generate(con, gather_signals(con), n=opts.get("n", 5), brief=opts.get("brief", ""))
            result = f"ideas {ids} · cost ${meta.get('cost_usd') or 0:.3f}"
        elif kind == "verify":
            r = ideas.verify(con, int(arg))
            result = r.get("summary", "")
        elif kind == "preview":
            do_preview(con, int(arg))
        elif kind == "render":
            do_render(con, int(arg))
        else:
            raise ValueError(f"unknown job kind {kind}")
        status = "done"
    except Exception as e:  # recorded for the UI; the traceback goes to the job log
        traceback.print_exc()
        status, result = "failed", f"{type(e).__name__}: {e}"[:500]
    con.execute("UPDATE jobs SET status=?, finished_at=?, result=? WHERE job_id=?", (status, now(), result, job_id))
    con.commit()
    print(status, result, flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(int(sys.argv[2]))
