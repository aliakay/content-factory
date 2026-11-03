"""Studio API for v2 production lines (factory/hat). Mounted by studio/server.py under /api/hat/.

GET  /api/hat/lines                    every line, in the user's interface language
GET  /api/hat/projects                 every project with where it stands
GET  /api/hat/styles                   the film style library (cards + preview frames)
GET  /api/hat/ownstyles                the creator's own film styles; /api/hat/ownstyle/<id> one, with its questions
POST /api/hat/ownstyles     {name, base}                      step 1: a draft from a base style or a blank page
POST /api/hat/ownstyle/<id> {action: answer|sample|approve|delete, q?, value?}   steps 2-5
GET  /api/hat/project/<id>             the flow view of one project: stages, their outputs, stills, live events
GET  /api/hat/project/<id>/scenes      the scene editor: scenes, their text elements, frames with boxes, versions
POST /api/hat/project/<id>/scenes {action: edit|frames|save_version|restore|cut, ...}   hand edits at the scene plan gate
GET  /api/hat/project/<id>/export      the export package card: exportable items and the packages made so far
POST /api/hat/project/<id>/export {items: [...]}   queue the export_pack job (no credits)
POST /api/hat/lang          {lang}     the user's interface language (tr | en)
POST /api/hat/projects      {line, brief, title?, video_lang, aspect, channel?, proof?}   create and start
POST /api/hat/project/<id>  {action: approve|feedback|back|retry|advance, stage, note?}  a gate action
"""
import glob, json, os, re

from factory import accounts
from factory.config import ROOT
from factory.hat import manifest, project as P, runner

ID = re.compile(r"^\d{3}-[a-z0-9-]+$")
VIDEO_LANGS = ("tr", "en")
ASPECTS = ("9:16", "16:9")


def lang():
    return accounts.ui_lang()


def _media(path):
    """Project file -> its Studio URL (or None)."""
    if not path:
        return None
    full = path if os.path.isabs(path) else os.path.join(ROOT, path)
    rel = os.path.relpath(os.path.realpath(full), os.path.realpath(P.root()))
    return None if rel.startswith("..") else "/media/projects/" + rel


def lines():
    from factory import proof
    out = []
    for m in manifest.all_lines().values():
        v = manifest.localize(m, lang())
        out.append({k: v[k] for k in ("id", "order", "status", "category", "inputs", "duration", "name", "tagline",
                                      "makes", "good_for", "not_for", "needs", "cost")} |
                   {"stages": [{k: s[k] for k in ("id", "name", "says", "gate", "run")} for s in v["stages"]],
                    "proof": proof.supports(m)})
    return out


def _check(pid):
    if not ID.match(pid or "") or not os.path.isfile(P.path(pid, "project.json")):
        raise ValueError("no such project")
    return pid


def projects():
    out = []
    for pid in P.list_ids():
        try:
            p = P.load(pid)
            state, cur = P.next_stage(pid)
            m = manifest.localize(manifest.get(p["line"]), lang())
        except Exception:
            continue
        ev = P.tail(pid, n=1)
        cur_name = next((s["name"] for s in m["stages"] if s["id"] == cur), None)
        final = P.path(pid, "renders", "final.mp4")
        preview = P.path(pid, "renders", "preview.mp4")
        if p.get("status") == "archived":
            state, cur = "archived", None
            cur_name = None
            final = _archived_final(pid) or final
        out.append({"id": pid, "title": p["title"], "line": p["line"], "line_name": m["name"], "state": state,
                    "stage": cur, "stage_name": cur_name, "video_lang": p.get("video_lang"), "aspect": p.get("aspect"),
                    "channel": p.get("channel"), "created_at": p.get("created_at"),
                    "updated_at": ev[0]["at"] if ev else p.get("created_at"),
                    "video": _media(final if os.path.exists(final) else preview if os.path.exists(preview) else None),
                    "legacy": p.get("legacy")})
    return out


def _archived(pid):
    try:
        return P.load(pid).get("status") == "archived"
    except P.GateError:
        return False


def _archived_final(pid):
    f = (P.read_artifact(pid, "render") or {}).get("final")      # the compose stage's artifact
    return os.path.join(ROOT, f) if f else None


def _stills(pid, stage):
    """The newest stills folder of a stage (render_stills writes stills/<stage>-<time>/)."""
    dirs = sorted(glob.glob(P.path(pid, "stills", stage + "-*")), key=os.path.getmtime)
    if not dirs:
        return []
    return [_media(f) for f in sorted(glob.glob(os.path.join(dirs[-1], "*.png")))]


def _public(name, data):
    """An artifact as the board shows it: scene code stays on the server, media paths become URLs."""
    if not isinstance(data, dict):
        return data
    data = dict(data)
    if name == "scene_plan":
        data["scenes"] = [{k: sc.get(k) for k in ("id", "lines", "trigger", "notes")} for sc in data.get("scenes") or []]
        data.pop("global_css", None)
    for k in ("preview", "final"):
        if isinstance(data.get(k), str):
            data[k + "_url"] = _media(data[k])
    if isinstance(data.get("plates"), list):
        data["plate_urls"] = [_media(c) for c in data["plates"]]
    if isinstance(data.get("covers"), list):
        data["cover_urls"] = [_media(c) for c in data["covers"]]
    if isinstance(data.get("voice"), dict) and data["voice"].get("file"):
        data["voice"] = {k: v for k, v in data["voice"].items() if k not in ("words",)}
    return data


def project(pid):
    _check(pid)
    f = P.flow(pid, lang())
    for s in f["stages"]:
        art = P.read_artifact(pid, s["artifact"]) if s["status"] not in ("pending",) else None
        s["output"] = _public(s["artifact"], art) if art is not None else None
        if s["id"] == "scene_plan":
            s["stills"] = _stills(pid, "scene_plan")
    from factory import filmstyles as styles
    line = manifest.get(P.load(pid)["line"])
    for s in f["stages"]:
        if styles.picks_style(manifest.stage(line, s["id"])):   # the gate offers the style library
            s["style_pick"] = True
            look = str((s.get("output") or {}).get("look") or "")
            st = styles.get(look[6:]) if look.startswith("style.") else None
            if st:
                s["style"] = styles.card(st, lang())
    from factory import sceneedit
    for s in f["stages"]:
        if sceneedit.editable(manifest.stage(line, s["id"])) and s.get("output"):
            s["scene_edit"] = True
    from factory import proof
    if proof.on(pid):                 # proof mode: each checked gate carries its number-by-number report
        for s in f["stages"]:
            if s["status"] not in ("pending", "running") and s.get("output") is not None:
                r = proof.check(pid, s["id"])
                if r:
                    s["proof"] = r | {"problems": proof.problems(r, lang())}
    from factory import export
    if export.final(pid):             # the export package card (t505)
        f["export"] = exports(pid)
    f["events"] = P.tail(pid, n=40)
    f["ui_lang"] = lang()
    if _archived(pid):
        f["state"], f["current"] = "archived", None
    return f


def scenes(pid):
    from factory import sceneedit
    try:
        v = sceneedit.view(pid)
    except sceneedit.EditError as e:
        raise ValueError(e.text(lang())) from None
    for sc in v["scenes"]:
        sc["frame"] = _media(sc["frame"])
    v["archived"] = _archived(pid)
    return v


def _scenes_post(pid, b, queue, uid):
    from factory import sceneedit
    if _archived(pid):
        raise ValueError({"tr": "Bu bir arşiv kaydı; üzerinde iş yapılmaz.",
                          "en": "This is an archive record; no work is done on it."}[lang()])
    a = b.get("action")
    try:
        if a == "edit":
            return sceneedit.edit(pid, str(b.get("scene") or ""), str(b.get("e") or ""), text=b.get("text"),
                                  color=b.get("color"), dx=b.get("dx"), dy=b.get("dy"), by=uid)
        if a == "frames":
            sceneedit.prepare(pid)
            return {"job_id": queue("scene_frames", json.dumps({"project": pid}))}
        if a == "save_version":
            return sceneedit.save_version(pid, b.get("name"), by=uid)
        if a == "restore":
            return sceneedit.restore(pid, b.get("n"), by=uid)
        if a == "cut":
            return sceneedit.cut(pid, b.get("scene"), b.get("start"), by=uid)
    except sceneedit.EditError as e:
        raise ValueError(e.text(lang())) from None
    raise ValueError("unknown action")


def exports(pid):
    """The export package card (t505): what this project can export and the packages made so far."""
    from factory import export
    return {"ready": bool(export.final(pid)), "archived": _archived(pid),
            "items": [{"id": i, "name": export.NAMES[i][lang()], "default": i in export.DEFAULT} for i in export.available(pid)],
            "exports": [{"at": x["at"], "items": x["items"], "files": x["files"], "notes": x["notes"], "size": x["size"],
                         "zip": _media(x["zip"]), "name": os.path.basename(x["zip"] or "")} for x in export.exports(pid)[:5]]}


def _export_post(pid, b, queue):
    from factory import export
    if _archived(pid):
        raise ValueError({"tr": "Bu bir arşiv kaydı; üzerinde iş yapılmaz.",
                          "en": "This is an archive record; no work is done on it."}[lang()])
    if not export.final(pid):
        raise ValueError({"tr": "Henüz final video yok.", "en": "No final video yet."}[lang()])
    items = [i for i in b.get("items") or [] if i in export.available(pid)]
    if not items:
        raise ValueError({"tr": "Dışa aktarılacak en az bir şey seç.", "en": "Pick at least one thing to export."}[lang()])
    return {"job_id": queue("export_pack", json.dumps({"project": pid, "items": items}))}


def get(con, path, q):
    if path == "/api/hat/lines":
        return lines()
    if path == "/api/hat/projects":
        return projects()
    if path == "/api/hat/series":           # series whose book and characters are ready, for the episode line's form
        from factory import series
        return [{"id": x["series_id"], "title": x["title"], "episodes": x["episodes"], "made": x["made"]}
                for x in series.listing(con) if x["status"] == "ready"]
    if path == "/api/hat/styles":           # the film style library: cards in the UI language with preview frames
        from factory import filmstyles
        return filmstyles.cards(lang())
    if path == "/api/hat/ownstyles":
        from factory import ownstyles
        return [ownstyles.view(st, lang()) for st in ownstyles.listing()]
    m = re.fullmatch(r"/api/hat/ownstyle/(own_[a-z0-9_]+)", path)
    if m:
        from factory import ownstyles
        return ownstyles.view(ownstyles.load(m.group(1)), lang())
    m = re.fullmatch(r"/api/hat/project/([\w-]+)/scenes", path)
    if m:
        return scenes(_check(m.group(1)))
    m = re.fullmatch(r"/api/hat/project/([\w-]+)/export", path)
    if m:
        return exports(_check(m.group(1)))
    m = re.fullmatch(r"/api/hat/project/([\w-]+)", path)
    if m:
        return project(m.group(1))
    raise ValueError("unknown hat endpoint")


def post(con, path, b, queue):
    try:
        return _post(con, path, b, queue)
    except P.GateError as e:          # a gate rule said no: the Studio shows the reason as it is
        raise ValueError(str(e)) from None


def _post(con, path, b, queue):
    uid = accounts.current()
    if path == "/api/hat/lang":
        return {"ui_lang": accounts.set_ui_lang(uid, b.get("lang"))}
    if path == "/api/hat/ownstyles" or path.startswith("/api/hat/ownstyle/"):
        return _own_style(path, b, queue, uid)
    if path == "/api/hat/projects":
        line = manifest.get(b.get("line") or "")
        if line["status"] != "ready":
            raise ValueError({"tr": "Bu hat henüz hazır değil.", "en": "This line is not ready yet."}[lang()])
        brief = str(b.get("brief") or "").strip()
        if len(brief) < 8:
            raise ValueError({"tr": "Ne üretmek istediğini birkaç kelimeyle yaz.",
                              "en": "Say in a few words what you want to make."}[lang()])
        vl = b.get("video_lang") if b.get("video_lang") in VIDEO_LANGS else lang()
        aspect = b.get("aspect") if b.get("aspect") in ASPECTS else "9:16"
        title = str(b.get("title") or "").strip() or brief.split(".")[0][:60]
        extra = {"ui_lang": lang(), "eleven_account": accounts.default_eleven(uid)}
        if "video" in (line.get("inputs") or []):          # the creator's own video, uploaded to raw/talk/ first
            src = str(b.get("source") or "")
            ok_ext = (".mp4", ".mov", ".m4v") + ((".mp3", ".m4a", ".wav", ".aac") if "audio" in line["inputs"] else ())
            if not re.fullmatch(r"raw/talk/[\w.-]+", src) or not src.lower().endswith(ok_ext) \
                    or not os.path.isfile(os.path.join(ROOT, src)):
                raise ValueError({"tr": "Önce videonu yükle.", "en": "Upload your video first."}[lang()])
            extra["source"] = src
        if "portrait" in (line.get("inputs") or []) and b.get("portrait"):   # optional: no portrait = a generated one
            src = str(b["portrait"])
            if not re.fullmatch(r"raw/avatar/[\w.-]+", src) or not os.path.isfile(os.path.join(ROOT, src)):
                raise ValueError({"tr": "Portre yüklenemedi; tekrar dene.", "en": "The portrait did not upload; try again."}[lang()])
            extra["portrait"] = src
        if "url" in (line.get("inputs") or []):           # a public page only: the browser runs next to the Studio
            from factory.hat import screendemo
            try:
                extra["url"] = screendemo.safe_url(b.get("url"))
            except P.GateError:
                raise ValueError({"tr": "Herkese açık bir http(s) adresi yaz (yerel ağ adresleri olmaz).",
                                  "en": "Give a public http(s) address (no local network addresses)."}[lang()]) from None
        if "source_lang" in (line.get("inputs") or []):
            extra["source_lang"] = b.get("source_lang") if b.get("source_lang") in VIDEO_LANGS else ("en" if vl == "tr" else "tr")
        if "series" in (line.get("inputs") or []):
            try:
                extra["series"] = {"id": int(b.get("series")), "episode": int(b.get("episode"))}
            except (TypeError, ValueError):
                raise ValueError({"tr": "Bir seri ve bölüm seç.", "en": "Pick a series and an episode."}[lang()]) from None
        from factory import proof
        if b.get("proof") and proof.supports(line):      # proof film: every number must match a source
            extra["proof"] = True
        from factory.hat import footage
        if b.get("format") in footage.FORMATS:
            extra["format"] = b["format"]
        p = P.create(line["id"], title, brief=brief, video_lang=vl, aspect=aspect, channel=b.get("channel"), user=uid,
                     con=con, extra=extra)
        state, stage = runner.advance(p["id"], queue, by=uid)
        return {"id": p["id"], "state": state, "stage": stage}
    m = re.fullmatch(r"/api/hat/project/([\w-]+)/scenes", path)
    if m:
        return _scenes_post(_check(m.group(1)), b, queue, uid)
    m = re.fullmatch(r"/api/hat/project/([\w-]+)/export", path)
    if m:
        return _export_post(_check(m.group(1)), b, queue)
    m = re.fullmatch(r"/api/hat/project/([\w-]+)", path)
    if m:
        pid, a, sid = _check(m.group(1)), b.get("action"), b.get("stage")
        if _archived(pid):
            raise ValueError({"tr": "Bu bir arşiv kaydı; üzerinde iş yapılmaz.",
                              "en": "This is an archive record; no work is done on it."}[lang()])
        if a == "approve":
            state, stage = runner.approve(pid, sid, queue, by=uid, note=b.get("note"))
        elif a == "feedback":
            state, stage = runner.feedback(pid, sid, b.get("note"), queue, by=uid)
        elif a == "back":
            state, stage = runner.back(pid, sid, by=uid)
        elif a == "retry":
            state, stage = runner.retry(pid, sid, queue, by=uid)
        elif a == "advance":          # start the next stage of a line that stands still (nothing queued it)
            state, stage = runner.advance(pid, queue, by=uid)
        else:
            raise ValueError("unknown action")
        return {"id": pid, "state": state, "stage": stage}
    raise ValueError("unknown hat endpoint")


def _own_style(path, b, queue, uid):
    from factory import ownstyles
    ui = lang()
    if path == "/api/hat/ownstyles":
        return ownstyles.view(ownstyles.create(b.get("name"), b.get("base"), user=uid, ui=ui), ui)
    m = re.fullmatch(r"/api/hat/ownstyle/(own_[a-z0-9_]+)", path)
    if not m:
        raise ValueError("unknown hat endpoint")
    sid, a = m.group(1), b.get("action")
    if a == "answer":
        return ownstyles.view(ownstyles.answer(sid, b.get("q"), b.get("value"), ui), ui)
    if a == "sample":                 # drawn as a job (about a minute); the page polls until the frame is there
        st = ownstyles.load(sid)
        if ownstyles.missing(st):
            raise ValueError({"tr": "Önce bütün soruları yanıtla.", "en": "Answer every question first."}[ui])
        return {**ownstyles.view(st, ui), "job_id": queue("own_style_sample", sid)}
    if a == "approve":
        return ownstyles.view(ownstyles.approve(sid, by=uid, ui=ui), ui)
    if a == "delete":
        ownstyles.delete(sid)
        return {"deleted": sid}
    raise ValueError("unknown action")


def media_file(rel):
    """/media/projects/<rel> -> (absolute path, content type) or None."""
    full = os.path.realpath(os.path.join(P.root(), rel))
    if not full.startswith(os.path.realpath(P.root()) + os.sep) or not os.path.isfile(full):
        return None
    types = {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg", ".mp3": "audio/mpeg", ".wav": "audio/wav",
             ".gif": "image/gif", ".zip": "application/zip"}
    t = types.get(os.path.splitext(full)[1].lower())
    return (full, t) if t else None
