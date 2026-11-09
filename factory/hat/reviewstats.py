"""What the reviewer and the deterministic gates cost and catch, across every project.

The Studio keeps each project's events on disk (`projects/<id>/events.jsonl`) and a review ledger per stage
(`artifacts/review_ledger.json`). This module reads them together and answers the two questions that change the
skills: which items reject the most submissions, and which stage burns the most time (a run per stage, including the
fix rounds). `report()` is what the Studio and `python -m factory.hat.reviewstats` show; `advice()` turns the worst
items into the lines a stage skill should carry, so the lesson is learned once instead of every film.

Nothing here writes: the aggregation is read-only over the project folders.
"""
import collections, json, os

from . import project as P

TOP = 8


def _events(pid, d=None):
    path = P.path(pid, "events.jsonl", d=d)
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def _minutes(a, b):
    from datetime import datetime
    try:
        start, end = datetime.fromisoformat(a), datetime.fromisoformat(b)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, (end - start).total_seconds() / 60)


def report(d=None, limit=TOP):
    """-> {rejections, stages, reviews, projects}: the most common gate refusals, time per stage, verdicts."""
    reject = collections.Counter()
    reject_by = collections.defaultdict(set)
    stages = collections.defaultdict(list)
    verdicts = collections.Counter()
    rounds = collections.Counter()
    pids = P.list_ids(d)
    for pid in pids:
        for e in _events(pid, d):
            kind = e.get("kind")
            if kind == "submit_rejected":
                for text in e.get("problems") or []:
                    key = str(text).split(":")[0].strip()[:120]
                    reject[key] += 1
                    reject_by[key].add(e.get("stage") or "?")
            elif kind == "agent_end":
                stages[e.get("stage") or "?"].append(float(e.get("seconds") or 0) / 60)
            elif kind == "review":
                verdicts[e.get("verdict") or "?"] += 1
                rounds[e.get("stage") or "?"] += 1
    return {"projects": len(pids),
            "rejections": [{"problem": k, "count": n, "stages": sorted(reject_by[k])}
                           for k, n in reject.most_common(limit)],
            "stages": [{"stage": k, "runs": len(v), "avg_min": round(sum(v) / len(v), 1), "max_min": round(max(v), 1)}
                       for k, v in sorted(stages.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))],
            "reviews": dict(verdicts)}


def advice(d=None):
    """The lines a skill should carry, from the two most common refusals: [{stage, line}]."""
    rep = report(d)
    out, seen = [], set()
    for row in rep["rejections"][:4]:
        for stage in row["stages"]:
            if stage in seen:
                continue
            seen.add(stage)
            out.append({"stage": stage, "line": f"- the gate refused {row['count']} times: {row['problem']}"})
    return out


def text(d=None):
    rep = report(d)
    lines = [f"{rep['projects']} proje", ""]
    if rep["stages"]:
        lines.append("Aşama süreleri (ajan turları, dk):")
        for s in rep["stages"]:
            lines.append(f"  {s['stage']:14} {s['runs']:3} koşu · ort {s['avg_min']:5.1f} · en uzun {s['max_min']:5.1f}")
    if rep["reviews"]:
        lines += ["", "Denetim kararları: " + ", ".join(f"{k} {v}" for k, v in rep["reviews"].items())]
    if rep["rejections"]:
        lines += ["", "En sık kapı reddi:"]
        for r in rep["rejections"]:
            lines.append(f"  {r['count']:2}x [{', '.join(r['stages'])}] {r['problem']}")
    adv = advice(d)
    if adv:
        lines += ["", "Skill'lere eklenecek satırlar:"]
        lines += [f"  [{a['stage']}] {a['line']}" for a in adv]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    print(text(sys.argv[1] if len(sys.argv) > 1 else None))
