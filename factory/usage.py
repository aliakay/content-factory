"""Usage of the factory's own headless Claude/Codex calls (llm_usage table, filled by llm._record).

Costs are Claude Code's list-price equivalent (total_cost_usd), not a share of the subscription's 5-hour limit, which
Anthropic does not expose. `pct_per_usd` turns dollars into an estimated limit share once the creator has calibrated it.
Calls from before the ledger existed are imported once from the CLI transcripts (source "transcript", cost estimated).
"""
import glob, json, os
from datetime import datetime, timedelta, timezone

from .config import CLAUDE_TRANSCRIPTS as TRANSCRIPTS, ROOT, WORK

CALIB = os.path.join(ROOT, "data", "claude_calibration.json")

# rough $/Mtok (input, output) only for the transcript import; live rows carry the CLI's own cost
_PRICE = {"opus": (5, 25), "sonnet": (3, 15), "haiku": (1, 5)}

# transcript prompt prefix -> step name used by live rows (module.function)
_PREFIX = [
    ("You pick story ideas", "discover.make_cards"),
    ("You are the editor of a faceless explainer", "explainer.generate"),
    ("You edit one faceless explainer short", "explainer.revise"),
    ("You are the motion designer of", "motiondesign.author"),
    ("You are the motion designer reviewing", "motiondesign.critique"),
    ("You are the editor of a short-video factory", "productions.plan_edit"),
    ("You edit one short video", "productions.revise"),
    ("You are the social-media expert", "productions.generate"),
    ("You are the creative director", "productions.generate"),
    ("You are the ART DIRECTOR", "artdirector.direct"),
    ("You are the art director", "artdirector.direct"),
    ("You art-directed this short video", "artdirector.review"),
    ("Fact-check each claim", "ideas.check_claims"),
    ("Read each image file below", "jobs.do_describe"),
    (f"Read the image {WORK}/qa/", "qa.review"),
    (f"Read the image {WORK}/refgrids/", "refs.describe"),
    ("Read the reference image", "styles.extract"),
    ("Use the ElevenLabs tools. Generate speech", "eleven.tts"),
    ("Use the ElevenLabs tools. Run ONE", "eleven.generate"),
    ("Use ElevenLabs", "eleven.read"),
    ("Use the ElevenLabs", "eleven.read"),
    ("Call creative_list_voices", "eleven.list_voices"),
]

STEP_TR = {
    "discover.make_cards": "Günlük keşif", "ideas.generate": "Fikir üretimi (çekimli)",
    "productions.generate": "Fikir + senaryo", "explainer.generate": "Konu araştırma + senaryo",
    "ideas.check_claims": "Doğrulama", "motiondesign.author": "Hareket tasarımı",
    "motiondesign.critique": "Tasarım kontrolü", "artdirector.direct": "Art direction",
    "artdirector.review": "Art direction kontrolü", "productions.plan_edit": "Düzenleme planı",
    "productions.revise": "Revizyon", "explainer.revise": "Revizyon", "qa.review": "Render QA",
    "jobs.do_describe": "Klip açıklama", "refs.describe": "Referans profil", "refs.describe_recipes": "Kurgu tarifi",
    "styles.extract": "Stil çıkarma",
}


def step_tr(step):
    if step.startswith("eleven."):
        return "ElevenLabs aracı"
    return STEP_TR.get(step, step)


def _family(model):
    if "gpt-" in (model or "").lower():
        return "codex"
    return next((k for k in _PRICE if k in (model or "")), "opus")


def import_transcripts(con, days=7):
    """One-off import of factory calls made before the ledger existed (skips sessions already imported)."""
    have = {r[0] for r in con.execute("SELECT source FROM llm_usage WHERE source LIKE 'transcript:%'")}
    first_live = con.execute("SELECT MIN(at) FROM llm_usage WHERE source LIKE 'live%'").fetchone()[0] or "9999"
    cut = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    n = 0
    for f in glob.glob(os.path.join(TRANSCRIPTS, "*.jsonl")):
        src = "transcript:" + os.path.basename(f)[:36]
        if src in have:
            continue
        step, at, model, seen = None, None, None, set()
        tok = [0, 0, 0, 0]
        for line in open(f, errors="ignore"):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            m = e.get("message") if isinstance(e.get("message"), dict) else {}
            if e.get("type") == "user" and step is None:
                c = m.get("content")
                text = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict))
                step = next((s for p, s in _PREFIX if text.startswith(p)), "?")
                at = e.get("timestamp")
            if e.get("type") == "assistant" and m.get("usage") and m.get("id") not in seen:
                seen.add(m.get("id"))
                u = m["usage"]
                model = m.get("model")
                for i, k in enumerate(("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")):
                    tok[i] += u.get(k, 0)
        if not at or not seen or at < cut or at >= first_live or step == "?":
            continue
        pi, po = _PRICE[_family(model)]
        cost = (tok[0] * pi + tok[1] * pi * 1.25 + tok[2] * pi * 0.1 + tok[3] * po) / 1e6
        at = datetime.fromisoformat(at.replace("Z", "+00:00")).replace(microsecond=0).isoformat()
        con.execute("INSERT INTO llm_usage (at, step, model, input, cache_write, cache_read, output, cost_usd, ok, source)"
                    " VALUES (?,?,?,?,?,?,?,?,1,?)", (at, step, model, *tok, round(cost, 4), src))
        n += 1
    con.commit()
    return n


def calibration():
    try:
        return json.load(open(CALIB))
    except (OSError, ValueError):
        return {}


def summary(con):
    import_transcripts(con)
    now = datetime.now(timezone.utc)
    win = {"5h": (now - timedelta(hours=5)).isoformat(), "today": now.astimezone().replace(
        hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat(),
           "7d": (now - timedelta(days=7)).isoformat()}
    rows = [dict(r) for r in con.execute("SELECT * FROM llm_usage WHERE at >= ? ORDER BY at DESC", (win["7d"],))]
    tot = {k: round(sum(r["cost_usd"] or 0 for r in rows if r["at"] >= v), 2) for k, v in win.items()}
    by_step, by_model, by_prod = {}, {}, {}
    for r in rows:
        if r["at"] < win["today"]:
            continue
        s = step_tr(r["step"])
        by_step[s] = by_step.get(s, 0) + (r["cost_usd"] or 0)
        fam = _family(r["model"])
        by_model[fam] = by_model.get(fam, 0) + (r["cost_usd"] or 0)
    for r in rows:
        if r["prod_id"]:
            by_prod[r["prod_id"]] = by_prod.get(r["prod_id"], 0) + (r["cost_usd"] or 0)
    names = {}
    if by_prod:
        q = ",".join("?" * len(by_prod))
        names = {r[0]: r[1] for r in con.execute(f"SELECT prod_id, COALESCE(title, name) FROM productions WHERE prod_id IN ({q})",
                                                 list(by_prod))}
    cal = calibration()
    return {"totals": tot, "estimated": any(r["source"] not in ("live", "live_codex") for r in rows),
            "by_step": sorted(([k, round(v, 2)] for k, v in by_step.items()), key=lambda x: -x[1]),
            "by_model": {k: round(v, 2) for k, v in by_model.items()},
            "by_prod": sorted(([k, names.get(k) or f"#{k}", round(v, 2)] for k, v in by_prod.items()), key=lambda x: -x[2])[:10],
            "recent": [{"at": r["at"], "step": step_tr(r["step"]), "model": r["model"], "prod_id": r["prod_id"],
                        "cost": round(r["cost_usd"], 3) if r["cost_usd"] is not None else None, "ok": r["ok"], "live": r["source"].startswith("live"),
                        "tokens": (r["input"] or 0) + (r["cache_write"] or 0) + (r["output"] or 0)} for r in rows[:40]],
            "pct_per_usd": cal.get("pct_per_usd"), "calibrated_at": cal.get("at")}
