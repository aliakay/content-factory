"""The cold test: can someone who has not seen the film say what it is about, in one sentence?

A script can pass every rule and still be about nothing. The throughline is invisible to the writer, who knows what
they meant, and invisible to the reviewer, who has just read the plan. The cold test is the viewer's test:

  throughline   the subject line 1 opens on is still the subject of the last line before the call to action. A film
                that starts on gas prices and ends on "innovation" is two films.
  two_subjects  two different subjects each carry a large share of the lines and never share one: the film argues two
                things and the viewer remembers neither.
  late_subject  the thing the title names first appears in the second half: the film spent its hook on something else.
  promise       the title or hook asks a question ("nasıl", "neden", "kaç", "how", "why") and the closing line does
                not answer it: the viewer leaves with the question they came with.

The four are deterministic and run at the script gate. `cold_read()` is the human half, run from a tool: a model that
has not seen the film reads the lines and says in one sentence what it is about, and the answer is compared with the
title. It costs one call and it is never part of the deterministic path.
"""
import hashlib, json, re

from . import words

CTA = ("takip et", "takip edin", "abone ol", "daha fazlasi", "follow for more", "follow me", "subscribe",
       "like and follow", "begen ve takip")
QUESTION = {
    "tr": ("nasil", "neden", "nicin", "kac", "ne zaman", "kim", "nerede", "mi ", "mu ", "midir", "mudur", "?"),
    "en": ("how", "why", "what", "when", "who", "where", "does ", "is ", "can ", "?"),
}
ANSWER = {
    "tr": ("cunku", "bu yuzden", "nedeniyle", "dolayisiyla", "sonuc", "demek ki", "yani", "aslinda", "gercek",
           "olctuk", "hesapladik", "bulduk"),
    "en": ("because", "so ", "therefore", "as a result", "the reason", "actually", "in fact", "turns out", "we found",
           "we measured"),
}
LATE = 0.50              # the title's subject may not first appear after this share of the lines
TWO = 0.40               # a subject on this share of the lines, alone, is one of two subjects

BRIEF = """COLD TEST (binding: a viewer who has not seen the film must be able to say what it is about)
- The subject line 1 opens on is the subject of the last line before the call to action. Do not start on one thing and
  end on another.
- One film, one subject. Two subjects that never meet in a line means the viewer remembers neither.
- The thing the title names appears early, in the first third, not after the turn.
- If the title or the hook asks a question, the closing line answers it: with the figure, the cause or the result.
"""


def _fold(text):
    return words.fold(text)


def content_lines(script, lang="tr"):
    """The lines that carry the film, without a closing call to action."""
    lines = [str(x) for x in (script or {}).get("lines") or []]
    while lines and any(c in _fold(lines[-1]) for c in CTA):
        lines = lines[:-1]
    return lines


def _main_word(text, lang="tr"):
    """The word a line is about: its longest content word (names and figures fold in as themselves)."""
    cs = words.content(text, lang)
    return max(cs, key=len) if cs else ""


def throughline(script, lang="tr"):
    """(share, first subject, last subject): how much of line 1's subject the closing line still carries."""
    lines = content_lines(script, lang)
    if len(lines) < 2:
        return 1.0, "", ""
    head = set(words.content(lines[0], lang))
    tail = set(words.content(lines[-1], lang))
    if not head or not tail:
        return 1.0, "", ""
    shared = head & tail
    carries = bool(shared) or words.shares_content(" ".join(head), " ".join(tail), lang)
    return (1.0 if carries else 0.0, " ".join(sorted(head)), " ".join(sorted(tail)))


def two_subjects(script, lang="tr"):
    """The one pair (word a, word b) of subjects that each own a large share of the lines and never share one.

    Only the strongest pair is reported: a film has one such split or none, and listing every synonym pair of it
    buries the finding."""
    lines = content_lines(script, lang)
    if len(lines) < 4:
        return []
    per_line = [set(words.content(x, lang)) for x in lines]
    counts = {}
    for ws in per_line:
        for w in ws:
            counts[w] = counts.get(w, 0) + 1
    n = len(lines)
    strong = [w for w, c in counts.items() if c >= max(2, round(TWO * n))]
    best = None
    for i, a in enumerate(strong):
        for b in strong[i + 1:]:
            if not any(a in ws and b in ws for ws in per_line):
                rank = counts[a] + counts[b]
                if best is None or rank > best[0]:
                    best = (rank, a, b)
    return [(best[1], best[2])] if best else []


def new_subject(script, lang="tr"):
    """A name the closing line introduces that the film never mentions before: the end is about something else."""
    lines = content_lines(script, lang)
    if len(lines) < 2:
        return []
    title = str((script or {}).get("title") or "")
    before = _fold(title + " " + " ".join(lines[:-1]))
    return [name for name in words.proper_nouns(lines[-1]) if _fold(name) not in before]


def late_subject(script, lang="tr"):
    """No useful title subject appears until the second half -> the hook is about something else."""
    lines = content_lines(script, lang)
    title = str((script or {}).get("title") or "")
    if not lines or not words.content(title, lang):
        return None
    for i, line in enumerate(lines):
        if words.shares_content(title, line, lang):
            return i if i > LATE * len(lines) else None
    return len(lines)                    # never named at all: the title promises a subject the film does not have


def asks(script, lang="tr"):
    """Does the title or the hook ask a question the closing line must answer?"""
    text = _fold(str((script or {}).get("title") or "") + " " + str((script or {}).get("hook") or ""))
    return any(q in text for q in QUESTION.get(lang if lang in QUESTION else "en", QUESTION["en"]))


def answered(script, lang="tr"):
    """Does the closing line answer a question the title asked: a figure, a cause, a result, or the subject back?"""
    lines = content_lines(script, lang)
    if not lines:
        return False
    last = lines[-1]
    low = _fold(last)
    if words.has_number(last, lang) or any(a in low for a in ANSWER.get(lang if lang in ANSWER else "en", ANSWER["en"])):
        return True
    share, head, _ = throughline({"lines": [str((script or {}).get("title") or "")] + lines[-2:]}, lang)
    return share >= 0.5


def findings(script, lang="tr"):
    """[{kind, severity, detail}] for the four cold-test failures."""
    out = []
    share, head, tail = throughline(script, lang)
    if share == 0.0 and not answered(script, lang):
        out.append({"kind": "throughline", "severity": "warn",
                    "detail": f"line 1 is about '{head}' and the closing line is about '{tail}': no word carries "
                              f"across; say what the film was about in the last line"})
    for name in new_subject(script, lang):
        out.append({"kind": "new_subject", "severity": "block",
                    "detail": f"the closing line introduces '{name}', which the film never mentions before: end on "
                              f"the subject it opened on"})
    for a, b in two_subjects(script, lang):
        out.append({"kind": "two_subjects", "severity": "block",
                    "detail": f"'{a}' and '{b}' each carry the film and never appear in the same line: one film, one "
                              f"subject"})
    late = late_subject(script, lang)
    if late is not None:
        n = len(content_lines(script, lang))
        where = "never" if late >= n else f"only at line {late + 1} of {n}"
        out.append({"kind": "late_subject", "severity": "block" if late >= n else "warn",
                    "detail": f"the title's subject appears {where}: name it in the first third"})
    if asks(script, lang) and not answered(script, lang):
        out.append({"kind": "promise", "severity": "warn",
                    "detail": "the title or hook asks a question and the closing line does not answer it: give the "
                              "figure, the cause or the result"})
    return out


def _reaches(sentence, script, lang="tr"):
    """Does the cold reader's sentence reach the film's subject? The title is the test, but the hook says the same
    thing sooner, a proper name (ASELSAN) or a figure carries the subject across languages, and a reader that
    answers in the other language still names it."""
    title = str((script or {}).get("title") or "")
    hook = str((script or {}).get("hook") or "")
    if not words.content(title, lang):
        return True                                   # a title with no content word cannot be compared
    if words.shares_content(title, sentence, lang) or words.shares_content(hook, sentence, lang):
        return True
    folded = words.fold(sentence)
    for name in words.proper_nouns(title) + words.proper_nouns(hook):
        if len(name) > 2 and words.fold(name) in folded:
            return True
    import re as _re
    def nums(text):
        return {x.replace(".", "").replace(",", ".") for x in _re.findall(r"\d[\d.,]*", text)}
    return bool(nums(title + " " + hook) & nums(sentence))


def problems(script, lang="tr"):
    """The blocking cold-test failures, as short sentences for `submit_artifact`."""
    return [f["detail"] for f in findings(script, lang) if f["severity"] == "block"]


LANG = {"tr": "Turkish", "en": "English"}
COLD = """You have not seen this short video and you will not see it. You have only its lines, in order.

Title: {title}
Lines:
{lines}

Answer with ONLY JSON:
{{"one_sentence": "what this film is about, in one sentence, using your own words",
  "throughline": "the one thing it is really about, in two or three words",
  "delivers": true,
  "remembered": "the one phrase or figure you would remember tomorrow"}}
`delivers` is true only if the closing line gives the viewer what the title and the first line promised.
Write `one_sentence` and `throughline` in {language} — the video's language, the same language as the title — and name
the title's subject with the title's own words: a reviewer compares them word for word."""


def cold_read(script, lang="tr", ask=None):
    """One model cold read of the script: {one_sentence, throughline, delivers, remembered, problems}.

    `ask` is injectable (a function taking the prompt and returning parsed JSON) so the check is testable with no
    model. A failed call is a missing check, never a failed stage: `ok` is None and `error` says why.
    """
    ask = ask or _ask
    lines = content_lines(script, lang)
    prompt = COLD.format(title=str((script or {}).get("title") or ""),
                         lines="\n".join(f"{i + 1}. {x}" for i, x in enumerate(lines)),
                         language=LANG.get(lang, LANG["en"]))
    try:
        out = ask(prompt) or {}
    except Exception as e:
        return {"ok": None, "error": f"{type(e).__name__}: {e}"[:200], "problems": []}
    problems = []
    if out.get("delivers") is False:
        problems.append("a cold read says the closing line does not deliver what the title promised")
    sentence = str(out.get("one_sentence") or "")
    if sentence and not _reaches(sentence, script, lang):
        problems.append(f"a cold read of the lines does not reach the title's subject ('{sentence[:120]}')")
    return {"ok": bool(out.get("delivers")) and not problems, "one_sentence": sentence,
            "throughline": out.get("throughline"), "delivers": out.get("delivers"),
            "remembered": out.get("remembered"), "problems": problems}


def fingerprint(script):
    """The title and exact lines the independent reader saw; edits invalidate its verdict."""
    body = {k: (script or {}).get(k) for k in ("title", "hook", "lines")}
    raw = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def guard(pid, sid, d=None):
    """Require a passing cold read of the exact submitted script before its gate can open.

    Only for a script that is written for the film (hookrule.authored): a dub and the creator's own text keep theirs.
    """
    from .hookrule import authored
    from .hat import manifest, project as P
    p = P.load(pid, d)
    if not authored(p["line"], sid):
        return None
    script = P.read_artifact(pid, manifest.stage(manifest.get(p["line"]), sid)["artifact"], d) or {}
    evidence = P.read_artifact(pid, "cold_read", d) or {}
    if evidence.get("fingerprint") != fingerprint(script):
        raise P.GateError("Cold test: run `cold_test` on the exact submitted title and lines before approving.")
    result = evidence.get("result") or {}
    if result.get("ok") is not True:
        details = result.get("problems") or [result.get("error") or "the cold reader did not confirm the film's subject"]
        raise P.GateError("Cold test did not pass; change the script and run it again:\n" + "\n".join("- " + x for x in details))
    return result


def _ask(prompt):
    from . import llm
    return llm.ask(prompt, tools=(), timeout=600, model="haiku")[0]


def summary(result, lang="tr"):
    """One line for the creator from `findings()`: the first failure, or that the cold test passed."""
    blocks = [f for f in result if f["severity"] == "block"]
    if not blocks:
        return "Soğuk test geçti: film tek konuda ve vaadini yerine getiriyor." if lang == "tr" \
            else "Cold test passed: one subject, and the film delivers what it promised."
    return (("Soğuk test: " if lang == "tr" else "Cold test: ") + blocks[0]["detail"])


def brief(p=None):
    return BRIEF
