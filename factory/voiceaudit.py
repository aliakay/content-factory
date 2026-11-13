"""Voice stem audit: free checks on the narration take ALONE (no music, no effects), ported from AI-Video-Factory's
voice audit (F53) and widened with the things that make a take sound wrong. Numpy + the word timings; whisper only when
asked for the misread check. Same finding shape as soundqa ({kind, severity, detail, t}) so `soundqa.as_text` prints it.

  word_gap     a pause over 0.40 s INSIDE a script line (not after a sentence end): the voice stalled or the aligner lost words
  word_silent  the aligner put a word where the voice stem is silent (> 0.40 s of < -50 dBFS inside the word's window)
  level_jump   two adjacent lines differ by more than 12 dB (voiced RMS): one of them was voiced louder / softer
  clipped      the stem has runs of samples at full scale (>= -0.1 dBFS): the TTS or a processing step clipped
  pace         a line spoken much faster / slower than the take's own median (characters of SPOKEN text per second)
  misread      whisper heard a word that is not the expected spoken word (the TTS read it differently, e.g. a number or a
               foreign name); low confidence words are listed as info. Needs `heard` (whisper words) — optional.

`words` are [[token, start, end]] of the voice file in the script's own spelling (explainer.align_words); the expected
SPOKEN text comes from factory/speech_tr.py, the same text the TTS was given.
"""
import difflib

import numpy as np

from . import soundqa, speech_tr

GAP_S = 0.40            # inner word gap / silence inside a word window
QUIET_DB = -50.0        # F53: a 100 ms block under this is quiet
JUMP_DB = 12.0          # level difference between adjacent lines
CLIP_AT = 0.99          # |sample| at or above this ...
CLIP_RUN = 3            # ... for this many samples in a row is a clipped peak
FAST, SLOW = 1.5, 0.6   # pace outliers: x the median chars/s
MIN_LINE_S = 0.8        # shorter lines have no meaningful pace
LOW_PROB = 0.35         # whisper word probability under this is "low confidence"
SENTENCE_END = (".", "!", "?", "…")


def _norm(w):
    from .explainer import _norm as n
    return n(w)


def line_ranges(words, lines=None):
    """[(i0, i1)] word-index range of every script line (token count per line, as productions.align counts them); without
    lines, sentences (a word ending in . ! ? …)."""
    out, k = [], 0
    if lines:
        for ln in lines:
            n = len([w for w in ln.split() if _norm(w)])
            if n:
                out.append((k, min(k + n, len(words))))
            k += n
        return [r for r in out if r[1] > r[0]]
    start = 0
    for i, w in enumerate(words):
        if str(w[0]).rstrip("\"')]”’").endswith(SENTENCE_END) or i == len(words) - 1:
            out.append((start, i + 1))
            start = i + 1
    return out


def _db_frames(y, sr, win):
    n = int(win * sr)
    if len(y) < n:
        return np.array([])
    f = y[:len(y) // n * n].astype(np.float64).reshape(-1, n)
    return soundqa.db(np.sqrt(np.mean(f ** 2, axis=1)))


def line_level(y, sr, a, b, rel_db=25.0):
    """Voiced RMS (dBFS) of y[a:b] seconds: 50 ms frames within `rel_db` of the line's loudest, averaged as power."""
    seg = y[int(a * sr):int(b * sr)]
    lv = _db_frames(seg, sr, 0.05)
    if not len(lv):
        return None
    v = lv[lv > lv.max() - rel_db]
    return float(10 * np.log10(np.mean(10 ** (v / 10))))


def clipped(y, sr):
    """[(start s)] of runs of >= CLIP_RUN samples at or above CLIP_AT."""
    hot = np.abs(y) >= CLIP_AT
    if not hot.any():
        return []
    edges = np.diff(np.concatenate([[0], hot.astype(np.int8), [0]]))
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
    return [round(float(a) / sr, 3) for a, b in zip(starts, ends) if b - a >= CLIP_RUN]


def misreads(plan, heard):
    """(findings, matched share) of whisper's words against the expected spoken tokens. Respelled / numeric groups are
    skipped (whisper writes digits and its own spelling for them); plain words that were replaced by something different,
    runs of missing words and low-confidence words are reported."""
    exp = [(t, g.kind) for g in plan.groups for t in g.spoken if _norm(t)]
    en = [_norm(t) for t, _ in exp]
    hn = [_norm(h[0]) for h in heard]
    sm = difflib.SequenceMatcher(None, en, hn, autojunk=False)
    hit = {i for blk in sm.get_matching_blocks() for i in range(blk.a, blk.a + blk.size)}
    plain = [i for i, (_, k) in enumerate(exp) if k == "plain"] or list(range(len(exp)))   # respelled words match by luck
    out, share = [], sum(i in hit for i in plain) / max(1, len(plain))
    if share < 0.5:
        return [{"kind": "misread", "severity": "info", "detail": f"only {round(100 * share)} % of the words matched: whisper "
                 "drifted, the misread check is not reliable on this take"}], share
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                if len(heard[j]) > 3 and heard[j][3] < LOW_PROB and exp[i][1] == "plain":
                    out.append({"kind": "misread", "severity": "info", "t": round(float(heard[j][1]), 2),
                                "detail": f"'{heard[j][0]}' heard with low confidence ({heard[j][3]:.2f}): possible misread"})
        elif op == "replace":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                if exp[i][1] != "plain" or hn[j].isdigit():
                    continue
                if difflib.SequenceMatcher(None, en[i], hn[j]).ratio() < 0.6:
                    out.append({"kind": "misread", "severity": "warn", "t": round(float(heard[j][1]), 2),
                                "detail": f"expected '{exp[i][0]}', heard '{heard[j][0]}': the voice read the word differently"})
        elif op == "delete" and sum(k == "plain" for _, k in exp[i1:i2]) >= 2:
            at = float(heard[j1 - 1][2]) if j1 else 0.0
            out.append({"kind": "misread", "severity": "warn", "t": round(at, 2),
                        "detail": "words skipped by the voice: " + " ".join(t for t, _ in exp[i1:i2][:6])})
    return out[:12], share


def audit(path=None, words=None, lines=None, lang="tr", pron=None, heard=None, y=None, sr=soundqa.SR):
    """-> {"findings": [...], "metrics": {...}} for one voice file.

    words: [[token, start, end]] (explainer.align_words); lines: the script lines (line boundaries + the expected spoken
    text); heard: whisper words [[word, start, end, prob]] for the misread check (None skips it)."""
    words = [list(w) for w in words or []]
    if y is None:
        y = soundqa.decode(path, sr) if path else np.zeros(0, np.float32)
    findings, m = [], {}

    def add(kind, sev, detail, t=None):
        findings.append({"kind": kind, "severity": sev, "detail": detail, **({"t": round(float(t), 2)} if t is not None else {})})

    m["duration"] = round(len(y) / sr, 2)
    if len(y) == 0 or float(np.max(np.abs(y))) < 1e-4:
        add("voice_silent", "fail", "the voice file has no sound")
        return {"findings": findings, "metrics": m}
    peak = float(np.max(np.abs(y)))
    m["peak_db"] = round(float(soundqa.db(peak)), 1)
    runs = clipped(y, sr)
    m["clipped_runs"] = len(runs)
    if runs:
        add("clipped", "warn", f"{len(runs)} clipped peak(s) at {', '.join(f'{t:.2f}s' for t in runs[:5])} (peak {m['peak_db']} dBFS)",
            runs[0])
    ranges = line_ranges(words, lines)
    # --- pauses inside a line
    gaps = []
    for a, b in ranges:
        for i in range(a, b - 1):
            gap = float(words[i + 1][1]) - float(words[i][2])
            if gap > GAP_S and not str(words[i][0]).rstrip("\"')]”’").endswith(SENTENCE_END):
                gaps.append((words[i][2], gap, words[i][0], words[i + 1][0]))
    m["word_gaps"] = len(gaps)
    for t, gap, w1, w2 in gaps[:6]:
        add("word_gap", "warn", f"{gap:.2f} s pause inside a line between '{w1}' and '{w2}'", t)
    # --- a word where the stem is silent
    blocks = _db_frames(y, sr, 0.1)
    if len(blocks):
        quiet = blocks < QUIET_DB
        for w in words:
            a, b = int(float(w[1]) / 0.1), int(float(w[2]) / 0.1 + 0.999)
            seg = quiet[a:min(b, len(quiet))]
            run = best = 0
            for q in seg:
                run = run + 1 if q else 0
                best = max(best, run)
            if best * 0.1 >= GAP_S:
                add("word_silent", "warn", f"'{w[0]}' has {best * 0.1:.1f} s of silence inside its window: the alignment "
                    "or the voice lost this word", w[1])
    # --- level between adjacent lines
    levels = [line_level(y, sr, float(words[a][1]), float(words[b - 1][2])) for a, b in ranges]
    m["line_db"] = [None if x is None else round(x, 1) for x in levels]
    for k in range(1, len(levels)):
        if levels[k] is not None and levels[k - 1] is not None and abs(levels[k] - levels[k - 1]) > JUMP_DB:
            add("level_jump", "warn", f"line {k + 1} is {levels[k] - levels[k - 1]:+.0f} dB against line {k} "
                "(adjacent lines should sit within ~12 dB)", words[ranges[k][0]][1])
    # --- pace of every line against the take's own median
    texts = speech_tr.spoken_lines(lines, lang, pron) if lines else None
    rates = []
    for k, (a, b) in enumerate(ranges):
        dur = float(words[b - 1][2]) - float(words[a][1])
        if texts and k < len(texts):
            chars = len(texts[k].replace(" ", ""))
        else:
            chars = len("".join(str(w[0]) for w in words[a:b]))
        rates.append((chars / dur, k, dur) if dur >= MIN_LINE_S and b - a >= 3 else None)
    ok = [r for r in rates if r]
    if len(ok) >= 4:
        med = float(np.median([r[0] for r in ok]))
        m["chars_per_s"] = round(med, 1)
        for r, rng in zip(rates, ranges):
            if not r:
                continue
            if r[0] > FAST * med:
                add("pace", "warn", f"line {r[1] + 1} is rushed: {r[0]:.1f} characters/s against the take's {med:.1f}",
                    words[rng[0]][1])
            elif r[0] < SLOW * med:
                add("pace", "info", f"line {r[1] + 1} drags: {r[0]:.1f} characters/s against the take's {med:.1f}",
                    words[rng[0]][1])
    # --- whisper against the expected spoken words
    if heard:
        found, share = misreads(speech_tr.plan(" ".join(lines) if lines else " ".join(str(w[0]) for w in words), lang, pron),
                                heard)
        m["heard_match"] = round(share, 2)
        findings.extend(found)
    findings.sort(key=lambda f: f.get("t", 0.0))
    return {"findings": findings, "metrics": m}


def audit_take(path, lines, lang="tr", pron=None, words=None, hear=False):
    """One call for a voice file: word timings from the aligner when not given, whisper (local, free) when `hear`."""
    if words is None:
        from . import explainer
        words = explainer.align_words(path, lines, lang, pron)
    heard = None
    if hear:
        from . import talk
        heard = talk.transcribe(path, lang)
    return audit(path, words, lines, lang, pron, heard)
