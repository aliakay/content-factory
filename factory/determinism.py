"""Determinism: the same plan and the same timing must draw the same film, and the check says so with a hash.

A scene's JS runs inside a headless browser, so a single `Math.random()` or `Date.now()` makes the film different on
every render: a part that was fine in the preview is different in the final, a re-render of one scene does not match
the scenes around it, and no review of a still predicts the next frame. The renderer already caches parts by their
input; this keeps that promise honest.

`problems()` refuses a plan whose scene code reads a clock or a random source. `fingerprint()` is a stable hash of
everything that decides the picture (the timing spec and the design), recorded in the render and animatic artifacts so
two runs of the same inputs can be compared: equal inputs, equal hash. `drift()` is what a stage reports when the hash
changed although nothing it depends on did.
"""
import hashlib, json, re

PATTERNS = (
    (re.compile(r"\bMath\.random\s*\("), "Math.random()"),
    (re.compile(r"\bDate\.now\s*\("), "Date.now()"),
    (re.compile(r"\bnew\s+Date\s*\("), "new Date()"),
    (re.compile(r"\bperformance\.now\s*\("), "performance.now()"),
    (re.compile(r"\bcrypto\.(getRandomValues|randomUUID)\b"), "crypto randomness"),
    (re.compile(r"\bsetInterval\s*\("), "setInterval()"),
)

BRIEF = """DETERMINISM (binding)
Scene code is drawn twice (a preview and the final) and a single scene is re-rendered on its own after a fix. So the
picture must be a function of the plan and the timing alone: never `Math.random()`, `Date.now()`, `new Date()`,
`performance.now()`, `crypto` randomness or `setInterval()`. A random-looking effect is a fixed sequence you write
down (an array of offsets, a sine of the scene time); the timeline is GSAP's, driven by the renderer's clock, not
yours. The render records a fingerprint of the plan; two runs of the same inputs must produce the same one.
"""


def problems(plan):
    """Scene code that would draw differently on every render: one string per scene and source."""
    out = []
    for i, sc in enumerate((plan or {}).get("scenes") or []):
        code = "\n".join(str(sc.get(k) or "") for k in ("js", "html", "css"))
        hits = sorted({name for pat, name in PATTERNS if pat.search(code)})
        if hits:
            out.append(f"scene {sc.get('id') or i}: {', '.join(hits)} makes the render non-deterministic; "
                       f"use a fixed sequence or the scene's own time")
    return out


def _canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fingerprint(spec, design):
    """A stable hash of what decides the picture: timing, words, scenes and their code. Same inputs, same hash."""
    keep = {k: spec.get(k) for k in ("duration", "voice_start", "aspect", "lang", "captions", "scenes", "words")}
    body = {"spec": keep, "design": design}
    return hashlib.sha256(_canon(body).encode("utf-8")).hexdigest()[:16]


def drift(previous, current):
    """A finding when a render's fingerprint changed although its inputs did not, else None."""
    if not previous or not current or previous == current:
        return None
    return f"the render fingerprint changed ({previous} -> {current}) although the plan and timing did not: " \
           f"something in the scene code is not a function of its inputs"


def compare_frames(first, second):
    """Compare captured stills from two fresh browser processes by timestamp and exact PNG bytes."""
    import os
    def keyed(paths):
        out = {}
        for path in paths or []:
            if not isinstance(path, str):
                continue
            name = os.path.basename(path)
            if not name.startswith("shot_") or not name.endswith(".png"):
                continue
            try:
                t = name[5:-4]
                with open(path, "rb") as f:
                    out[t] = hashlib.sha256(f.read()).hexdigest()
            except OSError:
                continue
        return out
    a, b = keyed(first), keyed(second)
    if not a or set(a) != set(b):
        return {"identical": False, "different": sorted(set(a) ^ set(b)), "reason": "the two captures contain different frames"}
    different = sorted(t for t in a if a[t] != b[t])
    return {"identical": not different, "different": different,
            "reason": "" if not different else "the same frame rendered to different pixels"}


def brief(p=None):
    return BRIEF
