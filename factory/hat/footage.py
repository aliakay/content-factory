"""The travel vlog line's code side: the creator's own clips, cut by the factory's footage engine.

The footage engine (factory/productions.py: ideas on real clips, factory/artdirector.py: the edit, bin/cinecut.py
through factory/engines.py: the render, qa/soundqa: the checks) works on a production row. Each project of this line
keeps one such row per idea concept (project["prods"]); the stages below drive the chosen one and copy what it made
into the project's artifacts, so the board shows it and the gates decide it.

  idea        3 ideas on real clips (one LLM call with research), their voice + music estimate -> proposal (gate)
  scene_plan  the art director's edit + a free preview render -> cut_plan (gate)
  assets      the voice (when narrated) and the music inside the approved budget, then a preview -> assets (gate)
  edit        nothing to decide by hand: the art director's edit stands; the sound plan is recorded
  compose     final render + technical, visual and sound QA + covers -> render
  publish     the idea's post copy -> publish (gate)
"""
import json, os, re, shutil

from ..config import ROOT
from . import project as P
from .explainer import remaining_budget

FORMAT = "cinematic_calm"           # the default footage format; a project may name another in project["format"]
FORMATS = ("cinematic_calm", "story_vo", "unreal_places", "travel_facts", "long_compilation")
LETTERS = "ABCDE"


def _con():
    from ..store import connect
    return connect()


def _ui(p):
    return p.get("ui_lang") if p.get("ui_lang") in ("tr", "en") else "tr"


def _rel(path):
    return os.path.relpath(path if os.path.isabs(path) else os.path.join(ROOT, path), ROOT)


def chosen_prod(pid, d=None):
    """The production row of the concept the creator approved."""
    p = P.load(pid, d)
    if p.get("current_prod") in (p.get("prods") or []):      # a line that replaces its row on feedback (episode)
        return p["current_prod"]
    prop = P.read_artifact(pid, "proposal", d) or {}
    c = next((c for c in prop.get("concepts") or [] if c["id"] == prop.get("chosen")), None)
    if not c or not c.get("prod_id"):
        raise P.GateError("no chosen idea yet")
    if c["prod_id"] not in (p.get("prods") or []):
        raise P.GateError("the chosen idea does not belong to this project")
    return c["prod_id"]


def _pick(note, concepts):
    """A feedback note that only names a concept ("B", "2", "B'yi seç", "take the second") picks it."""
    n = (note or "").strip().lower()
    for i, c in enumerate(concepts):
        if re.fullmatch(rf"\W*({c['id'].lower()}|{i + 1})\W*(\w+\W*){{0,3}}", n):
            return c["id"]
    return None


def _concept(con, letter, prod_id):
    from .. import productions as PR
    row = PR.get(con, prod_id)
    dd = row["data"]
    v = PR.voice_estimate(con, dd) if (dd.get("voice") or {}).get("lines") else None
    m = PR.music_estimate(con, row)
    shots = dd.get("shots") or []
    return {"id": letter, "prod_id": prod_id, "title": row["title"], "hook": dd.get("hook") or "",
            "structure": dd.get("logline") or "", "look": row["format"], "why": dd.get("why") or "",
            "key_frame": (shots[0].get("shows") if shots else "") or "", "shots": len(shots),
            "places": sorted({s.get("place") for s in shots if s.get("place")}),
            "voice": {"use": bool(v), "lines": (dd.get("voice") or {}).get("lines") or []},
            "music": {"use": True, "prompt": m["prompt"], "seconds": m["seconds"]},
            "cost": {"credits": round((v or {}).get("credits", 0) + m["credits"]),
                     "lines": ([{"label": "voice", "credits": round(v["credits"])}] if v else []) +
                              [{"label": "music", "credits": round(m["credits"])}]}}


def idea(pid, s, note=None, d=None):
    """Three ideas on the creator's real clips. A note that names one of them picks it without a new call."""
    from .. import productions as PR
    con, p = _con(), P.load(pid, d)
    old = P.read_artifact(pid, "proposal", d) or {}
    if note and old.get("concepts") and _pick(note, old["concepts"]):
        old["chosen"] = _pick(note, old["concepts"])
        c = next(c for c in old["concepts"] if c["id"] == old["chosen"])
        old.update(seconds=c["music"]["seconds"], voice=c["voice"], music=c["music"], cost=c["cost"],
                   summary={"tr": f"{c['id']} seçildi: {c['title']}.", "en": f"Picked {c['id']}: {c['title']}."}[_ui(p)])
        return {"artifact": old, "summary": old["summary"]}
    fmt = p.get("format") if p.get("format") in FORMATS else FORMAT
    brief = p.get("brief") or ""
    if note:
        brief += f"\nThe creator's note on the previous ideas: {note}"
    ids, meta = PR.generate(con, fmt, n=3, brief=brief, aspect=p.get("aspect", "9:16"), channel_id=p.get("channel"),
                            lang=p.get("video_lang"))
    if not ids:
        raise P.GateError("no idea could be built on the clips (is an album synced?)")
    p = P.load(pid, d)
    p["prods"] = (p.get("prods") or []) + list(ids)
    P.save(p, d)
    concepts = [_concept(con, LETTERS[i], pr) for i, pr in enumerate(ids[:len(LETTERS)])]
    c = concepts[0]
    summary = {"tr": f"{len(concepts)} fikir: " + " · ".join(f"{x['id']}) {x['title']}" for x in concepts) +
                     f". A seçili; başka birini istersen geri bildirime harfini yaz. Tahmini {c['cost']['credits']} kredi.",
               "en": f"{len(concepts)} ideas: " + " · ".join(f"{x['id']}) {x['title']}" for x in concepts) +
                     f". A is picked; to take another, write its letter as feedback. About {c['cost']['credits']} credits."
               }[_ui(p)]
    art = {"concepts": concepts, "chosen": c["id"], "seconds": c["music"]["seconds"], "look": fmt,
           "voice": c["voice"], "music": c["music"], "cost": c["cost"], "summary": summary}
    usd = float((meta or {}).get("cost_usd") or 0)
    return {"artifact": art, "summary": summary, "cost": {"usd": usd}}


def scene_plan(pid, s, note=None, d=None):
    """The art director's edit on the chosen idea, and a free preview render of it (no credits)."""
    from .. import productions as PR
    con, p = _con(), P.load(pid, d)
    prod = chosen_prod(pid, d)
    row = PR.direct(con, prod, note or "")
    dst = PR.preview(con, prod)
    row = PR.get(con, prod)
    out = P.path(pid, "renders", "preview.mp4", d=d)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    shutil.copy2(dst, out)
    dr = row["data"].get("direction") or {}
    _, total, starts, warn = PR.timeline(con, row)
    shots = [{"clip": sh.get("clip_id"), "in": sh.get("in"), "out": sh.get("out"), "text": sh.get("text") or "",
              "shows": sh.get("shows") or ""} for sh in row["data"].get("shots") or []]
    summary = {"tr": f"Kurgu hazır: {len(shots)} plan, {total:.0f} sn. Önizlemeyi izle (ses ve müzik sonraki adımda).",
               "en": f"Edit ready: {len(shots)} shots, {total:.0f} s. Watch the preview (voice and music come next)."}[_ui(p)]
    art = {"concept": dr.get("concept") or "", "shots": shots, "duration": round(total, 1), "warnings": warn,
           "preview": _rel(out), "prod_id": prod, "summary": summary}
    return {"artifact": art, "summary": summary}


def assets(pid, s, note=None, d=None):
    """Voice (when the idea is narrated) and music, each inside what is left of the approved budget; then a preview."""
    from .. import productions as PR
    con, p = _con(), P.load(pid, d)
    prod = chosen_prod(pid, d)
    row = PR.get(con, prod)
    spent, voice = 0.0, None
    if PR.voice_text(row["data"]):
        path, cost = PR.make_voice(con, prod, approved=remaining_budget(pid, d))
        spent += cost
        voice = {"file": _rel(path), "credits": round(cost)}
    prop = P.read_artifact(pid, "proposal", d) or {}
    left = max(0, remaining_budget(pid, d) - round(spent))
    mpath, mcost = PR.make_music(con, prod, approved=left, prompt=(prop.get("music") or {}).get("prompt"))
    spent += mcost
    dst = PR.preview(con, prod)
    out = P.path(pid, "renders", "preview.mp4", d=d)
    shutil.copy2(dst, out)
    total = round(spent)
    summary = {"tr": f"{'Ses ve müzik' if voice else 'Müzik'} hazır ({total} kredi). Önizlemeyi izle.",
               "en": f"{'Voice and music' if voice else 'Music'} ready ({total} credits). Watch the preview."}[_ui(p)]
    art = {"voice": voice, "music": {"file": _rel(mpath), "credits": round(mcost)}, "preview": _rel(out),
           "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"credits": total}}


def edit(pid, s, note=None, d=None):
    P.decision(pid, "edit", "the art director's edit stands; sound as mixed by the engine", d=d)
    return {"artifact": {"sound": {"level": "full"}, "summary": "", "note": note}, "summary": ""}


def compose(pid, s, note=None, d=None):
    """Final render with the engine's QA, copied into the project."""
    from .. import productions as PR
    con, p = _con(), P.load(pid, d)
    prod = chosen_prod(pid, d)
    dst = PR.render(con, prod)
    row = PR.get(con, prod)
    out = P.path(pid, "renders", "final.mp4", d=d)
    shutil.copy2(dst, out)
    covers = []
    for c in sorted(f for f in os.listdir(os.path.dirname(dst)) if f.startswith("cover") and f.endswith(".jpg")):
        covers.append(_rel(shutil.copy2(os.path.join(os.path.dirname(dst), c), P.path(pid, "renders", c, d=d))))
    qa = row.get("qa") or {}
    probs = (qa.get("technical") or {}).get("problems") or []
    summary = ({"tr": "Final hazır; kontroller temiz.", "en": "Final ready; checks clean."} if qa.get("pass") else
               {"tr": f"Final hazır; {len(probs)} teknik bulgu, görsel kontrolü oku.",
                "en": f"Final ready; {len(probs)} technical findings, read the visual check."})[_ui(p)]
    art = {"final": _rel(out), "qa": qa, "covers": covers, "summary": summary}
    return {"artifact": art, "summary": summary}


def publish(pid, s, note=None, d=None):
    """The idea's post copy (the idea call wrote it with the edit in mind)."""
    from .. import productions as PR
    con, p = _con(), P.load(pid, d)
    row = PR.get(con, chosen_prod(pid, d))
    post = row["data"].get("post") or {}
    if isinstance(post, str):
        post = json.loads(post or "{}")
    tags = post.get("hashtags") or []
    tags = tags.split() if isinstance(tags, str) else list(tags)
    caption = post.get("caption") or row["title"]
    summary = {"tr": "Açıklama ve etiketler hazır; müzik uygulama içinden eklenmez, video kendi müziğiyle hazır.",
               "en": "Caption and hashtags ready; the video carries its own music."}[_ui(p)]
    art = {"caption": caption, "hashtags": tags, "notes": post.get("music") or "", "summary": summary}
    return {"artifact": art, "summary": summary}
