"""Studio API for v2 production lines (factory/hat). Mounted by studio/server.py under /api/hat/.

GET  /api/hat/lines                    every line, in the user's interface language
GET  /api/hat/projects                 every project with where it stands
GET  /api/hat/project/<id>             the flow view of one project: stages, their outputs, stills, live events
POST /api/hat/lang          {lang}     the user's interface language (tr | en)
POST /api/hat/projects      {line, brief, title?, video_lang, aspect, channel?}   create and start
POST /api/hat/project/<id>  {action: approve|feedback|back|retry|advance, stage, note?}  a gate action
"""
import glob, os, re

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
    out = []
    for m in manifest.all_lines().values():
        v = manifest.localize(m, lang())
        out.append({k: v[k] for k in ("id", "order", "status", "category", "inputs", "duration", "name", "tagline",
                                      "makes", "good_for", "not_for", "needs", "cost")} |
                   {"stages": [{k: s[k] for k in ("id", "name", "says", "gate", "run")} for s in v["stages"]]})
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
    f["events"] = P.tail(pid, n=40)
    f["ui_lang"] = lang()
    if _archived(pid):
        f["state"], f["current"] = "archived", None
    return f


def get(con, path, q):
    if path == "/api/hat/lines":
        return lines()
    if path == "/api/hat/projects":
        return projects()
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
        p = P.create(line["id"], title, brief=brief, video_lang=vl, aspect=aspect, channel=b.get("channel"), user=uid,
                     con=con, extra={"ui_lang": lang(), "eleven_account": accounts.default_eleven(uid)})
        state, stage = runner.advance(p["id"], queue, by=uid)
        return {"id": p["id"], "state": state, "stage": stage}
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


def media_file(rel):
    """/media/projects/<rel> -> (absolute path, content type) or None."""
    full = os.path.realpath(os.path.join(P.root(), rel))
    if not full.startswith(os.path.realpath(P.root()) + os.sep) or not os.path.isfile(full):
        return None
    types = {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg", ".mp3": "audio/mpeg", ".wav": "audio/wav"}
    t = types.get(os.path.splitext(full)[1].lower())
    return (full, t) if t else None
