"""The series episode line's code side: one episode of a series whose book and character sheets are ready
(the Series page writes the bible and casts the characters; factory/series.py). Same characters, same art each time.

  proposal    the episode adapted from its chapters (series.write_episode files it as a production row), with the
              cost of its illustrations, voices and music -> proposal (gate; approving it fixes the budget)
  script      the lines with who says each -> script (gate; feedback rewrites the episode with the note)
  scene_plan  the illustrations, drawn from the character sheets inside the budget, then the motion design
              -> plates (gate)
  assets, edit, compose, publish   the footage line's steps (cast voices + music, preview, final with QA, post copy)
The project names its series and episode: project["series"] = {"id": <series id>, "episode": <n>}.
"""
import os

from ..config import ROOT
from . import project as P
from .explainer import remaining_budget
from .footage import _con, _ui, _rel, chosen_prod, assets, edit, compose, publish   # noqa: F401 (stages of this line)


def _series(p):
    s = p.get("series") or {}
    if not s.get("id") or not s.get("episode"):
        raise P.GateError("this project names no series episode")
    return int(s["id"]), int(s["episode"])


def _use(pid, prod, d=None):
    """Make `prod` the production every later stage works on."""
    p = P.load(pid, d)
    p["prods"] = (p.get("prods") or []) + ([prod] if prod not in (p.get("prods") or []) else [])
    p["current_prod"] = prod
    P.save(p, d)


def proposal(pid, s, note=None, d=None):
    from .. import illustrate, productions as PR, series
    con, p = _con(), P.load(pid, d)
    sid, n = _series(p)
    prod = series.write_episode(con, sid, n, note or "")
    _use(pid, prod, d)
    row = PR.get(con, prod)
    dd = row["data"]
    chars, _ = series.cast_for(con, row)
    plates = illustrate.estimate(con, dd, PR.eleven_account(dd), chars)
    voice = PR.voice_estimate(con, dd)
    music = PR.music_estimate(con, row)
    lines = [{"label": "illustrations", "credits": round(plates["credits"])},
             {"label": "voices", "credits": round(voice["credits"])}, {"label": "music", "credits": round(music["credits"])}]
    total = sum(x["credits"] for x in lines)
    summary = {"tr": f"Bölüm {n}: {row['title']}. {plates['images']} çizim, {len(dd['voice']['lines'])} satır; ~{total} kredi.",
               "en": f"Episode {n}: {row['title']}. {plates['images']} illustrations, {len(dd['voice']['lines'])} lines; ~{total} credits."}[_ui(p)]
    concept = {"id": "A", "prod_id": prod, "title": row["title"], "hook": dd.get("hook") or dd["voice"]["lines"][0],
               "structure": dd.get("logline") or "", "look": dd.get("art_style") or "illustrated", "why": dd.get("why") or ""}
    art = {"concepts": [concept], "chosen": "A", "seconds": music["seconds"], "look": "illustrated",
           "voice": {"use": True}, "music": {"use": True, "prompt": music["prompt"]},
           "cost": {"credits": total, "lines": lines}, "summary": summary}
    return {"artifact": art, "summary": summary}


def script(pid, s, note=None, d=None):
    """The episode's lines and speakers. A note rewrites the episode (a new production row; the old one stays)."""
    from .. import productions as PR, series
    con, p = _con(), P.load(pid, d)
    if note:
        sid, n = _series(p)
        _use(pid, series.write_episode(con, sid, n, note), d)
    row = PR.get(con, chosen_prod(pid, d))
    v = row["data"]["voice"]
    lines = v["lines"]
    speakers = v.get("speakers") or ["narrator"] * len(lines)
    summary = {"tr": f"{len(lines)} satır; konuşanlar: {', '.join(sorted(set(speakers)))}.",
               "en": f"{len(lines)} lines; speakers: {', '.join(sorted(set(speakers)))}."}[_ui(p)]
    art = {"title": row["title"], "hook": lines[0], "lines": [f"{sp}: {ln}" if sp != "narrator" else ln
                                                              for sp, ln in zip(speakers, lines)],
           "speakers": speakers, "claims": [], "summary": summary}
    return {"artifact": art, "summary": summary}


def scene_plan(pid, s, note=None, d=None):
    """The illustrations (inside the approved budget, drawn from the character sheets), then the motion design."""
    from .. import illustrate, productions as PR, series
    con, p = _con(), P.load(pid, d)
    prod = chosen_prod(pid, d)
    row = PR.get(con, prod)
    chars, flow = series.cast_for(con, row)
    cost = illustrate.make_plates(con, row, remaining_budget(pid, d), chars, flow)
    PR.save(con, row, "çizimler", f"{round(cost)} kredi")
    PR.design(con, prod, note or "")
    row = PR.get(con, prod)
    plates = [pl["file"] for pl in (row["data"].get("plates") or {}).values() if pl.get("file")]
    concept = ((row["data"].get("motion") or {}).get("concept") or "")
    summary = {"tr": f"{len(plates)} çizim hazır ({round(cost)} kredi). Hepsine bak: karakterler aynı mı?",
               "en": f"{len(plates)} illustrations ready ({round(cost)} credits). Look at them all: are the characters the same?"}[_ui(p)]
    art = {"concept": concept, "plates": plates, "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"credits": round(cost)}}
