"""Cut the creator's own camera footage before editing: silence shortened to a natural breath, repeated takes flagged.

Raw talking-head / travel-vlog camera tracks are never watchable as recorded: minutes of dead air around the
action, three-second gaps between sentences, and the same sentence filmed two or three times because a moped
drove through the shot. This module turns word timings (as the aligner writes them: `(word, start, end)`
tuples, seconds) into what a cutter consumes:

  - leading silence keeps HEAD, trailing silence keeps TAIL;
  - a gap under BREATH_MIN_GAP is a natural breath and is left completely alone;
  - a longer gap is shortened to a breath sized by its surroundings (sentence end, a long draw-up of
    courage, or a plain hesitation), split 55/45 around the cut: the bigger part of the kept breath stays
    attached to the word that was said, the rest leads into the next one — that is what reads as a breath
    instead of a hiccup;
  - repeated takes (stutter, retake, false start) are NEVER cut automatically. `find_flags` returns them
    with a suggested cut so the creator approves each one — the "retake" is often the better take.

Everything is pure stdlib, no numpy: this runs per clip on the VM while ffmpeg does the actual cutting.
"""
import re

BREATH_MIN_GAP = 0.55      # gaps shorter than this are the breath: leave them alone
BREATH_SENTENCE = 0.20     # kept breath after a sentence end (. ! ?)
BREATH_LONG = 0.24         # kept breath when the pause was > 2.0 s
BREATH_OTHER = 0.14        # kept breath elsewhere
LONG_PAUSE = 2.0
BEFORE_SHARE = 0.45        # of the shortened gap, 45 % goes before the next word, 55 % after the previous
HEAD = 0.22                # kept before the first word
TAIL = 0.34                # kept after the last word
MIN_PIECE = 0.15           # a kept piece shorter than this is dropped
FADE = 0.012               # 12 ms fade in/out on every join

STUTTER_WINDOW = 0.5       # the same word twice within this is a stutter
PASSAGE_GAP = 0.85         # a pause longer than this splits two passages
PASSAGE_SENTENCE = 7.5     # a sentence end after this much passage also splits it
PASSAGE_MAX = 16.0         # passages never run longer than this
RETAKE_DISTANCE = 9        # candidate retakes at most this many passages apart
RETAKE_SPAN = 75.0         # ... and at most this many seconds apart (passage start to start)
RETAKE_RATIO = 0.34        # shared-word ratio (intersection / union) that makes a retake
RETAKE_RATIO_LOOSE = 0.24  # ... or this much when 2 of the first 4 meaningful words match
RETAKE_HIGH = 0.45         # ratio for "high" confidence; RETAKE_RATIO gives "medium", below is "look"
FALSE_START_LEN = 6.0      # a first attempt shorter than this
FALSE_START_GAP = 12.0     # ... whose restart begins within this many seconds

MEANINGFUL_MAX = 18        # a passage is reduced to at most this many meaningful words
KEY_LEN = 5                # words are compared by their first 5 letters (Turkish suffixes)

SENTENCE_END = re.compile(r"""[.!?…。！？]['")\]\u201d]*$""")
_LETTERS = re.compile(r"[^\w]+", re.UNICODE)

# Function words never carry a retake: both takes share the sentence scaffolding, only the content repeats.
STOPWORDS = {
    # English
    "the", "and", "but", "for", "nor", "yet", "with", "that", "this", "from", "have", "has", "had",
    "was", "were", "been", "into", "your", "you", "they", "them", "their", "there", "then", "than",
    "just", "very", "also", "some", "what", "when", "where", "which", "how", "why", "not", "are",
    "will", "would", "could", "should", "about", "after", "before", "because", "here", "him", "her",
    # Turkish (len <= 2 tokens are dropped by length alone)
    "bir", "için", "ile", "ama", "veya", "çünkü", "gibi", "değil", "daha", "çok", "sonra", "önce",
    "olan", "oldu", "olarak", "bunu", "şunu", "onun", "bizim", "her", "bütün", "kadar", "yok",
}


def key(word):
    """First 5 letters, lowercased, punctuation stripped — Turkish endings ("geliyor"/"geliyorlar") must not
    split a match, so words are compared from the front."""
    return "".join(ch for ch in word.lower() if ch.isalpha())[:KEY_LEN]


def _sentence_end(word):
    return bool(SENTENCE_END.search(word.strip()))


def _breath(gap, prev_word):
    """Kept breath for a gap >= BREATH_MIN_GAP: sentence end first, then a long draw-up, then plain."""
    if _sentence_end(prev_word):
        return BREATH_SENTENCE
    if gap > LONG_PAUSE:
        return BREATH_LONG
    return BREATH_OTHER


def keep_intervals(words, duration, head=HEAD, tail=TAIL):
    """The intervals of the recording that survive, merged where everything between words is kept.

    Leading silence keeps `head` seconds, trailing silence keeps `tail` seconds (clamped to `duration`),
    a gap under BREATH_MIN_GAP is kept whole (so its piece merges with both words), a longer gap keeps a
    BREATH_* breath split 55/45 around the cut. With no words at all the recording is kept whole —
    an empty keep-list would silently delete the take."""
    if not words:
        return [[0.0, float(duration)]] if duration and duration > 0 else []
    n, out = len(words), []
    for i, (w, s, e) in enumerate(words):
        if i == 0:
            lead = head
        else:
            gap = s - words[i - 1][2]
            lead = BEFORE_SHARE * _breath(gap, words[i - 1][0]) if gap >= BREATH_MIN_GAP else 0.0
        lag = (tail if i == n - 1 else
               (1 - BEFORE_SHARE) * _breath(words[i + 1][1] - e, w) if i + 1 < n else 0.0)
        piece = [max(0.0, s - lead), e + lag]
        if i == n - 1 and duration:
            piece[1] = min(piece[1], float(duration))
        # merge into the previous piece when the untouched breath between the words glues them together
        if out and (i and piece[0] - out[-1][1] <= 0 or s - words[i - 1][2] < BREATH_MIN_GAP):
            out[-1][1] = max(out[-1][1], piece[1])
        else:
            out.append(piece)
    return out


def subtract(keep, cuts):
    """Remove [a, b] ranges from the keep list; surviving pieces shorter than MIN_PIECE are dropped
    (they would blink on screen for a couple of frames and read as a glitch)."""
    merged = []
    for a, b in sorted((min(a, b), max(a, b)) for a, b in cuts):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out = []
    for s, e in keep:
        pieces = [(s, e)]
        for a, b in merged:
            nxt = []
            for ps, pe in pieces:
                if b <= ps or a >= pe:
                    nxt.append((ps, pe))
                    continue
                if a > ps:
                    nxt.append((ps, a))
                if b < pe:
                    nxt.append((b, pe))
            pieces = nxt
        out.extend([[ps, pe] for ps, pe in pieces if pe - ps >= MIN_PIECE])
    return out


def _passages(words):
    """Split the take into passages: at a pause over PASSAGE_GAP, at a sentence end after PASSAGE_SENTENCE
    of passage, and at PASSAGE_MAX no matter what (so one long ramble cannot mask a retake)."""
    out, cur = [], []
    for w in words:
        if cur:
            plen = cur[-1][2] - cur[0][1]
            if (w[1] - cur[-1][2] > PASSAGE_GAP
                    or (plen > PASSAGE_SENTENCE and _sentence_end(cur[-1][0]))
                    or plen >= PASSAGE_MAX):
                out.append(cur)
                cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def _meaningful(passage):
    """The words of a passage that can carry a retake: lowercase, no punctuation, no scaffolding words,
    no tokens of length <= 2, at most MEANINGFUL_MAX — compared via `key`."""
    out = []
    for w, _, _ in passage:
        k = key(w)
        if len(k) <= 2 or k in STOPWORDS:
            continue
        out.append(k)
        if len(out) == MEANINGFUL_MAX:
            break
    return out


def _stutters(words):
    out = []
    for (w1, s1, _), (w2, s2, _) in zip(words, words[1:]):
        k = key(w1)
        if k and k == key(w2) and s2 - s1 < STUTTER_WINDOW:
            out.append({"kind": "stutter", "at": s1, "cut": [s1, s2], "confidence": "high",
                        "first": [w1], "second": [w2]})
    return out


def _retakes(passages):
    out = []
    means = [_meaningful(p) for p in passages]
    starts = [p[0][1] for p in passages]
    for i in range(len(passages)):
        for j in range(i + 1, min(len(passages), i + RETAKE_DISTANCE + 1)):
            if starts[j] - starts[i] > RETAKE_SPAN:
                continue
            a, b = means[i], means[j]
            union = set(a) | set(b)
            if not union:
                continue
            ratio = len(set(a) & set(b)) / len(union)
            loose = len(set(a[:4]) & set(b[:4])) >= 2
            if not (ratio >= RETAKE_RATIO or (loose and ratio >= RETAKE_RATIO_LOOSE)):
                continue
            conf = "high" if ratio >= RETAKE_HIGH else ("medium" if ratio >= RETAKE_RATIO else "look")
            out.append({"kind": "retake", "at": starts[i], "cut": [starts[i], starts[j]],
                        "confidence": conf, "first": a, "second": b})
    return out


def _false_starts(passages):
    out = []
    for p, q in zip(passages, passages[1:]):
        if p[-1][2] - p[0][1] < FALSE_START_LEN and q[0][1] - p[-1][2] <= FALSE_START_GAP:
            out.append({"kind": "false_start", "at": p[0][1], "cut": [p[0][1], q[0][1]],
                        "confidence": "high", "first": [w for w, _, _ in p],
                        "second": [w for w, _, _ in q]})
    return out


def find_flags(words, duration):
    """Repeated takes to approve before cutting: [{id, kind, at, cut, confidence, first, second}, ...].

    kind is "stutter" (same word twice within STUTTER_WINDOW), "retake" (two passages whose meaningful
    words overlap, see _retakes) or "false_start" (a short first attempt quickly restarted). `at` is where
    the suggested cut begins, `cut` = [earlier point, later point] — for retakes and false starts the
    restart of the later passage, so approving the flag cuts up TO the take the creator probably wants.
    `first`/`second` are the meaningful words of each side. Sorted by time, ids 1-based."""
    passages = _passages(words)
    flags = _stutters(words) + _retakes(passages) + _false_starts(passages)
    flags.sort(key=lambda f: f["at"])
    for i, f in enumerate(flags):
        f["id"] = i + 1
        f["cut"] = [min(f["cut"][0], duration), min(f["cut"][1], duration)] if duration else f["cut"]
    return flags


def filter_args(intervals, fps=30):
    """ffmpeg-friendly form of a keep list:

        {"fps": 30, "select": "between(n,8,146)+between(n,183,404)", "frames": [[8, 147], ...],
         "segments": [[0.27, 4.9], ...]}

    "select" is an expression for `-vf select=` over the output frame number n (frame-end exclusive);
    "frames" are the [start_frame, end_frame) pairs it is built from; "segments" is the same list in
    seconds snapped to frame boundaries, usable directly as trim=start:end per segment."""
    frames = [[int(round(s * fps)), int(round(e * fps))] for s, e in intervals]
    sel = "+".join(f"between(n,{a})" if b - a == 1 else f"between(n,{a},{b - 1})"
                   for a, b in frames if b > a)
    return {"fps": fps, "select": sel or "0", "frames": frames,
            "segments": [[a / fps, b / fps] for a, b in frames]}
