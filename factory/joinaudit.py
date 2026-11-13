"""Free quality checks for cuts of the creator's OWN footage (talking head / vlog): the joins and the pace.

No model is called: numpy on the source audio's own level picture + the word timings the aligner wrote. The two checks
answer the questions a cutter asks after a jump-cut edit, and a creator cannot hear on a phone:

  levels / ref    the recording's own levels: dB per 10 ms frame, its floor (15th percentile) and its speech level
                  (85th percentile) — every threshold below is relative to THIS take, so a quiet phone mic and a loud
                  studio take are judged the same way
  edge_class      what sits under a cut: "silence", "low" or "speech" (the loudest frame within ±20 ms of the point)
  audit           every join between two kept ranges (plus the first start and the last end): was the cut made in
                  speech, and does it clip a word (> 20 ms of the word on the wrong side)? A join in speech WITH a
                  clipped word is a warn ("clipped_word"); a join in speech without one is info ("cut_in_speech")
  pacing          the delivered pace in OUTPUT time: holes >= 0.5 s, how many are >= 1.0 s, dead air (the part of a hole
                  over 0.25 s), and doubled deliveries — the same word or the same 2-5 word phrase said twice within
                  3 s ("bu bu", "the big the big"). A repeat inside the running speech is usually emphasis (info);
                  one that sits across a join is a leftover stutter (warn).

Findings keep the shape the rest of the QA uses ({kind, severity, detail, t} so soundqa.as_text prints them) and also
carry `level`, `code` and a Turkish `detail_tr`. They are findings for the creator, never a reason to fail a render.
"""
import re

import numpy as np

from . import audiofx

SR = 16000
FRAME = 0.01            # level frame (s)
EDGE_WIN = 0.02         # ±window the class of a cut edge is measured over (s)
CLIP_S = 0.02           # more than this much of a word on the wrong side of an edge = clipped
SILENCE_DB = 8.0        # a frame this far over the floor is no longer silence
SPEECH_DB = 18.0        # a frame this far under the speech level is no longer speech
GAP_MIN = 0.5           # holes shorter than this are just the rhythm
GAP_LONG = 1.0          # a hole this long is dead air
DEAD_KEEP = 0.25        # of a hole, this much is a breath and is not dead air
DOUBLE_GAP = 3.0        # a repeat whose second take starts this soon after the first is a doubled delivery
DOUBLE_MAX = 5          # longest repeated phrase (words)
JOIN_TOL = 0.15         # a gap / double this close to a join is "across_join"


def norm(w):
    """Comparison key of a word, Turkish-aware (talk.norm / explainer._norm): lowercase, no punctuation, ı/i folded."""
    try:
        from .explainer import _norm
        return _norm(w)
    except Exception:      # explainer not importable is never a reason to lose the check
        return re.sub(r"[^\w']", "", str(w).replace("İ", "i").lower())


# ---------- the level picture ----------
def levels(y, sr=SR):
    """dBFS per 10 ms frame of a mono signal (silence floors at about -180 dB, never -inf)."""
    n = int(FRAME * sr)
    y = np.asarray(y, dtype=np.float64)
    m = len(y) // n if n else 0
    if m <= 0:
        return np.zeros(0, dtype=np.float64)
    f = y[:m * n].reshape(m, n)
    return 20.0 * np.log10(np.sqrt(np.mean(f * f, axis=1)) + 1e-9)


def ref(levels):
    """(floor, speech) of one recording: its 15th and 85th percentile frame level in dBFS."""
    lv = np.asarray(levels, dtype=np.float64)
    if not len(lv):
        return -120.0, -120.0
    return round(float(np.percentile(lv, 15)), 2), round(float(np.percentile(lv, 85)), 2)


def edge_class(levels, t, floor, speech):
    """What is under a cut at `t`: "silence" (< floor+8 dB), "speech" (>= speech-18 dB) or "low" in between.
    The loudest frame within ±20 ms decides (a cut is never judged on a single frame)."""
    lv = np.asarray(levels, dtype=np.float64)
    n = len(lv)
    if not n:
        return "silence"
    i0 = max(0, int(round((float(t) - EDGE_WIN) / FRAME)))
    i1 = min(n, max(i0 + 1, int(np.ceil((float(t) + EDGE_WIN) / FRAME))))
    db = float(np.max(lv[i0:i1]))
    if db < floor + SILENCE_DB:
        return "silence"
    if db >= speech - SPEECH_DB:
        return "speech"
    return "low"


# ---------- join audit ----------
def _words(words):
    out = []
    for w in words or []:
        try:
            out.append((str(w[0]), float(w[1]), float(w[2])))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _crossing(ws, t):
    """Words whose span crosses the point `t` by more than CLIP_S on both sides (a cut through a word)."""
    return [{"word": w, "start": round(s, 3), "end": round(e, 3)} for w, s, e in ws
            if s <= t - CLIP_S and e >= t + CLIP_S]


def _edge_tr(edge):
    return {"in": "giriş", "out": "çıkış", "head": "baş", "tail": "son"}[edge]


def _clipped_msg(at, word, edge):
    en = (f'cut at {at:.2f} s falls inside "{word}" ({edge}): the voice is cut mid-word, '
          "the join will read as a splice")
    tr = (f'{at:.2f} sn\'deki kesim "{word}" ({_edge_tr(edge)}) kelimesinin ortasına düşüyor: ses kelimenin '
          "ortasında kesiliyor, ek yapışmış gibi duyulur")
    return en, tr


def _speech_msg(at, edge):
    en = (f"cut at {at:.2f} s lands in speech ({edge}): no word is clipped, but a jump cut mid-word "
          "leaves an audible splice")
    tr = (f"{at:.2f} sn'deki kesim konuşmanın ortasına düşüyor ({_edge_tr(edge)}): kelime kesilmiyor ama "
          "konuşma ortasından kesilince ek duyulur")
    return en, tr


def _finding(code, level, at, en, tr, **extra):
    """One finding in the shape the QA uses (soundqa/craftcheck) plus level, code and the Turkish detail."""
    out = {"kind": code, "severity": level, "level": level, "code": code, "detail": en, "detail_tr": tr}
    if at is not None:
        out["t"] = round(float(at), 3)
    out.update(extra)
    return out


def audit(src_audio_path, ranges, words=()):
    """Join audit of a cut. `ranges` = kept [(start, end)] in SOURCE seconds (sorted), `words` = [[w, s, e], ...] in
    SOURCE time. -> {"joins": [...], "findings": [...], "floor": dB, "speech": dB}.

    Every join between ranges[i] and ranges[i+1] is reported with its output time (`at_out`: the end of the kept
    material before the join), the class of both edges and the words it clips; the first start and the last end are
    reported too (kind "head" / "tail")."""
    rs = sorted((float(a), float(b)) for a, b in ranges or [] if float(b) > float(a))
    ws = _words(words)
    y = audiofx.decode(src_audio_path, SR)
    lv = levels(y, SR)
    floor, speech = ref(lv)
    joins, findings, acc = [], [], 0.0
    for i, (a, b) in enumerate(rs):
        if i == 0:
            joins.append({"kind": "head", "at_out": 0.0, "in_at": round(a, 3),
                          "in_edge": edge_class(lv, a, floor, speech), "clipped": _crossing(ws, a)})
        else:
            j = {"kind": "join", "at_out": round(acc, 3), "out_at": round(rs[i - 1][1], 3), "in_at": round(a, 3),
                 "out_edge": edge_class(lv, rs[i - 1][1], floor, speech),
                 "in_edge": edge_class(lv, a, floor, speech),
                 "clipped": [dict(c, edge="out") for c in _crossing(ws, rs[i - 1][1])] +
                            [dict(c, edge="in") for c in _crossing(ws, a)]}
            joins.append(j)
            _join_findings(j, findings)
        acc += b - a
    if rs:
        a, b = rs[-1]
        joins.append({"kind": "tail", "at_out": round(acc, 3), "out_at": round(b, 3),
                      "out_edge": edge_class(lv, b, floor, speech), "clipped": _crossing(ws, b)})
    return {"joins": joins, "findings": findings, "floor": floor, "speech": speech}


def _join_findings(j, findings):
    """clipped word + speech edge = warn; speech edge alone = info; a clipped word on a quiet edge is still reported."""
    clipped = j.get("clipped") or []
    speech_edges = [e for e in ("out", "in") if j.get(f"{e}_edge") == "speech"]
    first = clipped[0] if clipped else None
    if first and speech_edges:
        edge = next((c.get("edge") for c in clipped if c.get("edge") in speech_edges), speech_edges[0])
        en, tr = _clipped_msg(j["at_out"], first["word"], edge)
        findings.append(_finding("clipped_word", "warn", j["at_out"], en, tr, word=first["word"],
                                 edges=speech_edges, clipped=len(clipped)))
    elif speech_edges:
        en, tr = _speech_msg(j["at_out"], speech_edges[0])
        findings.append(_finding("cut_in_speech", "info", j["at_out"], en, tr, edges=speech_edges))
    elif first:
        en, tr = _clipped_msg(j["at_out"], first["word"], first.get("edge") or "out")
        findings.append(_finding("clipped_word", "info", j["at_out"], en, tr, word=first["word"],
                                 edges=[], clipped=len(clipped)))


# ---------- pacing ----------
def _gap_msg(g):
    en = (f'{g["gap"]:.2f} s hole at {g["from"]:.2f} s (after "{g["after"]}", before "{g["before"]}"): '
          "dead air inside the cut")
    tr = (f'{g["from"]:.2f} sn\'de {g["gap"]:.2f} sn boşluk ("{g["after"]}" sonrası, "{g["before"]}" öncesi): '
          "kurguda ölü hava")
    return en, tr


def _double_msg(d):
    en = (f'doubled "{d["text"]}" at {d["at"]:.2f} s: the same words are delivered twice, {d["gap"]:.2f} s apart')
    tr = (f'{d["at"]:.2f} sn\'de "{d["text"]}" iki kez söylenmiş: aynı söz {d["gap"]:.2f} sn arayla tekrar ediyor')
    return en, tr


def pacing(words_out, join_times=None):
    """The delivered pace, `words_out` already remapped to OUTPUT time ([[w, start, end], ...]).

    -> {"gaps": [...], "long_gaps": n, "long_gap_times": [...], "dead_air": s, "doubled": [...], "findings": [...]}.
    A gap is a hole >= 0.5 s between two deliveries; dead air is the part of those holes over 0.25 s. A doubled
    delivery is the same normalised word (or the same 2-5 word phrase) said again with the second take starting
    within 3 s of the first ending; reported at level "info" (usually emphasis) unless `join_times` puts it across a
    join (within 0.15 s), then "warn" — a leftover stutter the cut exposed."""
    ws = sorted(_words(words_out), key=lambda w: w[1])
    joins = sorted(float(t) for t in join_times or [])

    def across(*ts):
        return any(abs(j - t) <= JOIN_TOL for j in joins for t in ts)

    gaps = []
    for (w0, _, e0), (w1, s1, _) in zip(ws, ws[1:]):
        g = s1 - e0
        if g >= GAP_MIN:
            gaps.append({"from": round(e0, 3), "to": round(s1, 3), "gap": round(g, 3), "after": w0, "before": w1,
                         "across_join": across(e0, s1)})
    long_gaps = [g for g in gaps if g["gap"] >= GAP_LONG]
    dead = round(sum(max(0.0, g["gap"] - DEAD_KEEP) for g in gaps), 3)

    toks = [norm(w) for w, _, _ in ws]
    doubled, k, n = [], 0, len(ws)
    while k < n - 1:
        hit = 0
        for m in range(min(DOUBLE_MAX, (n - k) // 2), 1, -1):
            if all(toks[k:k + m]) and toks[k:k + m] == toks[k + m:k + 2 * m]:
                hit = m
                break
        if not hit and toks[k] and toks[k] == toks[k + 1]:
            hit = 1
        if hit:
            first_e, second_s = ws[k + hit - 1][2], ws[k + hit][1]
            if second_s - first_e <= DOUBLE_GAP:
                text = " ".join(w for w, _, _ in ws[k:k + hit])
                adj = across(first_e, second_s)
                doubled.append({"at": round(second_s, 3), "from": round(ws[k][1], 3),
                                "gap": round(second_s - first_e, 3), "words": hit, "text": text,
                                "across_join": adj, "level": "warn" if adj else "info"})
                k += hit
                continue
        k += 1

    findings = []
    for g in long_gaps:
        en, tr = _gap_msg(g)
        findings.append(_finding("gap", "warn" if g["across_join"] else "info", g["from"], en, tr,
                                 gap=g["gap"], across_join=g["across_join"]))
    for d in doubled:
        en, tr = _double_msg(d)
        findings.append(_finding("doubled", d["level"], d["at"], en, tr, text=d["text"], gap=d["gap"],
                                 across_join=d["across_join"]))
    return {"words": len(ws), "gaps": gaps, "long_gaps": len(long_gaps),
            "long_gap_times": [g["from"] for g in long_gaps], "dead_air": dead, "doubled": doubled,
            "findings": findings}
