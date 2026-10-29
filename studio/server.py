#!/usr/bin/env python3
"""Content Factory Studio: production board, generation, publish tracking and budget in one phone-friendly page.

Stdlib only (like the Shorts panel). Listens on the Tailscale address and refuses clients outside the tailnet.
State-changing calls are POSTs that must carry the X-Studio header (a cross-site form cannot set it).
Long work runs as factory jobs (separate processes), so the server stays responsive.

Usage: server.py [--port 8501] [--host <tailscale ip>]   (defaults from config.env: CF_STUDIO_PORT, CF_HOST)
"""
import argparse, hashlib, shutil, importlib.util, json, os, re, secrets, subprocess, sys, threading, time, traceback, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from factory import accounts, channels, claudeauth, credits, discover, eleven_api, explainer, illustrate, planner, series, styles, formats, jobs, productions as P, refs, signals, tracking, usage, llm  # noqa: E402
from factory.store import connect  # noqa: E402

# the Shorts panel's module (caption parsing, out/ listing, thumbnails, range streaming), loaded by path because
# both files are called server.py
_spec = importlib.util.spec_from_file_location("shorts_panel", os.path.join(ROOT, "shorts", "server.py"))
shorts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shorts)

from factory.config import FFMPEG, HOST, ROOT, STUDIO_PORT  # noqa: E402  (data root may differ from the code dir: CF_ROOT)
THUMBS = os.path.join(ROOT, "work", "thumbs")
PROFILE = os.path.join(ROOT, "data", "eleven_profile.json")
MAX_UPLOAD = 600 * 1024 * 1024
OUT = os.path.join(ROOT, "out")
TAILNET = shorts.TAILNET
thumb_lock = threading.Lock()
CODEX_MCP_LOCK = threading.Lock()
CODEX_MCP_FLOW = {"status": "idle", "url": None, "state": None, "callback_url": None,
                  "process": None, "error": None, "owner": None}
CODEX_MCP_CALLBACK = "/api/codex/elevenlabs/callback"


def codex_public_url():
    """HTTPS tailnet URL used as the OAuth redirect target (Tailscale Serve fronts this app)."""
    configured = os.environ.get("CF_PUBLIC_URL", "").rstrip("/")
    if configured.startswith("https://"):
        return configured
    try:
        serve = subprocess.run(["tailscale", "serve", "status", "--json"], capture_output=True,
                               text=True, timeout=5)
        serve_config = json.loads(serve.stdout or "{}") if serve.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        serve_config = {}
    if not serve_config:
        raise ValueError("Hesaplar → Tailscale Serve'de HTTPS'i etkinleştir; OAuth dönüş adresi için güvenli bağlantı gerekiyor")
    try:
        p = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=5)
        name = json.loads(p.stdout).get("Self", {}).get("DNSName", "").rstrip(".") if p.returncode == 0 else ""
        if name:
            return "https://" + name
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    raise ValueError("Güvenli OAuth dönüş adresi bulunamadı (CF_PUBLIC_URL veya Tailscale Serve gerekli)")


def _read_codex_oauth(proc, ready):
    """Keep the CLI login alive, expose only its authorization URL, and track completion."""
    try:
        for line in iter(proc.stdout.readline, ""):
            if "elevenlabs.io/app/oauth/authorize?" in line:
                url = line.strip()
                parsed = urllib.parse.urlsplit(url)
                state = (urllib.parse.parse_qs(parsed.query).get("state") or [None])[0]
                with CODEX_MCP_LOCK:
                    if CODEX_MCP_FLOW.get("process") is proc:
                        CODEX_MCP_FLOW.update(url=url, state=state, status="waiting", error=None)
                ready.set()
            if proc.poll() is not None:
                break
        rc = proc.wait(timeout=10)
        with CODEX_MCP_LOCK:
            if CODEX_MCP_FLOW.get("process") is proc:
                CODEX_MCP_FLOW.update(status="connected" if rc == 0 and llm.codex_elevenlabs_status().get("connected")
                                      else "error", url=None,
                                      error=None if rc == 0 else "Codex OAuth girişi tamamlanamadı", process=None)
    except Exception as exc:
        with CODEX_MCP_LOCK:
            if CODEX_MCP_FLOW.get("process") is proc:
                CODEX_MCP_FLOW.update(status="error", error=f"Codex OAuth: {exc}", process=None, url=None)


def start_codex_oauth(uid):
    if not accounts.is_owner(uid):
        raise ValueError("Codex ElevenLabs bağlantısını yalnızca hesap sahibi yönetebilir")
    status = llm.codex_elevenlabs_status()
    if status.get("connected"):
        return {"connected": True}
    with CODEX_MCP_LOCK:
        proc = CODEX_MCP_FLOW.get("process")
        if proc and proc.poll() is None and CODEX_MCP_FLOW.get("url"):
            return {"url": CODEX_MCP_FLOW["url"]}
        if proc and proc.poll() is None:
            raise ValueError("Codex bağlantı penceresi hazırlanıyor; birkaç saniye sonra tekrar dene")
    public_url = codex_public_url()
    callback_url = public_url + CODEX_MCP_CALLBACK
    server_name = status.get("name") or "elevenlabs"
    cmd = [llm.CODEX, "mcp", "login", server_name, "--no-browser", "--oauth-client-registration", "dcr",
           "-c", f'mcp_oauth_callback_url="{callback_url}"']
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, cwd=ROOT)
    except OSError as exc:
        raise ValueError(f"Codex CLI başlatılamadı: {exc}") from None
    ready = threading.Event()
    with CODEX_MCP_LOCK:
        CODEX_MCP_FLOW.update(status="starting", url=None, state=None, callback_url=callback_url,
                              process=proc, error=None, owner=uid)
    threading.Thread(target=_read_codex_oauth, args=(proc, ready), daemon=True).start()
    if not ready.wait(20):
        with CODEX_MCP_LOCK:
            error = CODEX_MCP_FLOW.get("error")
        raise ValueError(error or "Codex OAuth bağlantısı başlatılamadı")
    with CODEX_MCP_LOCK:
        if CODEX_MCP_FLOW.get("status") != "waiting":
            raise ValueError(CODEX_MCP_FLOW.get("error") or "Codex OAuth bağlantısı başlatılamadı")
        return {"url": CODEX_MCP_FLOW["url"]}


# ---------- read models ----------
def job_rows(con, limit=10):
    out = []
    for r in con.execute("SELECT * FROM jobs ORDER BY job_id DESC LIMIT ?", (limit,)):
        d = dict(r)
        if d["status"] in ("running", "queued", "failed") and d["log"] and os.path.exists(d["log"]):
            d["tail"] = "".join(open(d["log"], errors="replace").readlines()[-6:])
        d.pop("log", None)
        out.append(d)
    return out


def busy(con, p):
    if not p.get("job_id"):
        return None
    j = con.execute("SELECT job_id, kind, status FROM jobs WHERE job_id=?", (p["job_id"],)).fetchone()
    return dict(j) if j and j["status"] in ("queued", "running") else None


_timeline_cache = {}   # (prod_id, updated_at) -> (total, warnings): compiling every timeline on every poll was slow


def prod_summary(con, p):
    d = p["data"] or {}
    shots = d.get("shots") or [{}]
    key = (p["prod_id"], p["updated_at"])
    if key not in _timeline_cache:
        try:
            _, total, _, warn = P.shown_timeline(con, p)
        except Exception:
            total, warn = None, ["zaman çizelgesi hesaplanamadı"]
        if len(_timeline_cache) > 2000:
            _timeline_cache.clear()
        _timeline_cache[key] = (total, warn)
    total, warn = _timeline_cache[key]
    thumb = None
    if d.get("plates"):   # illustrated / series: the first illustration is the cover
        first = next(iter(d["plates"].values()))
        thumb = "/media/assets/" + first["file"].split("assets/", 1)[-1] if first.get("file") else None
    elif p["output"]:
        thumb = f"/thumb/out/{p['output']}/{p['output']}.mp4"
    return {"prod_id": p["prod_id"], "title": p["title"], "format": p["format"], "stage": p["stage"],
            "updated_at": p["updated_at"], "created_at": p["created_at"], "hook": d.get("hook"),
            "thumb": shots[0].get("clip_id"), "thumb_t": shots[0].get("in", 0), "thumb_url": thumb, "duration": total,
            "warn": len(warn), "busy": busy(con, p), "output": p["output"], "name": p["name"],
            "voice": bool(d.get("voice")), "qa_pass": (p["qa"] or {}).get("pass"), "aspect": d.get("aspect", "9:16"),
            "channel_id": p.get("channel_id"), "kind": "series" if d.get("series") else d.get("kind") or "footage",
            "look": d.get("look_pack"), "series": d.get("series")}


def all_prods(con, channel=None):
    P.ensure(con)
    q, args = "SELECT prod_id FROM productions", []
    if channel:
        q, args = q + " WHERE channel_id=?", [channel]
    rows = con.execute(q + " ORDER BY updated_at DESC", args).fetchall()
    return [prod_summary(con, P.get(con, r["prod_id"])) for r in rows]


NEXT_STEP = {"idea": "Fikri onayla veya değiştir", "voice": "Ses metnini ve kredi tahminini onayla",
             "preview": "Önizlemeyi izle, onayla", "ready": "Paylaş ve linki ekle"}


def overview(con, channel=None):
    prods = all_prods(con, channel)
    counts = {s: 0 for s in P.STAGES}
    for p in prods:
        counts[p["stage"]] = counts.get(p["stage"], 0) + 1
    has_preview = {r["prod_id"] for r in con.execute("SELECT prod_id FROM productions WHERE preview IS NOT NULL")}
    pending = [{**p, "next": NEXT_STEP[p["stage"]]} for p in prods if p["stage"] in NEXT_STEP and not p["busy"]
               and not (p["stage"] == "preview" and p["prod_id"] not in has_preview)]
    month = time.strftime("%Y-%m-01")
    made = con.execute("SELECT COUNT(*) n FROM productions WHERE stage IN ('ready','published') AND updated_at>=?",
                       (month,)).fetchone()["n"]
    clips = con.execute("SELECT COUNT(*) n, SUM(kind='video') v, SUM(described_at IS NOT NULL) d FROM clips").fetchone()
    jr = job_rows(con, 8)
    return {"counts": counts, "pending": pending, "jobs": jr, "made_this_month": made,
            "budget": {"spent": round(credits.month_spent(con)), "cap": credits.MONTHLY_CAP},
            "tracking": tracking.summary(con),
            "clips": {"total": clips["n"] or 0, "videos": clips["v"] or 0, "described": clips["d"] or 0},
            "albums": [dict(r) for r in con.execute("SELECT * FROM albums ORDER BY last_sync DESC")],
            "busy": any(j["status"] in ("queued", "running") for j in jr), "recent": prods[:12]}


def production_detail(con, pid):
    p = P.get(con, pid)
    fmt = formats.for_data(p["format"], p["data"])
    out = {**p, "format_info": fmt, "busy": busy(con, p), "claims_ok": P.claims_ok(p)}
    try:
        spec, total, starts, warn = P.shown_timeline(con, p)
        if p["data"].get("motion"):   # HTML-designed scenes: the script-stage stock photos are not used
            warn = [w for w in warn if "açık lisanslı görsel" not in w]
        out["timeline"] = {"spec": spec, "total": total, "starts": starts, "warn": warn}
    except Exception as e:
        out["timeline"] = {"error": f"{type(e).__name__}: {e}"}
    if fmt["voice"]:
        out["estimate"] = P.voice_estimate(con, p["data"])
    lib = {r["ref_id"]: r for r in refs.library(con)}
    out["refs"] = [lib[r] for r in (p["data"].get("refs") or []) if r in lib]
    aid = P.eleven_account(p["data"])
    out["eleven_account"], out["eleven_accounts"] = aid, accounts.usable_eleven()
    out["voices"] = eleven_info(aid)["voices"]
    out["default_voice"] = formats.default_voice(p["data"].get("lang"), aid)
    if True:  # every production can get a generated track (styled ones also cut on its beats)
        try:
            out["music_estimate"] = P.music_estimate(con, p)
        except Exception as e:
            out["music_estimate"] = {"error": str(e)}
    if out["busy"]:
        log = con.execute("SELECT log FROM jobs WHERE job_id=?", (p["job_id"],)).fetchone()["log"]
        if log and os.path.exists(log):
            out["busy"]["tail"] = "".join(open(log, errors="replace").readlines()[-8:])
    clip_ids = [s["clip_id"] for s in p["data"].get("shots", [])]
    if clip_ids:
        q = f"SELECT clip_id, description, captured_at, kind FROM clips WHERE clip_id IN ({','.join('?' * len(clip_ids))})"
        out["clips"] = {r["clip_id"]: dict(r) for r in con.execute(q, clip_ids)}
    if p["output"]:
        folder = os.path.join(OUT, p["output"])
        cap = os.path.join(folder, "caption.txt")
        out["caption"] = shorts.parse_caption(open(cap).read()) if os.path.exists(cap) else None
        out["caption_copy"] = shorts.copy_text(out["caption"])
        out["thumbs"] = sorted(f for f in os.listdir(folder) if f.startswith("thumb_") and f.endswith(".jpg")) \
            if os.path.isdir(folder) else []
    out["posts"] = [x for x in tracking.posts(con) if x["prod_id"] == pid]
    out["channel"] = channels.of(con, p)
    out["brand_on"] = p["data"].get("brand") is not False
    from factory import capabilities, talk
    out["recipe"] = {"direction": (p["data"].get("recipe") or {}).get("direction"),
                     "techniques": capabilities.labels(p["data"]), "seconds": (p["data"].get("recipe") or {}).get("seconds")}
    from factory import explainer
    if explainer.is_explainer(p["data"]):
        from factory import renderspeed   # how long this one's render takes on this machine (measured)
        sec = (p["data"].get("voice_take") or {}).get("duration") or ((p["data"].get("recipe") or {}).get("seconds") or [0, 30])[-1]
        e = renderspeed.estimate(float(sec), capabilities.techniques(p["data"]), int(p["data"].get("motion_blur") or 1))
        out["render_eta"] = {**e, "preview": renderspeed.label(e["preview_s"]), "final": renderspeed.label(e["final_s"])}
    if talk.is_talk(p["data"]):
        try:
            out["talk"] = talk.summary(p["data"])
        except (OSError, ValueError, KeyError) as e:
            out["talk"] = {"error": str(e)}
    snd = (p.get("qa") or {}).get("sound") or {}
    if snd.get("sheet"):
        out["sound_sheet"] = "/media/" + snd["sheet"]
    if illustrate.needs_plates(p["data"]) or p["data"].get("plates"):
        out["plates_estimate"] = illustrate.estimate(con, p["data"], aid)
        out["plates"] = {k: "/media/assets/" + v["file"].split("assets/", 1)[-1] for k, v in (p["data"].get("plates") or {}).items()}
    if p["data"].get("series"):
        try:
            s = series.get(con, p["data"]["series"]["id"])
            out["series_info"] = {"id": s["series_id"], "title": s["title"],
                                  "characters": [{k: c.get(k) for k in ("id", "name")} for c in s["data"].get("characters") or []]}
        except ValueError:
            pass
    return out


def budget(con):
    credits.ensure(con)
    ledger = [dict(r) for r in con.execute("SELECT * FROM eleven_ledger ORDER BY id DESC LIMIT 100")]
    by_kind = {}
    month = time.strftime("%Y-%m-01")
    for r in ledger:
        if r["at"] >= month:
            by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + (r["credits"] or 0)
    return {"spent": round(credits.month_spent(con)), "cap": credits.MONTHLY_CAP, "ledger": ledger,
            "by_kind": {k: round(v) for k, v in by_kind.items()}, "rates": credits.rates()}


def signal_data(con, profile):
    _, short, runs = signals.radar_candidates(profile=profile)
    keep = ("title", "url", "views", "duration_s", "viral_score", "confidence", "icahn", "views_per_sub",
            "channel_title", "age_h", "thumbnail", "subtopics")
    trends, when = signals.latest_trends(con)
    return {"radar": [{k: c.get(k) for k in keep} for c in short[:20]], "runs": runs[:3],
            "trends": [dict(t) for t in trends][:30], "trends_at": when}


def places(con):
    rows = con.execute("""SELECT p.place_id, p.name, p.day, COUNT(c.clip_id) n, SUM(c.kind='video') v,
                          MIN(c.clip_id) sample FROM places p JOIN clips c ON c.place_id=p.place_id AND c.usable=1
                          GROUP BY p.place_id ORDER BY p.day, p.place_id""").fetchall()
    return [dict(r) for r in rows]


def library(con):
    vids = shorts.list_videos(OUT)
    names = {r["name"]: r["prod_id"] for r in con.execute("SELECT name, prod_id FROM productions WHERE name IS NOT NULL")}
    posted = {}
    for x in tracking.posts(con):
        posted.setdefault(x["out_name"], []).append({"platform": x["platform"], "url": x["url"]})
    for v in vids:
        folder = v["id"].split("/")[0]
        v["prod_id"], v["posts"], v["folder"] = names.get(folder), posted.get(folder, []), folder
    return vids



def _rm(path, roots):
    """Remove a file or folder, but only if it really sits inside one of the allowed roots."""
    real = os.path.realpath(path)
    if not any(real.startswith(os.path.realpath(r) + os.sep) for r in roots) or not os.path.lexists(path):
        return 0
    size = 0
    for dp, _, fs in os.walk(real):
        size += sum(os.path.getsize(os.path.join(dp, f)) for f in fs if os.path.isfile(os.path.join(dp, f)))
    size += os.path.getsize(real) if os.path.isfile(real) else 0
    shutil.rmtree(real) if os.path.isdir(real) else os.remove(real)
    return size


def purge_production(con, p):
    """Delete a production for good: its row and every file made for it (final video, preview, work folders)."""
    freed, work = 0, os.path.join(ROOT, "work")
    names = {n for n in (p.get("name"), p.get("output")) if n and "/" not in n and not n.startswith(".")}
    for n in names:
        freed += _rm(os.path.join(OUT, n), [OUT])
        for sub in os.scandir(work):
            if sub.is_dir():
                for cand in (n, n + ".mp4", n + ".json"):
                    freed += _rm(os.path.join(sub.path, cand), [work])
    freed += _rm(os.path.join(work, "explainer", f"auto-{p['prod_id']}"), [work])
    con.execute("UPDATE posts SET prod_id=NULL WHERE prod_id=?", (p["prod_id"],))
    con.execute("DELETE FROM productions WHERE prod_id=?", (p["prod_id"],))
    con.commit()
    return freed


def delete_library_video(con, folder):
    """Delete a finished video folder from out/; its production goes back to the preview stage."""
    if not folder or "/" in folder or folder.startswith("."):
        raise ValueError("geçersiz klasör")
    freed = _rm(os.path.join(OUT, folder), [OUT])
    if not freed:
        raise ValueError("video bulunamadı")
    for r in con.execute("SELECT prod_id FROM productions WHERE output=?", (folder,)).fetchall():
        p = P.get(con, r["prod_id"])
        p["output"], p["stage"] = None, ("preview" if p["stage"] in ("ready", "published") else p["stage"])
        P.save(con, p, "video silindi", folder)
    return {"ok": True, "freed_mb": round(freed / 1e6)}


def delete_ref(con, ref_id):
    r = con.execute("SELECT path, grid FROM ref_videos WHERE ref_id=?", (ref_id,)).fetchone()
    if not r:
        raise ValueError("referans bulunamadı")
    freed = _rm(r["path"], refs.LIBRARY_DIRS)   # the file too, or the folder scan would add it again
    if r["grid"]:
        freed += _rm(r["grid"], [os.path.join(ROOT, "work")])
    con.execute("DELETE FROM ref_videos WHERE ref_id=?", (ref_id,))
    con.commit()
    try:
        tp = os.path.join(refs.REFS, ".themes.json")
        t = json.load(open(tp))
        if t.pop(os.path.basename(r["path"]), None) is not None:
            json.dump(t, open(tp, "w"))
    except (OSError, ValueError):
        pass
    return {"ok": True, "freed_mb": round(freed / 1e6)}


# ---------- actions ----------
class Conflict(Exception):
    pass


def queue_for(con, p, kind, arg):
    jid = jobs.queue(con, kind, arg)
    p = P.get(con, p["prod_id"])
    p["job_id"] = jid
    P.save(con, p)
    return jid


def act(con, pid, body):
    p = P.get(con, pid)
    a = body.get("action")
    if busy(con, p) and a not in ("note",):
        raise Conflict("Bu video için bir iş zaten çalışıyor")
    if a == "delete":
        return {"ok": True, "freed_mb": round(purge_production(con, p) / 1e6)}
    fmt = formats.for_data(p["format"], p["data"])
    if a == "approve_idea":
        p["stage"] = "voice" if fmt["voice"] else "preview"
        P.save(con, p, "onay", "fikir onaylandı")
        if not fmt["voice"]:
            queue_for(con, p, "p_preview", str(pid))
    elif a == "reject":
        p["stage"] = "rejected"
        reason = (body.get("reason") or "").strip()
        P.save(con, p, "reddedildi", reason)
        if reason and body.get("lesson"):
            con.execute("INSERT INTO playbook (lesson, source, created_at) VALUES (?,?,datetime('now'))",
                        (reason, "dislike"))
            con.commit()
    elif a == "restore":
        p["stage"] = "idea"
        P.save(con, p, "geri alındı")
    elif a == "save":
        new = json.loads(json.dumps(p["data"]))
        e = body.get("edit") or {}
        for k in ("title", "hook", "end_card"):
            if k in e:
                new[k] = e[k].strip()
        if "voice_lines" in e and new.get("voice") is not None:
            new["voice"]["lines"] = [x.strip() for x in e["voice_lines"] if x.strip()]
        if "shot_texts" in e:
            for s, t in zip(new["shots"], e["shot_texts"]):
                s["text"] = t.strip()
        for k in ("caption", "hashtags", "location", "music"):
            if k in e:
                new.setdefault("post", {})[k] = e[k].strip()
        P.apply_edit(con, p, new, "düzenleme", "elle düzenlendi")
    elif a == "revise":
        fb = (body.get("feedback") or "").strip()
        if not fb:
            raise ValueError("Ne değişsin? Kısa bir not yaz.")
        queue_for(con, p, "p_revise", json.dumps({"id": pid, "feedback": fb}, ensure_ascii=False))
    elif a == "plan_edit":
        fb = (body.get("feedback") or "").strip()
        if not fb:
            raise ValueError("Neyi düzenlemek istediğini yaz.")
        if p["stage"] in ("published", "rejected"):
            raise ValueError("Yayınlanmış/reddedilmiş videoda düzenleme yok")
        queue_for(con, p, "p_plan", json.dumps({"id": pid, "feedback": fb}, ensure_ascii=False))
    elif a == "apply_plan":
        plan = p["data"].get("edit_plan")
        steps = [x for x in (body.get("steps") or []) if x in ("script", "design", "voice")]
        if not plan or not steps:
            raise ValueError("Önce plan çıkar, en az bir adım seç")
        queue_for(con, p, "p_plan_apply", json.dumps({"id": pid, "steps": steps}))
    elif a == "discard_plan":
        p["data"].pop("edit_plan", None)
        P.save(con, p, "plan iptal")
    elif a == "verify":
        queue_for(con, p, "p_verify", str(pid))
    elif a == "approve_voice":
        est = P.voice_estimate(con, p["data"])
        approved = int(body.get("approved") or 0)
        if est["unknown"] or approved < est["credits"]:
            raise ValueError("Onaylanan kredi, güncel tahminden düşük. Sayfayı yenileyip tekrar onayla.")
        if not est["budget"]["ok"]:
            raise ValueError("Aylık kredi tavanı aşılır")
        P.save(con, p, "kredi onayı", f"{est['credits']} kredi ({est['chars']} karakter)")
        queue_for(con, p, "p_voice", json.dumps({"id": pid, "approved": est["credits"]}))
    elif a == "preview":
        if fmt["voice"] and not (p["data"].get("voice_take") and p["data"]["voice_take"].get("text") == P.voice_text(p["data"])):
            raise ValueError("Önce ses üretilmeli")
        queue_for(con, p, "p_preview", str(pid))
    elif a == "approve_render":
        if not P.claims_ok(p) and not body.get("force"):
            raise ValueError("Doğrulanmamış iddialar var: önce doğrula ya da 'yine de render' seç")
        P.save(con, p, "onay", "önizleme onaylandı")
        queue_for(con, p, "p_render", str(pid))
    elif a == "set_refs":
        ids = [r for r in (body.get("ref_ids") or []) if isinstance(r, str)][:3]
        p["data"]["refs"] = ids
        P.save(con, p, "referans", ", ".join(ids) or "kaldırıldı")
        if ids and not p["data"].get("look") and body.get("restyle", True):
            queue_for(con, p, "p_revise", json.dumps({"id": pid, "feedback": "Re-edit this video in the style of "
                      "the attached reference videos (frame, grade, pace on the beat, title card and text layers). "
                      "Keep the story and the best shots."}))
    elif a == "set_channel":
        cid = body.get("channel")
        if not channels.get(con, cid):
            raise ValueError("kanal bulunamadı")
        con.execute("UPDATE productions SET channel_id=? WHERE prod_id=?", (cid, pid))
        con.commit()
        P.save(con, P.get(con, pid), "kanal", channels.get(con, cid)["name"])
    elif a == "set_brand":
        p["data"]["brand"] = bool(body.get("on"))
        if p["stage"] == "preview":
            p["preview"] = None
        P.save(con, p, "marka katmanı", "açık" if p["data"]["brand"] else "kapalı")
        if p["stage"] == "preview" and (not fmt["voice"] or p["data"].get("voice_take")):
            queue_for(con, p, "p_preview", str(pid))
    elif a == "approve_plates":
        est = illustrate.estimate(con, p["data"], P.eleven_account(p["data"]))
        approved = int(body.get("approved") or 0)
        if not est["images"]:
            raise ValueError("Bütün çizimler hazır")
        if est["unknown"] or approved < est["credits"]:
            raise ValueError("Onaylanan kredi güncel tahminden düşük; sayfayı yenile")
        if not est["budget"]["ok"]:
            raise ValueError("Aylık kredi tavanı aşılır")
        P.save(con, p, "kredi onayı", f"çizimler {est['credits']} kredi ({est['images']} görsel)")
        queue_for(con, p, "p_plates", json.dumps({"id": pid, "approved": est["credits"]}))
    elif a == "set_aspect":
        asp = body.get("aspect")
        if asp not in formats.ASPECTS:
            raise ValueError("Kadraj 9:16 ya da 16:9 olmalı")
        if asp == p["data"].get("aspect", "9:16"):
            return production_detail(con, pid)
        label = "yatay 16:9" if asp == "16:9" else "dikey 9:16"
        if p["stage"] in ("ready", "published"):
            # keep the finished version; the other canvas becomes its own production (e.g. Shorts + YouTube)
            data = json.loads(json.dumps(p["data"]))
            data["aspect"] = asp
            new_id = P.create(con, p["format"], data, p.get("brief") or "")
            c = P.get(con, new_id)
            c["title"] = f"{p['title']} ({label})"
            c["stage"] = "preview"
            c["history"].append({"at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), "event": "kopya",
                                 "detail": f"#{pid} videosunun {label} sürümü"})
            P.save(con, c)
            fmt_c = formats.for_data(c["format"], data)
            if not fmt_c["voice"] or (data.get("voice_take") and data["voice_take"].get("text") == P.voice_text(data)):
                queue_for(con, c, "p_preview", str(new_id))
            P.save(con, p, "kopya", f"{label} sürümü → #{new_id}")
            out = production_detail(con, new_id)
            out["redirect"] = new_id
            return out
        p["data"]["aspect"] = asp
        if p["stage"] == "preview":
            p["preview"] = None
        if explainer.is_explainer(p["data"]) and p["data"].get("motion"):
            # an Opus design is laid out for one canvas: design again for the new one before any preview
            p["data"]["look_pack"] = "illustrated" if p["data"].get("illustrated") else "auto"
            P.save(con, p, "kadraj", label + " · yeniden tasarım")
            queue_for(con, p, "p_design", json.dumps({"id": pid, "note": f"The canvas changed to {asp}: lay every scene out for it."}))
            return production_detail(con, pid)
        P.save(con, p, "kadraj", label)
        if p["stage"] == "preview" and (not fmt["voice"] or (p["data"].get("voice_take") and
                                                             p["data"]["voice_take"].get("text") == P.voice_text(p["data"]))):
            queue_for(con, p, "p_preview", str(pid))
    elif a == "redesign":
        if not explainer.is_explainer(p["data"]) or p["stage"] in ("ready", "published", "rejected"):
            raise ValueError("Yeniden tasarım yalnızca bitmemiş konu anlatımı videolarında")
        p["data"]["look_pack"] = "auto"
        p["data"]["motion_note"] = (body.get("note") or "")[:400]
        p["preview"] = None
        P.save(con, p, "yeniden tasarım", p["data"]["motion_note"])
        queue_for(con, p, "p_design", json.dumps({"id": pid, "note": p["data"].get("motion_note", "")}, ensure_ascii=False))
    elif a == "direct":   # footage videos: Opus researches and art-directs again (optional note)
        if explainer.is_explainer(p["data"]) or p["stage"] in ("ready", "published", "rejected"):
            raise ValueError("Yeniden yönetim yalnızca bitmemiş footage videolarında")
        note = (body.get("note") or "")[:500]
        p["data"]["art"] = True   # the old direction stays until the new one has been made
        p["preview"] = None
        P.save(con, p, "yeniden yönet", note)
        queue_for(con, p, "p_direct", json.dumps({"id": pid, "note": note}, ensure_ascii=False))
    elif a == "set_eleven":   # which ElevenLabs account pays for this video's voice and music
        aid = body.get("account")
        if not accounts.can_use(aid):
            raise ValueError("Bu ElevenLabs hesabını kullanamazsın")
        p["data"]["eleven_account"] = aid
        vids = voice_ids(aid)
        if p["data"].get("voice_id") not in vids:   # the voice must exist on the new account
            prof_default = eleven_profile().get("defaults", {}).get(p["data"].get("lang", "en"))
            p["data"]["voice_id"] = prof_default if prof_default in vids else (sorted(vids)[0] if vids else None)
        P.save(con, p, "ElevenLabs hesabı", (accounts.eleven(aid) or {}).get("name", aid))
    elif a == "reroll_plate":   # one illustration again (a new take), after its own credit approval
        sid = body.get("scene")
        if sid not in (p["data"].get("plates") or {}):
            raise ValueError("bu sahnenin çizimi yok")
        est = credits.estimate([{"kind": "image", "model": "gpt-image-2", "units": 1, "unit": "img"}])
        if int(body.get("approved") or 0) < est["total"]:
            raise ValueError("Onaylanan kredi tahminden düşük")
        for sc in p["data"]["scenes"]:
            if sc["id"] == sid and sc.get("plate"):
                sc["plate"]["take"] = int(sc["plate"].get("take") or 1) + 1   # a new prompt variant = a new image
                if body.get("note"):
                    sc["plate"]["prompt"] = (sc["plate"]["prompt"] + " " + str(body["note"])[:300]).strip()
        p["data"]["plates"].pop(sid)
        P.save(con, p, "çizim yeniden", sid)
        queue_for(con, p, "p_plates", json.dumps({"id": pid, "approved": est["total"]}))
    elif a == "set_grammar":
        from factory import motiondesign
        g = body.get("grammar")
        if g not in motiondesign.GRAMMARS:
            raise ValueError("bilinmeyen gramer")
        p["data"]["grammar"] = g
        P.save(con, p, "anlatım grameri", g)
    elif a == "set_look":
        look = body.get("look")
        if not styles.valid(look) or not explainer.is_explainer(p["data"]):
            raise ValueError("Görünüm 'tech', 'paper' ya da kayıtlı bir stil olmalı (yalnızca konu anlatımı videoları)")
        if p["stage"] in ("ready", "published", "rejected"):
            raise ValueError("Bitmiş videonun görünümü değişmez; yeni üretimde seç")
        p["data"]["look_pack"] = look
        if p["stage"] == "preview":
            p["preview"] = None
        P.save(con, p, "görünüm", look)
        if p["stage"] == "preview" and p["data"].get("voice_take"):
            queue_for(con, p, "p_preview", str(pid))
    elif a in ("set_voice", "set_lang"):
        vids = voice_ids(P.eleven_account(p["data"]))
        new_lang = None
        if a == "set_lang":   # the video's language; the voice follows (creator's default voice for that language)
            new_lang = body.get("lang")
            if new_lang not in explainer.LANGS or not explainer.is_explainer(p["data"]):
                raise ValueError("Dil yalnızca konu anlatımı videolarında seçilir (tr / en)")
            if p["stage"] not in ("idea", "voice"):
                raise ValueError("Dil ses üretilmeden önce değişir; sonrası için yeni üretim yap")
            vid = eleven_profile().get("defaults", {}).get(new_lang)
            vid = vid if vid in vids else p["data"].get("voice_id")
        else:
            vid = body.get("voice_id")
        if vid not in vids:
            raise ValueError("Bu ses seçili ElevenLabs hesabında yok")
        p["data"]["voice_id"] = vid
        new_lang = new_lang or explainer.voice_lang(vid)
        if explainer.is_explainer(p["data"]) and new_lang != p["data"].get("lang", "en"):
            # the script and every on-screen text must be in the voice's language: rewrite it (no credits involved)
            p["data"]["lang"] = new_lang
            P.save(con, p, "ses seçimi", f"{vid} ({new_lang})")
            queue_for(con, p, "p_revise", json.dumps({"id": pid, "feedback": "The voice language changed to "
                      f"{explainer.LANGS[new_lang]}. Rewrite the whole script, every on-screen text, the header, the "
                      "caption and the hashtags in that language; keep the facts, sources, scene structure and visuals."}))
            return production_detail(con, pid)
        P.save(con, p, "ses seçimi", vid)
    elif a == "approve_music":
        est = P.music_estimate(con, p)
        approved = int(body.get("approved") or 0)
        if est["unknown"] or approved < est["credits"]:
            raise ValueError("Onaylanan kredi güncel tahminden düşük; sayfayı yenile")
        if not est["budget"]["ok"]:
            raise ValueError("Aylık kredi tavanı aşılır")
        P.save(con, p, "kredi onayı", f"müzik {est['credits']} kredi ({est['seconds']} s)")
        queue_for(con, p, "p_music", json.dumps({"id": pid, "approved": est["credits"],
                                                  "prompt": (body.get("prompt") or "").strip() or None}))
    elif a == "drop_music":
        p["data"].pop("music_take", None)
        P.save(con, p, "müzik kaldırıldı")
    elif a == "publish":
        post_id = tracking.add_post(con, body.get("url", ""), out_name=p["output"], prod_id=pid)
        con.execute("UPDATE posts SET channel_id=? WHERE post_id=?", (p.get("channel_id"), post_id))
        p = P.get(con, pid)
        p["stage"] = "published"
        P.save(con, p, "yayın", body.get("url", ""))
    else:
        raise ValueError(f"bilinmeyen işlem {a}")
    return production_detail(con, pid)


def channel_tracking(con, cid):
    rows = [x for x in tracking.posts(con) if x.get("channel_id") == cid or
            (x.get("channel_id") is None and x.get("prod_channel") == cid)]
    views = [(x.get("latest") or {}).get("views") or 0 for x in rows]
    return {"posts": len(rows), "views": sum(views), "best": max(views, default=0),
            "rows": [{k: x.get(k) for k in ("post_id", "platform", "url", "prod_title", "title", "posted_at", "history")}
                     | {"views": (x.get("latest") or {}).get("views")} for x in rows[:20]]}


def series_detail(con, sid):
    s = series.get(con, sid)
    d = s["data"]
    aid = accounts.default_eleven()
    prods = {}
    for e in d.get("episodes") or []:
        if e.get("prod_id"):
            try:
                prods[e["n"]] = prod_summary(con, P.get(con, e["prod_id"]))
            except ValueError:
                pass
    job = None
    if s.get("job_id"):
        j = con.execute("SELECT job_id, kind, status FROM jobs WHERE job_id=?", (s["job_id"],)).fetchone()
        job = dict(j) if j and j["status"] in ("queued", "running") else None
    asset = lambda f: "/media/assets/" + f.split("assets/", 1)[-1] if f else None  # noqa: E731
    return {**s, "styles": {k: v[0] for k, v in series.STYLES.items()}, "busy": job, "episodes_made": prods,
            "cast_estimate": series.cast_estimate(con, s, aid), "voices": eleven_info(aid)["voices"],
            "sheets": {c["id"]: asset((c.get("sheet") or {}).get("file")) for c in d.get("characters") or []},
            "channel": channels.get(con, s["channel_id"])}


def clip_search(con, text, k=24):
    """Clips ranked by how close their description / place / tags are to `text` (factory/embed.py)."""
    from factory import embed
    text = (text or "").strip()
    rows = [dict(r) for r in con.execute("""SELECT c.clip_id, c.kind, c.description, c.tags, c.mood, c.duration, p.name place
                                             FROM clips c LEFT JOIN places p ON p.place_id=c.place_id WHERE c.usable=1""")]
    if not text or not rows:
        return []
    docs = [" ".join(x for x in (r["description"], r["place"], r["mood"], " ".join(json.loads(r["tags"] or "[]"))) if x) for r in rows]
    mat = embed.vectors(docs, con)
    qv = embed.vectors([text], con)[0]
    sims = mat @ qv
    order = sims.argsort()[::-1][:k]
    return [{**rows[i], "score": round(float(sims[i]), 3)} for i in order if sims[i] > 0.05]


def search(con, text):
    """Command palette: productions, channels, series and pages matching `text`."""
    t = (text or "").strip().lower()
    out = []
    for c in channels.listing(con, counts=False):
        if not t or t in c["name"].lower():
            out.append({"kind": "kanal", "label": c["name"], "href": f"#/c/{c['id']}"})
    for s in series.listing(con):
        if not t or t in (s["title"] or "").lower():
            out.append({"kind": "seri", "label": s["title"], "href": f"#/s/{s['series_id']}"})
    if t:
        for r in con.execute("SELECT prod_id, title, stage FROM productions WHERE lower(title) LIKE ? ORDER BY updated_at DESC "
                             "LIMIT 12", (f"%{t}%",)):
            out.append({"kind": "video", "label": r["title"], "href": f"#/p/{r['prod_id']}", "stage": r["stage"]})
    return out[:30]


def eleven_info(aid, fresh=False):
    """Voices + balance of one ElevenLabs account: the owner's connector account from its saved profile and the
    ledger, API-key accounts live from ElevenLabs (cached 10 min, `fresh` re-reads at once)."""
    acc = accounts.eleven(aid)
    if not acc:
        return {"voices": [], "error": "hesap yok"}
    if acc["type"] == "apikey":
        try:
            i = eleven_api.info(acc["key"], fresh)
            return {"voices": i["voices"], "balance": i["subscription"]}
        except eleven_api.ApiError as e:
            return {"voices": [], "error": str(e)}
    con = connect()
    try:
        spent = round(credits.month_spent(con, aid))
    finally:
        con.close()
    if aid != "ali":   # a member's own connector: voices read by the eleven_voices job, cap optional
        cap = acc.get("month_cap")
        return {"voices": with_default_voices({"voices": list(acc.get("voices") or [])})["voices"],
                "balance": {"tier": "connector", "used": spent, "limit": cap,
                "left": max(0, cap - spent) if cap else None}, "error": None if acc.get("voices") else
                "sesler okunuyor ya da okunamadı (Hesaplar → Sesleri yenile)"}
    prof = eleven_profile()
    return {"voices": prof["voices"], "balance": {"tier": "connector", "used": spent, "limit": credits.MONTHLY_CAP,
                                                  "left": max(0, credits.MONTHLY_CAP - spent)}}


def voice_ids(aid):
    return {v["voice_id"] for v in eleven_info(aid)["voices"]}


def me(con):
    uid = accounts.current()
    u = accounts.user(uid) or {}
    accs = accounts.usable_eleven(uid)
    for a in accs:
        i = eleven_info(a["id"])
        a.update(balance=i.get("balance"), error=i.get("error"), voices=len(i["voices"]))
        if not a["mine"] and a.get("member_month_cap") is not None:
            a["my_month"] = round(credits.month_spent(con, a["id"], uid))
    out = {"id": uid, "name": u.get("name", uid), "role": u.get("role", "owner"), "login": accounts.enabled(),
           "claude": accounts.claude_status(uid), "eleven": accs, "default_eleven": accounts.default_eleven(uid),
           "llm_settings": accounts.llm_settings(uid), "codex_elevenlabs": llm.codex_elevenlabs_status(),
           "llm_models": {p: llm.model_options(p) for p in ("claude", "codex")},
           "llm_default_models": {p: {step: llm.default_model(step, p) for step in llm.AGENT_STEPS} for p in ("claude", "codex")},
           "llm_agents": [{"id": k, "name": v} for k, v in llm.AGENT_STEPS.items()]}
    if accounts.is_owner(uid):
        out["users"] = [{"id": k, "name": v["name"], "role": v["role"], "claude": accounts.claude_status(k)}
                        for k, v in accounts.users()["users"].items()]
    return out


def eleven_profile():
    try:
        prof = json.load(open(PROFILE))
    except (OSError, ValueError):
        prof = {"voices": [], "defaults": {}, "avatar": {}}
    return with_default_voices(prof)


def with_default_voices(prof):
    """The built-in narrators (formats.DEFAULT_VOICES) are in every connector voice list and fill missing language
    defaults, so a fresh machine without data/eleven_profile.json still has a working voice for TR and EN."""
    have = {v["voice_id"] for v in prof.setdefault("voices", [])}
    for lang, v in formats.DEFAULT_VOICES.items():
        prof.setdefault("defaults", {}).setdefault(lang, v["voice_id"])
        if v["voice_id"] not in have:
            prof["voices"].append(dict(v))
    return prof


def ref_thumb(con, ref_id):
    r = con.execute("SELECT path, duration FROM ref_videos WHERE ref_id=?", (ref_id,)).fetchone()
    if not r or not os.path.exists(r["path"]):
        return None
    photo = refs.ref_kind(r["path"]) == "photo"
    key = hashlib.sha1(f"ref:{r['path']}".encode()).hexdigest()
    dst = os.path.join(THUMBS, key + ".jpg")
    with thumb_lock:
        if not os.path.exists(dst):
            os.makedirs(THUMBS, exist_ok=True)
            # a third of the way in (past any intro ad), cropped to the video area of a phone screen recording
            if photo:
                cmd = [FFMPEG, "-v", "error", "-y", "-i", r["path"], "-frames:v", "1", "-vf", "scale=270:-2", "-q:v", "5", dst]
            else:
                cmd = [FFMPEG, "-v", "error", "-y", "-ss", f"{(r['duration'] or 3) * 0.35:.2f}", "-i", r["path"],
                       "-frames:v", "1", "-vf", "crop=iw:ih*0.78:0:ih*0.08,scale=270:-2", "-q:v", "5", dst]
            subprocess.run(cmd, capture_output=True, timeout=60)
    return dst if os.path.exists(dst) else None


# ---------- thumbnails ----------
def clip_thumb(con, clip_id, t):
    r = con.execute("SELECT path, kind FROM clips WHERE clip_id=?", (clip_id,)).fetchone()
    if not r or not os.path.exists(r["path"]):
        return None
    t = max(0.0, float(t or 0)) if r["kind"] == "video" else 0.0
    key = hashlib.sha1(f"{r['path']}:{t:.1f}".encode()).hexdigest()
    dst = os.path.join(THUMBS, key + ".jpg")
    with thumb_lock:
        if os.path.exists(dst):
            return dst
        os.makedirs(THUMBS, exist_ok=True)
        if r["kind"] == "photo":
            from PIL import Image, ImageOps
            im = ImageOps.exif_transpose(Image.open(r["path"])).convert("RGB")
            im.thumbnail((360, 640))
            im.save(dst, quality=82)
        else:
            subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", r["path"], "-frames:v", "1",
                            "-vf", "scale=270:-2", "-q:v", "5", dst], capture_output=True, timeout=60)
    return dst if os.path.exists(dst) else None


def prod_thumb(con, prod_id, t):
    """A frame at `t` s of a production's latest video (final if rendered, else the preview): the storyboard of an
    Opus-designed (HTML) explainer shows what was really rendered, not the script-stage scene plan."""
    p = P.get(con, int(prod_id))
    src = os.path.join(OUT, p["output"], p["output"] + ".mp4") if p["output"] else None
    if not (src and os.path.exists(src)) and p["preview"]:
        src = os.path.join(ROOT, p["preview"])
    if not src or not os.path.exists(src):
        return None
    t = max(0.0, float(t or 0))
    key = hashlib.sha1(f"{src}:{os.path.getmtime(src)}:{t:.1f}".encode()).hexdigest()
    dst = os.path.join(THUMBS, key + ".jpg")
    with thumb_lock:
        if not os.path.exists(dst):
            os.makedirs(THUMBS, exist_ok=True)
            subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1",
                            "-vf", "scale=270:-2", "-q:v", "5", dst], capture_output=True, timeout=60)
    return dst if os.path.exists(dst) else None


# ---------- HTTP ----------
LOGIN_PAGE = """<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Studio giriş</title><style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0f1115;
color:#e8e8ea;font:16px system-ui,sans-serif;padding:16px}form{width:100%;max-width:340px;background:#181b22;padding:24px;border-radius:14px}
input,button{width:100%;box-sizing:border-box;padding:12px;margin-top:10px;border-radius:10px;border:1px solid #2c313c;background:#0f1115;color:inherit;font:inherit}
button{background:#e8e8ea;color:#0f1115;font-weight:600;border:0;cursor:pointer}#e{color:#ff7b7b;min-height:20px;margin-top:8px;font-size:14px}</style></head>
<body><form onsubmit="go(event)"><h2 style="margin:0 0 6px">Content Studio</h2><input id="u" placeholder="kullanıcı adı" autocomplete="username" autocapitalize="none">
<input id="p" type="password" placeholder="şifre" autocomplete="current-password"><button>Giriş</button><div id="e"></div></form>
<script>async function go(ev){ev.preventDefault();const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json","X-Studio":"1"},
body:JSON.stringify({user:document.getElementById("u").value.trim().toLowerCase(),password:document.getElementById("p").value})});
if(r.ok)location.href="/";else document.getElementById("e").textContent="Kullanıcı adı ya da şifre yanlış"}</script></body></html>"""


class Handler(shorts.Handler):
    server_version = "FactoryStudio"

    def session_user(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == accounts.COOKIE:
                return accounts.read_session(v)
        return None

    def gate(self, head):
        """Login check for every request once users exist; sets the current user for this request's thread."""
        if not accounts.enabled():
            accounts.set_current(accounts.OWNER)
            return True
        uid = self.session_user()
        if uid:
            accounts.set_current(uid)
            return True
        path = urllib.parse.urlsplit(self.path).path
        if path == "/login":
            self.send_bytes(200, LOGIN_PAGE.encode(), "text/html; charset=utf-8", head)
        elif path.startswith("/api/"):
            self.json(401, {"error": "giriş gerekli"}, head)
        else:
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Content-Length", "0")
            self.end_headers()
        return False

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if self.allowed() and path == CODEX_MCP_CALLBACK:
            return self.codex_oauth_callback()
        if self.allowed() and self.gate(False):
            self.route(head=False)
        elif not self.allowed():
            self.send_bytes(403, b"Forbidden\n", "text/plain; charset=utf-8", False)

    def codex_oauth_callback(self):
        """Pass the OAuth redirect URL to Codex CLI, which validates state and exchanges the code."""
        parsed = urllib.parse.urlsplit(self.path)
        params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        state = (params.get("state") or [None])[0]
        with CODEX_MCP_LOCK:
            flow = CODEX_MCP_FLOW
            proc = flow.get("process")
            if not proc or proc.poll() is not None or flow.get("status") != "waiting":
                return self.send_bytes(400, b"OAuth flow expired. Return to Content Factory and try again.\n",
                                       "text/plain; charset=utf-8", False)
            if not state or not flow.get("state") or not secrets.compare_digest(state, flow["state"]):
                return self.send_bytes(400, b"OAuth state mismatch. Return to Content Factory and try again.\n",
                                       "text/plain; charset=utf-8", False)
            if params.get("error"):
                flow.update(status="error", error="ElevenLabs yetkilendirmesi reddedildi", url=None)
                try:
                    proc.stdin.close()
                except Exception:
                    pass
                return self.send_bytes(400, b"ElevenLabs connection was cancelled. Return to Content Factory.\n",
                                       "text/plain; charset=utf-8", False)
            callback = urllib.parse.urlsplit(flow.get("callback_url") or "")
            try:
                full_url = urllib.parse.urlunsplit((callback.scheme, callback.netloc, callback.path, parsed.query, ""))
                proc.stdin.write(full_url + "\n")
                proc.stdin.flush()
                flow.update(status="finishing", url=None, state=None)
            except (OSError, BrokenPipeError, AttributeError):
                flow.update(status="error", error="Codex OAuth akışı kapandı", process=None)
                return self.send_bytes(500, b"Codex could not finish the ElevenLabs connection.\n",
                                       "text/plain; charset=utf-8", False)
        html = ("<!doctype html><meta name=viewport content='width=device-width'><title>Bağlandı</title>"
                "<body style='font:16px system-ui;background:#101116;color:#eee;padding:32px'>"
                "<h2>ElevenLabs izni alındı</h2><p>Content Factory bağlantıyı tamamlıyor.</p>"
                "<a style='color:#8eb7ff' href='/#/hesaplar'>Hesaplara dön</a>"
                "<script>setTimeout(()=>location.replace('/#/hesaplar'),1500)</script></body>").encode()
        return self.send_bytes(200, html, "text/html; charset=utf-8", False)

    def do_HEAD(self):
        if self.allowed() and self.gate(True):
            self.route(head=True)
        elif not self.allowed():
            self.send_bytes(403, b"Forbidden\n", "text/plain; charset=utf-8", True)

    def login(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            b = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
        except ValueError:
            b = {}
        uid = str(b.get("user") or "")
        if not accounts.check_password(uid, str(b.get("password") or "")):
            time.sleep(1.0)
            return self.json(401, {"error": "yanlış"})
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Set-Cookie", f"{accounts.COOKIE}={accounts.make_session(uid)}; Path=/; Max-Age={30 * 86400}; "
                                       "HttpOnly; SameSite=Strict")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.allowed() or self.headers.get("X-Studio") != "1":
            return self.send_bytes(403, b"Forbidden\n", "text/plain; charset=utf-8", False)
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/login":
            return self.login()
        if path == "/api/logout":
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Set-Cookie", f"{accounts.COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")
            self.end_headers()
            return self.wfile.write(body)
        if not self.gate(False):
            return
        if urllib.parse.urlsplit(self.path).path == "/api/refs/upload":
            return self.upload()
        m = re.fullmatch(r"/api/channels/([\w-]+)/logo", urllib.parse.urlsplit(self.path).path)
        if m:
            n = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(min(n, 11 << 20))
            name = os.path.basename(urllib.parse.unquote(self.headers.get("X-Filename") or "logo.png"))
            con = connect()
            try:
                return self.json(200, channels.set_logo(con, m.group(1), data, name))
            except ValueError as e:
                return self.json(400, {"error": str(e)})
            finally:
                con.close()
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            body = {}
        con = connect()
        try:
            res = self.post(con, urllib.parse.urlsplit(self.path).path, body)
            self.json(200, res)
        except Conflict as e:
            self.json(409, {"error": str(e)})
        except (ValueError, KeyError, credits.BudgetError) as e:
            self.json(400, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            self.json(500, {"error": f"{type(e).__name__}: {e}"})
        finally:
            con.close()

    def style_upload(self, n, name):
        """One reference IMAGE (png/jpg/webp) -> job style_extract -> a saved custom look (factory/styles.py)."""
        video = name.lower().endswith(styles.VIDEO_EXT)
        if not (name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) or video) or not 0 < n <= (200 << 20 if video else 25 << 20):
            self.rfile.read(min(n, 1 << 20))
            return self.json(400, {"error": "PNG/JPG/WEBP (25 MB) ya da MP4/MOV video (200 MB)"})
        inbox = os.path.join(styles.DIR, "_inbox")
        os.makedirs(inbox, exist_ok=True)
        dst = os.path.join(inbox, f"{int(time.time())}_{name}")
        with open(dst, "wb") as f:
            left = n
            while left:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        note = urllib.parse.unquote(self.headers.get("X-Style-Note") or "")[:300]
        con = connect()
        try:
            jid = jobs.queue(con, "style_extract", json.dumps({"files": [dst], "note": note}, ensure_ascii=False))
        finally:
            con.close()
        return self.json(200, {"ok": True, "job_id": jid})

    def talk_upload(self, n, name):
        """The creator's raw talking video -> raw/talk/ (never modified); the composer attaches it to the next plan."""
        from factory import talk
        if not name.lower().endswith(talk.VIDEO_EXT) or not 0 < n <= MAX_UPLOAD:
            self.rfile.read(min(n, 1 << 20))
            return self.json(400, {"error": "MP4/MOV video, en fazla 600 MB"})
        os.makedirs(talk.RAW, exist_ok=True)
        stem, ext = os.path.splitext(name)
        safe = re.sub(r"[^\w-]", "_", stem)[:60]
        dst = os.path.join(talk.RAW, f"{safe}_{int(time.time())}{ext.lower()}")
        part = dst + ".part"
        with open(part, "wb") as f:
            left = n
            while left:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left:
            os.remove(part)
            return self.json(400, {"error": "yükleme yarıda kaldı"})
        os.replace(part, dst)
        return self.json(200, {"ok": True, "file": os.path.relpath(dst, ROOT), "name": name})

    def upload(self):
        """A reference video sent as the raw request body (phone browser fetch with the File as body)."""
        n = int(self.headers.get("Content-Length") or 0)
        name = os.path.basename(urllib.parse.unquote(self.headers.get("X-Filename") or "ref.mp4"))
        name = re.sub(r"[^\w.\- ]", "_", name)[:120] or "ref.mp4"
        if self.headers.get("X-Style") == "1":
            return self.style_upload(n, name)
        if self.headers.get("X-Talk") == "1":
            return self.talk_upload(n, name)
        if not name.lower().endswith((".mp4", ".mov", ".m4v") + refs.REF_PHOTO_EXT) or not 0 < n <= MAX_UPLOAD:
            self.rfile.read(min(n, 1 << 20))
            return self.json(400, {"error": "MP4/MOV ya da JPG/PNG/WEBP fotoğraf, en fazla 600 MB"})
        os.makedirs(refs.REFS, exist_ok=True)
        dst = os.path.join(refs.REFS, name)
        if os.path.exists(dst):
            stem, ext = os.path.splitext(name)
            dst = os.path.join(refs.REFS, f"{stem}_{int(time.time())}{ext}")
        part = dst + ".part"
        with open(part, "wb") as f:
            left = n
            while left:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left:
            os.remove(part)
            return self.json(400, {"error": "yükleme yarıda kaldı"})
        os.replace(part, dst)
        con = connect()
        try:
            jid = jobs.queue(con, "ref_lib")
            theme = urllib.parse.unquote(self.headers.get("X-Theme") or "")
            if theme in refs.THEMES:  # remembered for the scan, which creates the row
                pend = os.path.join(refs.REFS, ".themes.json")
                try:
                    m = json.load(open(pend))
                except (OSError, ValueError):
                    m = {}
                m[os.path.basename(dst)] = theme
                json.dump(m, open(pend, "w"))
        finally:
            con.close()
        return self.json(200, {"ok": True, "file": os.path.basename(dst), "job_id": jid})

    def post(self, con, path, b):
        uid = accounts.current()
        if path == "/api/llm/settings":
            provider, models = b.get("provider"), b.get("models", {})
            if provider not in ("claude", "codex") or not isinstance(models, dict):
                raise ValueError("CLI veya agent model seçimi geçersiz")
            allowed_models = {x["id"] for x in llm.model_options(provider)}
            if any(not isinstance(step, str) or not isinstance(model, str) or step not in llm.AGENT_STEPS
                   or model not in allowed_models for step, model in models.items()):
                raise ValueError("Agent veya model seçimi listede yok")
            return {"llm_settings": accounts.set_llm_settings(uid, provider, models)}
        if path == "/api/codex/elevenlabs/start":
            if not accounts.is_owner(uid):
                raise ValueError("Codex ElevenLabs bağlantısını yalnızca hesap sahibi yönetebilir")
            status = llm.codex_elevenlabs_status()
            if not status.get("configured"):
                try:
                    subprocess.run([llm.CODEX, "mcp", "add", "elevenlabs", "--url", "https://api.elevenlabs.io/v1/mcp"],
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, check=False)
                except (OSError, subprocess.TimeoutExpired):
                    raise ValueError("Codex ElevenLabs connector kaydedilemedi") from None
            return start_codex_oauth(uid)
        if path == "/api/claude/start":
            if accounts.is_owner(uid):
                raise ValueError("Sahip VM'deki Claude girişini kullanıyor")
            return {"url": claudeauth.start(uid, "token" if b.get("mode") == "token" else "login")}
        if path == "/api/eleven/accounts/add_connector":
            if not accounts.claude_status(uid).get("connectors"):
                raise ValueError("Önce Claude'u 'tam giriş' ile bağla; connector'lar sadece tam girişte çalışır")
            if any(a["owner"] == uid and a["type"] == "connector" for a in accounts.usable_eleven(uid)):
                raise ValueError("Connector hesabın zaten ekli")
            aid = accounts.add_eleven_connector(uid, f"{(accounts.user(uid) or {}).get('name', uid)} (connector)")
            jobs.queue(con, "eleven_voices", aid)
            return me(con)
        m = re.fullmatch(r"/api/eleven/accounts/([\w-]+)/voices", path)
        if m:
            acc = accounts.eleven(m.group(1))
            if not acc or acc["owner"] != uid:
                raise ValueError("Bu hesap senin değil")
            if acc["type"] == "apikey":
                eleven_api.info(acc["key"], fresh=True)
                return me(con)
            if m.group(1) == "ali":
                raise ValueError("Senin seslerin Ses & Avatar sayfasındaki profilden geliyor")
            jobs.queue(con, "eleven_voices", m.group(1))
            return me(con)
        if path == "/api/claude/finish":
            claudeauth.finish(uid, str(b.get("code") or ""))
            return me(con)
        if path == "/api/eleven/accounts/add":
            key = str(b.get("key") or "").strip()
            if len(key) < 20:
                raise ValueError("Geçerli bir ElevenLabs API anahtarı yapıştır")
            try:
                eleven_api.info(key, fresh=True)   # read voices + balance at once: proves the key works
            except eleven_api.ApiError as e:
                raise ValueError(f"Anahtar çalışmadı: {e}")
            name = str(b.get("name") or "").strip()[:60] or f"{(accounts.user(uid) or {}).get('name', uid)}'in ElevenLabs'ı"
            accounts.add_eleven(uid, name, key)
            return me(con)
        m = re.fullmatch(r"/api/eleven/accounts/([\w-]+)/(update|delete)", path)
        if m:
            acc = accounts.eleven(m.group(1))
            if not acc or (acc["owner"] != uid and not accounts.is_owner(uid)):
                raise ValueError("Bu hesap senin değil")
            if m.group(2) == "delete":
                if m.group(1) == "ali":
                    raise ValueError("Sahibin connector hesabı silinemez")
                accounts.remove_eleven(m.group(1))
            else:
                kw = {}
                if "name" in b:
                    kw["name"] = str(b["name"])[:60]
                if "shared" in b:
                    kw["shared"] = bool(b["shared"])
                for k in ("member_month_cap", "month_cap"):
                    if k in b:
                        v = b[k]
                        kw[k] = None if v in (None, "") else max(0, int(v))
                if b.get("key"):
                    try:
                        eleven_api.info(str(b["key"]).strip(), fresh=True)
                    except eleven_api.ApiError as e:
                        raise ValueError(f"Anahtar çalışmadı: {e}")
                    kw["key"] = str(b["key"]).strip()
                accounts.update_eleven(m.group(1), **kw)
            return me(con)
        m = re.fullmatch(r"/api/production/(\d+)/action", path)
        if m:
            return act(con, int(m.group(1)), b)
        if path == "/api/generate":
            fmt = formats.get(b.get("format"))
            if fmt["status"] != "ready":
                raise ValueError("Bu format henüz hazır değil")
            arg = {"format": fmt["id"], "n": max(1, min(int(b.get("n") or 3), 5)), "brief": b.get("brief", ""),
                   "places": [int(x) for x in b.get("places") or []],
                   "refs": [r for r in (b.get("refs") or []) if isinstance(r, str)][:3],
                   "aspect": b.get("aspect") if b.get("aspect") in formats.ASPECTS else "9:16",
                   "narrate": b.get("narrate") if b.get("narrate") in ("auto", "on", "off") else "auto",
                   "look": b.get("look") if styles.valid(b.get("look")) else "tech",
                   "voice_id": b.get("voice_id") if b.get("voice_id") in voice_ids(accounts.default_eleven()) else None,
                   "channel": channels.resolve(con, b.get("channel"), fmt["mode"])}
            return {"job_id": jobs.queue(con, "p_ideas", json.dumps(arg, ensure_ascii=False))}
        if path == "/api/catalog/demos":
            from factory import catalog
            ids = [x for x in b.get("ids") or [] if x in catalog.DEMOS] or None
            return {"job_id": jobs.queue(con, "catalog_demos", json.dumps({"ids": ids, "force": bool(b.get("force"))}))}
        if path == "/api/discover/run":
            sc = {"region": b.get("region") if b.get("region") in discover.REGIONS else None,
                  "only": [k for k in (b.get("only") or []) if k in discover.NICHES["categories"]] or None}
            return {"job_id": jobs.queue(con, "discover", json.dumps(sc))}
        # ---- composer / planner ----
        if path == "/api/plan":
            att = b.get("attachments") if isinstance(b.get("attachments"), dict) else {}
            att = {k: att[k] for k in ("places", "refs", "series_id", "channel", "links", "clips", "pins", "pin_mode") if att.get(k)}
            if att.get("pins"):    # techniques the creator pinned in the catalog (planner must use them)
                from factory import capabilities
                att["pins"] = [x for x in att["pins"] if isinstance(x, str) and x in capabilities.CAPS][:12]
                att["pin_mode"] = "only" if att.get("pin_mode") == "only" else "add"
            pid = planner.create(con, b.get("prompt", ""), att, uid)
            voices = [{"voice_id": v["voice_id"], "name": v.get("name"), "language": v.get("language")}
                      for v in eleven_info(accounts.default_eleven())["voices"]]
            jid = jobs.queue(con, "plan", json.dumps({"id": pid, "voices": voices}, ensure_ascii=False))
            return {"plan_id": pid, "job_id": jid}
        m = re.fullmatch(r"/api/plan/(\d+)/(update|start|cancel)", path)
        if m:
            pid = int(m.group(1))
            if m.group(2) == "update":
                voices = [{"voice_id": v["voice_id"], "name": v.get("name")} for v in eleven_info(accounts.default_eleven())["voices"]]
                return planner.update(con, pid, b.get("changes") or {}, voices)
            if m.group(2) == "cancel":
                planner.cancel(con, pid)
                return planner.get(con, pid)
            return planner.start(con, pid, lambda kind, arg: jobs.queue(con, kind, arg))
        # ---- channels ----
        if path == "/api/channels":
            return channels.create(con, b.get("name"), b)
        m = re.fullmatch(r"/api/channels/([\w-]+)/(update|delete|logo_delete|reorder)", path)
        if m:
            cid, op = m.group(1), m.group(2)
            if op == "update":
                return channels.update(con, cid, b)
            if op == "logo_delete":
                return channels.drop_logo(con, cid)
            if op == "reorder":
                channels.reorder(con, [x for x in b.get("ids") or [] if isinstance(x, str)])
                return channels.listing(con)
            return {"moved_to": channels.delete(con, cid, b.get("move_to"))}
        # ---- series ----
        m = re.fullmatch(r"/api/series/(\d+)/(revise|approve|cast|voice|episode|delete)", path)
        if m:
            sid, op = int(m.group(1)), m.group(2)
            s = series.get(con, sid)
            if s.get("job_id") and op != "voice":
                j = con.execute("SELECT status FROM jobs WHERE job_id=?", (s["job_id"],)).fetchone()
                if j and j["status"] in ("queued", "running"):
                    raise Conflict("Bu seri için bir iş zaten çalışıyor")
            if op == "revise":
                fb = (b.get("feedback") or "").strip()
                if not fb:
                    raise ValueError("Ne değişsin? Kısa bir not yaz.")
                return {"job_id": jobs.queue(con, "series_bible", json.dumps({"id": sid, "feedback": fb}, ensure_ascii=False))}
            if op == "approve":
                return series_detail(con, series.approve_bible(con, sid)["series_id"])
            if op == "cast":
                aid = accounts.default_eleven()
                est = series.cast_estimate(con, s, aid)
                approved = int(b.get("approved") or 0)
                if est["unknown"] or approved < est["credits"]:
                    raise ValueError("Onaylanan kredi güncel tahminden düşük; sayfayı yenile")
                if not est["budget"]["ok"]:
                    raise ValueError("Aylık kredi tavanı aşılır")
                return {"job_id": jobs.queue(con, "series_cast", json.dumps({"id": sid, "approved": est["credits"], "account": aid}))}
            if op == "voice":
                vid = b.get("voice_id")
                if vid and vid not in voice_ids(accounts.default_eleven()):
                    raise ValueError("Bu ses hesabında yok")
                series.set_voice(con, sid, b.get("who"), vid)
                return series_detail(con, sid)
            if op == "episode":
                return {"job_id": jobs.queue(con, "series_episode", json.dumps({"id": sid, "n": int(b.get("n") or 1),
                                                                                "note": b.get("note", "")}, ensure_ascii=False))}
            con.execute("DELETE FROM series WHERE series_id=?", (sid,))
            con.commit()
            return {"ok": True}
        # ---- styles ----
        m = re.fullmatch(r"/api/styles/([\w-]+)/(approve|delete|stills)", path)
        if m:
            if m.group(2) == "approve":
                styles.approve(m.group(1))
            elif m.group(2) == "delete":
                styles.delete(m.group(1))
            else:
                styles.preview_stills(m.group(1))
            return styles.listing()
        m = re.fullmatch(r"/api/discover/card/(\d+)/(pick|skip)", path)
        if m:
            row = con.execute("SELECT * FROM disc_cards WHERE card_id=?", (int(m.group(1)),)).fetchone()
            if not row:
                raise ValueError("kart bulunamadı")
            if m.group(2) == "skip":
                discover.set_status(con, row["card_id"], "skipped")
                return {"ok": True}
            card = json.loads(row["data"])
            vids = voice_ids(accounts.default_eleven())
            lang = b.get("lang") if b.get("lang") in explainer.LANGS else None
            voice = b.get("voice_id") if b.get("voice_id") in vids else None
            if lang and not voice:   # the creator's default voice for that language (Ali EN / Ali TR)
                voice = eleven_profile().get("defaults", {}).get(lang)
                voice = voice if voice in vids else None
            cid = channels.resolve(con, b.get("channel"), "topic")
            ch = channels.get(con, cid)
            arg = {"format": "explainer_short", "n": 1, "brief": discover.brief_for(card),
                   "aspect": b.get("aspect") if b.get("aspect") in formats.ASPECTS else ch["defaults"]["aspect"],
                   "look": b.get("look") if styles.valid(b.get("look")) else (ch["defaults"]["look"] if styles.valid(ch["defaults"]["look"]) else "auto"),
                   "voice_id": voice or ch["defaults"].get("voice_id"), "channel": cid, "lang": lang}
            jid = jobs.queue(con, "p_ideas", json.dumps(arg, ensure_ascii=False))
            discover.set_status(con, row["card_id"], "picked", jid, cid)
            return {"job_id": jid}
        if path == "/api/refs/delete":
            return delete_ref(con, b.get("ref_id"))
        if path == "/api/library/delete":
            return delete_library_video(con, b.get("folder"))
        if path == "/api/refs/scan":
            return {"job_id": jobs.queue(con, "ref_lib")}
        if path == "/api/refs/theme":
            th = b.get("theme")
            if th not in refs.THEMES:
                raise ValueError("Tema: " + ", ".join(refs.THEMES))
            con.execute("UPDATE ref_videos SET theme=? WHERE ref_id=?", (th, b.get("ref_id")))
            con.commit()
            return {"ok": True}
        if path == "/api/eleven/default":
            prof = eleven_profile()
            if b.get("voice_id") not in {v["voice_id"] for v in prof["voices"]} or b.get("lang") not in ("en", "tr"):
                raise ValueError("Bilinmeyen ses veya dil")
            prof.setdefault("defaults", {})[b["lang"]] = b["voice_id"]
            json.dump(prof, open(PROFILE, "w"), ensure_ascii=False, indent=1)
            return {"ok": True}
        if path == "/api/eleven/voices/add":
            if not accounts.is_owner(uid):
                raise ValueError("Ses eklemek sahibin işi")
            vid = str(b.get("voice_id") or "").strip()
            lang = str(b.get("language") or "")
            if not re.fullmatch(r"[A-Za-z0-9]{16,40}", vid):
                raise ValueError("Ses ID'si 20 karakterlik harf/rakam olmalı (ElevenLabs → ses → ID kopyala)")
            if lang not in {c for c, _ in formats.ELEVEN_LANGUAGES}:
                raise ValueError("Listeden bir dil seç")
            if vid in {v["voice_id"] for v in eleven_profile()["voices"]}:
                raise ValueError("Bu ses zaten listede")
            arg = json.dumps({"voice_id": vid, "language": lang, "name": str(b.get("name") or "")}, ensure_ascii=False)
            return {"job_id": jobs.queue(con, "voice_add", arg)}
        if path == "/api/eleven/voices/remove":
            if not accounts.is_owner(uid):
                raise ValueError("Ses silmek sahibin işi")
            prof = eleven_profile()
            if b.get("voice_id") in prof.get("defaults", {}).values():
                raise ValueError("Varsayılan ses silinemez; önce başka bir sesi varsayılan yap")
            prof["voices"] = [v for v in prof["voices"] if not (v["voice_id"] == b.get("voice_id") and v.get("category") == "custom")]
            json.dump(prof, open(PROFILE, "w"), ensure_ascii=False, indent=1)
            return {"ok": True}
        if path == "/api/eleven/avatar_check":
            return {"job_id": jobs.queue(con, "avatar_check")}
        if path == "/api/ingest":
            link = (b.get("link") or "").strip()
            if not link.startswith("https://photos.icloud.com/"):
                raise ValueError("iCloud paylaşımlı albüm linki olmalı")
            return {"job_id": jobs.queue(con, "ingest", link)}
        if path == "/api/radar":
            prof = b.get("profile") if b.get("profile") in ("travel", "psychology") else "travel"
            return {"job_id": jobs.queue(con, "radar", prof)}
        if path == "/api/trends":
            return {"job_id": jobs.queue(con, "trends")}
        if path == "/api/posts":
            out_name = b.get("out_name") or None
            prod = con.execute("SELECT prod_id FROM productions WHERE name=?", (out_name,)).fetchone() if out_name else None
            pid = tracking.add_post(con, b.get("url", ""), out_name=out_name, prod_id=prod["prod_id"] if prod else None)
            if prod:
                p = P.get(con, prod["prod_id"])
                if p["stage"] == "ready":
                    p["stage"] = "published"
                    P.save(con, p, "yayın", b.get("url", ""))
            return {"post_id": pid}
        m = re.fullmatch(r"/api/posts/(\d+)/stats", path)
        if m:
            vals = {k: (int(b[k]) if str(b.get(k, "")).strip().isdigit() else None)
                    for k in ("views", "likes", "comments", "shares")}
            if all(v is None for v in vals.values()):
                raise ValueError("En az bir sayı gir")
            tracking.add_stats(con, int(m.group(1)), **vals)
            return {"ok": True}
        m = re.fullmatch(r"/api/posts/(\d+)/delete", path)
        if m:
            con.execute("DELETE FROM post_stats WHERE post_id=?", (int(m.group(1)),))
            con.execute("DELETE FROM posts WHERE post_id=?", (int(m.group(1)),))
            con.commit()
            return {"ok": True}
        m = re.fullmatch(r"/api/places/(\d+)/rename", path)
        if m:
            name = (b.get("name") or "").strip()
            if not name:
                raise ValueError("İsim boş olamaz")
            con.execute("UPDATE places SET name=? WHERE place_id=?", (name[:80], int(m.group(1))))
            con.commit()
            return {"ok": True}
        if path == "/api/posts/refresh":
            return {"job_id": jobs.queue(con, "yt_stats")}
        raise ValueError("bilinmeyen adres")

    def route(self, head):
        if not self.allowed():
            return self.send_bytes(403, b"Forbidden\n", "text/plain; charset=utf-8", head)
        url = urllib.parse.urlsplit(self.path)
        path, q = urllib.parse.unquote(url.path), urllib.parse.parse_qs(url.query)
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self.send_bytes(200, f.read(), "text/html; charset=utf-8", head)
        if path.startswith("/static/"):   # the Studio's own css / js (read per request, like index.html)
            f = self.inside(HERE, path[len("/static/"):])
            types = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
            if f and os.path.splitext(f)[1] in types:
                with open(f, "rb") as fh:
                    return self.send_bytes(200, fh.read(), types[os.path.splitext(f)[1]], head)
        if path.startswith("/fonts/"):
            f = self.inside(os.path.join(ROOT, "fonts"), path[len("/fonts/"):])
            if f and f.endswith(".ttf"):
                return self.send_file(f, "font/ttf", head, cache="private, max-age=604800")
        m = re.fullmatch(r"/media/channel/([\w-]+)/logo", path)
        if m:
            con = connect()
            try:
                f = channels.logo_path(con, m.group(1))
            finally:
                con.close()
            if f:
                return self.send_file(f, "image/png", head, cache="private, max-age=60")
        if path.startswith("/media/styles/"):
            f = self.inside(styles.DIR, path[len("/media/styles/"):])
            if f and f.endswith((".png", ".jpg")):
                return self.send_file(f, "image/png" if f.endswith(".png") else "image/jpeg", head, cache="no-store")
        if path.startswith("/api/"):
            con = connect()
            try:
                return self.json(200, self.get_api(con, path, q), head)
            except ValueError as e:
                return self.json(404, {"error": str(e)}, head)
            except Exception as e:
                traceback.print_exc()
                return self.json(500, {"error": f"{type(e).__name__}: {e}"}, head)
            finally:
                con.close()
        if path.startswith("/media/out/"):
            f = self.inside(OUT, path[len("/media/out/"):])
            if f and f.endswith(".mp4"):
                return self.send_file(f, "video/mp4", head, download="dl" in q)
            if f and f.endswith(".jpg"):   # cover / thumbnail candidates
                return self.send_file(f, "image/jpeg", head, download="dl" in q, cache="no-store")
        if path.startswith("/media/work/"):
            f = self.inside(os.path.join(ROOT, "work"), path[len("/media/work/"):])
            if f:
                ctype = "video/mp4" if f.endswith(".mp4") else "image/jpeg" if f.endswith(".jpg") else \
                    "image/png" if f.endswith(".png") else None
                if ctype:
                    return self.send_file(f, ctype, head, cache="no-store")
        if path.startswith("/media/art/"):  # stills of the auto art directions
            f = self.inside(os.path.join(ROOT, "work", "explainer"), path[len("/media/art/"):])
            if f and f.endswith(".png"):
                return self.send_file(f, "image/png", head, cache="private, max-age=3600")
        if path.startswith("/media/plans/"):  # the director team's sketch frames (work/plans/<plan>/t<i>/shot_*.png)
            f = self.inside(os.path.join(ROOT, "work", "plans"), path[len("/media/plans/"):])
            if f and f.endswith(".png"):
                return self.send_file(f, "image/png", head, cache="private, max-age=3600")
        if path.startswith("/media/research/"):  # screenshots the art director looked at while researching
            f = self.inside(os.path.join(ROOT, "work", "research"), path[len("/media/research/"):])
            if f and f.endswith(".png"):
                return self.send_file(f, "image/png", head, cache="private, max-age=3600")
        if path.startswith("/media/artstills/"):  # frames the art director checked in its own preview
            f = self.inside(os.path.join(ROOT, "work", "artstills"), path[len("/media/artstills/"):])
            if f and f.endswith(".jpg"):
                return self.send_file(f, "image/jpeg", head, cache="no-store")
        if path.startswith("/media/stock/"):  # open-licence backgrounds used by explainer storyboards
            f = self.inside(os.path.join(ROOT, "assets", "stock"), path[len("/media/stock/"):])
            if f and f.endswith(".jpg"):
                return self.send_file(f, "image/jpeg", head, cache="private, max-age=604800")
        if path.startswith("/media/assets/"):
            f = self.inside(os.path.join(ROOT, "assets"), path[len("/media/assets/"):])
            if f and f.endswith(".mp3"):
                return self.send_file(f, "audio/mpeg", head)
            if f and f.endswith(".png"):   # illustrations and character sheets
                return self.send_file(f, "image/png", head, cache="private, max-age=604800")
        if path.startswith("/thumb/clip/"):
            con = connect()
            try:
                t = clip_thumb(con, path[len("/thumb/clip/"):], (q.get("t") or ["0"])[0])
            finally:
                con.close()
            if t:
                return self.send_file(t, "image/jpeg", head, cache="private, max-age=604800")
        m = re.fullmatch(r"/thumb/prod/(\d+)", path)
        if m:
            con = connect()
            try:
                t = prod_thumb(con, m.group(1), (q.get("t") or ["0"])[0])
            finally:
                con.close()
            if t:
                return self.send_file(t, "image/jpeg", head, cache="private, max-age=604800")
        if path == "/media/ref" or path == "/thumb/ref":
            con = connect()
            try:
                rid = (q.get("id") or [""])[0]
                if path == "/thumb/ref":
                    t = ref_thumb(con, rid)
                    if t:
                        return self.send_file(t, "image/jpeg", head, cache="private, max-age=604800")
                else:
                    r = con.execute("SELECT path FROM ref_videos WHERE ref_id=?", (rid,)).fetchone()
                    if r and os.path.isfile(r["path"]):
                        mime = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
                            os.path.splitext(r["path"])[1].lower(), "video/mp4")
                        return self.send_file(r["path"], mime, head)
            finally:
                con.close()
        if path.startswith("/thumb/out/"):
            f = self.inside(OUT, path[len("/thumb/out/"):])
            t = shorts.thumbnail(f, os.stat(f)) if f else None
            if t:
                return self.send_file(t, "image/jpeg", head, cache="private, max-age=604800")
        self.send_bytes(404, b"Not found\n", "text/plain; charset=utf-8", head)

    def get_api(self, con, path, q):
        ch = (q.get("channel") or [None])[0]
        if path == "/api/overview":
            return overview(con, ch)
        if path == "/api/formats":
            P.ensure(con)
            n = {r["format"]: r["n"] for r in con.execute(
                "SELECT format, COUNT(*) n FROM productions WHERE stage!='rejected' GROUP BY format")}
            return [{**f, "count": n.get(f["id"], 0)} for f in formats.FORMATS]
        if path == "/api/catalog":
            from factory import catalog
            kind = (q.get("kind") or [None])[0]
            return {"items": catalog.listing(kind), "missing": len(catalog.missing())}
        if path == "/api/techniques":
            from factory import capabilities
            return capabilities.chips((q.get("kind") or [None])[0])
        if path == "/api/modes":
            return formats.MODES
        if path == "/api/places":
            return places(con)
        if path == "/api/productions":
            return all_prods(con, ch)
        if path == "/api/channels":
            P.ensure(con)
            return channels.listing(con)
        m = re.fullmatch(r"/api/channels/([\w-]+)", path)
        if m:
            c = channels.get(con, m.group(1))
            if not c:
                raise ValueError("kanal bulunamadı")
            return {**c, "overview": overview(con, c["id"]), "series": series.listing(con, c["id"]),
                    "tracking": channel_tracking(con, c["id"])}
        if path == "/api/plans":
            return planner.recent(con)
        m = re.fullmatch(r"/api/plan/(\d+)", path)
        if m:
            return planner.get(con, int(m.group(1)))
        if path == "/api/series":
            return series.listing(con, ch)
        m = re.fullmatch(r"/api/series/(\d+)", path)
        if m:
            return series_detail(con, int(m.group(1)))
        if path == "/api/clips/search":   # semantic search over the footage library (descriptions + places)
            from factory import embed
            return {"results": clip_search(con, (q.get("q") or [""])[0]), "backend": embed.backend()}
        if path == "/api/search":   # command palette
            return search(con, (q.get("q") or [""])[0])
        m = re.fullmatch(r"/api/production/(\d+)", path)
        if m:
            return production_detail(con, int(m.group(1)))
        if path == "/api/jobs":
            return job_rows(con, 25)
        if path == "/api/library":
            return library(con)
        if path == "/api/posts":
            return {"posts": tracking.posts(con), "summary": tracking.summary(con)}
        if path == "/api/budget":
            return budget(con)
        if path == "/api/claude_usage":
            return usage.summary(con)
        if path == "/api/refs":
            return {"refs": refs.library(con), "themes": refs.THEMES}
        if path == "/api/me":
            return me(con)
        if path == "/api/codex/elevenlabs/status":
            state = llm.codex_elevenlabs_status()
            with CODEX_MCP_LOCK:
                state["flow"] = CODEX_MCP_FLOW.get("status")
                state["error"] = CODEX_MCP_FLOW.get("error")
            return state
        if path == "/api/eleven":
            aid = (q.get("account") or [accounts.default_eleven()])[0]
            if not accounts.can_use(aid):
                raise ValueError("Bu ElevenLabs hesabını kullanamazsın")
            if accounts.eleven(aid)["type"] == "apikey":
                i = eleven_info(aid, fresh="fresh" in q)
                return {"account": aid, "voices": i["voices"], "defaults": {}, "avatar": {}, "balance": i.get("balance"),
                        "error": i.get("error"), "spent": round(credits.month_spent(con, aid)),
                        "cap": (i.get("balance") or {}).get("limit"),
                        "music_rate": credits.rates().get(f"music:{P.MUSIC_MODEL}", {}).get("rate")}
            prof = eleven_profile()
            prof["account"] = aid
            prof["music_rate"] = credits.rates().get(f"music:{P.MUSIC_MODEL}", {}).get("rate")
            prof["spent"], prof["cap"] = round(credits.month_spent(con, aid)), credits.MONTHLY_CAP
            prof["languages"] = formats.ELEVEN_LANGUAGES
            return prof
        if path == "/api/discover":
            cats = (channels.get(con, ch) or {}).get("discover") if ch else None
            reg = (q.get("region") or [""])[0]
            return discover.cards(con, categories=cats or None, region=reg if reg in discover.REGIONS else None)
        if path == "/api/styles":
            return styles.listing()
        if path == "/api/signals":
            return signal_data(con, (q.get("profile") or ["travel"])[0])
        raise ValueError("bilinmeyen adres")

    def inside(self, base, rel):
        base = os.path.realpath(base)
        full = os.path.realpath(os.path.join(base, rel))
        return full if full.startswith(base + os.sep) and os.path.isfile(full) else None

    def json(self, status, obj, head=False):
        self.send_bytes(status, json.dumps(obj, ensure_ascii=False, default=str).encode(),
                        "application/json; charset=utf-8", head)


def stats_loop():
    """YouTube numbers every 6 hours while there are YouTube posts (a few quota units per run)."""
    while True:
        time.sleep(6 * 3600)
        try:
            con = connect()
            if con.execute("SELECT 1 FROM posts WHERE platform='youtube' LIMIT 1").fetchone():
                print(time.strftime("%F %T"), "youtube stats:", tracking.refresh_youtube(con), flush=True)
            con.close()
        except Exception as e:
            print("stats loop:", e, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host")
    ap.add_argument("--port", type=int, default=STUDIO_PORT)
    a = ap.parse_args()
    host = a.host or HOST or shorts.tailscale_ip()
    if not host:
        sys.exit("Tailscale IP not found; refusing to listen on a public address. "
                 "For local use set CF_HOST=127.0.0.1 in config.env.")
    con = connect()
    P.ensure(con)
    con.close()
    threading.Thread(target=stats_loop, daemon=True).start()
    srv = ThreadingHTTPServer((host, a.port), Handler)
    srv.daemon_threads = True
    srv.out_dir = os.path.realpath(OUT)
    print(f"{time.strftime('%F %T')} Studio on http://{host}:{a.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
