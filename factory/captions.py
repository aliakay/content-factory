"""Caption blocks that do not flicker: words grouped per line, gaps bridged, short holds kept.

Word-by-word captions blink: every gap in speech (a breath, a comma) empties the screen for a fraction of a second and
the eye reads it as a flash. This module turns word timings into blocks the way a captioner would, with the geometry
of the target aspect (three words a line on 9:16, seven on 16:9), and closes the micro-gaps:

  - a gap up to JOIN (0.35 s) between two blocks is closed: the first block holds until the next one starts;
  - a longer gap keeps a HOLD (0.12 s) of extra screen time, then the block ends;
  - a block never shows for less than MIN_S (0.20 s);
  - a block breaks on punctuation, on MAX_WORDS words, on MAX_CHARS characters, or on a pause over BREAK (0.6 s).

`blocks(words, aspect)` returns [{start, end, text}] ready for the caption layer; `words` are (word, start, end)
tuples as the aligner writes them.
"""
import re

SENTENCE_END = re.compile(r"""[.!?…。！？]["')\]\u201d]*$""")
GEOMETRY = {                       # aspect -> (words per line, characters per line, font size share of the width, y)
    "9:16": {"max_words": 3, "max_chars": 20, "font": 0.078, "y": 0.66},
    "16:9": {"max_words": 7, "max_chars": 42, "font": 0.033, "y": 0.86},
}
BREAK = 0.6                        # a pause longer than this starts a new block
JOIN = 0.35                        # a gap up to this is closed (no blink)
HOLD = 0.12                        # extra screen time after a longer gap
MIN_S = 0.20                       # nothing shorter than this


def geometry(aspect="9:16"):
    return GEOMETRY.get(aspect) or GEOMETRY["9:16"]


def chunk_words(words, aspect="9:16"):
    """Word tuples -> blocks of words (lists of tuples), split like a captioner would."""
    g = geometry(aspect)
    chunks, cur = [], []
    for w, s, e in words:
        if cur:
            chars = sum(len(x[0]) for x in cur) + len(cur) + len(w)
            if len(cur) >= g["max_words"] or chars > g["max_chars"] or (s - cur[-1][2]) > BREAK:
                chunks.append(cur)
                cur = []
        cur.append((w, s, e))
        if SENTENCE_END.search(str(w)):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def chunk_times(chunks, join=JOIN, hold=HOLD, min_s=MIN_S):
    """Blocks of words -> [(start, end, text)] with the micro-gaps closed and a minimum on-screen time."""
    out = []
    for i, chunk in enumerate(chunks):
        start, end = chunk[0][1], chunk[-1][2]
        nxt = chunks[i + 1][0][1] if i + 1 < len(chunks) else None
        if nxt is not None and (nxt - end) <= join:
            end = nxt                      # hold the words until the next block: no empty frame
        else:
            end += hold
            if nxt is not None:
                end = min(end, nxt)
        end = max(end, start + min_s)
        out.append((round(start, 3), round(end, 3), " ".join(str(x[0]) for x in chunk)))
    return out


def blocks(words, aspect="9:16", join=JOIN, hold=HOLD, min_s=MIN_S):
    """(word, start, end) timings -> [{start, end, text}], the caption layer's blocks."""
    return [{"start": a, "end": b, "text": text}
            for a, b, text in chunk_times(chunk_words(words, aspect), join, hold, min_s)]


def overlapping(blocks_, start, end):
    """The blocks that show inside [start, end) — a scene's caption window."""
    return [b for b in blocks_ if b["end"] > start and b["start"] < end]
