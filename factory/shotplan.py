"""The shape of a scene plan, before anything about its taste: does it cover the script, in order, in time?

The other checks look at a scene (`camera`, `subjectqc`, `motiongrammar`) or at the film as a picture (`originality`,
`determinism`, `direction`). None of them notices a plan that simply *skips* line 7, plays line 9 twice, starts on
line 2, or spreads 9 scenes over 25 seconds so each is on screen for 2.8 s. Those are structural, cheap to check and
they are what a viewer feels first, so they are refused before the taste checks run.

`problems(scenes, lines, seconds)` returns short sentences, in the same voice as the other checkers.
"""
COUNT_PER_SHOT = (4.0, 12.0)     # seconds per scene: an average shot between these reads as a film, not a slideshow
MIN_WORDS_PER_SCENE = 1          # a scene with no spoken line is a card, not a scene (cards are `card: true`)


def _ranges(scenes):
    out = []
    for i, sc in enumerate(scenes or []):
        a, b = (sc.get("lines") or [0, 0])[:2]
        out.append((i, int(a), int(b)))
    return out


MIN_SCENE_S = 1.0                # a scene shorter than this is a blink, not a scene


def timing_problems(scenes, words, starts):
    """Cut laws that need real timing: a cut may not land inside a spoken word, no scene under a second.

    `words` are (word, start, end) with the voice start already folded in, `starts` the scene starts in order
    (the last scene's start is its own; its end is the film's end, so it is not checked).
    """
    out = []
    spans = [(s, starts[i + 1] if i + 1 < len(starts) else None) for i, s in enumerate(starts or [])]
    for i, (a, b) in enumerate(spans):
        if b is None:
            continue
        if b - a < MIN_SCENE_S:
            out.append(f"scene {scenes[i].get('id') if i < len(scenes) else i + 1}: {b - a:.2f} s long; "
                       f"a scene needs at least {MIN_SCENE_S:g} s")
        for w, ws, we in words or []:
            if ws < b < we:
                out.append(f"the cut at {b:.2f} s falls inside the word '{w}' ({ws:.2f}-{we:.2f} s): "
                           f"cut on a pause, not mid-word")
                break
    return out


def problems(scenes, lines=None, seconds=None, cards=True, words=None, starts=None, partial=False):
    """Structural refusals: coverage and order of the script's lines, and the pace of the plan.

    `partial=True` checks a slice of the script (one designer's part of a long explainer): its scenes must still be in
    order, must not overlap or run past the script, but they only cover their own part — the full coverage is checked
    when the parts are merged."""
    scenes = [sc for sc in (scenes or []) if isinstance(sc, dict)]
    out = []
    if not scenes:
        return ["the plan has no scenes"]
    n_script = len(lines or [])
    shown = set()
    for i, sc in enumerate(scenes):
        sid = sc.get("id") or i
        rng = (sc.get("lines") or [])
        if len(rng) != 2 or not all(isinstance(x, int) for x in rng):
            out.append(f"scene {sid}: `lines` must be [first, last] (two integers)")
            continue
        a, b = rng
        if b < a:
            out.append(f"scene {sid}: `lines` runs backwards ({a}..{b})")
            continue
        if a == 0 and i > 0 and not partial:
            out.append(f"scene {sid}: starts on line 0 again; the film begins once")
        if n_script and b >= n_script:
            out.append(f"scene {sid}: lines {a}..{b} run past the script ({n_script} lines)")
        overlap = shown & set(range(a, b + 1))
        if overlap:
            out.append(f"scene {sid}: line(s) {sorted(overlap)[:3]} appear twice in the plan")
        shown |= set(range(a, b + 1))
        if not cards and sc.get("card") is None and (b - a + 1) < MIN_WORDS_PER_SCENE:
            out.append(f"scene {sid}: no line of the script lands here")
    if n_script and not partial:
        missing = sorted(set(range(n_script)) - shown)
        if missing:
            out.append(f"the plan never shows line(s) {missing[:5]}" + (" …" if len(missing) > 5 else ""))
    order = [r[1] for r in _ranges(scenes)]
    if order != sorted(order):
        out.append("the scenes are not in script order: line ranges must rise from scene to scene")
    if words and starts:
        out += timing_problems(scenes, words, starts)
    if seconds and n_script:
        lo, hi = COUNT_PER_SHOT
        want_lo, want_hi = max(3, int(float(seconds) / hi)), max(6, int(float(seconds) / lo))
        if not want_lo <= len(scenes) <= want_hi:
            out.append(f"{len(scenes)} scenes for {float(seconds):g} s: keep it between {want_lo} and {want_hi} "
                       f"(a shot lasts {lo:g}-{hi:g} s)")
    return out
