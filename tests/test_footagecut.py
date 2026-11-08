"""Footage cut (t513): silence shortened to a breath, repeated takes flagged for approval, never auto-cut."""
import pytest

from factory import footagecut as F


# --- keep_intervals -----------------------------------------------------------

def test_3s_silence_keeps_breath_long_split_55_45():
    words = [("kelime", 0.5, 1.0), ("ikinci", 4.0, 4.6)]
    keep = F.keep_intervals(words, 6.0)
    # 3.0 s gap > LONG_PAUSE -> BREATH_LONG (0.24); 55 % (0.132) stays after "kelime", 45 % (0.108) before "ikinci"
    assert keep[0] == [pytest.approx(0.28), pytest.approx(1.0 + 0.55 * 0.24)]
    assert keep[1] == [pytest.approx(4.0 - 0.45 * 0.24), pytest.approx(4.94)]
    kept_in_silence = (keep[0][1] - 1.0) + (4.0 - keep[1][0])
    assert kept_in_silence == pytest.approx(0.24)
    assert kept_in_silence * 0.55 == pytest.approx(keep[0][1] - 1.0)


def test_1_2s_gap_keeps_breath_other():
    words = [("selam", 0.5, 1.0), ("naber", 2.2, 2.6)]
    keep = F.keep_intervals(words, 3.5)
    assert keep[0][1] == pytest.approx(1.0 + 0.55 * 0.14)      # 0.077 after the word
    assert keep[1][0] == pytest.approx(2.2 - 0.45 * 0.14)      # 0.063 before the next


def test_short_gap_untouched():
    words = [("selam", 0.5, 1.0), ("naber", 1.5, 2.0)]
    keep = F.keep_intervals(words, 3.0)
    assert keep == [[pytest.approx(0.28), pytest.approx(2.34)]]   # 0.5 s breath kept whole, one piece


def test_sentence_end_breath_and_head_tail():
    words = [("bitti.", 0.5, 1.0), ("merhaba", 2.0, 2.5)]
    keep = F.keep_intervals(words, 4.0)
    assert keep[0][1] == pytest.approx(1.0 + 0.55 * F.BREATH_SENTENCE)
    assert keep[0][0] == pytest.approx(0.5 - F.HEAD)
    assert keep[-1][1] == pytest.approx(2.5 + F.TAIL)


# --- find_flags ---------------------------------------------------------------

def _take(words, start, dur=0.5, gap=0.6):
    """Words of one passage starting at `start`, `gap` between them (< PASSAGE_GAP, so one passage)."""
    out, t = [], start
    for w in words:
        out.append((w, t, t + dur))
        t += dur + gap
    return out


def test_retake_40pct_shared_one_high_flag():
    # A = {kalem, defte, çanta}, B = {kalem, defte, plaj}: 2/4 shared -> 0.50 -> "high".
    # Passage A is 6.3 s long, so it is not a false start; the 1.0 s gap splits the passages.
    a = _take(["kalem", "ama", "defter", "çanta"], 1.0, dur=0.5, gap=0.6)
    a[-1] = ("çanta", a[-1][1], 7.3)          # stretch the last word: passage length 6.3 s >= FALSE_START_LEN
    b = _take(["kalem", "defter", "plaj"], 8.3)
    flags = F.find_flags(a + b, 14.0)
    assert len(flags) == 1
    f = flags[0]
    assert f["kind"] == "retake" and f["confidence"] == "high"
    assert f["cut"] == [pytest.approx(1.0), pytest.approx(8.3)]


def test_retake_20pct_shared_no_flag():
    a = _take(["kalem", "defter", "çanta", "plaj", "liman"], 1.0, dur=1.0, gap=0.8)   # 8.2 s: no false start
    b = _take(["kalem", "deniz", "yolcu", "martı", "ruzgar"], 10.3, dur=1.0, gap=0.8)  # 1/9 shared = 0.11
    assert F.find_flags(a + b, 20.0) == []


def test_false_start():
    p1 = _take(["selam", "bugün", "iptal"], 0.5, dur=0.5, gap=0.5)   # 3.0 s first attempt
    p2 = _take(["merhaba", "motor", "yolculuk"], 11.5, dur=0.5, gap=0.5)  # restart 8 s later
    flags = F.find_flags(p1 + p2, 16.0)
    assert len(flags) == 1
    f = flags[0]
    assert f["kind"] == "false_start"
    assert f["cut"] == [pytest.approx(0.5), pytest.approx(11.5)]
    assert f["confidence"] == "high"


def test_stutter_flag():
    words = [("gel", 1.0, 1.3), ("gel", 1.4, 1.7), ("bakalım", 2.0, 2.5)]
    flags = F.find_flags(words, 3.0)
    assert [f["kind"] for f in flags] == ["stutter"]
    assert flags[0]["cut"] == [pytest.approx(1.0), pytest.approx(1.4)]


# --- subtract -----------------------------------------------------------------

def test_subtract_10s_keep_one_1s_cut():
    keep = F.subtract([[0.0, 10.0]], [[4.0, 5.0]])
    assert keep == [[0.0, 4.0], [5.0, 10.0]]
    assert sum(e - s for s, e in keep) == pytest.approx(9.0)
    assert all(e - s >= F.MIN_PIECE for s, e in keep)


def test_subtract_drops_tiny_pieces_and_merges_cuts():
    keep = F.subtract([[0.0, 10.0]], [[4.0, 5.0], [4.2, 5.4], [9.95, 10.0]])
    assert keep == [[0.0, 4.0], [5.4, 9.95]]              # the 0.05 s sliver at the end is dropped
    assert F.subtract([[1.0, 2.0]], [[1.0, 2.0]]) == []   # fully cut -> gone


# --- helpers ------------------------------------------------------------------

def test_key_and_meaningful():
    assert F.key("Geliyor,") == "geliy"                        # suffixes stay out of the comparison
    assert F.key("çanta") == "çanta" and F.key("!!!") == ""
    p = [("ve", 0, 1), ("kalem", 1, 2), ("bu", 2, 3), ("deftere", 3, 4)]
    assert F._meaningful(p) == ["kalem", "defte"]


def test_filter_args_shape():
    args = F.filter_args([[0.28, 1.13], [3.89, 4.94]], fps=30)
    assert args["fps"] == 30
    assert args["frames"] == [[8, 34], [117, 148]]
    assert args["select"] == "between(n,8,33)+between(n,117,147)"
    assert args["segments"] == [[8 / 30, 34 / 30], [117 / 30, 148 / 30]]
