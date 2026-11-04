"""Production-line manifests (pipelines/*.yaml): what each line makes, its stages in order, which stages are gates,
how each stage runs and which tools it may use. The manifest is binding: the line manager (factory/hat/runner.py)
never re-judges a gate, and a stage only sees the tools its manifest lists.

User-facing text is bilingual ({tr, en}); `localize()` picks one language for the Studio. Agent-facing text
(review focus) stays English.
"""
import functools, glob, os

import yaml

from ..config import ROOT

DIR = os.path.join(ROOT, "pipelines")
LANGS = ("tr", "en")
STATUSES = ("ready", "partial", "planned")
RUNS = ("agent", "code", "planned")
TEXT = ("name", "tagline", "makes", "needs", "cost")          # {tr, en} strings
LISTS = ("good_for", "not_for")                               # {tr, en} lists


class ManifestError(ValueError):
    pass


def _bi(v, key, where, list_=False):
    if not isinstance(v, dict) or any(l not in v for l in LANGS):
        raise ManifestError(f"{where}: '{key}' needs both tr and en")
    for l in LANGS:
        ok = isinstance(v[l], list) and all(isinstance(x, str) and x for x in v[l]) if list_ else isinstance(v[l], str)
        if not ok:
            raise ManifestError(f"{where}: '{key}.{l}' must be {'a list of texts' if list_ else 'a text'}")


def stage_vocab(d=None):
    with open(os.path.join(d or DIR, "_stages.yaml"), encoding="utf-8") as f:
        vocab = yaml.safe_load(f)
    for sid, st in vocab.items():
        for k in ("name", "says"):
            _bi(st.get(k), k, f"_stages.{sid}")
    return vocab


def validate(m, vocab):
    """Check one manifest and fill each stage from the shared vocabulary. Returns the completed manifest."""
    where = m.get("id") or "?"
    for k in ("id", "order", "status", "category", "inputs", "stages"):
        if k not in m:
            raise ManifestError(f"{where}: missing '{k}'")
    if m["status"] not in STATUSES:
        raise ManifestError(f"{where}: status must be one of {STATUSES}")
    for k in TEXT:
        _bi(m.get(k), k, where)
    for k in LISTS:
        _bi(m.get(k), k, where, list_=True)
    seen, stages = set(), []
    for st in m["stages"]:
        sid = st.get("id")
        if sid not in vocab and "name" not in st:
            raise ManifestError(f"{where}: stage '{sid}' is not in _stages.yaml and has no name")
        if sid in seen:
            raise ManifestError(f"{where}: stage '{sid}' appears twice")
        seen.add(sid)
        run = st.get("run", "planned")
        if run not in RUNS:
            raise ManifestError(f"{where}.{sid}: run must be one of {RUNS}")
        if run == "code" and ":" not in str(st.get("call", "")):
            raise ManifestError(f"{where}.{sid}: a code stage needs call: module:function")
        base = vocab.get(sid, {})
        full = {"id": sid, "gate": bool(st.get("gate")), "run": run, "call": st.get("call"), "model": st.get("model"),
                "tools": list(st.get("tools") or []), "review": list(st.get("review") or []),
                "artifact": st.get("artifact") or base.get("artifact") or sid,
                "schema": st.get("schema") or st.get("artifact") or base.get("artifact") or sid,
                "name": st.get("name") or base["name"], "says": st.get("says") or base.get("says") or {"tr": "", "en": ""},
                "gate_says": st.get("gate_says") or base.get("gate_says") or {"tr": "", "en": ""},
                "pass_score": st.get("pass_score")}
        if full["pass_score"] is not None and not (isinstance(full["pass_score"], int) and 50 <= full["pass_score"] <= 100):
            raise ManifestError(f"{where}.{sid}: pass_score must be a whole number 50-100")
        _bi(full["name"], "name", f"{where}.{sid}")
        stages.append(full)
    if m.get("aspect") is not None and m["aspect"] not in ("9:16", "16:9"):
        raise ManifestError(f"{where}: aspect must be 9:16 or 16:9")
    if m["status"] == "ready" and any(s["run"] == "planned" for s in stages):
        raise ManifestError(f"{where}: a ready line cannot have planned stages")
    return {**m, "stages": stages}


@functools.lru_cache(maxsize=4)
def _load(d):
    vocab = stage_vocab(d)
    out = {}
    for path in sorted(glob.glob(os.path.join(d, "*.yaml"))):
        if os.path.basename(path).startswith("_"):
            continue
        with open(path, encoding="utf-8") as f:
            m = validate(yaml.safe_load(f), vocab)
        if m["id"] != os.path.splitext(os.path.basename(path))[0]:
            raise ManifestError(f"{path}: id '{m['id']}' must match the file name")
        out[m["id"]] = m
    return dict(sorted(out.items(), key=lambda kv: kv[1]["order"]))


def all_lines(d=None):
    return _load(d or DIR)


def get(line_id, d=None):
    lines = all_lines(d)
    if line_id not in lines:
        raise ManifestError(f"unknown production line '{line_id}'")
    return lines[line_id]


def stage(m, sid):
    for s in m["stages"]:
        if s["id"] == sid:
            return s
    raise ManifestError(f"{m['id']}: no stage '{sid}'")


def localize(m, lang):
    """One language view of a manifest for the Studio (ids, flags and tools stay as they are)."""
    lang = lang if lang in LANGS else "tr"
    pick = lambda v: v[lang] if isinstance(v, dict) and lang in v else v
    out = {k: v for k, v in m.items() if k != "stages"}
    for k in TEXT + LISTS:
        out[k] = pick(m[k])
    out["stages"] = [{**s, "name": pick(s["name"]), "says": pick(s["says"]), "gate_says": pick(s["gate_says"])}
                     for s in m["stages"]]
    return out
