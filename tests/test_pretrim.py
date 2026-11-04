"""Voice pre-trim (t512): only fillers and restarts the script lacks are cut from a take; every other word stays, and
the cut file is shorter by exactly the cut spans."""
import os, subprocess

import pytest

from factory import audiofx, config, pretrim
from factory.hat import explainer as E, project as P


def _heard(words, step=0.4):
    return [[w, round(i * step, 2), round(i * step + 0.3, 2), 0.9] for i, w in enumerate(words)]


SCRIPT = "the big idea is simple and it works".split()


def _cut(heard, lang="en", script=SCRIPT):
    return [heard[j][0] for j in pretrim.extras(script, heard, lang)]


def test_fillers_and_restarts_are_cut_other_words_stay():
    assert _cut(_heard("the big uh idea is simple and it works".split())) == ["uh"]
    h = _heard("the big the big idea is simple and it works".split())
    assert len(pretrim.extras(SCRIPT, h, "en")) == 2 and _cut(h) == ["the", "big"]
    assert sorted(_cut(_heard("the big uh the big idea is simple and it works".split()))) == ["big", "the", "uh"]
    assert _cut(_heard("the big id idea is simple and it works".split())) == ["id"]           # a cut-off word
    assert _cut(_heard("the big idea is really simple and it works".split())) == []           # a new word stays
    assert _cut(_heard("the big idea is simpler and it works".split())) == []                 # a misread stays
    assert _cut(_heard("the big idea is simple and it works".split())) == []


def test_turkish_fillers_and_a_drifted_take():
    tr = "bu fikir çok basit ve işe yarıyor".split()
    assert _cut(_heard("bu fikir ıı çok basit eee ve işe yarıyor".split()), "tr", tr) == ["ıı", "eee"]
    assert _cut(_heard("tamamen başka bir kayıt uh burada".split()), "en") == []              # under MIN_MATCH


def test_spans_pad_without_touching_neighbours_and_merge():
    h = _heard("a uh the the b".split())
    assert pretrim.spans(h, [1], 2.0) == [(0.37, 0.73)]
    merged = pretrim.spans(h, [1, 2], 2.0)
    assert len(merged) == 1 and merged[0][0] == 0.37 and merged[0][1] <= (h[2][2] + h[3][1]) / 2


def _tone(path, secs):
    subprocess.run([config.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=f=220:d={secs}", "-ac", "1",
                    "-ar", "16000", path], check=True)


def test_trim_cuts_the_audio(tmp_path, monkeypatch):
    src = str(tmp_path / "take.wav")
    _tone(src, 4.0)
    heard = _heard("the big uh idea is simple and it works".split())
    monkeypatch.setattr(pretrim.talk, "transcribe", lambda path, lang="en": heard)
    out, info = pretrim.trim(src, [" ".join(SCRIPT)], "en")
    assert out != src and os.path.exists(out)
    assert info["cuts"][0][2] == "uh" and 0.3 < info["seconds"] < 0.45
    assert abs(len(audiofx.decode(out)) / 16000 - (4.0 - info["seconds"])) < 0.03
    monkeypatch.setattr(pretrim.talk, "transcribe", lambda path, lang="en": _heard(SCRIPT))
    assert pretrim.trim(src, [" ".join(SCRIPT)], "en") == (src, {"cuts": [], "seconds": 0.0})


def test_explainer_hook_can_be_switched_off_and_never_loses_a_take(tmp_path, monkeypatch):
    d = str(tmp_path)
    pid = P.create("explainer", "t", d=d)["id"]
    called = []
    monkeypatch.setattr(pretrim, "trim", lambda path, lines, lang: called.append(1) or (path + ".t", {"cuts": [[0, 1, "uh"]], "seconds": 1.0}))
    assert E.pretrim_voice(pid, "v.wav", ["x"], "en", {}, d) == ("v.wav.t", {"cuts": [[0, 1, "uh"]], "seconds": 1.0})
    assert E.pretrim_voice(pid, "v.wav", ["x"], "en", {"pretrim": False}, d) == ("v.wav", None) and called == [1]

    def boom(*a):
        raise RuntimeError("no whisper")
    monkeypatch.setattr(pretrim, "trim", boom)
    assert E.pretrim_voice(pid, "v.wav", ["x"], "en", {}, d) == ("v.wav", None)
    monkeypatch.setattr(pretrim, "trim", lambda path, lines, lang: (path, {"cuts": [], "seconds": 0.0}))
    assert E.pretrim_voice(pid, "v.wav", ["x"], "en", {}, d) == ("v.wav", None)


def test_hat_js_has_the_strings_in_both_languages():
    src = open(os.path.join(config.ROOT, "studio", "hat.js"), encoding="utf-8").read()
    assert src.count("pt_cut:") == 2 and src.count("pt_label:") == 2
