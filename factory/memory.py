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
import json, re
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


def _v2_recent(d=None, pid=None, n=6):
    """The v2 projects (not the mirrored old rows) as `recent()` records, so the memory sees what the new flow made."""
    out = []
    for f in films("explainer", d, exclude=pid):
        if f["legacy"]:
            continue
        out.append({"prod_id": f["id"], "title": f["title"], "when": f["at"][:10], "stage": "v2", "format": "explainer",
                    "techniques": [f"style.{f['look']}"] if f["kind"] == "style" else [f"grammar.{f['look']}"] if f["look"] else [],
                    "concept": "", "notes": [], "views": None})
    return out[:n]


def brief(con, kinds=("topic",), v2=False, d=None, pid=None):
    """The memory as one compact dict for the prompts (and the plan card). `v2`: the projects/ folders count too, newest
    first, and the film styles the novelty brief governs are left out of `unexplored`."""
    rec = recent(con)
    if v2:
        rec = (_v2_recent(d, pid) + rec)[:12]
    return {"recent": [{k: r[k] for k in ("title", "when", "stage", "techniques", "concept", "views", "notes") if r.get(k)}
                       for r in rec[:8]],
            "overused": overused(rec), "unexplored": [u for u in unexplored(rec, kinds) if not (v2 and u.startswith("style."))],
            **taste(con),
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


# ================================================================ the novelty brief (v2)
# The tables above describe the old `productions` flow. A v2 film lives in projects/<id>/ (proposal, direction board,
# scene plan), so none of it ever reached `recent()`: the proposal agent was told the studio had never used the look it
# had used twice in a row. Everything below reads the project folders and turns the history into a BRIEF computed in code
# (no model, no tokens): the least recently used film styles, the recipe families and cards nobody has used, and what is
# overused. It binds at the proposal gate, the direction board and the scene plan (see `proposal_problems`,
# `plan_problems`); the creator can always name a look in the brief or a gate note, and then the brief yields.
LOOK_WINDOW = 4        # a look used in two of the last four films is off the table; the last film's look always is
PLAN_WINDOW = 3        # mechanisms / camera moves are judged over the last three films that have a scene plan
NEEDED = 6             # recipes handed out per film (two each from the three least-used families)
SAME_FILM = 0.6        # mean palette / camera / mechanism / timing overlap with the previous film that counts as a repeat
GRAMMAR_ASK = re.compile(r"(?:stil|style|look|tarz|grammar)\s*[:=]?\s*(kurzgesagt|vox|whiteboard|3b1b|kinetic|keynote|"
                         r"finance|storytime)\b", re.I)
OFF = re.compile(r"(?:novelty|çeşitlilik|cesitlilik|yenilik)\s*[:=]?\s*(?:off|kapalı|kapali|yok)", re.I)


def _style_ids():
    return [s["id"] for s in capabilities._film_styles()]


def _look_of(proposal, board, legacy):
    """('style', id) | ('grammar', name) | (None, None): the look a film was made in. The board is what was drawn, so it
    wins over the proposal's words; the old `html` / `paper` look packs say nothing about a look and are ignored."""
    styles = set(_style_ids())
    made = [(board or {}).get("style")] + [t[6:] for t in legacy.get("techniques") or [] if str(t).startswith("style.")]
    for s in made:
        if s in styles:
            return "style", s
    look = str((proposal or {}).get("look") or "")
    if not look and (proposal or {}).get("chosen"):
        look = str(next((c.get("look") for c in (proposal or {}).get("concepts") or []
                         if isinstance(c, dict) and c.get("id") == proposal["chosen"]), "") or "")
    sid = look[6:] if look.startswith("style.") else look
    if sid in styles:
        return "style", sid
    if look and look != "auto":
        return "grammar", look
    return None, None


def _recipes_used(plan):
    """Recipe card ids a scene plan names (the designer declares them in each scene's `recipes`)."""
    out = []
    for sc in (plan or {}).get("scenes") or []:
        if isinstance(sc, dict):
            out += [str(x) for x in sc.get("recipes") or [] if x]
    return list(dict.fromkeys(out))


def film(pid, d=None):
    """One finished (or started) v2 film as its usage record, or None when the project says nothing yet."""
    from . import originality
    from .hat import project as P
    try:
        p = P.load(pid, d)
    except Exception:
        return None
    art = lambda n: P.read_artifact(pid, n, d) or {}   # noqa: E731
    prop, board, plan, old = art("proposal"), art("direction"), art("scene_plan"), art("legacy")
    legacy = {}
    if old:
        legacy = jload(old.get("data"), {}) if isinstance(old.get("data"), str) else (old.get("data") or {})
        legacy = legacy.get("recipe") or {}
    kind, look = _look_of(prop, board, legacy)
    scenes = [s for s in plan.get("scenes") or [] if isinstance(s, dict) and not s.get("card")]
    if not (kind or scenes):
        return None
    from . import camera
    return {"id": pid, "num": p.get("num") or 0, "title": p.get("title") or pid, "at": p.get("created_at") or "",
            "legacy": bool(old), "kind": kind, "look": look,
            "mechanisms": [str(s.get("mechanism") or "") for s in scenes],
            "moves": [camera.parse(s.get("camera"))["move"] for s in scenes],
            "recipes": _recipes_used(plan), "sig": originality.signature(plan) if scenes else None}


def films(line="explainer", d=None, exclude=None):
    """Every v2 film of this line that left a trace, newest first."""
    from .hat import project as P
    out = []
    for pid in P.list_ids(d):
        if pid == exclude:
            continue
        try:
            if P.load(pid, d).get("line") != line:
                continue
        except Exception:
            continue
        f = film(pid, d)
        if f:
            out.append(f)
    return sorted(out, key=lambda f: (f["at"], f["num"]), reverse=True)


def _count(items):
    return Counter(x for x in items if x)


def _twice(per_film):
    """Values that show up in two or more of these films (each film counted once)."""
    return [k for k, n in Counter(x for s in per_film for x in set(s) if x).most_common() if n >= 2]


def novelty_brief(con=None, line="explainer", d=None, pid=None, history=None):
    """What the next film of `line` must not repeat and what it should reach for, from the v2 projects' usage:

      styles    film style ids, least recently used first (never used ones first, the newest additions ahead)
      families  recipe families, the least used first (a family is found from `recipes.cards()`, never listed here)
      recipes   cards nobody used (else the rarest), spread over those families: the film must use one of them
      avoid     'style:<id>' / 'grammar:<name>' looks, 'mechanism:<id>' and 'move:<id>' that are overused
      text      the few English lines a prompt carries

    `d` = projects folder, `pid` = a project to leave out of the history (the one being made). No history = an empty
    brief: a studio's first film has nothing to be pushed away from. `con` is kept for the call shape: the old
    `productions` rows are already mirrored in projects/ (artifacts/legacy.json), so they are counted from there."""
    from . import recipes
    hist = films(line, d, exclude=pid) if history is None else history
    if not hist:
        return {"styles": [], "families": [], "recipes": [], "avoid": [], "text": ""}
    looks = [(f["kind"], f["look"]) for f in hist if f["look"]]
    avoid = []
    if looks:
        avoid.append(looks[0])                                          # never the last film's look twice in a row
        avoid += [k for k, n in Counter(looks[:LOOK_WINDOW]).items() if n >= 2]
    avoid = [f"{k}:{v}" for k, v in dict.fromkeys(avoid)]
    planned = [f for f in hist if f["mechanisms"]][:PLAN_WINDOW]
    avoid += [f"mechanism:{m}" for m in _twice([f["mechanisms"][1:-1] for f in planned])][:2]
    avoid += [f"move:{m}" for m in _twice([f["moves"] for f in planned])][:2]
    last_used = {}
    for i, f in enumerate(hist):            # newest first: i = how many films ago
        if f["kind"] == "style":
            last_used.setdefault(f["look"], i)
    offered = [s for s in _style_ids() if f"style:{s}" not in avoid]
    # never used first, the most recently added ahead of the old ones (the owner asked for NEW things), then the ones
    # used longest ago
    styles = ([s for s in reversed(offered) if s not in last_used]
              + sorted((s for s in offered if s in last_used), key=lambda s: -last_used[s]))[:5]
    cards = recipes.cards()
    fam_n, card_n = _count(f for h in hist for f in (c.split(".")[0] for c in h["recipes"])), _count(c for h in hist for c in h["recipes"])
    offered_fams = list(dict.fromkeys(c["family"] for c in cards))
    order = sorted(offered_fams, key=lambda f: (fam_n[f], -offered_fams.index(f)))      # newest family first on a tie
    fams = order[:3]
    picks = {f: sorted((c["id"] for c in cards if c["family"] == f), key=lambda i: card_n[i])[:2] for f in fams}
    rec = [i for pair in zip(*picks.values()) for i in pair] if picks else []
    rec = (rec + [i for f in fams for i in picks[f] if i not in rec])[:NEEDED]
    by_id = {c["id"]: c for c in cards}
    lines = [f"NOVELTY BRIEF (from the last {len(hist)} films; the creator can override by naming a look)"]
    if styles:
        lines.append("Look: choose from the least-used film styles " + ", ".join(f"style.{s}" for s in styles) + ".")
    if avoid:
        lines.append("Off the table for this film: " + ", ".join(avoid) + ".")
    if rec:
        lines.append("Under-used recipes (families " + ", ".join(fams) + "): use at least one, named in a scene's "
                     "`recipes`: " + "; ".join(f"{i} ({by_id[i]['name']['en']})" for i in rec) + ".")
    return {"styles": styles, "families": fams, "recipes": rec, "avoid": avoid, "text": "\n".join(lines)}


# ---------------------------------------------------------------- the creator can always override

def named_look(pid, d=None):
    """What the creator named for this film in the brief or in any gate note: 'off' (no novelty rules), 'style:<id>',
    'grammar:<name>', or None. Reading the words is deliberately generous: a film style's id or name on a word
    boundary counts, so naming a look is always enough to take the look out of the brief's hands."""
    from . import words
    from .hat import project as P
    try:
        p = P.load(pid, d)
    except Exception:
        return None
    texts = [p.get("brief") or ""]
    for s in P.manifest.get(p["line"])["stages"]:
        try:
            cp = P.checkpoint(pid, s["id"], d)
        except Exception:
            continue
        texts += [cp.get("note") or ""] + [h.get("note") or "" for h in cp.get("history") or []]
    text = "\n".join(t for t in texts if t)
    if OFF.search(text):
        return "off"
    g = GRAMMAR_ASK.search(text)
    if g:
        return "grammar:" + g.group(1).lower()
    for st in capabilities._film_styles():
        names = {st["id"], st["id"].replace("_", " "), str(st.get("name") or ""), str(st.get("tr") or "")}
        if any(n and words.has_phrase(text, n) for n in names):
            return "style:" + st["id"]
    return None


def project_brief(pid, d=None, line=None):
    """The brief of one project, frozen on first use (`artifacts/novelty.json`) so the proposal, the direction board
    and the scene plan all answer to the same one even while newer films finish; the creator's override is read fresh
    every time. -> the brief dict, plus {"yielded": "style:x"|"grammar:x"|"off"} when the creator named a look."""
    from .hat import project as P
    cur = P.read_artifact(pid, "novelty", d)
    if not (cur and isinstance(cur.get("brief"), dict)):
        try:
            line = line or P.load(pid, d).get("line") or "explainer"
        except Exception:
            line = line or "explainer"
        cur = {"brief": novelty_brief(None, line, d, pid=pid)}
        try:
            P.write_artifact(pid, "novelty", cur, d)
        except OSError:
            pass
    out = dict(cur["brief"])
    named = named_look(pid, d)
    if named:
        out = {"styles": [named[6:]] if named.startswith("style:") else [], "families": out["families"],
               "recipes": [], "avoid": [], "yielded": named,
               "text": f"NOVELTY BRIEF yields: the creator named the look ({named}); the look is theirs and no "
                       f"novelty rule is enforced on this film."}
    return out


def novelty_text(p):
    """The brief's lines for a stage brief that includes them ({{include:factory.memory:novelty_text}}); "" without."""
    try:
        return project_brief(p["id"])["text"]
    except Exception:
        return ""


def _look_id(look):
    look = str(look or "")
    return look[6:] if look.startswith("style.") else look


def proposal_problems(data, brief):
    """The proposal gate: the chosen look must be one of the brief's least-used film styles (never an off-the-table
    one). Empty brief or a yielded brief (the creator named a look) = nothing to refuse."""
    if not brief or brief.get("yielded") or not brief.get("styles"):
        return []
    chosen = str((data or {}).get("chosen") or "")
    look = (data or {}).get("look") or next((c.get("look") for c in (data or {}).get("concepts") or []
                                              if isinstance(c, dict) and str(c.get("id")) == chosen), "")
    if not look or _look_id(look) in brief["styles"]:
        return []
    return [f"the chosen look '{look}' repeats the studio's recent films or is not one of this film's least-used "
            f"styles: choose {', '.join('style.' + s for s in brief['styles'])} (the bold concept must use one). "
            f"Only the creator can name another look, in the brief or a gate note"]


def plan_problems(plan, brief, history=None, pid=None, d=None):
    """The scene-plan gate: at least one of the required under-used recipes is named in a scene's `recipes`, and the
    plan does not repeat the previous film's signature (palette, camera order, mechanism order, timing)."""
    from . import originality
    if not brief or brief.get("yielded"):
        return []
    out = []
    need = brief.get("recipes") or []
    if need and not set(need) & set(_recipes_used(plan)):
        out.append("the scene plan uses none of this film's required under-used recipes (" + ", ".join(need) + "): "
                   "name at least one in a scene's `recipes` and build that scene with its card")
    hist = films("explainer", d, exclude=pid) if history is None else history
    prev = next((f for f in hist if f.get("sig")), None)
    if prev and brief.get("text"):
        sim, parts = originality.similarity(originality.signature(plan), prev["sig"])
        core = sum(parts[k] for k in ("palette", "cameras", "mechanisms", "seconds")) / 4
        if core >= SAME_FILM:
            same = ", ".join(k for k in ("palette", "cameras", "mechanisms", "seconds") if parts[k] >= 0.6)
            out.append(f"the plan repeats the previous film's signature ('{prev['title']}': {same}): change the "
                       "mechanism order, the camera moves and their lengths")
    return out
