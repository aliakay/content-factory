"""The hybrid line's code side: the creator's footage with sourced information on top.

v1 runs on the footage engine's "travel_facts" format (2-3 verifiable facts, each over footage of what it is about);
the art director sets the information layers. The difference from the travel vlog is the fact gate:
  idea        three ideas on real clips, each carrying its facts as claims -> proposal (gate)
  script      every claim checked against sources (ideas.check_claims) -> script (gate); unsupported facts are named
  scene_plan, assets, edit, compose, publish   the footage line's steps
"""
from . import footage, project as P
from .footage import _con, _ui, chosen_prod, scene_plan, assets, edit, compose, publish   # noqa: F401 (stages)

FORMAT = "travel_facts"


def idea(pid, s, note=None, d=None):
    p = P.load(pid, d)
    if p.get("format") != FORMAT:
        p["format"] = FORMAT
        P.save(p, d)
    return footage.idea(pid, s, note, d)


def script(pid, s, note=None, d=None):
    """The idea's lines and its facts, each checked. A note goes to the art director with the next stage."""
    from .. import productions as PR
    con, p = _con(), P.load(pid, d)
    prod = chosen_prod(pid, d)
    PR.verify(con, prod)
    row = PR.get(con, prod)
    dd = row["data"]
    verdicts = {v.get("claim"): v for v in (row.get("verification") or {}).get("verdicts", [])}
    claims = []
    for c in dd.get("claims") or []:
        text = c.get("claim") if isinstance(c, dict) else str(c)
        v = verdicts.get(text) or {}
        src = ((v.get("sources") or [{}])[0] or {}).get("url")
        claims.append({"text": text, "verified": v.get("verdict") == "supported", **({"source": src} if src else {}),
                       **({"safer": v["safer_wording"]} if v.get("safer_wording") else {})})
    bad = [c for c in claims if not c["verified"]]
    lines = (dd.get("voice") or {}).get("lines") or [sh.get("text") for sh in dd.get("shots") or [] if sh.get("text")]
    summary = ({"tr": f"{len(claims)} bilginin hepsi kaynaklarla doğrulandı.", "en": f"All {len(claims)} facts are backed by sources."}
               if not bad else
               {"tr": f"{len(bad)}/{len(claims)} bilgi doğrulanamadı; onaylamadan önce geri bildirimle çıkar ya da düzelt.",
                "en": f"{len(bad)}/{len(claims)} facts could not be verified; remove or fix them with feedback before approving."}
               )[_ui(p)]
    if note:
        summary += " · " + note
    art = {"title": row["title"], "hook": dd.get("hook") or (lines[0] if lines else ""), "lines": lines or [row["title"], ""],
           "claims": claims, "caption": ((dd.get("post") or {}) if isinstance(dd.get("post"), dict) else {}).get("caption", ""),
           "summary": summary}
    return {"artifact": art, "summary": summary}
