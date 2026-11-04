"""Motion recipe cards and the shotbook (t510): our own library of about a hundred moves the motion engine can make.

A card says when to use a move, what it takes, how it is timed, what goes wrong with it, and carries a short demo
scene. The cards live in motion/recipes/<family>.yaml (written by us, in Turkish and English). Scene plans refer to
cards by id (a scene's "recipes": ["text.rise_mask", ...]); the designer of that scene then gets the full cards.

Demos are drawn by the studio's own motion engine (no Claude, no credits): the job "recipe_demos" renders them into
work/recipes/<id>.mp4, and the shotbook page in the Studio plays them.
"""
import json, os, sys, time

import yaml

from .config import ROOT

SRC = os.path.join(ROOT, "motion", "recipes")
DIR = os.path.join(ROOT, "work", "recipes")
FAMILIES = {
    "text": {"tr": "Yazı", "en": "Text"},
    "annotate": {"tr": "İşaretleme", "en": "Annotation"},
    "data": {"tr": "Veri ve bilim", "en": "Data and science"},
    "camera": {"tr": "Kamera", "en": "Camera"},
    "transition": {"tr": "Geçiş", "en": "Transition"},
    "setpiece": {"tr": "Büyük sahne", "en": "Set piece"},
    "character": {"tr": "Karakter", "en": "Character"},
    "living": {"tr": "Canlı dünya", "en": "Living world"},
    "rhythm": {"tr": "Ritim", "en": "Rhythm"},
}
FIELDS = ("id", "name", "use", "call", "timing", "pitfalls", "seconds", "demo")
LANGS = ("tr", "en")
# Every demo starts with this helper: D(html, css) puts a positioned div on the stage. It is a demo shorthand, the
# designer's own scenes build their elements as they like.
PRELUDE = ("const D = (html, css = '') => { const e = document.createElement('div'); e.innerHTML = html; "
           "e.style.cssText = 'position:absolute;' + css; root.appendChild(e); return e; };\n")

_cache = {"key": None, "cards": None}


def _key():
    try:
        return tuple((f, os.path.getmtime(os.path.join(SRC, f))) for f in sorted(os.listdir(SRC)) if f.endswith(".yaml"))
    except OSError:
        return ()


def problems(cards):
    """What is wrong with a list of cards (missing fields, both languages, unknown family, repeated ids)."""
    out, seen = [], set()
    for c in cards:
        cid = c.get("id") or "?"
        for f in FIELDS:
            if not c.get(f):
                out.append(f"{cid}: no {f}")
        fam = cid.split(".")[0]
        if fam not in FAMILIES or c.get("family") != fam:
            out.append(f"{cid}: family {c.get('family')!r} does not match the id")
        for f in ("name", "use", "timing", "pitfalls"):
            if isinstance(c.get(f), dict) and any(not c[f].get(lang) for lang in LANGS):
                out.append(f"{cid}: {f} needs tr and en")
        if cid in seen:
            out.append(f"{cid}: repeated id")
        seen.add(cid)
    return out


def cards():
    """Every card, in family order then file order."""
    k = _key()
    if _cache["key"] != k:
        out = []
        for fam in FAMILIES:
            p = os.path.join(SRC, fam + ".yaml")
            if os.path.exists(p):
                for c in yaml.safe_load(open(p, encoding="utf-8")) or []:
                    out.append({**c, "family": fam})
        _cache.update(key=k, cards=out)
    return _cache["cards"]


def get(cid):
    return next((c for c in cards() if c["id"] == cid), None)


def unknown(ids):
    have = {c["id"] for c in cards()}
    return [i for i in ids or [] if i not in have]


def _lang(lang):
    return lang if lang in LANGS else "en"


def index(lang="en", family=None):
    """One line per card for a planner: id, name and when to use it."""
    lang = _lang(lang)
    rows = []
    for fam, names in FAMILIES.items():
        if family and fam != family:
            continue
        cs = [c for c in cards() if c["family"] == fam]
        if cs:
            rows.append(f"[{fam}] {names[lang]}")
            rows += [f"  {c['id']} — {c['name'][lang]}: {c['use'][lang]}" for c in cs]
    return "\n".join(rows)


def card_text(ids, lang="en"):
    """The full cards a designer gets for the recipes a scene plan names (unknown ids are skipped)."""
    lang = _lang(lang)
    out = []
    for cid in dict.fromkeys(ids or []):
        c = get(cid)
        if not c:
            continue
        pit = "; ".join(c["pitfalls"][lang])
        out.append(f"RECIPE {c['id']} — {c['name'][lang]}\n  use: {c['use'][lang]}\n  call: {c['call']}\n"
                   f"  timing: {c['timing'][lang]}\n  pitfalls: {pit}\n  example ({c['seconds']} s, D(html, css) = a positioned div):\n"
                   + "\n".join("    " + ln for ln in c["demo"].strip().splitlines()))
    return "\n\n".join(out)


# ---------------------------------------------------------------- demos

def demo_file(cid):
    return os.path.join(DIR, cid + ".mp4")


def bundle(cid):
    """A one-scene bundle that plays the card's demo on the catalog palette."""
    from . import catalog
    c = get(cid)
    if not c:
        raise KeyError(cid)
    dur = float(c["seconds"])
    return {"palette": catalog.PALETTE, "global_css": "", "words": [], "duration": dur, "w": 1080, "h": 1920,
            "lang": "en", "captions": {}, **({"bpm": c["bpm"], "beat0": 0} if c.get("bpm") else {}),
            **({"math": True} if "FX.math" in c["demo"] or "FX.eqSteps" in c["demo"] else {}),
            "scenes": [{"id": "demo", "start": 0, "end": dur, "hide_captions": True, "lines_t": [], "html": "",
                        "css": c.get("css") or catalog.BG, "js": PRELUDE + c["demo"]}]}


def _write_bundle(cid):
    from . import catalog
    os.makedirs(DIR, exist_ok=True)
    catalog._picture()        # the stand-in picture some demos show (work/catalog/picture.png)
    p = os.path.join(DIR, cid + ".json")
    json.dump(bundle(cid), open(p, "w"))
    return p


def _hm():
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import htmlmotion
    return htmlmotion


def render(cid, force=False):
    """Render one card's demo (0.4 scale, 24 fps, silent). -> path"""
    out = demo_file(cid)
    if os.path.exists(out) and not force:
        return out
    bp = _write_bundle(cid)
    r = _hm()._node(bp, out, float(get(cid)["seconds"]), ["--opaque", "--scale=0.4"], 24)
    if r.returncode or not os.path.exists(out):
        raise RuntimeError(f"recipe {cid}: " + (r.stderr or "")[-300:])
    return out


def render_all(ids=None, force=False):
    done, failed = [], []
    for cid in ids or [c["id"] for c in cards()]:
        try:
            render(cid, force)
            done.append(cid)
        except Exception as e:
            failed.append(f"{cid}: {str(e)[:120]}")
            print(failed[-1], flush=True)
    return done, failed


def check(cid):
    """The page errors of a card's demo and a still from its middle (free, a few seconds). -> (pngs, errors)"""
    import tempfile
    bp = _write_bundle(cid)
    out = tempfile.mkdtemp(dir=DIR)
    return _hm().shots(bp, [round(float(get(cid)["seconds"]) * 0.7, 2)], out)


def missing():
    return [c["id"] for c in cards() if not os.path.exists(demo_file(c["id"]))]


def listing(lang="en"):
    """The shotbook: every card with its family and its demo clip if it has been rendered."""
    lang = _lang(lang)
    out = []
    for c in cards():
        f = demo_file(c["id"])
        out.append({"id": c["id"], "family": c["family"], "family_name": FAMILIES[c["family"]][lang],
                    "name": c["name"][lang], "use": c["use"][lang], "call": c["call"], "timing": c["timing"][lang],
                    "pitfalls": c["pitfalls"][lang], "seconds": c["seconds"], "demo_js": c["demo"].strip(),
                    "demo": ("/media/work/recipes/" + os.path.basename(f) + f"?v={int(os.path.getmtime(f))}")
                            if os.path.exists(f) else None})
    return {"cards": out, "families": [{"id": k, "name": v[lang]} for k, v in FAMILIES.items()],
            "missing": len(missing())}


if __name__ == "__main__":
    if sys.argv[1:2] == ["check"]:
        bad = 0
        for cid in sys.argv[2:] or [c["id"] for c in cards()]:
            t0 = time.time()
            _, errs = check(cid)
            bad += bool(errs)
            print(f"{cid}: {'OK' if not errs else errs} ({time.time() - t0:.1f} s)", flush=True)
        sys.exit(1 if bad else 0)
    d, f = render_all(sys.argv[1:] or None, force=bool(sys.argv[1:]))
    print(f"{len(d)} demos, {len(f)} failed")
