"""Viral Score (0-100) and confidence. Missing components are omitted and weights renormalized."""
import math, re
from datetime import datetime, timezone

from .config import WEIGHTS

AGE_COHORTS = [(0, 24), (24, 72), (72, 168), (168, 336), (336, 24 * 31)]  # hours since publish

SUBTOPICS = {
    "memory": r"memor|forget|remember|recall|déjà|deja vu",
    "habits": r"habit|discipline|procrastinat|routine|dopamine|motivation",
    "relationships": r"relationship|love|crush|attract|friend|partner|texting|ex\b",
    "cognitive_bias": r"bias|effect\b|fallacy|heuristic|illusion",
    "body_language": r"body language|eye contact|gesture|posture|nonverbal|smile",
    "emotions": r"emotion|anxiety|stress|sad|happy|anger|lonel|overthink",
    "sleep_dreams": r"sleep|dream|nightmare|insomnia",
    "social": r"social|people who|introvert|extrovert|manipulat|persuasi|first impression",
    "brain": r"brain|neuro|iq|intelligen|genius",
}


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def subtopics(text):
    # hashtags are mostly generic spam (#motivation #shorts), so classify on the words only
    t = re.sub(r"#\w+", " ", (text or "").lower())
    return sorted(k for k, rx in SUBTOPICS.items() if re.search(rx, t))


def pct_rank(value, population):
    """Share of the population strictly below `value` plus half of ties (0..1)."""
    if value is None or not population:
        return None
    below = sum(1 for p in population if p < value)
    ties = sum(1 for p in population if p == value)
    return (below + 0.5 * ties) / len(population)


def cohort(age_h):
    for lo, hi in AGE_COHORTS:
        if lo <= age_h < hi:
            return (lo, hi)
    return AGE_COHORTS[-1]


def score_all(cands, now=None, topic_signals=None):
    """
    cands: dicts with published_at, views, likes, comments, channel_id, title, description,
           optional channel_median, optional snapshots [(ts, views), ...] oldest first.
    Adds 'components', 'viral_score', 'confidence', 'missing' to each candidate.
    """
    now = now or datetime.now(timezone.utc)
    topic_signals = topic_signals or {}
    for c in cands:
        pub = parse_ts(c.get("published_at"))
        c["age_h"] = max((now - pub).total_seconds() / 3600, 1.0) if pub else None
        c["velocity_raw"] = c["views"] / c["age_h"] if c.get("views") is not None and c["age_h"] else None
        subs, views = c.get("subscribers"), c.get("views")
        # Icahn-style small-channel outlier: 100K+ views, under 100K subscribers, views/subs >= 5
        c["views_per_sub"] = round(views / subs, 1) if subs and views is not None else None
        c["icahn"] = (views >= 100_000 and subs < 100_000 and views / max(subs, 1) >= 5) \
            if subs is not None and views is not None else None
        c["subtopics"] = subtopics(f"{c.get('title', '')} {(c.get('description') or '')[:300]}")

    # creators per subtopic, for cross-creator replication
    creators = {}
    for c in cands:
        for s in c["subtopics"]:
            creators.setdefault(s, set()).add(c.get("channel_id"))

    eng_pop = [e for e in (_engagement(c) for c in cands) if e is not None]
    out_pop = [o for o in (_outlier(c) for c in cands) if o is not None]
    acc_pop = [a for a in (_acceleration(c) for c in cands) if a is not None]

    for c in cands:
        comp = {}
        if c["velocity_raw"] is not None:
            co = cohort(c["age_h"])
            peers = [x["velocity_raw"] for x in cands if x["velocity_raw"] is not None and cohort(x["age_h"]) == co]
            comp["velocity"] = pct_rank(c["velocity_raw"], peers)
            c["cohort_size"] = len(peers)
        comp["outlier"] = pct_rank(_outlier(c), out_pop)
        comp["engagement"] = pct_rank(_engagement(c), eng_pop)
        comp["acceleration"] = pct_rank(_acceleration(c), acc_pop)
        if c["subtopics"]:
            n = max(len(creators[s]) for s in c["subtopics"])
            comp["replication"] = min(1.0, (n - 1) / 4)
        sig = [topic_signals[s] for s in c["subtopics"] if s in topic_signals]
        if sig:
            comp["trend"] = max(sig)
        comp = {k: v for k, v in comp.items() if v is not None}

        avail = sum(WEIGHTS[k] for k in comp)
        c["components"] = comp
        c["missing"] = [k for k in WEIGHTS if k not in comp]
        c["viral_score"] = round(100 * sum(WEIGHTS[k] * v for k, v in comp.items()) / avail, 1) if avail else None
        c["confidence"] = confidence(c, avail, now)
    return sorted(cands, key=lambda c: (c["viral_score"] is None, -(c["viral_score"] or 0)))


def _engagement(c):
    v = c.get("views")
    if not v or c.get("likes") is None:
        return None
    return (c["likes"] + (c.get("comments") or 0)) / v


def _outlier(c):
    med, v = c.get("channel_median"), c.get("views")
    if not med or v is None:
        return None
    return math.log10((v + 1) / (med + 1))


def _acceleration(c):
    """Change in views/hour between the last two snapshot intervals (needs >= 3 snapshots)."""
    s = c.get("snapshots") or []
    if len(s) < 3:
        return None
    (t0, v0), (t1, v1), (t2, v2) = s[-3:]
    h1 = (parse_ts(t1) - parse_ts(t0)).total_seconds() / 3600
    h2 = (parse_ts(t2) - parse_ts(t1)).total_seconds() / 3600
    if h1 < 6 or h2 < 6 or None in (v0, v1, v2):
        return None
    r1, r2 = (v1 - v0) / h1, (v2 - v1) / h2
    return (r2 - r1) / max(r1, 1)


def confidence(c, available_weight, now):
    """0..1: data completeness x cohort sample size x snapshot freshness."""
    completeness = available_weight
    sample = min(1.0, (c.get("cohort_size") or 0) / 10)
    snaps = c.get("snapshots") or []
    if snaps:
        age = (now - parse_ts(snaps[-1][0])).total_seconds() / 3600
        fresh = 1.0 if age <= 24 else max(0.2, 1 - (age - 24) / 144)
    else:
        fresh = 0.5
    return round(completeness * (0.5 + 0.5 * sample) * fresh, 2)


def shortlist(cands, n=15, per_creator=2):
    """Best-scored candidates with at most `per_creator` per channel, preferring unseen subtopics."""
    picked, per_ch, covered = [], {}, set()
    pool = [c for c in cands if c.get("viral_score") is not None]
    while pool and len(picked) < n:
        def key(c):
            new = len(set(c["subtopics"]) - covered)
            return (c["viral_score"] + 5 * min(new, 2))
        pool.sort(key=key, reverse=True)
        c = pool.pop(0)
        ch = c.get("channel_id")
        if per_ch.get(ch, 0) >= per_creator:
            continue
        per_ch[ch] = per_ch.get(ch, 0) + 1
        covered |= set(c["subtopics"])
        picked.append(c)
    return picked
