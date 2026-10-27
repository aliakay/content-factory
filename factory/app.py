"""Content Factory — Streamlit panel. Run: streamlit run factory/app.py"""
import json, os, sys

import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, ROOT)
from factory import jobs, refs, signals  # noqa: E402
from factory.store import connect, jload  # noqa: E402

st.set_page_config(page_title="Content Factory", page_icon="🎬", layout="wide")
con = connect()


def queue(kind, arg="", label=None):
    jid = jobs.queue(con, kind, arg)
    st.toast(f"{label or kind} started (job #{jid})")


@st.fragment(run_every=5)
def job_panel():
    # fragments re-run on their own thread, and a SQLite connection may only be used by the thread that made it
    fcon = connect()
    try:
        rows = fcon.execute("SELECT * FROM jobs ORDER BY job_id DESC LIMIT 6").fetchall()
    finally:
        fcon.close()
    if not rows:
        return
    with st.expander("Jobs", expanded=any(r["status"] in ("queued", "running") for r in rows)):
        for r in rows:
            icon = {"queued": "⏳", "running": "🔄", "done": "✅", "failed": "❌"}.get(r["status"], "•")
            st.markdown(f"{icon} **#{r['job_id']} {r['kind']}** · {r['status']} · {r['result'] or ''}")
            if r["status"] in ("running", "failed") and r["log"] and os.path.exists(r["log"]):
                st.code("".join(open(r["log"]).readlines()[-8:]) or "…", language=None)
        st.caption("Claude steps (describe, ideas, verify, QA) run on your Claude subscription's usage limits; "
                   "the $ figures are API-equivalent estimates, not charges.")


st.title("🎬 Content Factory")
job_panel()
tab_in, tab_clips, tab_sig, tab_ref, tab_ideas, tab_out = st.tabs(
    ["📥 Inbox", "🎞 Clips", "📈 Signals", "🧪 Reference Lab", "💡 Ideas", "🎬 Shorts"])

# ---------------- Inbox ----------------
with tab_in:
    st.subheader("Add raw footage")
    link = st.text_input("iCloud shared album link", placeholder="https://photos.icloud.com/shared/album/…")
    if st.button("Download & analyse", type="primary", disabled=not link.startswith("https://photos.icloud.com/")):
        queue("ingest", link.strip(), "Ingest")
    albums = con.execute("SELECT * FROM albums ORDER BY last_sync DESC").fetchall()
    for a in albums:
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"**{a['title']}** · last sync {a['last_sync'][:16].replace('T', ' ')}")
        if c2.button("Sync", key=f"sync{a['link']}"):
            queue("ingest", a["link"], "Sync")
    n = con.execute("SELECT COUNT(*) n, SUM(kind='video') v, SUM(described_at IS NOT NULL) d FROM clips").fetchone()
    st.caption(f"{n['n'] or 0} clips ({n['v'] or 0} videos) · {n['d'] or 0} described by Claude")
    c1, c2 = st.columns(2)
    if c1.button("Analyse files already in raw/"):
        queue("analyze")
    if c2.button("Describe undescribed clips"):
        queue("describe")

# ---------------- Clips ----------------
with tab_clips:
    places = con.execute("SELECT p.*, COUNT(c.clip_id) n FROM places p JOIN clips c ON c.place_id=p.place_id "
                         "GROUP BY p.place_id ORDER BY p.day, p.place_id").fetchall()
    st.caption("Places are grouped automatically from GPS (same day, within 4 km). Rename them so ideas use real names.")
    for p in places:
        with st.expander(f"📍 {p['name']} · {p['n']} clips"):
            new = st.text_input("Place name", p["name"], key=f"pn{p['place_id']}")
            if new != p["name"]:
                con.execute("UPDATE places SET name=? WHERE place_id=?", (new, p["place_id"]))
                con.commit()
            for c in con.execute("SELECT * FROM clips WHERE place_id=? ORDER BY captured_at", (p["place_id"],)):
                cols = st.columns([2, 3])
                if c["sheet"] and os.path.exists(c["sheet"]):
                    cols[0].image(c["sheet"])
                info = f"**{c['clip_id']}** · {c['kind']} · {(c['captured_at'] or '')[:16]}"
                if c["kind"] == "video":
                    segs = jload(c["segments"], [])
                    info += f" · {c['duration']:.1f}s · steady: " + ", ".join(f"{s['start']}–{s['end']}s" for s in segs)
                cols[1].markdown(info)
                cols[1].write(c["description"] or "_not described yet_")
                if c["note"]:
                    cols[1].warning(c["note"])
                use = cols[1].checkbox("usable", bool(c["usable"]), key=f"u{c['clip_id']}")
                if use != bool(c["usable"]):
                    con.execute("UPDATE clips SET usable=? WHERE clip_id=?", (int(use), c["clip_id"]))
                    con.commit()
    nogps = con.execute("SELECT COUNT(*) n FROM clips WHERE place_id IS NULL").fetchone()["n"]
    if nogps:
        st.caption(f"{nogps} clips without GPS are still available to ideas.")

# ---------------- Signals ----------------
with tab_sig:
    st.subheader("YouTube · Viral Radar")
    cands, short, runs = signals.radar_candidates()
    if runs:
        r = runs[0]
        st.caption(f"Last run {r['ts'][:16].replace('T', ' ')} UTC · {r['status']} · {r['results']} verified <15s · "
                   f"{r['quota_units']} quota units. Daily run at 06:17 UTC.")
    if st.button("Run radar now (~950 quota units)"):
        queue("radar")
    st.caption("Icahn ✓ = small-channel outlier: 100K+ views, under 100K subscribers, views ≥ 5× subscribers "
               "(the idea carried the video).")
    for c in short[:12]:
        ic = " · **Icahn ✓** " + f"({c['views_per_sub']}× subs)" if c.get("icahn") else ""
        st.markdown(f"**{c['viral_score']}** (conf {c['confidence']}){ic} · {c['duration_s']:g}s · "
                    f"{c['views']:,} views · {c['age_h'] / 24:.1f}d · {', '.join(c['subtopics']) or '—'}  \n"
                    f"[{(c['title'] or '')[:90]}]({c['url']})")

    st.divider()
    st.subheader("Google Trends · trending searches")
    items, when = signals.latest_trends(con)
    st.caption(f"Public trending-searches feed for US + GB · fetched {when[:16] if when else 'never'} · "
               "a topic-interest signal, not video data")
    if st.button("Refresh trends"):
        queue("trends")
    if items:
        st.dataframe([{"geo": i["geo"], "search": i["title"], "traffic": i["traffic"]} for i in items],
                     hide_index=True, width='stretch', height=260)

    st.divider()
    st.subheader("TikTok · manual import")
    st.markdown(f"Find references in **[TikTok Creative Center]({signals.CREATIVE_CENTER})** "
                "(region, last 30 days), then paste the video link here. Title/author come from TikTok's official "
                "oEmbed; views are only stored if you type them (marked *manual*).")
    with st.form("tt", clear_on_submit=True):
        url = st.text_input("TikTok video URL")
        c1, c2 = st.columns(2)
        views = c1.number_input("Views (optional)", min_value=0, step=1000, value=0)
        likes = c2.number_input("Likes (optional)", min_value=0, step=100, value=0)
        note = st.text_input("Why it's interesting (optional)")
        if st.form_submit_button("Import"):
            try:
                status = signals.import_tiktok(con, url, views or None, likes or None, note)
                st.success(f"Imported · oEmbed: {status}")
            except ValueError as e:
                st.error(str(e))
    for t in con.execute("SELECT * FROM tiktok_refs ORDER BY added_at DESC LIMIT 20"):
        m = f" · {t['views']:,} views (manual)" if t["views"] else ""
        st.markdown(f"[{t['title'] or t['url']}]({t['url']}) · {t['author'] or '?'}{m} · oEmbed {t['oembed_status']}")

# ---------------- Reference Lab ----------------
with tab_ref:
    st.subheader("Learn editing style from example videos")
    st.markdown("Save example videos you like (TikTok's *Save video*, or a screen recording) into a separate iCloud "
                "shared album, then paste its link. Only files you provide are analysed — nothing is downloaded "
                "from TikTok/YouTube. Cuts and shot lengths are measured; Claude describes the style from frames.")
    rlink = st.text_input("References album link", key="rlink", placeholder="https://photos.icloud.com/shared/album/…")
    c1, c2 = st.columns(2)
    if c1.button("Fetch & analyse references", disabled=not rlink.startswith("https://photos.icloud.com/")):
        queue("refs", rlink.strip(), "Reference Lab")
    if c2.button("Re-analyse files in refs/"):
        queue("refs", "", "Reference Lab")
    refs.ensure(con)
    for r in con.execute("SELECT * FROM ref_videos ORDER BY analyzed_at DESC"):
        stt, prof = jload(r["shot_stats"], {}), jload(r["profile"], {})
        with st.expander(f"🎞 {r['ref_id']} · {r['duration']:.1f}s · {stt.get('shots')} shots · "
                         f"avg {stt.get('avg_shot_s')}s"):
            if r["strip"] and os.path.exists(r["strip"]):
                st.image(r["strip"])
            if prof:
                hk, tx = prof.get("hook", {}), prof.get("text", {})
                st.markdown(f"**Hook:** {hk.get('pattern')} — {hk.get('first_text', '')}  \n"
                            f"**Text:** {tx.get('density')} · {tx.get('position')} · {tx.get('treatment')} · "
                            f"{tx.get('animation')}  \n**Loop:** {prof.get('loop', '')}  \n"
                            f"**Why it might work (hypothesis):** {prof.get('why_it_might_work', '')}")
                st.markdown("**Style rules:**\n" + "\n".join(f"- {x}" for x in prof.get("style_rules", [])))
                st.caption(f"With your footage: {prof.get('fit_with_travel_footage', '')}")
            else:
                st.caption("Waiting for Claude's style profile…")

# ---------------- Ideas ----------------
with tab_ideas:
    with st.expander("🎨 Brand kit — style lock used by every video"):
        from factory.ideas import brand, BRAND_PATH
        bk = brand()
        c1, c2 = st.columns(2)
        acc = c1.color_picker("Accent colour (key words, numbers)", bk.get("accent_hex", "#FFD93D"))
        pers = c2.selectbox("Motion personality", ["auto", "premium", "energetic"],
                            index=["auto", "premium", "energetic"].index(bk.get("personality", "auto")))
        c3, c4 = st.columns(2)
        sfx_d = c3.selectbox("Default sound effects", ["subtle", "full", "off"],
                             index=["subtle", "full", "off"].index(bk.get("sfx_default", "subtle")))
        opacity = c4.slider("Card panel opacity %", 50, 95, round((255 - int(bk.get("panel_alpha", "38"), 16)) / 2.55))
        if st.button("Save brand kit"):
            bk.update(accent_hex=acc, personality=pers, sfx_default=sfx_d,
                      panel_alpha=f"{round(255 - opacity * 2.55):02X}")
            json.dump(bk, open(BRAND_PATH, "w"), indent=2)
            st.success("Saved — applies to the next render.")
    with st.expander("📒 Playbook & taste — lessons, likes and dislikes (fed into every idea run)"):
        c1, c2 = st.columns([3, 1])
        lesson = c1.text_input("New note", placeholder="e.g. list cards over 8 s lost viewers; keep them 6-7 s")
        kind = c2.selectbox("Type", ["lesson", "like", "dislike"])
        if st.button("Add note") and lesson.strip():
            con.execute("INSERT INTO playbook (lesson, source, created_at) VALUES (?,?,datetime('now'))",
                        (lesson.strip(), kind))
            con.commit()
        icon_k = {"like": "👍", "dislike": "👎"}
        for p in con.execute("SELECT * FROM playbook ORDER BY id DESC"):
            st.markdown(f"- {icon_k.get(p['source'], '📌')} {p['lesson']}")
    st.subheader("Generate ideas from your clips + signals")
    brief = st.text_area("Brief (optional)", placeholder="e.g. energetic, use the Partnach gorge, sourced psychology facts")
    n = st.slider("How many ideas", 1, 8, 4)
    if st.button("Generate ideas", type="primary"):
        queue("ideas", json.dumps({"n": n, "brief": brief}), "Idea generation")
    status_icon = {"proposed": "🆕", "verified": "✅", "needs_changes": "⚠️", "approved": "👍", "rendered": "🎬"}
    for row in con.execute("SELECT * FROM ideas ORDER BY idea_id DESC LIMIT 30"):
        idea = jload(row["data"], {})
        with st.expander(f"{status_icon.get(row['status'], '•')} #{row['idea_id']} {row['title']} · {row['series']}"):
            th = idea.get("theme", {})
            st.markdown(f"**Theme:** {th.get('concept', '')} · *{th.get('mood', '')}* · {th.get('palette', '')}")
            st.markdown(f"**Hook:** {idea.get('hook', '')} · *{idea.get('hook_pattern', '')}*  \n"
                        f"**Mechanism (hypothesis):** {idea.get('mechanism', '')}")
            cv = idea.get("cover") or {}
            if cv:
                st.markdown(f"**Cover:** {cv.get('clip_id')} @ {cv.get('time')}s · **{cv.get('text', '')}**  \n"
                            f"**Congruency:** {idea.get('congruency', '')}")
            st.markdown(f"**Content fit:** {idea.get('content_fit', '—')} — {idea.get('fit_reason', '')}")
            st.markdown("**Script & animation** — edit text (use `/` for a new line, `*word*` for the accent) "
                        "or timings, then save")
            from factory.ideas import ANIMATIONS, BEAT_TYPES
            rows = [{"t0": float(b.get("t0", 0)), "t1": float(b.get("t1", 0)), "type": b.get("type"),
                     "animation": b.get("animation"), "text": (b.get("text") or "").replace("\\N", " / ")}
                    for b in idea.get("beats", [])]
            edited = st.data_editor(rows, key=f"be{row['idea_id']}", hide_index=True, width='stretch',
                                    num_rows="dynamic", column_config={
                                        "type": st.column_config.SelectboxColumn(options=list(BEAT_TYPES)),
                                        "animation": st.column_config.SelectboxColumn(options=list(ANIMATIONS))})
            cs1, cs2 = st.columns(2)
            level = cs1.selectbox("Sound effects", ["subtle", "full", "off"], key=f"sfx{row['idea_id']}",
                                  index=["subtle", "full", "off"].index(idea.get("sfx_level", "subtle")))
            if cs2.button("Save edits", key=f"save{row['idea_id']}"):
                new_beats = []
                for r_, old in zip(edited, idea.get("beats", []) + [{}] * len(edited)):
                    nb = {**old, **r_, "text": (r_.get("text") or "").replace(" / ", "\\N")}
                    new_beats.append(nb)
                idea["beats"], idea["sfx_level"] = new_beats, level
                status = "proposed" if row["status"] in ("verified", "rendered") else row["status"]
                con.execute("UPDATE ideas SET data=?, status=? WHERE idea_id=?",
                            (json.dumps(idea, ensure_ascii=False), status, row["idea_id"]))
                con.commit()
                st.success("Saved — re-verify if you changed a claim, then render again.")
            st.markdown("**Shots:** " + " → ".join(
                f"{s['clip_id']}" + (f" [{s['start']}–{s['end']}s ×{s.get('speed', 1)}]" if "start" in s else f" [{s['dur']}s]")
                + f" ({s.get('transition')})" for s in idea.get("shots", [])))
            if idea.get("animation_notes"):
                st.markdown("**Animation ideas:** " + "; ".join(idea["animation_notes"]))
            prod = idea.get("production", {})
            st.markdown(f"**Production:** music: {prod.get('music', '')} · pacing: {prod.get('pacing', '')}")
            for k in ("edit_notes", "shooting_tips"):
                if prod.get(k):
                    st.markdown(f"*{k.replace('_', ' ')}:* " + "; ".join(prod[k]))
            st.code(f"{idea.get('caption', '')}\n\n{idea.get('hashtags', '')}", language=None)
            claims = idea.get("claims", [])
            ver = jload(row["verification"], None)
            if claims:
                st.markdown("**Claims to verify:** " + "; ".join(c.get("claim", "") for c in claims))
            if ver:
                for v in ver.get("verdicts", []):
                    icon = {"supported": "✅", "partly": "🟡", "unsupported": "⚠️", "false": "❌"}.get(v.get("verdict"), "•")
                    src = ", ".join(f"[{s.get('title', 'source')[:40]}]({s.get('url')})" for s in v.get("sources", [])[:3])
                    st.markdown(f"{icon} {v.get('claim')} — {v.get('note', '')} {src}")
                    if v.get("safer_wording"):
                        st.caption(f"Safer wording: {v['safer_wording']}")
            if idea.get("preview_sheet") and os.path.exists(idea["preview_sheet"]):
                st.image(idea["preview_sheet"], caption="Style frames (draft): cover + one frame per beat")
            if st.button("Preview frames (fast draft)", key=f"pv{row['idea_id']}"):
                queue("preview", str(row["idea_id"]), "Preview")
            c1, c2, c3 = st.columns(3)
            if c1.button("Verify claims", key=f"v{row['idea_id']}", disabled=not claims):
                queue("verify", str(row["idea_id"]), "Verification")
            ok = row["status"] == "verified" or not claims
            force = c3.checkbox("render anyway", key=f"f{row['idea_id']}") if not ok else True
            if c2.button("Approve & render", key=f"r{row['idea_id']}", type="primary", disabled=not (ok or force)):
                con.execute("UPDATE ideas SET status='approved' WHERE idea_id=?", (row["idea_id"],))
                con.commit()
                queue("render", str(row["idea_id"]), "Render")
            if row["output"]:
                st.success(f"Rendered → Shorts tab / {row['output']}")
            qa_ = jload(row["qa"], None)
            if qa_:
                tech, vis = qa_.get("technical", {}), qa_.get("visual", {})
                st.markdown(("✅ **QA passed**" if qa_.get("pass") else "🔎 **QA found issues**") +
                            f" · {tech.get('duration')}s · {tech.get('lufs', '—')} LUFS · peak {tech.get('true_peak_db', '—')} dBFS")
                for pr in tech.get("problems", []):
                    st.error(pr)
                for it in vis.get("issues", []):
                    st.markdown(f"- **{it.get('severity')}** @ {it.get('time')}s — {it.get('problem')}  \n  *fix:* {it.get('fix')}")
                if qa_.get("sheet") and os.path.exists(qa_["sheet"]):
                    st.image(qa_["sheet"], caption="QA frames (mid-beat; t=0 is the cover)")

# ---------------- Shorts (finished videos) ----------------
# The Shorts Paneli (shorts/, port 8095) is the phone-friendly player/downloader for out/: it streams
# with range requests, copies captions over plain http and lists every finished video. It is embedded here so the
# whole studio lives behind one address.
with tab_out:
    import streamlit.components.v1 as components
    from factory import config
    SHORTS_URL = os.environ.get("CF_SHORTS_URL") or f"http://{config.HOST or st.context.headers.get('host', 'localhost').split(':')[0]}:{config.SHORTS_PORT}"
    c1, c2 = st.columns([3, 1])
    c1.caption("Finished videos with preview, download and caption copy.")
    c2.link_button("Open full screen", SHORTS_URL)
    components.iframe(SHORTS_URL, height=1500, scrolling=True)
