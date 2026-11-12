"""The review-focus lines code can decide, settled before a model is asked to.

`agent.review_stage` asks a reviewer model for one 0-10 mark per review-focus line. Many of those lines are ordinary
measurements — a source count, a word budget, a claim flag, a hashtag count — and paying a model to read them is waste
with a real failure mode: a reviewer can pass a 40-word script for a 45 s film, or miss a source with no URL. This
module answers those lines the same way every time, and returns None for a line only a reader can judge.

The rule table is keyed by stage id plus a pattern on the line's own text, because one stage id carries different
lines on different production lines (animation.yaml's script has one word-count line per mode). Every check reads the
project and the stage's artifact and writes nothing.
"""
import os
import re

from .. import craftcheck, coldtest, hookrule, licence
from . import manifest, project

FULL = 10        # the line holds
FAIL = 3         # a measurable part of the line does not hold; the note says which, with the numbers
MISSING = 1      # the artifact or evidence the line talks about is not there at all


class _Ctx:
    """What a check may read: the project, the stage entry, and the artifacts it already wrote (cached)."""

    def __init__(self, pid, stage, d=None):
        self.pid, self.stage, self.d = pid, stage, d
        self.p = project.load(pid, d)
        self._arts = {}

    def art(self, name=None):
        name = name or self.stage.get("artifact") or self.stage.get("id")
        if name not in self._arts:
            got = project.read_artifact(self.pid, name, self.d)
            self._arts[name] = got if isinstance(got, dict) else None
        return self._arts[name]

    @property
    def lang(self):
        return self.p.get("video_lang") or "tr"


def _mark(score, note):
    return {"score": max(0, min(10, int(score))), "note": str(note)[:600]}


def _lines(art):
    """Narration lines as strings; an artifact may carry {"text": ...} objects in older projects."""
    out = []
    for line in (art or {}).get("lines") or []:
        if isinstance(line, str):
            out.append(line)
        elif isinstance(line, dict):
            out.append(str(line.get("text") or ""))
        else:
            out.append(str(line))
    return out


def _words(lines):
    return sum(len(str(x).split()) for x in lines)


def _seconds(ctx):
    """The duration the creator approved, from whichever proposal artifact the line writes."""
    for name in ("proposal", "proposal_code", "idea", "outline"):
        got = ctx.art(name)
        try:
            if got and float(got.get("seconds")) > 0:
                return float(got["seconds"])
        except (TypeError, ValueError):
            continue
    return None


def _scenes(art):
    return [s for s in (art or {}).get("scenes") or [] if isinstance(s, dict)]


# ---------------------------------------------------------------- research

def _sources(ctx, line, m):
    """ "At least N sources with URLs; every data point names its source" (and animation's two-count variant)."""
    g = m.groups()
    need = int(g[0])
    need_angles = int(g[1]) if len(g) > 1 and g[1] else 0
    art = ctx.art()
    srcs = art.get("sources") if isinstance(art.get("sources"), list) else []
    urls = [s for s in srcs if isinstance(s, dict) and str(s.get("url") or "").strip().lower().startswith(("http://", "https://"))]
    dps = art.get("data_points") if isinstance(art.get("data_points"), list) else []
    unnamed = [i for i, x in enumerate(dps) if not (isinstance(x, dict) and str(x.get("source") or "").strip())]
    angles = art.get("angles") if isinstance(art.get("angles"), list) else []
    bad = []
    if len(urls) < need:
        bad.append(f"{len(urls)} of {len(srcs)} sources carry an http(s) URL (need {need})")
    if unnamed:
        bad.append(f"{len(unnamed)} of {len(dps)} data points name no source")
    if need_angles and len(angles) < need_angles:
        bad.append(f"{len(angles)} angles (need {need_angles})")
    if bad:
        return _mark(FAIL, "; ".join(bad))
    return _mark(FULL, f"{len(urls)} sources with URLs; all {len(dps)} data points name their source")


def _angles(ctx, line, m):
    """ "At least 3 genuinely different angles": a short list is a definite fail, a long one is the reader's call."""
    need, angles = int(m.group(1)), ctx.art().get("angles") or []
    if not isinstance(angles, list):
        return None
    if len(angles) < need:
        return _mark(FAIL, f"{len(angles)} angles (need {need})")
    return None


# ---------------------------------------------------------------- script

def _wordcount(ctx, line, m):
    """ "Word count fits the approved duration within 10%" — the film's own words against its own seconds."""
    art = ctx.art()
    if art.get("narrate") is False:          # music-led: its contract is the holds line, not a word budget
        return None
    secs = _seconds(ctx)
    if secs is None:
        return None
    n = _words(_lines(art))
    wps = hookrule.WPS.get(ctx.lang, 2.5)
    lo, hi = secs * wps * 0.9, secs * wps * 1.1
    if lo <= n <= hi:
        return _mark(FULL, f"{n} words at {wps} words/s ≈ {n / wps:.1f} s against an approved {secs:g} s "
                           f"({lo:.0f}–{hi:.0f} words allowed)")
    return _mark(FAIL, f"{n} words at {wps} words/s ≈ {n / wps:.1f} s; the approved {secs:g} s allows "
                       f"{lo:.0f}–{hi:.0f} words (10%)")


def _musicled(ctx, line, m):
    """The animation script's music-led contract: <= 7 words a line, one hold each, holds sum to the length."""
    art = ctx.art()
    if art.get("narrate") is not False:
        return None
    lines = _lines(art)
    holds = art.get("holds") if isinstance(art.get("holds"), list) else []
    bad = []
    long_ = [i for i, l in enumerate(lines) if len(l.split()) > 7]
    if long_:
        bad.append(f"{len(long_)} line(s) over 7 words (line {long_[0] + 1} has {len(lines[long_[0]].split())})")
    if len(holds) != len(lines):
        bad.append(f"{len(holds)} holds for {len(lines)} lines")
    secs = _seconds(ctx)
    if secs is None:
        return _mark(FAIL, "; ".join(bad)) if bad else None
    try:
        total = sum(float(h) for h in holds)
    except (TypeError, ValueError):
        return _mark(FAIL, "a hold is not a number of seconds")
    if len(holds) == len(lines) and not (secs * 0.9 <= total <= secs * 1.1):
        bad.append(f"holds add up to {total:.1f} s against an approved {secs:g} s")
    if bad:
        return _mark(FAIL, "; ".join(bad))
    return _mark(FULL, f"{len(lines)} lines of at most 7 words; holds add up to {total:.1f} s of {secs:g} s")


def _claims(ctx, line, m):
    """ "Every factual claim is marked verified with a source, or removed": a flag and a source, read from the file."""
    claims = ctx.art().get("claims")
    if not isinstance(claims, list) or not claims:
        return None                    # nothing declared: whether a claim was removed is the reader's call
    bad = [c for c in claims if not (isinstance(c, dict) and c.get("verified") is True
                                     and str(c.get("source") or "").strip())]
    if bad:
        return _mark(FAIL, f"{len(bad)} of {len(claims)} claims are not marked verified with a source")
    # every DECLARED claim is in order; whether a line makes a claim that is not in the list at all is reading, and
    # that is the half the reviewer found wrong in real films (project 121, line 4): code can fail this line, not pass it
    return None


def _wordscheck(ctx, line, m):
    found = craftcheck.words_check(_lines(ctx.art()), ctx.lang)
    if found:
        kinds = sorted({f["kind"] for f in found})
        return _mark(FAIL, f"{len(found)} finding(s) ({', '.join(kinds)}): {found[0]['detail']}")
    return _mark(FULL, "no dashes, stock phrasing or greeting in the lines")


def _hookrule(ctx, line, m):
    if not hookrule.authored(ctx.p.get("line"), ctx.stage.get("id")):
        return None                    # a dub or the creator's own text is not written to this rule
    found = hookrule.problems(ctx.art(), ctx.lang)
    if found:
        return _mark(FAIL, " | ".join(found))
    return _mark(FULL, "line 1 is within the hook budget and shares the title's subject")


def _coldtest(ctx, line, m):
    if not hookrule.authored(ctx.p.get("line"), ctx.stage.get("id")):
        return None
    art, evidence = ctx.art(), ctx.art("cold_read")
    if not evidence:
        return _mark(MISSING, "no cold_read evidence: run cold_test on this title and these lines")
    if evidence.get("fingerprint") != coldtest.fingerprint(art):
        return _mark(MISSING, "the cold_read evidence is for a different title or lines: run cold_test again")
    result = evidence.get("result") or {}
    if result.get("ok") is True and not result.get("problems"):
        said = str(result.get("one_sentence") or "")[:120]
        return _mark(FULL, f"the cold reader said: {said}")
    found = result.get("problems") or [result.get("error") or "the cold reader did not confirm the subject"]
    return _mark(FAIL, "; ".join(str(x) for x in found))


# ---------------------------------------------------------------- scene plan

def _coverage_trigger(ctx, line, m):
    """ "Scenes cover the whole script with no gaps; every scene has a trigger word" — ranges plus presence."""
    scenes, lines = _scenes(ctx.art()), _lines(ctx.art("script"))
    if not scenes or not lines:
        return None
    covered, bad_ranges = set(), []
    for i, sc in enumerate(scenes):
        r = sc.get("lines")
        if not (isinstance(r, list) and len(r) == 2):
            bad_ranges.append(i + 1)
            continue
        try:
            covered.update(range(int(r[0]), int(r[1]) + 1))
        except (TypeError, ValueError):
            bad_ranges.append(i + 1)
    missing = sorted(set(range(len(lines))) - covered)
    extra = sorted(covered - set(range(len(lines))))
    no_trigger = [sc.get("id") or f"scene {i + 1}" for i, sc in enumerate(scenes)
                  if not str(sc.get("trigger") or "").strip()]
    bad = []
    if bad_ranges:
        bad.append(f"scene(s) {bad_ranges} have no [first, last] line range")
    if missing:
        bad.append(f"line(s) {[i + 1 for i in missing]} are shown by no scene")
    if extra:
        bad.append(f"line number(s) {[i + 1 for i in extra]} point past the script")
    if no_trigger:
        bad.append(f"{len(no_trigger)} scene(s) have no trigger word: {', '.join(map(str, no_trigger[:4]))}")
    if bad:
        return _mark(FAIL, "; ".join(bad))
    return _mark(FULL, f"{len(scenes)} scenes cover all {len(lines)} lines and each names its trigger")


def _devices(ctx, line, m):
    """ "No two consecutive scenes use the same visual device" — compare the named device or mechanism."""
    scenes = _scenes(ctx.art())
    labels = [str(sc.get("device") or sc.get("mechanism") or "").strip() for sc in scenes]
    if len(scenes) < 2 or not all(labels):
        return None                    # scenes name neither field: only a reader can tell two devices apart
    dups = [i for i in range(1, len(labels)) if labels[i] == labels[i - 1]]
    if dups:
        return _mark(FAIL, f"{len(dups)} consecutive pair(s) repeat the device '{labels[dups[0]]}' "
                           f"(scenes {dups[0]}–{dups[0] + 1})")
    return _mark(FULL, f"{len(scenes)} scenes; no device repeats back to back")


def _rhythm(ctx, line, m):
    """The same measurement the `rhythm_check` tool makes: scene word counts through craftcheck.rhythm."""
    scenes, lines = _scenes(ctx.art()), _lines(ctx.art("script"))
    sizes = []
    for sc in scenes:
        r = sc.get("lines")
        if not (isinstance(r, list) and len(r) == 2):
            return None
        try:
            sizes.append(_words(lines[int(r[0]):int(r[1]) + 1]))
        except (TypeError, ValueError, IndexError):
            return None
    if len(sizes) < 4:
        return None                    # the check says nothing below four scenes
    found = craftcheck.rhythm(sizes)
    if found:
        return _mark(FAIL, " | ".join(f["detail"] for f in found))
    return _mark(FULL, f"{len(sizes)} scenes vary in length with the idea")


# ---------------------------------------------------------------- animatic

def _animatic_lines(ctx, line, m):
    """ "Every script line is shown by a scene; no scene reads faster than the voice can speak"."""
    scenes, lines = _scenes(ctx.art()), _lines(ctx.art("script"))
    if not scenes or not lines:
        return None
    covered = set()
    for sc in scenes:
        r = sc.get("lines")
        if isinstance(r, list) and len(r) == 2:
            try:
                covered.update(range(int(r[0]), int(r[1]) + 1))
            except (TypeError, ValueError):
                pass
    missing = sorted(set(range(len(lines))) - covered)
    wps = hookrule.WPS.get(ctx.lang, 2.5)
    fast = []
    for sc in scenes:
        try:
            words, spoken = float(sc.get("words") or 0), float(sc.get("spoken") or sc.get("seconds") or 0)
        except (TypeError, ValueError):
            continue
        if words and spoken and words / spoken > wps * 1.05:
            fast.append((sc.get("id") or "?", words / spoken))
    bad = []
    if missing:
        bad.append(f"line(s) {[i + 1 for i in missing]} are shown by no scene")
    if fast:
        bad.append(f"{len(fast)} scene(s) read faster than {wps} words/s, e.g. '{fast[0][0]}' at {fast[0][1]:.2f}")
    if bad:
        return _mark(FAIL, "; ".join(bad))
    return _mark(FULL, f"all {len(lines)} lines are shown and no scene reads over {wps} words/s")


def _animatic_motion(ctx, line, m):
    """ "The picture moves in the first two seconds and never sits still for long": the hook rule's own opening test."""
    found = hookrule.animatic_problems(ctx.art())
    if found:
        return _mark(FAIL, " | ".join(found))
    return _mark(FULL, "motion starts at once and no still hold fills a second of the first two")


# ---------------------------------------------------------------- assets

def _budget(ctx, line, m):
    """ "Spend stays inside the approved budget" — the running credit spend against the creator's cap.

    The spend is the one the code side already enforces (`spent_credits`: every stage's cost plus the generated
    clips), so the review and the budget guard can never disagree. Only credits are an approval ceiling; the budget's
    usd figure is an estimate.
    """
    try:
        cap = float((ctx.p.get("budget") or {})["credits"])
    except (KeyError, TypeError, ValueError):
        return None
    from .explainer import spent_credits
    spent = float(spent_credits(ctx.pid, ctx.d))
    if spent > cap:
        return _mark(FAIL, f"credits {spent:.0f} > {cap:g}")
    return _mark(FULL, f"{spent:.0f} of {cap:g} credits spent")


# ---------------------------------------------------------------- publish

def _caption(ctx, line, m):
    """The two measurable parts of the caption line; the language check stays with the reader."""
    cap = str(ctx.art().get("caption") or "")
    if not cap.strip():
        return _mark(MISSING, "no caption")
    bad = []
    if len(cap) >= 150:
        bad.append(f"{len(cap)} characters (must be under 150)")
    if not cap.rstrip().endswith("?"):
        bad.append("it does not end with a question mark")
    if bad:
        return _mark(FAIL, "; ".join(bad) + f"; the language ({ctx.lang}) was not verified by code")
    return _mark(FULL, f"{len(cap)} characters and it ends with a question; the language ({ctx.lang}) is the "
                       f"reader's check")


def _hashtags(ctx, line, m):
    """ "3–5 hashtags": a wrong count is a definite fail; the right count still needs a reader for "match the topic"."""
    lo, hi = int(m.group(1)), int(m.group(2))
    tags = ctx.art().get("hashtags")
    tags = tags if isinstance(tags, list) else []
    if not lo <= len(tags) <= hi:
        return _mark(FAIL, f"{len(tags)} hashtags (need {lo}–{hi})")
    return None


def _title_len(ctx, line, m):
    """ "Title ... under N characters": too long is a definite fail; language and promise are the reader's."""
    limit = int(m.group(1))
    title = str(ctx.art().get("title") or "")
    if not title:
        return None
    if len(title) > limit:
        return _mark(FAIL, f"the title is {len(title)} characters (limit {limit})")
    return None


def _ledger(ctx):
    """The attribution ledger minus the source-clip half.

    `licence.entries()` also reads the studio database (source clips); a review must not open or write the store, so
    the half that needs it is skipped. The lines this rule serves (explainer, long_explainer, animation) are drawn
    from code and carry no source clips; `_credits` returns None if such an artifact exists, so the comparison is
    never made on a film where the skipped half would matter.
    """
    plan, assets = ctx.art("scene_plan") or {}, ctx.art("assets") or {}
    stocks, sfx, typefaces = licence.stock_entries(plan), licence.builtin_sfx(plan), licence.fonts(plan)
    plates, made = licence.plate_entries(ctx.pid, ctx.d), licence.made_entries(assets)
    known = [r.get("file") for r in stocks + sfx + plates + made + typefaces]
    rows = stocks + licence.untracked_media({**plan, "project_id": ctx.pid}, known) + sfx + plates + made + typefaces
    unique, seen = [], set()
    for row in rows:
        key = os.path.normpath(str(row.get("file") or row.get("url") or row.get("what") or ""))
        if key and key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def _flat(text):
    return " ".join(str(text or "").split())


def _credits(ctx, line, m):
    """ "`credits` is the attribution tool's block verbatim; no asset is unlicensed"."""
    if any(ctx.art(n) for n in ("shot_list", "cut_plan", "capture")):
        return None                    # credits there include source clips, whose ledger needs the studio database
    rows = _ledger(ctx)
    missing = licence.missing(rows)
    if missing:
        return _mark(FAIL, f"{len(missing)} asset(s) have no known licence: "
                           + ", ".join(str(r.get("file")) for r in missing[:4]))
    want = licence.block(rows, ctx.lang)
    got = _flat(ctx.art().get("credits"))
    if got != _flat(want):
        return _mark(FAIL, f"credits is not the attribution block verbatim (expected {_flat(want)[:200]!r}, "
                           f"found {got[:200]!r})")
    return _mark(FULL, "credits is the attribution block verbatim and every asset has a known licence")


# ---------------------------------------------------------------- the table
# (stage id, pattern on the review line, check). The first match wins; a line that matches nothing is a model's job.
RULES = (
    ("research", re.compile(r"At least (\d+) sources with URLs", re.I), _sources),
    ("research", re.compile(r"At least (\d+) sources and (\d+) different angles", re.I), _sources),
    ("research", re.compile(r"At least (\d+) (?:genuinely )?different angles", re.I), _angles),
    ("script", re.compile(r"^Word count fits the approved duration", re.I), _wordcount),
    ("script", re.compile(r"^Music-led: every line is short", re.I), _musicled),
    ("script", re.compile(r"^Narrated: word count fits", re.I), _wordcount),
    ("script", re.compile(r"^Every factual claim is marked verified", re.I), _claims),
    ("script", re.compile(r"^words_check has no open findings", re.I), _wordscheck),
    ("script", re.compile(r"^The hook rule holds", re.I), _hookrule),
    ("script", re.compile(r"^The cold test passes", re.I), _coldtest),
    ("scene_plan", re.compile(r"^Scenes cover the whole script with no gaps", re.I), _coverage_trigger),
    ("scene_plan", re.compile(r"^No two consecutive scenes use the same visual device", re.I), _devices),
    ("scene_plan", re.compile(r"^rhythm_check is clean", re.I), _rhythm),
    ("animatic", re.compile(r"^Every script line is shown by a scene", re.I), _animatic_lines),
    ("animatic", re.compile(r"^The picture moves in the first two seconds", re.I), _animatic_motion),
    ("assets", re.compile(r"^Spend stays inside the approved budget", re.I), _budget),
    ("publish", re.compile(r"^Caption in the video's language", re.I), _caption),
    ("publish", re.compile(r"^Title in the video's language, under (\d+) characters", re.I), _title_len),
    ("publish", re.compile(r"^(\d+)[–-](\d+) hashtags", re.I), _hashtags),
    ("publish", re.compile(r"^`credits` is the attribution tool", re.I), _credits),
)


def _rule(stage_id, line):
    for sid, pattern, check in RULES:
        if sid == stage_id and isinstance(line, str) and pattern.search(line):
            return pattern, check
    return None


def settle(pid, stage, d=None):
    """One entry per line of stage["review"], in order: None when only a model can judge it, else {score, note}.

    A line is settled only when code decides it: 10 when it holds, a low score with the numbers when it does not.
    Never raises: a failed project load or a broken artifact gives None for the lines it touches.
    """
    review = [str(x) if isinstance(x, str) else x for x in (stage or {}).get("review") or []]
    try:
        ctx = _Ctx(pid, stage, d)
        have_artifact = bool(ctx.art())
    except Exception:
        return [None] * len(review)
    out = []
    out = []
    for line in review:
        if not have_artifact:
            out.append(None)
            continue
        try:
            found = _rule(stage.get("id"), line)
            got = found[1](ctx, line, found[0].search(line)) if found else None
            out.append(got if isinstance(got, dict) else None)
        except Exception:
            out.append(None)
    return out


def coverage(line_id):
    """{stage_id: [True per review line a rule exists for]} so the lead can print how much of a rubric is code-decided."""
    m = manifest.get(line_id)
    return {s["id"]: [bool(_rule(s["id"], line)) for line in s.get("review") or []] for s in m["stages"]}
