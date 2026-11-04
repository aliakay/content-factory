"""The talking-head line's code side: the creator's own video of them talking to camera, cut by factory/talk.py.

  idea     transcript + faces + the editor's first cut (talk.create files it as a production row) -> proposal (gate)
  script   the cut decision as the creator reads it: every phrase kept or cut, in play order, hook, B-roll -> cut (gate)
           feedback re-cuts the transcript with the note (talk.revise); nothing is rendered or paid yet
  assets   music inside the approved budget + a preview render (the footage line's step) -> assets (gate)
  edit, compose, publish   the footage line's steps (final render with QA, post copy)
The source file (project["source"], uploaded to raw/talk/) is never modified.
"""
import os

from ..config import ROOT
from . import project as P
from .footage import _con, _ui, chosen_prod, assets, edit, compose, publish   # noqa: F401 (stages of this line)

__all__ = ["idea", "script", "assets", "edit", "compose", "publish"]


def _source(p):
    src = p.get("source") or ""
    full = os.path.realpath(os.path.join(ROOT, src))
    if not src or not full.startswith(os.path.realpath(os.path.join(ROOT, "raw", "talk")) + os.sep) or not os.path.isfile(full):
        raise P.GateError("no uploaded video for this project (raw/talk/)")
    return full


def idea(pid, s, note=None, d=None):
    """Analyse the video and make the first cut. A note re-cuts the same video with it."""
    from .. import talk
    con, p = _con(), P.load(pid, d)
    if note and p.get("prods"):
        return script(pid, s, note, d, as_proposal=True)
    src = _source(p)
    brief = p.get("brief") or ""
    prod = talk.create(con, src, brief, p.get("channel"), p.get("aspect", "9:16"), lang=p.get("video_lang"))
    p = P.load(pid, d)
    p["prods"] = (p.get("prods") or []) + [prod]
    P.save(p, d)
    art = _proposal(con, p, prod)
    return {"artifact": art, "summary": art["summary"]}


def _proposal(con, p, prod):
    from .. import productions as PR, talk
    row = PR.get(con, prod)
    dd = row["data"]
    sm = talk.summary(dd)
    m = PR.music_estimate(con, row) if (dd.get("music") or {}).get("prompt") else None
    cost = round(m["credits"]) if m else 0
    summary = {"tr": f"Ham video {sm['raw_s']:.0f} sn → kesim {sm['kept_s']:.0f} sn. Kanca: “{sm.get('hook') or ''}”."
                     + (f" Müzik ~{cost} kredi." if m else " Müzik yok, ücretsiz."),
               "en": f"Raw video {sm['raw_s']:.0f} s → cut {sm['kept_s']:.0f} s. Hook: “{sm.get('hook') or ''}”."
                     + (f" Music ~{cost} credits." if m else " No music, free.")}[_ui(p)]
    concept = {"id": "A", "prod_id": prod, "title": row["title"], "hook": sm.get("hook") or "",
               "structure": dd.get("logline") or "", "look": sm.get("grade") or "natural", "why": dd.get("why") or ""}
    return {"concepts": [concept], "chosen": "A", "seconds": sm["kept_s"], "look": concept["look"],
            "voice": {"use": False}, "music": {"use": bool(m), "prompt": (dd.get("music") or {}).get("prompt", "")},
            "cost": {"credits": cost, "lines": [{"label": "music", "credits": cost}] if m else []}, "summary": summary}


def script(pid, s, note=None, d=None, as_proposal=False):
    """The cut decision: kept and cut phrases. A note re-cuts with it (the editor gets the current cut too)."""
    from .. import productions as PR, talk
    con, p = _con(), P.load(pid, d)
    prod = chosen_prod(pid, d) if not as_proposal else (p.get("prods") or [None])[-1]
    if note:
        talk.revise(con, PR.get(con, prod), note)
    if as_proposal:
        art = _proposal(con, p, prod)
        return {"artifact": art, "summary": art["summary"]}
    sm = talk.summary(PR.get(con, prod)["data"])
    cut = sum(1 for ph in sm["phrases"] if not ph["kept"])
    summary = {"tr": f"{len(sm['phrases']) - cut} cümle kaldı, {cut} kesildi; {sm['kept_s']:.0f} sn. Kesilenleri kontrol et.",
               "en": f"{len(sm['phrases']) - cut} phrases kept, {cut} cut; {sm['kept_s']:.0f} s. Check what was cut."}[_ui(p)]
    return {"artifact": dict(sm, summary=summary), "summary": summary}
