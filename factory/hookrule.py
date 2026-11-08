"""The hook rule, enforced: the first line must land under three seconds, say something concrete, and be about this film.

`craftcheck.words_check` already flags a greeting opener and stock phrasing, and the animatic measures how long the
first line takes once there is timing. Both are too late or too soft: by the time the animatic runs, the script is
approved and the scene plan is drawn on top of it, and a warning at a gate is a suggestion.

This is the gate rule. At the script gate the line is measured against what the voice can actually say in three
seconds at the language's speaking rate, and it must pass four checks: short enough, not a greeting or stock opener,
carrying something concrete (a figure, a name, or a stated contrast), and sharing its subject with the title. A film
whose first line is "Fiyatlar şaşırtıcı" has no hook, however well it is drawn.
"""
import math, re

from . import craftcheck, words

HOOK_S = 3.0
CONCRETE = ("but", "yet", "despite", "ama", "oysa", "rağmen", "ragmen", "fakat", "ancak", "yine de", "halbuki")
WPS = {"tr": 2.4, "en": 2.6}


def word_limit(lang="tr", wps=None):
    """How many words the voice can say in HOOK_S seconds."""
    return max(3, int(math.floor((wps or WPS.get(lang, 2.5)) * HOOK_S)))


def _concrete(line, lang="tr"):
    return bool(words.has_number(line, lang) or words.proper_nouns(line)
                or any(words.has_phrase(line, c) for c in CONCRETE))


def problems(script, lang="tr", wps=None, title=None):
    """What the script gate refuses. `script` is the artifact (or a draft): lines, hook, title."""
    lines = [str(x) for x in (script or {}).get("lines") or []]
    if not lines:
        return ["the script has no lines"]
    limit = word_limit(lang, wps)
    out, first = [], lines[0]
    n = len(first.split())
    if n > limit:
        out.append(f"the hook is {n} words: at {wps or WPS.get(lang, 2.5)} words/s that is over {HOOK_S:g} s. "
                   f"Cut it to {limit} words or fewer.")
    for f in craftcheck.words_check(lines[:1], lang):
        if f["kind"] in ("greeting", "stock_phrase"):
            out.append(f"the hook opens on {f['kind']}: {f['detail']}")
    if not _concrete(first, lang):
        out.append("the hook says nothing concrete: no figure, no name, no contrast. Open on the fact that surprises.")
    head = (title if title is not None else (script or {}).get("title")) or ""
    if head:
        shared = set(words.content(head, lang)) & set(words.content(first, lang))
        if not shared:
            out.append(f"the hook is not about the title's subject ('{head}'): the first line must name it")
    hook = (script or {}).get("hook")
    if hook and words.fold(str(hook)).strip() != words.fold(first).strip():
        out.append("`hook` and line 1 disagree: the hook is line 1, word for word")
    return out


def authored(line, sid):
    """Is this stage's script written for the film (rather than derived from a source: a dub, the creator's own text)?

    The hook rule judges writing. A translation must mirror its original and a talking head speaks the creator's
    words, so those lines keep their own text; an agent that writes the words opens on the fact that surprises.
    """
    from .hat import manifest
    st = manifest.stage(manifest.get(line), sid)
    return st.get("run") == "agent" and st.get("artifact") in ("script", "long_script")


def guard(pid, sid, d=None):
    """Refuse the script gate while the hook breaks the rule. Runs only on an authored script stage."""
    from .hat import manifest, project as P
    p = P.load(pid, d)
    if not authored(p["line"], sid):
        return None
    artifact = manifest.stage(manifest.get(p["line"]), sid)["artifact"]
    art = P.read_artifact(pid, artifact, d) or {}
    lang = p.get("video_lang") or "tr"
    found = problems(art, lang)
    if found:
        ui = p.get("ui_lang") if p.get("ui_lang") in ("tr", "en") else "tr"
        head = {"tr": "Kanca kuralı: ilk satır kapıyı geçmiyor. Notla düzelttir:",
                "en": "Hook rule: the first line does not pass the gate. Fix it with a note:"}[ui]
        raise P.GateError(head + "\n" + "\n".join("- " + x for x in found))
    return found


def animatic_problems(artifact):
    """Hard opening-motion rule: no still hold may occupy a full second in the first two seconds."""
    motion = (artifact or {}).get("motion") or {}
    holds = motion.get("holds") or []
    for row in holds:
        try:
            start, seconds = float(row[0]), float(row[1])
        except (TypeError, ValueError, IndexError):
            continue
        overlap = max(0.0, min(2.0, start + seconds) - max(0.0, start))
        if overlap >= 1.0:
            return [f"the opening stays still for {overlap:.1f} s in its first 2 s; movement must start at once"]
    if motion.get("still_share") is None:
        return ["the opening-motion check could not measure the animatic; render the draft again before approving"]
    return []


def brief(p=None):
    return (f"HOOK RULE (binding, the gate enforces it)\n"
            f"Line 1 must be sayable in under {HOOK_S:g} s at the video language's speaking rate "
            f"({word_limit('tr')} words in Turkish, {word_limit('en')} in English). It must carry something concrete "
            f"(a figure, a name, or a stated contrast), must not open on a greeting or stock phrasing, and must share "
            f"its subject with the title. `hook` is line 1 word for word.")
