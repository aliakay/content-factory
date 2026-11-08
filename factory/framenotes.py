"""Frame comments (t514): the creator clicks a frame (a scene editor still or the preview video) and writes a note.
The note carries the time, the scene, the text element under the cursor (the boxes the renderer measured) and that
element's source line in the scene's HTML. Sending the open notes re-runs the scene designer with them as a targeted
revision, and when the run ends every scene the notes do not name, the palette and the global CSS are put back
exactly as they were: the agent can only change the points the creator commented on. With partial render (t511) only
those scenes are drawn again.
"""
import json, os, re, uuid

from . import noteanchor, sceneedit
from .hat import project as P

FILE = "frame_notes.json"
TEXT_MAX = 600
NEAR = 60          # px: a click this close to a box still names it


class NoteError(ValueError):
    MSG = {"text": {"tr": "Yorum boş olamaz.", "en": "A comment cannot be empty."},
           "scene": {"tr": "Bu anda sahne yok.", "en": "No scene at this moment."},
           "none": {"tr": "Gönderilecek açık yorum yok.", "en": "No open comments to send."},
           "busy": {"tr": "Bir aşama çalışıyor; bitmesini bekle.", "en": "A stage is running; wait for it to finish."},
           "unknown": {"tr": "Böyle bir yorum yok.", "en": "No such comment."},
           "sent": {"tr": "Bu yorum tasarımcıya gönderildi; artık silinemez.",
                    "en": "This comment went to the designer; it can no longer be removed."}}

    def __init__(self, key):
        super().__init__(key)
        self.key = key

    def text(self, lang="tr"):
        return self.MSG.get(self.key, {}).get(lang) or self.key


def _path(pid, d=None):
    return P.path(pid, "artifacts", FILE, d=d)


def load(pid, d=None):
    f = _path(pid, d)
    if not os.path.exists(f):
        return {"notes": [], "batches": []}
    return json.load(open(f, encoding="utf-8"))


def _save(pid, data, d=None):
    os.makedirs(os.path.dirname(_path(pid, d)), exist_ok=True)
    with open(_path(pid, d), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _scene_at(pid, plan, t, d=None):
    from .hat import explainer
    try:
        scenes = explainer.spec(pid, plan, d)["scenes"]
    except Exception:
        return None
    for sc in scenes:
        if sc["start"] <= t < sc["end"]:
            return sc["id"]
    return scenes[-1]["id"] if scenes and t >= scenes[-1]["start"] else None


def element_at(boxes, x, y):
    """The smallest measured text box under (x, y), else the nearest one within NEAR px, else None."""
    inside = [b for b in boxes if b["x"] <= x <= b["x"] + b["w"] and b["y"] <= y <= b["y"] + b["h"]]
    if inside:
        return min(inside, key=lambda b: b["w"] * b["h"])
    dist = lambda b: max(b["x"] - x, 0, x - b["x"] - b["w"]) ** 2 + max(b["y"] - y, 0, y - b["y"] - b["h"]) ** 2
    near = [b for b in boxes if dist(b) <= NEAR ** 2]
    return min(near, key=dist) if near else None


def source_line(html, e):
    """{line, text} of the scene HTML line that holds data-e="<e>" (1-based), or None."""
    for k, ln in enumerate(str(html or "").split("\n"), 1):
        if re.search(rf'data-e="{re.escape(str(e))}"', ln):
            return {"line": k, "text": ln.strip()[:200]}
    return None


def locate(pid, t=None, scene=None, x=None, y=None, d=None):
    """Where a click landed: {t, scene, x, y, e, label, src}."""
    plan = sceneedit.prepare(pid, d)
    if scene is None and t is not None:
        scene = _scene_at(pid, plan, float(t), d)
    sc = next((s for s in plan["scenes"] if s.get("id") == scene), None)
    if not sc:
        raise NoteError("scene")
    out = {"t": None if t is None else round(float(t), 2), "scene": scene, "x": None, "y": None, "e": None,
           "label": None, "src": None}
    if x is not None and y is not None:
        out["x"], out["y"] = round(float(x)), round(float(y))
        info = sceneedit.frames_info(pid, d) or {}
        i = plan["scenes"].index(sc)
        shots = info.get("shots") or []
        boxes = [b for b in (shots[i].get("boxes") if i < len(shots) else []) or [] if b.get("scene") in (None, scene)]
        b = element_at(boxes, out["x"], out["y"])
        if b:
            out["e"], out["label"] = b["e"], (b.get("text") or "")[:80]
            out["src"] = source_line(sc.get("html"), b["e"])
    return out


def add(pid, text, t=None, scene=None, x=None, y=None, origin="frame", by=None, d=None):
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:TEXT_MAX]
    if not text:
        raise NoteError("text")
    where = locate(pid, t, scene, x, y, d)
    data = load(pid, d)
    note = {"id": "c" + uuid.uuid4().hex[:6], "text": text, "origin": origin if origin in ("frame", "video") else "frame",
            "status": "open", "by": by, "at": P.now(), **where}
    # the note stays with its moment: its scene and the offset inside it, so a re-timed scene keeps the note on frame
    try:
        note = noteanchor.anchor(note, sceneedit.prepare(pid, d).get("scenes") or [])
    except Exception:
        pass
    data["notes"].append(note)
    _save(pid, data, d)
    P.event(pid, "frame_note", d=d, id=note["id"], scene=note["scene"], by=by)
    return note


def remove(pid, nid, d=None):
    data = load(pid, d)
    n = next((x for x in data["notes"] if x["id"] == nid), None)
    if not n:
        raise NoteError("unknown")
    if n["status"] == "done":
        raise NoteError("sent")
    data["notes"] = [x for x in data["notes"] if x["id"] != nid]
    _save(pid, data, d)
    return {"removed": nid}


def _line(n, size):
    where = f'at {n["t"]:.2f} s, ' if n.get("t") is not None else ""
    where += f'scene "{n["scene"]}"'
    if n.get("e"):
        where += f', on element data-e="{n["e"]}" ("{n.get("label") or ""}")'
        if n.get("src"):
            where += f' (scene html line {n["src"]["line"]}: `{n["src"]["text"]}`)'
    if n.get("x") is not None:
        where += f', point ({n["x"]}, {n["y"]}) of the {size[0]}x{size[1]} frame'
    return f'- [{n["id"]}] {where}: "{n["text"]}"'


def note_text(pid, notes, d=None):
    """The targeted revision the designer gets as its feedback note."""
    aspect = P.load(pid, d).get("aspect") or "9:16"
    size = [1080, 1920] if aspect == "9:16" else [1920, 1080]
    scenes = sorted({n["scene"] for n in notes})
    return ("## Frame comments (a targeted revision)\nThe creator clicked on frames of the video and wrote these "
            "comments. Change ONLY what each comment asks, only in the scenes it names "
            f"({', '.join(scenes)}). Keep every data-e attribute. After you submit, every other scene, the palette and "
            "the global CSS are restored exactly as they are now, so a change anywhere else is lost; if a comment "
            "cannot be done inside its scene, say so in `summary`.\n" + "\n".join(_line(n, size) for n in notes))


def follow(pid, d=None):
    """Re-derive every open note's time from its anchor after the plan was re-timed (scene trimmed, cut moved).

    A note is written on a moment, not on a second: `factory/noteanchor.py` keeps scene + offset, so a re-cut film
    still points the designer at the right frame; a note whose scene is gone is marked stale and says so."""
    data = load(pid, d)
    try:
        scenes = sceneedit.prepare(pid, d).get("scenes") or []
        before = [dict(n) for n in data["notes"]]
        data["notes"] = noteanchor.follow(data["notes"], scenes)
        moved = [n["id"] for n, b in zip(data["notes"], before) if n.get("t") != b.get("t")]
        if moved or any(n.get("stale") for n in data["notes"]):
            _save(pid, data, d)
            P.event(pid, "notes_followed", d=d, moved=moved,
                    stale=[n["id"] for n in data["notes"] if n.get("stale")])
    except Exception:
        return data["notes"]
    return data["notes"]


def pending(pid, d=None):
    notes = follow(pid, d)
    return [n for n in notes if n["status"] in ("open", "sent")]


def send(pid, queue, by=None, d=None):
    """Send the open comments to the scene designer (re-opening the scene plan when a later gate is waiting)."""
    from .hat import runner
    notes = pending(pid, d)
    if not notes:
        raise NoteError("none")
    s = sceneedit._stage(pid, d)
    rows = P.stages(pid, d)
    if any(cp["status"] == "running" for _, cp in rows):
        raise NoteError("busy")
    if P.checkpoint(pid, s["id"], d)["status"] != "awaiting_approval":
        P.reopen(pid, s["id"], by=by, d=d)
    plan = sceneedit.prepare(pid, d)
    data = load(pid, d)
    ids = [n["id"] for n in notes]
    for b in data["batches"]:
        if b["status"] == "running":                # an earlier run that failed: its comments go again now
            b.update(status="failed", before=None)
    data["batches"].append({"n": len(data["batches"]) + 1, "at": P.now(), "by": by, "ids": ids, "status": "running",
                            "scenes": sorted({n["scene"] for n in notes}),
                            "before": {"scenes": plan["scenes"], **{k: plan.get(k) for k in ("palette", "global_css")}}})
    for n in data["notes"]:
        if n["id"] in ids:
            n["status"] = "sent"
    _save(pid, data, d)
    state = runner.feedback(pid, s["id"], note_text(pid, notes, d), queue, by=by, d=d)
    return {"sent": len(ids), "scenes": data["batches"][-1]["scenes"], "state": state}


def settle(pid, s, d=None):
    """After the designer's run: restore what the comments did not name. Returns the restored scene ids or None."""
    if not sceneedit.editable(s):
        return None
    data = load(pid, d)
    b = next((x for x in reversed(data["batches"]) if x["status"] == "running"), None)
    if not b:
        return None
    plan = P.read_artifact(pid, sceneedit.ART, d) or {}
    new = {sc.get("id"): sc for sc in plan.get("scenes") or []}
    scenes, restored = [], []
    for old in b["before"]["scenes"]:
        if old.get("id") in b["scenes"] and old.get("id") in new:
            scenes.append(new[old["id"]])
        else:
            if new.get(old.get("id")) != old:
                restored.append(old.get("id"))
            scenes.append(old)
    if [x.get("id") for x in plan.get("scenes") or []] != [x.get("id") for x in scenes]:
        restored.append("(scene list)")
    for k in ("palette", "global_css"):
        if plan.get(k) != b["before"].get(k):
            restored.append(k)
            plan[k] = b["before"].get(k)
    plan["scenes"] = scenes
    P.write_artifact(pid, sceneedit.ART, plan, d)
    b.update(status="done", restored=restored, done_at=P.now(), before=None)
    for n in data["notes"]:
        if n["id"] in b["ids"]:
            n["status"] = "done"
    _save(pid, data, d)
    P.event(pid, "frame_notes_done", d=d, batch=b["n"], scenes=b["scenes"], restored=restored)
    return restored


def view(pid, d=None):
    data = load(pid, d)
    return {"notes": data["notes"][-80:],
            "batches": [{k: v for k, v in b.items() if k != "before"} for b in data["batches"][-10:]]}
