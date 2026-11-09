"""Originality: is this film its own thing, or the same stock picture everyone makes?

Three failures look identical in a review and are different in the code:

  cliché      the picture is a stock metaphor for the idea instead of the idea (a lightbulb for "an idea", a rocket
              for "growth", a handshake for "a deal"). It reads as generated because it was never about this film.
  monotony    one mechanism, one camera move, one scene length for the whole film: the film has a look but no
              argument, and a viewer cannot tell one beat from the next.
  copying     the plan keeps a reference work's signature — the same palette, the same camera order, the same beat
              lengths — and changes only the words.

`check()` measures all three from the plan itself, with no model and no render, and turns them into a 0-100 score
(`distinct` / `derivative` / `copy`). `problems()` is the blocking subset `submit_artifact` refuses: a plan made of
stock metaphors, a film with one mechanism and one move, a duplicate picture, or a declared reference the plan copies.
A declared reference is a signature dict (`palette`, `cameras`, `mechanisms`, `seconds`) — the research's `visual_refs`
may carry them, and `signature()` turns a plan into the same shape, so a plan can be compared with anything.
"""
import re

from . import camera, words

# A picture that stands in for an idea. Matched on the folded `shows` / html alt text, stems included.
CLICHE = {
    "idea": ("ampul", "lightbulb", "light bulb", "bulb", "fikir ampulu", "beyin firtinasi", "brainstorm"),
    "growth": ("roket", "rocket", "filiz", "sprout", "buyuyen bitki", "growing plant", "merdiven", "staircase up",
               "yukari ok", "upward arrow", "yesil ok", "green arrow"),
    "deal": ("el sikisma", "handshake", "tokalasma", "sozlesme imzasi", "signing a contract"),
    "work": ("disli", "gears", "cogs", "cark", "makine dislisi", "factory gears"),
    "goal": ("hedef tahtasi", "target board", "bullseye", "ok ve hedef", "arrow in a target", "dartboard"),
    "solution": ("yapboz", "puzzle piece", "puzzle pieces", "eksik parca", "missing piece"),
    "money": ("kumbara", "piggy bank", "para yigini", "pile of coins", "coin stack", "banknote stack", "money pile"),
    "research": ("buyutec", "magnifying glass", "loupe", "mercek"),
    "strategy": ("satranc", "chess piece", "chess board", "satranc tahtasi"),
    "success": ("kupa", "trophy", "madalya", "medal", "birinci kürsü", "podium"),
    "approval": ("begeni", "thumbs up", "like button", "begeni ikonu"),
    "confusion": ("soru isareti", "question marks", "kafa karisikligi", "confused person"),
    "brain": ("beyin", "brain", "noron", "neuron", "sinir hucresi"),
    "globe": ("dunya haritasi", "world map", "kure", "globe with pins", "harita igneleri"),
    "time": ("kum saati", "hourglass", "saat", "clock face", "takvim", "calendar page"),
}
# Words that make a cliché a metaphor rather than the literal subject: "a real lightbulb factory" is not a metaphor.
LITERAL = ("fabrika", "factory", "uretim", "production", "gercek", "real", "santral", "plant", "atolye", "workshop")

MECH_MAX = 0.55          # one mechanism for more than this share of scenes is monotony
CAM_MAX = 0.60           # one camera move for more than this share
DUP_SHARE = 0.34         # this share of scenes with the same picture is a duplicate film
COPY = 0.80              # reference similarity at or above this is copying
COPY_PENALTY = {"palette": 22, "cameras": 22, "mechanisms": 18, "seconds": 18, "composition": 20}

BRIEF = """ORIGINALITY (binding: the film must be about this subject, not about its metaphor)
- Show the thing itself, not the symbol of it: a price line, the actual pipeline, the real street. A lightbulb, a
  rocket, a handshake, gears, a target, a puzzle piece, a piggy bank, a magnifying glass, a chess piece, a trophy,
  a thumbs-up or question marks are a stock picture for an idea; they read as generated.
- Do not give the whole film one mechanism and one camera move: at least three different mechanisms and three
  different moves, and no mechanism on more than half the scenes.
- No two scenes may show the same picture with a new label.
- If you borrow a reference's look, borrow its grammar, not its signature: the same palette + the same camera order +
  the same beat lengths is a copy, and the gate refuses it.
"""


def _fold(text):
    return words.fold(text)


def _scenes(plan):
    """Narrative scenes only; factory-generated chapter cards are visual chrome, not story beats."""
    return [sc for sc in (plan or {}).get("scenes") or [] if not sc.get("card")]


def _scene_text(sc, lines):
    a, b = (sc.get("lines") or [0, 0])[:2]
    said = " ".join(str(lines[i]) for i in range(a, b + 1) if 0 <= i < len(lines))
    return " ".join([str(sc.get("shows") or ""), said, str(sc.get("html") or ""), str(sc.get("notes") or "")])


def cliche(plan, lines=()):
    """[(scene id, the metaphor, the word that matched)] for pictures that stand in for the idea."""
    out = []
    for i, sc in enumerate(_scenes(plan)):
        text = _scene_text(sc, lines)
        if any(words.has_phrase(text, w) for w in LITERAL):
            continue                     # the literal thing is the subject, not a metaphor for it
        for name, hits in CLICHE.items():
            hit = next((h for h in hits if words.has_phrase(text, h)), None)
            if hit:
                out.append((sc.get("id") or i, name, hit))
                break
    return out


def _share(values, minimum=2):
    """(the most common value, its share) or (None, 0.0)."""
    vals = [v for v in values if v]
    if len(vals) < minimum:
        return None, 0.0
    top = max(set(vals), key=vals.count)
    return top, vals.count(top) / len(vals)


def monotony(plan):
    """Findings for a film with one mechanism / one move / one scene length: the picture stops carrying information."""
    scenes = _scenes(plan)
    out = []
    mech, mshare = _share([str(sc.get("mechanism") or "").strip().lower() for sc in scenes])
    if mech and mshare > MECH_MAX:
        out.append(f"'{mech}' is the mechanism of {round(100 * mshare)} % of the scenes: the film makes one argument "
                   f"{len(scenes)} times; give the middle scenes their own mechanism")
    moves = [camera.parse(sc.get("camera"))["move"] for sc in scenes]
    mv, vshare = _share(moves)
    if mv and vshare > CAM_MAX:
        out.append(f"'{mv}' is the camera move of {round(100 * vshare)} % of the scenes: vary the move with what each "
                   f"beat means")
    lengths = []
    for sc in scenes:
        c = camera.parse(sc.get("camera"))
        if c["seconds"]:
            lengths.append(round(c["seconds"], 1))
    ln, lshare = _share(lengths, minimum=3)
    if ln and lshare > 0.7:
        out.append(f"every camera move lasts {ln:g} s: the scenes have one length, so nothing accelerates or rests")
    return out


def _lines_per_scene(plan):
    out = []
    for sc in (plan or {}).get("scenes") or []:
        a, b = (sc.get("lines") or [0, 0])[:2]
        out.append(max(1, b - a + 1))
    return out


def signature(plan, lines=()):
    """A plan's originality signature: palette, camera order, mechanism order, beat lengths.

    The shape a reference work is described in, so a plan can be compared with one (`similarity`). Only what decides
    whether the film looks like the reference, nothing about the words.
    """
    plan = plan or {}
    pal = plan.get("palette") or {}
    colours = {str(v).lower() for v in pal.values() if isinstance(v, str) and str(v).startswith("#")} if isinstance(pal, dict) \
        else {str(v).lower() for v in pal if str(v).startswith("#")}
    scenes = _scenes(plan)
    durations, compositions = [], []
    for sc in scenes:
        c = camera.parse(sc.get("camera"))
        sec = c.get("seconds")
        durations.append(round(sec * 2) / 2 if sec else None)
        composition = str(sc.get("composition") or sc.get("shows") or c.get("target") or "")
        compositions.append(" ".join(words.tokens(composition)))
    return {"palette": sorted(colours),
            "cameras": [camera.parse(sc.get("camera"))["move"] for sc in scenes],
            "mechanisms": [str(sc.get("mechanism") or "").strip().lower() for sc in scenes],
            "seconds": durations, "composition": compositions}


def _jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def _order(a, b):
    """Share of positions where two equal-length sequences agree (the order, not the set)."""
    a, b = [x for x in a if x], [x for x in b if x]
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    return sum(1 for x, y in zip(a[:n], b[:n]) if x == y) / n


def similarity(a, b):
    """How much of `b`'s signature `a` repeats, 0-1, with the part that matched."""
    parts = {"palette": _jaccard(a.get("palette") or [], b.get("palette") or []),
             "cameras": _order(a.get("cameras") or [], b.get("cameras") or []),
             "mechanisms": _order(a.get("mechanisms") or [], b.get("mechanisms") or []),
             "seconds": _order(a.get("seconds") or [], b.get("seconds") or []),
             "composition": _order(a.get("composition") or [], b.get("composition") or [])}
    return round(sum(parts.values()) / len(parts), 3), parts


def check(plan, lines=(), references=()):
    """The 0-100 originality score and its findings: {score, verdict, findings, parts}.

    `references` are signatures of the works the plan says it borrows from (a research `visual_refs` entry may be one).
    A plan with no reference declared is scored on cliché and monotony alone.
    """
    findings, score = [], 100.0
    seen = cliche(plan, lines)
    for sid, name, hit in seen:
        findings.append({"kind": "cliche", "scene": sid, "severity": "warn",
                         "detail": f"scene {sid} shows '{hit}': the stock picture for {name}, not the subject"})
    score -= min(36, 12 * len(seen))
    for detail in monotony(plan):
        findings.append({"kind": "monotony", "scene": None, "severity": "warn", "detail": detail})
        score -= 12
    shows = [words.fold(str(sc.get("shows") or "")).strip() for sc in _scenes(plan)]
    dupes = {s: shows.count(s) for s in shows if s and shows.count(s) > 1}
    if dupes:
        worst = max(dupes.values())
        findings.append({"kind": "duplicate", "scene": None, "severity": "warn",
                         "detail": f"{sum(dupes.values())} scenes repeat a picture another scene already shows"})
        score -= min(24, 10 * worst)
    copy = 0.0
    for ref in references or ():
        if not isinstance(ref, dict):
            continue
        sim, parts = similarity(signature(plan, lines), ref)
        copy = max(copy, sim)
        if sim >= COPY:
            close = ", ".join(k for k, v in parts.items() if v >= 0.8) or "signature"
            past = ref.get("kind") == "past_film"
            findings.append({"kind": "copy", "scene": None, "severity": "warn" if past else "block",
                             "detail": f"the plan repeats {round(100 * sim)} % of "
                                       f"{'a previous film' if past else 'the reference work'}'s signature "
                                       f"({close}): vary the composition and timing"})
            score -= (8 if past else (sum(COPY_PENALTY[k] for k, v in parts.items() if v >= 0.8) or 40))
    score = int(max(0, min(100, round(score))))
    verdict = "distinct" if score >= 75 else "derivative" if score >= 55 else "copy"
    return {"score": score, "verdict": verdict, "findings": findings,
            "parts": {"cliche": len(seen), "copy": copy}}


def problems(plan, lines=(), references=()):
    """The blocking subset: what `submit_artifact` refuses on a scene plan, in short sentences."""
    out = []
    seen = cliche(plan, lines)
    if len(seen) >= 3:
        out.append(f"{len(seen)} scenes are stock metaphors ({', '.join(name for _, name, _ in seen[:4])}): show the "
                   f"subject itself")
    scenes = _scenes(plan)
    shows = [words.fold(str(sc.get("shows") or "")).strip() for sc in scenes]
    dup = {s: shows.count(s) for s in shows if s and shows.count(s) > 1}
    if dup and sum(dup.values()) >= max(2, round(DUP_SHARE * len(scenes))):
        out.append(f"{sum(dup.values())} of {len(scenes)} scenes show a picture another scene already shows: give "
                   f"each beat its own picture")
    out.extend(monotony(plan))
    if len(scenes) >= 3:
        moves = {camera.parse(sc.get("camera"))["move"] for sc in scenes} - {None}
        if len(moves) < 3:
            out.append(f"the film uses {len(moves)} camera move(s) across {len(scenes)} scenes; use at least three"
                       " distinct moves")
        mechanisms = {str(sc.get("mechanism") or "").strip().lower() for sc in scenes} - {""}
        if mechanisms and len(mechanisms) < 3:
            out.append(f"the film uses {len(mechanisms)} visual mechanism(s) across {len(scenes)} scenes; use at least"
                       " three distinct mechanisms")
    res = check(plan, lines, references)
    out += [f["detail"] for f in res["findings"] if f["severity"] == "block"]
    return out


def summary(result, lang="tr"):
    """One line for the creator: the score, the verdict and the first finding."""
    first = (result.get("findings") or [{}])[0].get("detail", "")
    if lang == "en":
        return f"Originality {result['score']}/100 ({result['verdict']})." + (f" {first}" if first else "")
    return f"Özgünlük {result['score']}/100 ({result['verdict']})." + (f" {first}" if first else "")


def brief(p=None):
    return BRIEF
