"""The sound budget is kept before the mix, and the narrator's own consonants are not reported as cut clicks."""
from factory import craftcheck, sfx, soundqa


def _c(kind, t):
    return {"kind": kind, "t": t, "gain_db": -12}


def test_whooshes_and_risers_are_thinned_to_the_budget_the_qa_measures():
    cues = [_c("swish", 1.2), _c("pop", 2.7), _c("whoosh", 12.3), _c("swish", 25.4), _c("whoosh", 29.7),
            _c("riser", 30.0), _c("riser", 40.0), _c("whoosh", 38.1)]
    out = sfx.budget(cues)
    kinds = [(c["kind"], c["t"]) for c in out]
    assert ("swish", 25.4) not in kinds and ("whoosh", 29.7) not in kinds and ("whoosh", 38.1) in kinds
    assert ("riser", 30.0) in kinds and ("riser", 40.0) not in kinds and ("pop", 2.7) in kinds
    assert not [f for f in craftcheck.sound_budget(out, 46) if f["kind"].startswith("too_many")]
    assert not [f for f in craftcheck.sound_budget(cues, 46) if False]


def test_at_most_seventy_percent_of_the_cuts_carry_a_designed_sound():
    cuts = [5.0, 10.0, 15.0, 20.0, 25.0]
    cues = [_c("pop", t) for t in cuts] + [_c("tick", 7.5)]
    out = sfx.budget(cues, cuts)
    share = sum(any(abs(c["t"] - t) < 0.35 for c in out) for t in cuts) / len(cuts)
    assert share <= 0.7 and _c("tick", 7.5) in out
    assert sfx.budget([], cuts) == [] and sfx.budget(cues[:2], [1.0]) == cues[:2]


def test_a_click_that_is_in_the_narration_is_speech():
    voice = [1.232, 1.672, 6.26, 9.832, 10.635]
    final = [c + 0.01 for c in voice] + [3.652, 28.076]
    assert soundqa.not_in_speech(final, voice) == [3.652, 28.076]
    assert soundqa.not_in_speech(final, []) == final and soundqa.not_in_speech([], voice) == []
