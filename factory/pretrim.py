"""Voice pre-trim (t512): a narration take sometimes carries a filler ("uh", "ıı") or a stutter ("the big the big idea")
that the script does not have. One filler-prompted whisper pass is matched to the script tokens; only heard words the
script lacks AND that are a filler or a restart are cut. Every other word stays, even one the script lacks. Free, local.
"""
import difflib, os

from . import audiofx, explainer, talk

PAD = 0.03          # room kept around a cut, never past the midpoint to the neighbouring word
MIN_MATCH = 0.6     # a take whose words match less than this share of the script is left alone (whisper drifted)


def _fillers(lang):
    return {explainer._norm(f) for f in talk.FILLERS.get(lang, set())} - {""}


def extras(tokens, heard, lang="en"):
    """Indexes of heard words to cut. tokens: the script tokens; heard: [[word, start, end, ...]]."""
    tn = [explainer._norm(t) for t in tokens]
    hn = [explainer._norm(w[0]) for w in heard]
    fill = _fillers(lang)
    sm = difflib.SequenceMatcher(None, tn, hn, autojunk=False)
    if sum(b.size for b in sm.get_matching_blocks()) < MIN_MATCH * max(1, len(tn)):
        return []
    cut = set()
    for op, _, _, j1, j2 in sm.get_opcodes():
        if op != "insert":
            continue
        run = list(range(j1, j2))
        for j in run:                                   # fillers anywhere in the inserted run
            if hn[j] in fill or not hn[j]:
                cut.add(j)
        rest = [j for j in run if j not in cut]
        words = [hn[j] for j in rest]
        after = [hn[k] for k in range(j2, len(hn)) if hn[k] not in fill][:len(rest)]
        before = [hn[k] for k in range(j1 - 1, -1, -1) if hn[k] not in fill][:len(rest)][::-1]
        if rest and (words == after or words == before):
            cut.update(rest)                            # a restart: the same words right after or right before it
            continue
        for j in rest:                                  # a cut-off start of the next word ("ide- idea")
            nxt = next((hn[k] for k in range(j + 1, len(hn)) if k not in cut and hn[k] not in fill), "")
            if hn[j] and nxt and nxt != hn[j] and nxt.startswith(hn[j]) and len(hn[j]) < len(nxt):
                cut.add(j)
    return sorted(cut)


def spans(heard, idx, total):
    """Cut ranges (seconds) for the heard words at idx, padded but never into a neighbour, merged when they touch."""
    out = []
    for j in idx:
        s, e = heard[j][1], heard[j][2]
        lo = (heard[j - 1][2] + s) / 2 if j else 0.0
        hi = (e + heard[j + 1][1]) / 2 if j + 1 < len(heard) else total
        a, b = max(lo, s - PAD), min(hi, e + PAD)
        if j and j - 1 in idx:
            a = heard[j - 1][2]
        if b - a > 0.02:
            if out and a - out[-1][1] < 0.02:
                out[-1][1] = b
            else:
                out.append([a, b])
    return [(round(a, 3), round(b, 3)) for a, b in out]


def trim(path, lines, lang="en", dst=None):
    """-> (file to use, {"cuts": [[start, end, "words"]], "seconds": cut total}). The original file when nothing is cut."""
    tokens = [t for ln in lines for t in ln.split() if explainer._norm(t)]
    heard = talk.transcribe(path, lang)
    idx = extras(tokens, heard, lang)
    if not idx:
        return path, {"cuts": [], "seconds": 0.0}
    total = len(audiofx.decode(path)) / 16000
    cuts = spans(heard, idx, total)
    if not cuts:
        return path, {"cuts": [], "seconds": 0.0}
    dst = dst or os.path.splitext(path)[0] + "_trim.wav"
    audiofx.concat_audio(path, audiofx.keep_ranges(cuts, total), dst)
    named = [[a, b, " ".join(heard[j][0] for j in idx if a - 0.05 <= heard[j][1] and heard[j][2] <= b + 0.05)]
             for a, b in cuts]
    return dst, {"cuts": named, "seconds": round(sum(b - a for a, b in cuts), 2)}
