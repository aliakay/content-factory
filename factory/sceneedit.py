"""Scene editor (t504): the creator edits the scene plan's frames by hand at its gate.

Every element of a scene that holds text gets a stable address, `data-e="<n>"`, written into the scene's HTML. The
editor draws one settled frame per scene with the text boxes the renderer measures (`frames`, a background job), so
the Studio can lay clickable boxes over the frame. An edit changes one element: its text, its colour (an inline
`color`) or its place (an inline CSS `translate`, which stacks with the scene's GSAP motion instead of fighting it).
Edits go straight into the scene_plan artifact and into its `edits` list, so the next stage renders them and a
re-run of the designer sees them in its task and keeps them. On the timeline the creator trims by moving the cut
between two scenes one script line at a time (`cut`); scene times follow their lines. Named versions copy the whole scene plan; restoring one
is itself recorded as an edit. Edits and restores happen only while the scene plan waits at its gate.
"""
import glob, html as H, json, os, re, time
from html.parser import HTMLParser

from .hat import manifest, project as P

ART = "scene_plan"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP = {"script", "style", "svg"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_SHIFT = 1920
TEXT_MAX = 400


MSG = {
    "nested": {"tr": "Bu öğenin içinde başka parçalar var; onları tek tek düzenle.", "en": "This element holds other parts; edit them one by one."},
    "unclosed": {"tr": "Bu öğe sahnenin HTML'inde kapanmıyor.", "en": "This element is not closed in the scene's HTML."},
    "no_line": {"tr": "Bu hatta düzenlenebilir sahne yok.", "en": "This line has no editable scenes."},
    "not_gate": {"tr": "Sahneler yalnız sahne planı kapıda beklerken düzenlenir.", "en": "Scenes can be edited only while the scene plan waits at its gate."},
    "no_plan": {"tr": "Henüz sahne planı yok.", "en": "No scene plan yet."},
    "no_scene": {"tr": "Böyle bir sahne yok.", "en": "No such scene."},
    "no_element": {"tr": "Bu sahnede böyle bir öğe yok.", "en": "No such element in this scene."},
    "text_len": {"tr": "Metin 1-400 karakter olmalı.", "en": "Text must be 1-400 characters."},
    "color": {"tr": "Renk #ff8800 biçiminde olmalı.", "en": "Colour must look like #ff8800."},
    "numbers": {"tr": "Taşıma için sayı gerekir.", "en": "A move needs numbers."},
    "too_far": {"tr": "Bu taşıma kareden çıkıyor.", "en": "That move leaves the frame."},
    "name": {"tr": "Sürüme bir ad ver.", "en": "Give the version a name."},
    "no_version": {"tr": "Böyle bir sürüm yok.", "en": "No such version."},
    "cut": {"tr": "Kesme her iki sahnede de en az bir satır bırakmalı; ilk sahnenin başı kesilmez.",
            "en": "A cut must leave both scenes at least one line; the first scene's start cannot move."},
}


class EditError(ValueError):
    def __init__(self, code):
        super().__init__(MSG[code]["en"])
        self.code = code

    def text(self, ui="tr"):
        return MSG[self.code].get(ui) or MSG[self.code]["en"]


# ---------------------------------------------------------------- the scene's HTML

class _Map(HTMLParser):
    """Elements with their source offsets: start, open_end (after the start tag), end (where the end tag starts)."""

    def __init__(self, src):
        super().__init__(convert_charrefs=True)
        self.src, self.stack, self.els = src, [], []
        self.lines = [0] + [i + 1 for i, c in enumerate(src) if c == "\n"]

    def _off(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def _open(self, tag, attrs, push):
        o = self._off()
        raw = self.get_starttag_text() or ""
        el = {"tag": tag, "start": o, "open_end": o + len(raw), "attrs": dict(attrs), "text": "", "kids": 0,
              "end": None, "skip": tag in SKIP or any(p["skip"] for p in self.stack)}
        if self.stack:
            self.stack[-1]["kids"] += 1
        self.els.append(el)
        if push and tag not in VOID:
            self.stack.append(el)

    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs, True)

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs, False)

    def handle_endtag(self, tag):
        o = self._off()
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                for el in self.stack[i:]:
                    el["end"] = o
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self.stack and data.strip():
            self.stack[-1]["text"] += data


def _parse(src):
    m = _Map(src or "")
    m.feed(src or "")
    m.close()
    return [e for e in m.els if not e["skip"]]


def _texty(el):
    return el["text"].strip() and el["tag"] not in SKIP


def tag(src):
    """Give every text-holding element a `data-e` address; existing addresses stay. Returns the new HTML."""
    els = _parse(src)
    used = [int(e["attrs"]["data-e"]) for e in els if str(e["attrs"].get("data-e") or "").isdigit()]
    n = max(used, default=0)
    out = src
    adds = []
    for el in els:
        if _texty(el) and "data-e" not in el["attrs"]:
            n += 1
            adds.append((el, n))
    for el, k in sorted(adds, key=lambda x: -x[0]["open_end"]):
        cut = el["open_end"] - (2 if out[el["open_end"] - 2:el["open_end"]] == "/>" else 1)
        out = out[:cut] + f' data-e="{k}"' + out[cut:]
    return out


def _style(attrs):
    s = attrs.get("style") or ""
    return {k.strip().lower(): v.strip() for k, v in (p.split(":", 1) for p in s.split(";") if ":" in p)}


def elements(src):
    """The addressed elements of a scene: [{e, tag, text, color, dx, dy, nested}]."""
    out = []
    for el in _parse(src):
        e = el["attrs"].get("data-e")
        if not e:
            continue
        st = _style(el["attrs"])
        mv = re.match(r"^(-?\d+(?:\.\d+)?)px\s+(-?\d+(?:\.\d+)?)px$", st.get("translate", ""))
        out.append({"e": str(e), "tag": el["tag"], "text": re.sub(r"\s+", " ", el["text"]).strip()[:TEXT_MAX],
                    "color": st.get("color") if HEX.match(st.get("color") or "") else None,
                    "dx": float(mv.group(1)) if mv else 0, "dy": float(mv.group(2)) if mv else 0,
                    "nested": el["kids"] > 0})
    return out


def _find(src, e):
    for el in _parse(src):
        if str(el["attrs"].get("data-e")) == str(e):
            return el
    raise EditError("no_element")


def set_text(src, e, text):
    el = _find(src, e)
    if el["kids"]:
        raise EditError("nested")
    if el["end"] is None:
        raise EditError("unclosed")
    return src[:el["open_end"]] + H.escape(text, quote=False) + src[el["end"]:]


def set_style(src, e, **props):
    """Merge inline style properties into the element's start tag (None removes one)."""
    el = _find(src, e)
    raw = src[el["start"]:el["open_end"]]
    st = _style(el["attrs"])
    for k, v in props.items():
        if v is None:
            st.pop(k, None)
        else:
            st[k] = v
    val = "; ".join(f"{k}: {v}" for k, v in st.items())
    rx = re.compile(r"""\sstyle\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.I)
    attr = f' style="{H.escape(val)}"' if val else ""
    if rx.search(raw):
        new = rx.sub(lambda m: attr, raw, count=1)
    else:
        cut = len(raw) - (2 if raw.endswith("/>") else 1)
        new = raw[:cut] + attr + raw[cut:]
    return src[:el["start"]] + new + src[el["open_end"]:]


# ---------------------------------------------------------------- the project side

def editable(stage):
    """A stage whose output is HTML scenes the engine can draw."""
    return stage.get("artifact") == ART and "render_stills" in (stage.get("tools") or [])


def _stage(pid, d=None):
    line = manifest.get(P.load(pid, d)["line"])
    s = next((x for x in line["stages"] if editable(x)), None)
    if not s:
        raise EditError("no_line")
    return s


def _at_gate(pid, d=None):
    s = _stage(pid, d)
    if P.checkpoint(pid, s["id"], d)["status"] != "awaiting_approval":
        raise EditError("not_gate")
    return s


def _plan(pid, d=None):
    plan = P.read_artifact(pid, ART, d)
    if not plan or not plan.get("scenes"):
        raise EditError("no_plan")
    return plan


def prepare(pid, d=None):
    """Address every text element (written back only when something changed). Returns the plan."""
    plan = _plan(pid, d)
    changed = False
    for sc in plan["scenes"]:
        new = tag(sc.get("html") or "")
        if new != sc.get("html"):
            sc["html"], changed = new, True
    if changed:
        P.write_artifact(pid, ART, plan, d)
    return plan


def edit(pid, scene, e, text=None, color=None, dx=None, dy=None, by=None, d=None):
    """One hand edit. Returns the element as it is now."""
    _at_gate(pid, d)
    plan = prepare(pid, d)
    sc = next((x for x in plan["scenes"] if x.get("id") == scene), None)
    if not sc:
        raise EditError("no_scene")
    src = sc["html"]
    before = next((x for x in elements(src) if x["e"] == str(e)), None)
    if not before:
        raise EditError("no_element")
    did = []
    if text is not None:
        text = re.sub(r"\s+", " ", str(text)).strip()
        if not text or len(text) > TEXT_MAX:
            raise EditError("text_len")
        if text != before["text"]:
            src = set_text(src, e, text)
            did.append(("text", before["text"], text))
    if color is not None:
        if color and not HEX.match(color):
            raise EditError("color")
        if (color or None) != before["color"]:
            src = set_style(src, e, color=color or None)
            did.append(("color", before["color"], color or None))
    if dx is not None or dy is not None:
        try:
            x, y = round(float(dx if dx is not None else before["dx"])), round(float(dy if dy is not None else before["dy"]))
        except (TypeError, ValueError):
            raise EditError("numbers") from None
        if abs(x) > MAX_SHIFT or abs(y) > MAX_SHIFT:
            raise EditError("too_far")
        if (x, y) != (before["dx"], before["dy"]):
            src = set_style(src, e, translate=f"{x}px {y}px" if (x or y) else None)
            did.append(("move", [before["dx"], before["dy"]], [x, y]))
    if not did:
        return before
    sc["html"] = src
    log = plan.setdefault("edits", [])
    for what, old, new in did:
        log.append({"scene": scene, "e": str(e), "what": what, "before": old, "after": new, "by": by,
                    "at": P.now(), "label": before["text"][:40]})
    P.write_artifact(pid, ART, plan, d)
    P.event(pid, "scene_edit", d=d, stage=_stage(pid, d)["id"], scene=scene, e=str(e), what=[w for w, _, _ in did], by=by)
    return next(x for x in elements(src) if x["e"] == str(e))


def cut(pid, scene, start, by=None, d=None):
    """Trim on the timeline: the scene starts at script line `start`, the scene before it ends one line earlier.
    Scene times follow the lines (explainer.spec), so this moves the cut between the two scenes."""
    _at_gate(pid, d)
    plan = _plan(pid, d)
    i = next((k for k, x in enumerate(plan["scenes"]) if x.get("id") == scene), None)
    if i is None:
        raise EditError("no_scene")
    try:
        start = int(start)
    except (TypeError, ValueError):
        raise EditError("numbers") from None
    sc, prev = plan["scenes"][i], plan["scenes"][i - 1] if i else None
    a, b = (sc.get("lines") or [0, 0])[:2]
    if prev is None or not (prev.get("lines") or [0])[0] < start <= b:
        raise EditError("cut")
    if start == a:
        return {"scene": scene, "lines": [a, b]}
    prev["lines"] = [prev["lines"][0], start - 1]
    sc["lines"] = [start, b]
    plan.setdefault("edits", []).append({"scene": scene, "e": None, "what": "cut", "before": a, "after": start, "by": by,
                                         "at": P.now(), "label": prev.get("id", "")})
    P.write_artifact(pid, ART, plan, d)
    P.event(pid, "scene_edit", d=d, stage=_stage(pid, d)["id"], scene=scene, what=["cut"], by=by)
    return {"scene": scene, "lines": sc["lines"]}


def timeline(pid, plan, d=None):
    """Each scene's seconds and script lines for the editor's timeline: [{id, start, end, lines}], the line texts."""
    from .hat import explainer
    try:
        sp = explainer.spec(pid, plan, d)
    except Exception:   # no script or timing yet: the timeline stays empty
        return [], []
    texts = (P.read_artifact(pid, "script", d) or {}).get("lines") or []
    return ([{"id": x["id"], "start": x["start"], "end": x["end"], "lines": x["lines"]} for x in sp["scenes"]],
            [str(t if isinstance(t, str) else (t or {}).get("text", "")) for t in texts])


def brief(pid, s, d=None):
    """The designer's task section listing the creator's hand edits, or ''."""
    if not editable(s):
        return ""
    plan = P.read_artifact(pid, ART, d) or {}
    rows = [x for x in plan.get("edits") or [] if x.get("what") != "restore"][-30:]
    if not rows:
        return ""
    fmt = lambda x: (f'- scene "{x["scene"]}" now starts at script line {x["after"]} (was {x["before"]}); the scene '
                     f'"{x.get("label", "")}" before it ends one line earlier' if x["what"] == "cut" else
                     f'- scene "{x["scene"]}", element data-e="{x["e"]}" ("{x.get("label", "")}"): {x["what"]} '
                     f'{json.dumps(x["before"], ensure_ascii=False)} -> {json.dumps(x["after"], ensure_ascii=False)}')
    return ("\n## The creator's hand edits (binding)\nThe creator edited these elements in the Studio's scene editor; "
            "they are already in the current scene plan. Keep them, and keep each element's data-e attribute, unless "
            "the feedback note asks to change that element.\n" + "\n".join(fmt(x) for x in rows) + "\n")


# ---------------------------------------------------------------- named versions

def _vdir(pid, d=None):
    return P.path(pid, "artifacts", "versions", d=d)


def versions(pid, d=None):
    out = []
    for f in sorted(glob.glob(os.path.join(_vdir(pid, d), ART + "-*.json"))):
        v = json.load(open(f, encoding="utf-8"))
        out.append({k: v.get(k) for k in ("n", "name", "by", "at", "scenes", "edits")})
    return sorted(out, key=lambda v: v["n"])


def save_version(pid, name, by=None, d=None):
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:60]
    if not name:
        raise EditError("name")
    plan = _plan(pid, d)
    os.makedirs(_vdir(pid, d), exist_ok=True)
    n = max([v["n"] for v in versions(pid, d)], default=0) + 1
    v = {"n": n, "name": name, "by": by, "at": P.now(), "scenes": len(plan["scenes"]),
         "edits": len(plan.get("edits") or []), "data": plan}
    with open(os.path.join(_vdir(pid, d), f"{ART}-{n:03d}.json"), "w", encoding="utf-8") as f:
        json.dump(v, f, ensure_ascii=False)
    P.event(pid, "scene_version", d=d, n=n, name=name, by=by)
    return {k: v[k] for k in ("n", "name", "by", "at", "scenes", "edits")}


def restore(pid, n, by=None, d=None):
    _at_gate(pid, d)
    f = os.path.join(_vdir(pid, d), f"{ART}-{int(n):03d}.json")
    if not os.path.exists(f):
        raise EditError("no_version")
    v = json.load(open(f, encoding="utf-8"))
    plan = v["data"]
    plan.setdefault("edits", []).append({"scene": None, "e": None, "what": "restore", "before": None,
                                         "after": v["name"], "by": by, "at": P.now(), "label": v["name"]})
    P.write_artifact(pid, ART, plan, d)
    P.event(pid, "scene_restore", d=d, n=v["n"], name=v["name"], by=by)
    return {"n": v["n"], "name": v["name"]}


# ---------------------------------------------------------------- frames with boxes

def frames(pid, d=None):
    """Draw one settled frame per scene with the text boxes (the `scene_frames` job). The folder is the stage's
    newest stills folder, so the gate shows the edited frames too."""
    from .hat import explainer
    plan = prepare(pid, d)
    sid = _stage(pid, d)["id"]
    b = explainer.bundle(pid, plan, d)
    times = explainer.scene_times(pid, plan, d)
    out = P.path(pid, "stills", f"{sid}-{int(time.time())}", d=d)
    os.makedirs(out, exist_ok=True)
    paths, errs, lint_path = explainer._htmlmotion().shots(b, times, out, lint=True)
    try:
        lint = json.load(open(lint_path)) if lint_path and os.path.exists(lint_path) else {}
    except (OSError, ValueError):
        lint = {}
    shots = []
    for i, (t, shot) in enumerate(sorted(lint.items(), key=lambda kv: float(kv[0]))):
        shots.append({"file": os.path.basename(shot.get("file") or ""), "t": float(t),
                      "boxes": [{k: x.get(k) for k in ("e", "scene", "text", "x", "y", "w", "h")}
                                for x in shot.get("boxes") or [] if x.get("e")]})
    with open(os.path.join(out, "boxes.json"), "w", encoding="utf-8") as f:
        json.dump({"at": time.time(), "plan_mtime": os.path.getmtime(P.path(pid, "artifacts", ART + ".json", d=d)),
                   "shots": shots, "errors": errs}, f, ensure_ascii=False)
    return {"folder": out, "frames": len(paths), "errors": errs}


def frames_info(pid, d=None):
    """The newest frames with boxes: {folder, shots, fresh} or None."""
    sid = _stage(pid, d)["id"]
    dirs = sorted(glob.glob(P.path(pid, "stills", sid + "-*", d=d)), key=os.path.getmtime)
    for folder in reversed(dirs):
        f = os.path.join(folder, "boxes.json")
        if os.path.exists(f):
            info = json.load(open(f, encoding="utf-8"))
            art = P.path(pid, "artifacts", ART + ".json", d=d)
            info["fresh"] = os.path.exists(art) and os.path.getmtime(art) <= info.get("plan_mtime", 0) + 0.001
            info["folder"] = folder
            return info
    return None


def view(pid, d=None):
    """Everything the editor shows: scenes with their elements and boxes, the frame size, versions, edits."""
    s = _stage(pid, d)
    plan = prepare(pid, d)
    aspect = P.load(pid, d).get("aspect") or "9:16"
    info = frames_info(pid, d)
    tl, texts = timeline(pid, plan, d)
    shots = (info or {}).get("shots") or []
    scenes = []
    for i, sc in enumerate(plan["scenes"]):
        shot = shots[i] if i < len(shots) else {}
        scenes.append({"id": sc.get("id"), "lines": sc.get("lines"), "elements": elements(sc.get("html") or ""),
                       "frame": os.path.join(info["folder"], shot["file"]) if info and shot.get("file") else None,
                       "boxes": [b for b in shot.get("boxes") or [] if b.get("scene") in (None, sc.get("id"))]})
    return {"stage": s["id"], "gate": P.checkpoint(pid, s["id"], d)["status"] == "awaiting_approval",
            "size": [1080, 1920] if aspect == "9:16" else [1920, 1080], "scenes": scenes,
            "timeline": tl, "line_texts": texts, "fresh": bool(info and info["fresh"]), "versions": versions(pid, d), "edits": (plan.get("edits") or [])[-40:]}
