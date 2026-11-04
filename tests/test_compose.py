"""The original music composer (t513): the ABC subset reads right, a bad score is named in words, the tempo puts the
scene cues on bar lines, our instruments play a score into a real file, and the explainer uses it for 0 credits."""
import json, os

import numpy as np
import pytest

from factory import compose as C


def test_abc_subset_pitches_lengths_key_and_accidentals():
    evs, total = C.parse("C D E F | c C, c' z |", "C")
    assert [p for _, _, p, _ in evs] == [60, 62, 64, 65, 72, 48, 84] and total == 1.0
    evs, _ = C.parse("F ^F F | F", "C")                          # ^ holds to the bar line, then the key again
    assert [p for _, _, p, _ in evs] == [65, 66, 66, 65] and C.parse("F", "G")[0][0][2] == 66
    evs, _ = C.parse("=F F _B B", "G")
    assert [p for _, _, p, _ in evs] == [65, 65, 70, 70]
    assert C.parse("B", "Bb")[0][0][2] == 70 and C.parse("B", "Dm")[0][0][2] == 70
    evs, total = C.parse("C2 D/2 E3/2 F/ [CEG]4", "C")
    assert [round(l, 4) for _, l, _, _ in evs] == [0.25, 0.0625, 0.1875, 0.0625, 0.5, 0.5, 0.5] and total == 1.0625


def test_ties_triplets_broken_rhythm_dynamics_and_drums():
    evs, total = C.parse("C2-C2 D", "C")
    assert [(round(a, 3), round(l, 3), p) for a, l, p, _ in evs] == [(0, 0.5, 60), (0.5, 0.125, 62)]
    evs, total = C.parse("(3CDE F2", "C")
    assert abs(total - 0.5) < 1e-9 and abs(evs[1][0] - 0.25 / 3) < 1e-9
    evs, _ = C.parse("C>D", "C")
    assert [round(l, 4) for _, l, _, _ in evs] == [0.1875, 0.0625] and abs(evs[1][0] - 0.1875) < 1e-9
    evs, _ = C.parse('!p! "Am" C !f! D', "C")
    assert [v for *_, v in evs] == [C.DYN["p"], C.DYN["f"]]
    evs, _ = C.parse("[BC] F D F", drums=True)
    assert [p for _, _, p, _ in evs] == ["crash", "kick", "hat", "snare", "hat"]
    with pytest.raises(C.ScoreError, match="at"):
        C.parse("C D $ E")
    with pytest.raises(C.ScoreError, match="key"):
        C.key_alters("H#")


def _score(**kw):
    return {"bpm": 100, "key": "Am", "meter": "4/4", "unit": "1/8",
            "voices": [{"inst": "pad", "abc": "[A,CE]8 | [F,A,C]8 |"}, {"inst": "drums", "abc": "CF DF CF DF |"}], **kw}


def test_problems_speak_to_the_agent():
    assert C.problems(_score()) == []
    bad = _score(voices=[{"inst": "kazoo", "abc": "C"}, {"inst": "bass", "abc": "C8 | D7 | E8 |"},
                         {"inst": "piano", "abc": "C $"}, {"inst": "bell", "abc": "C,,8 |"}])
    txt = " ".join(C.problems(bad))
    assert "unknown instrument 'kazoo'" in txt and "bars [2]" in txt and "piano:" in txt and "outside its range" in txt
    assert C.problems(_score(bpm=20)) == ["bpm must be 50-180"]
    assert "at least" in " ".join(C.problems(_score(), seconds=30))     # 2 bars = 4.8 s for a 30 s video


def test_tempo_puts_cues_on_bar_lines():
    cues = [4.8, 9.6, 14.4]                                           # exactly 2, 4, 6 bars at 100 bpm
    assert C.fit_bpm(cues, 80, 120) in (100, 50 * 4 / 2)
    assert C.where(4.8, 100) == "bar 3 beat 1" and C.where(5.4, 100) == "bar 3 beat 2"


@pytest.mark.parametrize("mood", ["calm", "bright", "tense", "drive"])
def test_plain_scores_are_valid_and_mark_the_cues(mood):
    sc = C.auto_score(mood, 24, [6.0, 12.0])
    assert C.problems(sc, 24) == [] and sc["mood"] == C.mood_of(mood)
    _, end = C.events(sc)
    assert end >= 24 - C.bar_seconds(sc["bpm"])
    assert C.mood_of("karanlık, gerilimli bir alt yapı") == "tense" and C.mood_of("") == "calm"


def test_render_plays_the_score_into_a_file(tmp_path):
    import soundfile as sf
    out = str(tmp_path / "m.wav")
    C.render(_score(), 6.0, out)                                      # 4.8 s of score, looped to 6 s
    y, sr = sf.read(out)
    assert sr == C.SR and y.shape[1] == 2 and abs(len(y) / sr - 6.0) < 0.01
    assert 0.5 < np.abs(y).max() <= 0.9 and np.abs(y[-50:]).max() < 0.01
    loud = [np.sqrt(np.mean(y[int(a * sr):int((a + 0.5) * sr)] ** 2)) for a in (0.5, 2.5, 4.9)]
    assert min(loud) > 0.02                                           # sound all the way, the loop included
    m4a = C.render(C.auto_score("drive", 5, []), 5.0, str(tmp_path / "m.m4a"))
    assert os.path.getsize(m4a) > 10000


def test_note_samples_replace_the_synth(tmp_path, monkeypatch):
    import soundfile as sf
    d = tmp_path / "piano"
    d.mkdir()
    sf.write(str(d / "A4.wav"), np.sin(2 * np.pi * 440 * np.arange(C.SR) / C.SR).astype(np.float32), C.SR)
    monkeypatch.setattr(C, "SAMPLES", str(tmp_path))
    monkeypatch.setattr(C, "_BANKS", {})
    monkeypatch.setattr(C, "_NOTES", {})
    y = C.voice_note("piano", 81, 0.5, 1.0)                           # an octave up: twice as fast
    spec = np.abs(np.fft.rfft(y[:C.SR // 4]))
    assert abs(np.argmax(spec) * 4 - 880) < 8
    assert C.bank("pluck") == {}


def test_agent_score_retries_then_falls_back(tmp_path):
    asks = []

    def good(prompt, tools=(), timeout=0):
        asks.append(prompt)
        return (_score(voices=[{"inst": "pad", "abc": "[A,CE]8 |" * 6}]) if len(asks) == 2 else
                {"key": "Am", "voices": [{"inst": "bass", "abc": "C7 | C8 |"}]}), {}
    sc, meta = C.write_score("calm bed", 10, [{"label": "scene s2", "t": 4.8}], ask=good)
    assert meta == {"agent": True, "tries": 2, "bpm": sc["bpm"]} and "problems" in asks[1]
    assert "scene s2 at 4.80 s = bar" in asks[0] and f"Tempo: {sc['bpm']} bpm" in asks[0]
    assert "A voice talks over it" in asks[0]

    def broken(prompt, tools=(), timeout=0):
        raise RuntimeError("limit")
    sc, meta = C.write_score("upbeat", 10, [], narrated=False, ask=broken)
    assert sc["auto"] and meta["agent"] is False and "limit" in meta["why"]
    r = C.compose("calm", 4.0, [], str(tmp_path / "x.m4a"), ask=broken)
    assert r["credits"] == 0 and os.path.exists(r["file"]) and json.load(open(str(tmp_path / "x.score.json")))["auto"]


def test_explainer_uses_the_composer_for_no_credits(tmp_path, monkeypatch):
    from factory.hat import explainer as E, project as P
    d = str(tmp_path)
    pid = P.create("explainer", "t", d=d)["id"]
    P.write_artifact(pid, "scene_plan", {"scenes": [{"id": "a", "lines": [0, 0]}, {"id": "b", "lines": [1, 1]}]}, d)
    seen = {}

    def fake(prompt, secs, cues, out, narrated=True, ask=None, end_at=None):
        seen.update(cues=cues, narrated=narrated, end_at=end_at)
        open(out, "wb").write(b"x")
        return {"file": out, "agent": True, "bpm": 96, "credits": 0}
    monkeypatch.setattr(C, "compose", fake)
    m = E.compose_music(pid, "calm", 10.0, [{"start": 0.1, "end": 2.0}, {"start": 2.4, "end": 5.0}], True, d)
    assert m["credits"] == 0 and m["source"] == "composer" and m["bpm"] == 96 and m["file"].endswith("music-composed.m4a")
    assert seen == {"cues": [{"label": "scene b", "t": 2.55}], "narrated": True, "end_at": 2.55}
    assert m["ending"] == {"end_card": 2.55, "hit": 2.55, "seek": 0.0, "fits": True}
    assert E.composed({"use": True, "source": "composer"}) and not E.composed({"use": True})


def _rms(y, sr, a, b):
    return float(np.sqrt(np.mean(y[int(a * sr):int(b * sr)] ** 2)))


def test_the_score_ends_on_the_tonic_at_the_end_card(tmp_path):
    """t518: with end_at the loop stops there and every voice lands on the tonic together and rings out."""
    import soundfile as sf
    from factory import audiofx
    assert C.tonic("Am") == (9, True) and C.tonic("Bb") == (10, False) and C.tonic("F#m") == (6, True)
    sc = C.auto_score("calm", 12, [])
    notes = C.ending_notes(sc, 3.0)
    pitched = [p for vi, p, ln, v in notes if sc["voices"][vi]["inst"] != "drums"]
    assert pitched and all(p % 12 in (9, 0, 4) for p in pitched)          # A minor triad only
    for vi, p, ln, v in notes:
        lo, hi = C.INSTRUMENTS[sc["voices"][vi]["inst"]][:2]
        assert sc["voices"][vi]["inst"] == "drums" or lo <= p <= hi
    out = str(tmp_path / "end.wav")
    C.render(sc, 12.0, out, end_at=8.0)
    y, sr = sf.read(out)
    y = y.mean(axis=1)
    assert abs(len(y) / sr - 12.0) < 0.01
    assert _rms(y, sr, 8.02, 8.5) > 1.5 * _rms(y, sr, 7.4, 7.9)          # the final chord is a hit, not a fade
    assert _rms(y, sr, 9.5, 10.5) > 0.005                                  # and it rings out
    hit = audiofx.final_hit(out)
    assert abs(hit - 8.0) < 0.15
    C.render(sc, 12.0, out, end_at=11.9)                                   # no room to end: a plain fade
    assert abs(len(sf.read(out)[0]) / sr - 12.0) < 0.01


def test_a_bought_track_is_placed_so_its_ending_lands_on_the_end_card(tmp_path, monkeypatch):
    from factory import audiofx
    from factory.hat import explainer as E, project as P
    d = str(tmp_path)
    pid = P.create("explainer", "t", d=d)["id"]
    P.write_artifact(pid, "scene_plan", {"scenes": [{"id": "a", "lines": [0, 0]}, {"id": "end", "lines": [1, 1]}]}, d)
    times = [{"start": 0.1, "end": 4.0}, {"start": 6.0, "end": 9.0}]
    assert E.end_card_at(pid, times, d) == 6.15
    track = tmp_path / "t.mp3"
    track.write_bytes(b"x")
    rel = os.path.relpath(str(track), E.ROOT)
    monkeypatch.setattr(audiofx, "final_hit", lambda f: 20.4)
    m = E.end_on_card(pid, {"file": rel, "db": -22}, times, d)
    assert m["seek"] == 14.25 and m["ending"] == {"end_card": 6.15, "hit": 20.4, "seek": 14.25, "fits": True}
    monkeypatch.setattr(audiofx, "final_hit", lambda f: 3.0)              # ends too early: left alone
    m = E.end_on_card(pid, {"file": rel, "db": -22}, times, d)
    assert "seek" not in m and m["ending"]["fits"] is False
    decisions = [json.loads(x) for x in open(P.path(pid, "decisions.jsonl", d=d))]
    assert [x.get("choice") for x in decisions if x.get("category") == "music_ending"] == ["aligned", "not aligned"]
    P.write_artifact(pid, "assets", {"music": {"file": rel, "db": -22, "seek": 14.25}}, d)
    monkeypatch.setattr(E, "spec", lambda pid, plan=None, d=None: {"scenes": []})
    assert E._render_spec(pid, P.read_artifact(pid, "scene_plan", d), d)["music"]["seek"] == 14.25


def test_ui_strings_and_proposal_skills():
    from factory.config import ROOT
    src = open(os.path.join(ROOT, "studio", "hat.js"), encoding="utf-8").read()
    assert all(src.count(k + ":") == 2 for k in ("mu_composer", "mu_composed", "mu_plain"))
    for line in ("explainer", "animation", "long_explainer"):
        assert '"source": "composer"' in open(os.path.join(ROOT, "skills", "pipelines", line, "proposal.md")).read()
