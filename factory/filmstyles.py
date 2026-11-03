"""The film style library: our own style cards (look, type, motion, sound, what to avoid, palette, fonts; TR and EN)
from data/film_styles.json, each with a preview frame drawn by the studio's motion engine from styles/<id>.json (a
small hand-written scene, rendered headless once: no Claude and no ElevenLabs cost) and finished with the style's own
film post (grain, mono, vignette...). Frames are committed in styles/previews/<id>.jpg.

At a proposal gate of a line whose proposal agent picks a look from the catalogue (explainer, animation), the note
"stil: <id>" / "style: <id>" sets the look to that style directly, without re-running the agent; the gate stays.
"""
import json, os, re, subprocess, sys

from . import capabilities
from .config import ROOT, FFMPEG

DIR = os.path.join(ROOT, "styles")
PREVIEWS = os.path.join(DIR, "previews")
WORK = os.path.join(ROOT, "work", "styles")
SECONDS_AT = 2.4      # where the preview frame is taken: every scene has settled by then
HELPER = ("const E = (css, html) => { const d = document.createElement('div'); d.style.cssText = 'position:absolute;' + css;"
          " if (html) d.innerHTML = html; root.appendChild(d); return d; };\n")
PICK = re.compile(r"^\s*(?:stil|style)\s*[:=]\s*([\w-]+)\s*$", re.I)


def ids():
    return [s["id"] for s in capabilities._film_styles()]


def get(sid):
    return next((s for s in capabilities._film_styles() if s["id"] == sid), None)


def preview_file(sid):
    return os.path.join(PREVIEWS, sid + ".jpg")


def preview_url(sid):
    f = preview_file(sid)
    return f"/media/filmstyles/{sid}.jpg?v={int(os.path.getmtime(f))}" if os.path.exists(f) else None


def card(s, ui="tr"):
    """One style as the Studio shows it, in the UI language."""
    c = s.get("card") or {}
    words = c.get(ui) or c.get("tr") or {}
    return {"id": s["id"], "cap": "style." + s["id"], "name": s.get("tr") if ui == "tr" and s.get("tr") else s["name"],
            "look": words.get("look", ""), "type": words.get("type", ""), "motion": words.get("motion", ""),
            "sound": words.get("sound", ""), "avoid": words.get("avoid", ""),
            "palette": c.get("palette") or [], "fonts": c.get("fonts") or [], "preview": preview_url(s["id"])}


def cards(ui="tr"):
    return [card(s, ui) for s in capabilities._film_styles()]


def _bundle(sid):
    sc = json.load(open(os.path.join(DIR, sid + ".json"), encoding="utf-8"))
    from .catalog import PALETTE
    dur = float(sc.get("seconds") or 3)
    return {"palette": PALETTE, "global_css": "", "words": [], "duration": dur, "w": 1080, "h": 1920, "lang": "tr",
            "captions": {}, "scenes": [{"id": "style", "start": 0, "end": dur, "hide_captions": True, "lines_t": [],
                                        "html": "", "css": sc.get("css") or "", "js": HELPER + (sc.get("js") or "")}]}, dur


def render_preview(sid, force=False):
    """Draw the style's scene and keep one frame with the style's post on it. -> path of the jpg."""
    out = preview_file(sid)
    if os.path.exists(out) and not force:
        return out
    s = get(sid)
    if not s or not os.path.exists(os.path.join(DIR, sid + ".json")):
        raise ValueError(f"no style scene for '{sid}'")
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(PREVIEWS, exist_ok=True)
    b, dur = _bundle(sid)
    bpath, clip = os.path.join(WORK, sid + ".json"), os.path.join(WORK, sid + ".mp4")
    json.dump(b, open(bpath, "w", encoding="utf-8"), ensure_ascii=False)
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import htmlmotion
    r = htmlmotion._node(bpath, clip, dur, ["--opaque", "--scale=0.5"], 24)
    if r.returncode or not os.path.exists(clip):
        raise RuntimeError(f"style {sid}: " + (r.stderr or "")[-300:])
    vf = ",".join(x for x in (htmlmotion.post_vf(s.get("post"), preview=True), "scale=540:-2") if x)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", str(min(SECONDS_AT, dur - 0.1)), "-i", clip, "-vf", vf,
                    "-frames:v", "1", "-q:v", "3", out], check=True)
    return out


def render_all(force=False):
    done, failed = [], []
    for sid in ids():
        try:
            render_preview(sid, force)
            done.append(sid)
        except Exception as e:
            failed.append(f"{sid}: {str(e)[:160]}")
            print(failed[-1], flush=True)
    return done, failed


def pick(note):
    """'stil: noir' / 'style: noir' -> 'noir' when it names a style, else None."""
    m = PICK.match(note or "")
    return m.group(1).lower().replace("-", "_") if m and get(m.group(1).lower().replace("-", "_")) else None


def picks_style(stage):
    """Does this stage choose a look from the catalogue (a proposal agent with the catalog tool)?"""
    return stage.get("artifact") == "proposal" and "catalog" in (stage.get("tools") or [])


def apply(pid, sid, style_id, by=None, d=None):
    """Set the proposal's look (and the chosen concept's) to the style. The stage keeps waiting at its gate."""
    from .hat import project as P
    prop = P.read_artifact(pid, "proposal", d)
    if not prop:
        raise P.GateError("no proposal yet")
    cap = "style." + style_id
    prop["look"] = cap
    for c in prop.get("concepts") or []:
        if c.get("id") == prop.get("chosen"):
            c["look"] = cap
    P.write_artifact(pid, "proposal", prop, d)
    P.decision(pid, "look", cap, reason="style picked at the gate", by=by, d=d)
    P.event(pid, "style", d=d, stage=sid, style=style_id, by=by)
    return prop


if __name__ == "__main__":
    d, f = render_all(force=True)
    print(f"{len(d)} previews, {len(f)} failed")
