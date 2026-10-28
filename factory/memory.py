"""Studio memory: what the factory has already made, how it did, and what the creator chose, so every new plan is
pushed AWAY from repeating itself and TOWARD what works for this creator.

Nothing is stored twice: the memory is read from the factory's own tables every time
  productions  each video's recipe (techniques, direction), its motion concept, its stage, the creator's revision /
               rejection notes
  posts        real numbers (views, likes, comments) per published video
  plans        which of the three treatments the creator picked, and which they passed over (taste)
  playbook     lessons the creator saved (likes / dislikes)
and condensed into one brief for the planner / art director, the critic and the motion designer:
  recent           the last videos as recipes (what was made, how, how it did)
  overused         techniques / film styles / story shapes used again and again lately -> avoid unless needed
  unexplored       techniques the studio has not used yet -> candidates for a bold option
  picked / passed  techniques in treatments the creator chose vs. the ones they skipped
  performance      the best and the weakest published videos with their techniques (real numbers only)
  dislikes         rejection reasons and saved dislikes
"""
import json
from collections import Counter

from . import capabilities
from .store import jload

DEFAULTS = {"sound.event_sfx", "voice.tighten", "sound.music_bed", "captions.energy"}   # house defaults: fine to repeat
WINDOW = 6          # "lately" = the last six videos


def _recipe_techs(d):
    techs = list(capabilities.techniques(d))
    if not techs:     # videos made before recipes existed still count, by their look
        look = d.get("look_pack") or ("footage" if d.get("shots") else None)
        if d.get("grammar"):
            techs.append(f"legacy.grammar.{d['grammar']}")
        if look:
            techs.append(f"legacy.look.{look}")
    return techs


def views_by_prod(con):
    out = {}
    try:
        from . import tracking
        for p in tracking.posts(con):
            v = (p.get("latest") or {}).get("views")
            if p.get("prod_id") and v is not None:
                out[p["prod_id"]] = max(out.get(p["prod_id"], 0), v)
    except Exception:
        pass
    return out


def recent(con, n=12):
    """The last n productions that got past the idea stage (or were rejected), newest first, as compact recipes."""
    try:
        rows = con.execute("SELECT prod_id, created_at, format, title, stage, data, history FROM productions "
                           "ORDER BY prod_id DESC LIMIT ?", (n * 3,)).fetchall()
    except Exception:
        return []
    views = views_by_prod(con)
    out = []
    for r in rows:
        d = jload(r["data"], {}) or {}
        hist = jload(r["history"], []) or []
        if r["stage"] == "idea" and not any(h.get("event") == "onay" for h in hist):
            continue        # an unapproved idea is not something the studio "made"
        techs = _recipe_techs(d)
        notes = [h.get("detail") for h in hist if h.get("event") in ("revizyon", "reddedildi", "düzenleme planı") and h.get("detail")]
        out.append({"prod_id": r["prod_id"], "title": r["title"], "when": (r["created_at"] or "")[:10], "stage": r["stage"],
                    "format": r["format"], "techniques": [t for t in techs if t not in DEFAULTS],
                    "concept": ((d.get("motion") or {}).get("concept") or (d.get("direction") or {}).get("concept")
                                or (d.get("recipe") or {}).get("direction") or "")[:180],
                    "notes": notes[-3:], "views": views.get(r["prod_id"])})
        if len(out) >= n:
            break
    return out


def taste(con, n=20):
    """Techniques of the treatments the creator picked vs. the ones they passed over (from started plans)."""
    picked, passed = Counter(), Counter()
    try:
        rows = con.execute("SELECT plan FROM plans WHERE status='started' ORDER BY plan_id DESC LIMIT ?", (n,)).fetchall()
    except Exception:
        return {"picked": [], "passed": []}
    for r in rows:
        p = jload(r["plan"], {}) or {}
        tr = p.get("treatments") or []
        ch = p.get("chosen", 0)
        for i, t in enumerate(tr):
            (picked if i == ch else passed).update(x for x in t.get("techniques") or [] if x not in DEFAULTS)
    return {"picked": [k for k, _ in picked.most_common(10) if picked[k] > passed.get(k, 0)],
            "passed": [k for k, _ in passed.most_common(10) if passed[k] > picked.get(k, 0)]}


def dislikes(con, n=10):
    out = []
    try:
        out += [r["lesson"] for r in con.execute("SELECT lesson FROM playbook WHERE source='dislike' ORDER BY id DESC LIMIT ?", (n,))]
        for r in con.execute("SELECT history FROM productions WHERE stage='rejected' ORDER BY prod_id DESC LIMIT ?", (n,)):
            for h in jload(r["history"], []) or []:
                if h.get("event") == "reddedildi" and h.get("detail"):
                    out.append(h["detail"])
    except Exception:
        pass
    return [x[:160] for x in out][:n]


def overused(rec, window=WINDOW):
    """Techniques used in half or more of the last `window` videos, plus any film style / story shape used in two of
    the last three (a style twice in a row already reads as 'the same video again')."""
    last = rec[:window]
    c = Counter(t for r in last for t in set(r["techniques"]))
    out = {t for t, k in c.items() if k >= max(2, (len(last) + 1) // 2)}
    c3 = Counter(t for r in rec[:3] for t in set(r["techniques"]))
    for t, k in c3.items():
        cap = capabilities.CAPS.get(t, {})
        if k >= 2 and (cap.get("style") or cap.get("shape") or t.startswith("legacy.")):
            out.add(t)
    return sorted(out)


def unexplored(rec, kinds=("topic",), limit=12):
    used = {t for r in rec for t in r["techniques"]}
    out = [k for k, v in capabilities.CAPS.items() if not v.get("always") and k not in used and k not in DEFAULTS
           and any(x in v["kinds"] for x in kinds)]
    # spread across areas so the list suggests different kinds of novelty, not twelve film styles
    by = {}
    for k in out:
        by.setdefault(capabilities.CAPS[k]["area"], []).append(k)
    mixed = []
    while any(by.values()) and len(mixed) < limit:
        for a in list(by):
            if by[a]:
                mixed.append(by[a].pop(0))
    return mixed[:limit]


def performance(rec):
    seen = [r for r in rec if r.get("views") is not None]
    if len(seen) < 2:
        return {}
    seen.sort(key=lambda r: r["views"], reverse=True)
    pick = lambda r: {"title": r["title"], "views": r["views"], "techniques": r["techniques"][:8]}  # noqa: E731
    return {"best": [pick(r) for r in seen[:3]], "weakest": [pick(r) for r in seen[-2:]]}


def brief(con, kinds=("topic",)):
    """The memory as one compact dict for the prompts (and the plan card)."""
    rec = recent(con)
    return {"recent": [{k: r[k] for k in ("title", "when", "stage", "techniques", "concept", "views", "notes") if r.get(k)}
                       for r in rec[:8]],
            "overused": overused(rec), "unexplored": unexplored(rec, kinds), **taste(con),
            "performance": performance(rec), "dislikes": dislikes(con), "made": len(rec)}


def novelty(techs, mem):
    """0..1: how different a treatment is from the studio's recent videos (1 = nothing like them). Average distance
    (1 - Jaccard) to the last six recipes, minus a penalty for every overused technique it leans on."""
    mine = {t for t in techs or [] if t not in DEFAULTS}
    rec = [set(r.get("techniques") or []) for r in (mem or {}).get("recent", [])[:WINDOW]]
    if not mine:
        return 0.0
    if not rec:
        return 1.0
    dist = [1 - len(mine & r) / max(1, len(mine | r)) for r in rec]
    pen = 0.12 * len(mine & set((mem or {}).get("overused") or []))
    return round(max(0.0, min(1.0, sum(dist) / len(dist) - pen)), 2)


def summary_tr(mem):
    """One Turkish line for the plan card: what the memory pushed away from / toward."""
    if not mem or not mem.get("made"):
        return "Hafıza boş: stüdyonun ilk videoları, her yön serbest."
    lab = lambda ids: ", ".join(capabilities.CAPS[i]["tr"] for i in ids if i in capabilities.CAPS)  # noqa: E731
    bits = [f"son {min(mem['made'], WINDOW)} video incelendi"]
    if mem.get("overused"):
        bits.append("çok kullanılan: " + (lab(mem["overused"][:4]) or ", ".join(mem["overused"][:4])))
    if mem.get("picked"):
        bits.append("senin seçtiklerin: " + lab(mem["picked"][:3]))
    if (mem.get("performance") or {}).get("best"):
        bits.append(f"en iyi: “{mem['performance']['best'][0]['title']}” ({mem['performance']['best'][0]['views']} izlenme)")
    return " · ".join(bits)


def designer_note(con, n=8):
    """Recent motion concepts, so the motion designer does not rebuild last week's video."""
    rec = [r for r in recent(con, n) if r.get("concept")]
    if not rec:
        return ""
    return ("STUDIO MEMORY (your own recent designs; do NOT repeat their composition, metaphor or opening move unless "
            "this creator's direction asks for continuity): " + json.dumps([{"title": r["title"], "concept": r["concept"]}
                                                                           for r in rec], ensure_ascii=False))
