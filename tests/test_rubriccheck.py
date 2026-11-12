"""The review lines code settles: order, the marks, and nothing raising on a broken artifact."""
import json

from factory import coldtest
from factory.hat import manifest, project as P, rubriccheck as R

TITLE = "Nvidia CEO'su Huang: Özür kesin, casusluk iddia"


def _proj(tmp_path, line="explainer", lang="tr"):
    d = str(tmp_path / "projects")
    return P.create(line, "Nvidia özür ve casusluk iddiası", video_lang=lang, d=d)["id"], d


def _write(d, pid, name, data):
    P.write_artifact(pid, name, data, d)


def _s(line_id, sid):
    return manifest.stage(manifest.get(line_id), sid)


def _script(words_per_line, hook="Nvidia patronu Jensen Huang eşini aldattı."):
    lines = [hook] + ["kelime " * n for n in words_per_line]
    return {"title": TITLE, "hook": hook, "lines": lines, "claims": [], "summary": "özet"}


# a 45 s Turkish film: 45 * 2.4 = 108 words; 102 words sit inside the 10 % band
def _fits():
    return _script([8] * 12)


def test_settle_keeps_the_review_order_and_returns_none_for_unknown_lines(tmp_path):
    pid, d = _proj(tmp_path)
    stage = _s("explainer", "script")
    out = R.settle(pid, stage, d)
    assert len(out) == len(stage["review"]) == 7
    assert all(x is None for x in out)          # no artifact yet: nothing can be decided


def test_research_sources_and_data_points(tmp_path):
    pid, d = _proj(tmp_path)
    stage = _s("explainer", "research")
    good = {"sources": [{"url": f"https://x.test/{i}", "title": f"s{i}"} for i in range(5)],
            "data_points": [{"claim": "c", "source": "https://x.test/0"}], "angles": [{"title": "a"}] * 3,
            "insight": "one thing", "misconception": "wrong thing", "summary": "özet"}
    _write(d, pid, "research", good)
    out = R.settle(pid, stage, d)
    assert out[0]["score"] == 10 and "5 sources" in out[0]["note"]
    assert out[1] is None and out[2] is None and out[3] is None

    bad = {**good, "sources": [{"url": f"not a url {i}"} for i in range(4)] + [{"url": "https://x.test"}],
           "data_points": [{"claim": "a", "source": "https://x.test"}, {"claim": "b"}]}
    _write(d, pid, "research", bad)
    out = R.settle(pid, stage, d)
    assert out[0]["score"] < 10 and "1 of 5" in out[0]["note"] and "1 of 2" in out[0]["note"]


def test_a_short_angle_list_fails_and_a_long_one_waits_for_the_reader(tmp_path):
    pid, d = _proj(tmp_path)
    stage = _s("explainer", "research")
    art = {"sources": [{"url": "https://x.test"}] * 5, "data_points": [{"claim": "c", "source": "https://x.test"}],
           "insight": "i", "misconception": "m", "summary": "s", "angles": [{"title": "a"}, {"title": "b"}]}
    _write(d, pid, "research", art)
    out = R.settle(pid, stage, d)
    assert out[2]["score"] < 10 and "2 angles" in out[2]["note"]
    art["angles"] = [{"title": x} for x in "abcd"]
    _write(d, pid, "research", art)
    assert R.settle(pid, stage, d)[2] is None


def test_script_word_count_reads_the_approved_duration(tmp_path):
    pid, d = _proj(tmp_path)
    stage = _s("explainer", "script")
    _write(d, pid, "proposal", {"seconds": 45, "chosen": "a", "concepts": [{"id": "a"}], "cost": {"credits": 1, "lines": []},
                                "look": "l", "summary": "s"})
    _write(d, pid, "script", _fits())
    out = R.settle(pid, stage, d)
    assert out[0]["score"] == 10 and "102 words" in out[0]["note"]

    _write(d, pid, "script", _script([17] * 11))        # ~190 words: a 78 s film, not a 45 s one
    out = R.settle(pid, stage, d)
    assert out[0]["score"] < 10 and "words at 2.4 words/s" in out[0]["note"] and "97–119" in out[0]["note"]


def test_script_claims_words_and_hook(tmp_path):
    pid, d = _proj(tmp_path)
    stage = _s("explainer", "script")
    script = _fits()
    script["claims"] = [{"text": "fact", "verified": True, "source": "https://x.test/1"}]
    _write(d, pid, "script", script)
    out = R.settle(pid, stage, d)
    assert out[2] is None            # declared claims in order: code cannot know a line makes an undeclared one
    assert out[4]["score"] == 10 and out[5]["score"] == 10

    script["claims"] = [{"text": "fact", "verified": False, "source": "https://x.test/1"}]
    script["lines"][2] = "Bu cümle bir — tire taşıyor."
    script["hook"] = "Merhaba arkadaşlar, bugün Nvidia."
    script["lines"][0] = script["hook"]
    _write(d, pid, "script", script)
    out = R.settle(pid, stage, d)
    assert out[2]["score"] < 10 and "1 of 1" in out[2]["note"]
    assert out[4]["score"] < 10 and "dash" in out[4]["note"]
    assert out[5]["score"] < 10 and "greeting" in out[5]["note"]


def test_cold_test_needs_evidence_for_this_exact_script(tmp_path):
    pid, d = _proj(tmp_path)
    stage = _s("explainer", "script")
    script = _fits()
    _write(d, pid, "script", script)
    out = R.settle(pid, stage, d)
    assert out[6]["score"] < 10 and "cold_test" in out[6]["note"]

    _write(d, pid, "cold_read", {"fingerprint": coldtest.fingerprint(script),
                                 "result": {"ok": True, "one_sentence": TITLE, "problems": []}})
    assert R.settle(pid, stage, d)[6]["score"] == 10

    script["lines"].append("Bir satır daha eklendi.")
    _write(d, pid, "script", script)                    # the evidence now belongs to another script
    out = R.settle(pid, stage, d)
    assert out[6]["score"] < 10 and "different title or lines" in out[6]["note"]


def test_scene_plan_coverage_devices_and_rhythm(tmp_path):
    pid, d = _proj(tmp_path)
    stage = _s("explainer", "scene_plan")
    script = {"title": TITLE, "hook": "bir", "lines": ["iki kelime", "sekiz kelime burada ve daha fazlası var",
                                                        "üç kelime", "dokuz kelime burada ve daha da fazlası var"],
              "claims": [], "summary": "s"}
    _write(d, pid, "script", script)
    plan = {"concept": "c", "palette": {}, "summary": "s", "scenes": [
        {"id": f"s{i}", "lines": [i, i], "html": "<div></div>", "trigger": f"t{i}", "mechanism": f"m{i}"}
        for i in range(4)]}
    _write(d, pid, "scene_plan", plan)
    out = R.settle(pid, stage, d)
    assert out[0]["score"] == 10 and out[1]["score"] == 10 and out[2]["score"] == 10
    assert out[3] is None and out[7] is None

    plan["scenes"][1]["trigger"] = ""
    plan["scenes"][1]["mechanism"] = plan["scenes"][0]["mechanism"]
    plan["scenes"] = plan["scenes"][:3]                 # line 4 is shown by no scene
    for i, sc in enumerate(plan["scenes"]):
        script["lines"][i] = "iki kelime"
    _write(d, pid, "script", script)
    _write(d, pid, "scene_plan", plan)
    out = R.settle(pid, stage, d)
    assert out[0]["score"] < 10 and "line(s) [4]" in out[0]["note"] and "trigger" in out[0]["note"]
    assert out[1]["score"] < 10 and "m0" in out[1]["note"]
    assert out[2] is None                              # three scenes: rhythm_check says nothing


def test_scene_plan_rhythm_catches_even_scenes(tmp_path):
    pid, d = _proj(tmp_path)
    stage = _s("explainer", "scene_plan")
    _write(d, pid, "script", {"title": TITLE, "hook": "bir", "lines": ["iki kelime"] * 4, "summary": "s"})
    _write(d, pid, "scene_plan", {"concept": "c", "palette": {}, "summary": "s", "scenes": [
        {"id": f"s{i}", "lines": [i, i], "html": "<div></div>", "trigger": "t", "mechanism": f"m{i}"}
        for i in range(4)]})
    out = R.settle(pid, stage, d)
    assert out[2]["score"] < 10 and "spread" in out[2]["note"]


def test_animatic_lines_and_opening_motion(tmp_path):
    pid, d = _proj(tmp_path)
    stage = _s("explainer", "animatic")
    _write(d, pid, "script", {"title": TITLE, "hook": "bir", "lines": ["bir iki", "üç dört", "beş altı", "yedi sekiz"],
                              "summary": "s"})
    good = {"file": "a.mp4", "duration": 10, "summary": "s", "fps": 15,
            "scenes": [{"id": "a", "start": 0, "end": 5, "seconds": 5, "lines": [0, 1], "words": 10, "spoken": 4.5},
                       {"id": "b", "start": 5, "end": 10, "seconds": 5, "lines": [2, 3], "words": 10, "spoken": 4.5}],
            "motion": {"holds": [[0, 0.2], [0.5, 0.3]], "still_share": 0.1}}
    _write(d, pid, "animatic", good)
    out = R.settle(pid, stage, d)
    assert out[2]["score"] == 10 and out[3]["score"] == 10
    assert out[0] is None and out[1] is None

    bad = {"file": "a.mp4", "duration": 10, "summary": "s", "fps": 15,
           "scenes": [{"id": "a", "start": 0, "end": 5, "seconds": 5, "lines": [0, 1], "words": 30, "spoken": 4.0}],
           "motion": {"holds": [[0.5, 1.5]], "still_share": 0.5}}
    _write(d, pid, "animatic", bad)
    out = R.settle(pid, stage, d)
    assert out[2]["score"] < 10 and "line(s) [3, 4]" in out[2]["note"] and "words/s" in out[2]["note"]
    assert out[3]["score"] < 10 and "still" in out[3]["note"]


def test_assets_spend_against_the_approved_budget(tmp_path):
    pid, d = _proj(tmp_path)
    p = P.load(pid, d)
    p["budget"] = {"credits": 100}
    P.save(p, d)
    stage = _s("explainer", "assets")
    _write(d, pid, "assets", {"summary": "s"})
    assert R.settle(pid, stage, d)[1]["score"] == 10

    cp = P.checkpoint(pid, "research", d)
    cp["cost"]["credits"] = 150
    P._write_cp(pid, cp, d)
    out = R.settle(pid, stage, d)
    assert out[1]["score"] < 10 and "150 > 100" in out[1]["note"]


def test_publish_caption_and_hashtags(tmp_path):
    pid, d = _proj(tmp_path)
    stage = _s("explainer", "publish")
    _write(d, pid, "publish", {"caption": "S" * 160, "hashtags": ["#a", "#b"], "summary": "s"})
    out = R.settle(pid, stage, d)
    assert out[0]["score"] < 10 and "160" in out[0]["note"] and "question mark" in out[0]["note"]
    assert out[1]["score"] < 10 and "2 hashtags" in out[1]["note"]

    _write(d, pid, "publish", {"caption": "Sence Huang görevde kalmalı mı?", "hashtags": ["#a", "#b", "#c", "#d"],
                               "summary": "s"})
    out = R.settle(pid, stage, d)
    assert out[0]["score"] == 10 and "language" in out[0]["note"]
    assert out[1] is None                              # the right count still needs a reader for "match the topic"
    assert out[2]["score"] == 10                       # no assets: the attribution block is empty

    _write(d, pid, "publish", {"caption": "Sence kalmalı mı?", "hashtags": ["#a"], "summary": "s", "credits": "x"})
    out = R.settle(pid, stage, d)
    assert out[1]["score"] < 10 and "1 hashtags" in out[1]["note"]
    assert out[2]["score"] < 10 and "verbatim" in out[2]["note"]


def test_publish_credits_is_compared_with_the_ledger_block(tmp_path):
    pid, d = _proj(tmp_path)
    stage = _s("explainer", "publish")
    _write(d, pid, "scene_plan", {"concept": "c", "palette": {}, "summary": "s", "scenes": [], "stock": [
        {"file": "assets/stock/chart.jpg", "title": "Chart", "author": "A. Author", "license": "CC BY 4.0",
         "url": "https://example.test/chart"}]})
    _write(d, pid, "publish", {"caption": "Sence kalmalı mı?", "hashtags": ["#a", "#b", "#c"], "summary": "s",
                               "credits": "something else"})
    out = R.settle(pid, stage, d)
    assert out[2]["score"] < 10 and "verbatim" in out[2]["note"] and "Chart" in out[2]["note"]

    _write(d, pid, "publish", {"caption": "Sence kalmalı mı?", "hashtags": ["#a", "#b", "#c"], "summary": "s",
                               "credits": "Varlıklar:\n- Chart · A. Author · CC BY 4.0 · https://example.test/chart"})
    assert R.settle(pid, stage, d)[2]["score"] == 10

    _write(d, pid, "scene_plan", {"concept": "c", "palette": {}, "summary": "s", "scenes": [], "stock": [
        {"file": "assets/stock/hand.jpg", "title": "Hand", "author": "unknown"}]})
    out = R.settle(pid, stage, d)
    assert out[2]["score"] < 10 and "no known licence" in out[2]["note"]


def test_animation_splits_the_two_script_modes(tmp_path):
    pid, d = _proj(tmp_path, line="animation")
    stage = _s("animation", "script")
    _write(d, pid, "proposal", {"seconds": 20, "chosen": "a", "concepts": [{"id": "a"}],
                                "cost": {"credits": 1, "lines": []}, "look": "l", "summary": "s"})
    music = {"title": TITLE, "hook": "bir", "claims": [], "summary": "s", "narrate": False,
             "lines": ["üç kelime var", "dört kelime burada var", "iki kelime"], "holds": [6, 8, 6]}
    _write(d, pid, "script", music)
    out = R.settle(pid, stage, d)
    assert out[0]["score"] == 10 and out[1] is None      # music-led: holds, not a word budget
    music["lines"] = ["dokuz kelime burada ve daha da fazlası var"] + music["lines"]
    music["holds"] = [10, 6, 8, 6]
    _write(d, pid, "script", music)
    out = R.settle(pid, stage, d)
    assert out[0]["score"] < 10 and "over 7 words" in out[0]["note"] and "add up to" in out[0]["note"]

    narrated = {"title": TITLE, "hook": "bir", "claims": [], "summary": "s", "narrate": True,
                "lines": ["sekiz kelime burada ve daha da fazlası var"] * 6}
    _write(d, pid, "script", narrated)                   # 48 words at 2.4 words/s = 20 s
    out = R.settle(pid, stage, d)
    assert out[1]["score"] == 10 and out[0] is None


def test_a_broken_artifact_never_raises(tmp_path):
    pid, d = _proj(tmp_path)
    stage = _s("explainer", "research")
    _write(d, pid, "research", {"sources": "oops", "data_points": 7, "angles": {"a": 1}})
    out = R.settle(pid, stage, d)
    assert len(out) == 4 and isinstance(out[0], dict) and out[0]["score"] < 10

    _write(d, pid, "research", ["not", "an", "object"])
    assert R.settle(pid, stage, d) == [None] * 4

    _write(d, pid, "research", {"sources": [{"url": None}, 5], "data_points": [{"source": None}, "x"]})
    out = R.settle(pid, stage, d)
    assert isinstance(out, list) and len(out) == 4

    assert R.settle("no-such-project", stage, d) == [None] * 4


def test_a_line_that_is_not_text_is_left_to_the_model(tmp_path):
    pid, d = _proj(tmp_path)
    _write(d, pid, "script", _fits())
    stage = {**_s("explainer", "script"), "review": [None, 42, "words_check has no open findings: no dashes"]}
    out = R.settle(pid, stage, d)
    assert out[0] is None and out[1] is None and out[2]["score"] == 10


def test_publish_title_length_is_a_fail_only_rule(tmp_path):
    pid, d = _proj(tmp_path, line="long_explainer")
    stage = _s("long_explainer", "publish")
    _write(d, pid, "publish", {"title": "Uzun " * 15, "caption": "c", "hashtags": ["#a"], "summary": "s"})
    out = R.settle(pid, stage, d)
    assert out[0]["score"] < 10 and "characters (limit 70)" in out[0]["note"]

    _write(d, pid, "publish", {"title": "Kısa bir başlık", "caption": "c", "hashtags": ["#a"], "summary": "s"})
    assert R.settle(pid, stage, d)[0] is None          # length holds; the promise needs a reader


def test_coverage_reports_which_lines_have_a_rule():
    cov = R.coverage("explainer")
    assert cov["research"] == [True, False, True, False]
    assert cov["script"] == [True, False, True, False, True, True, True]
    assert cov["direction"] == [False, False]
    assert cov["publish"] == [True, True, True]
    assert set(cov) == {s["id"] for s in manifest.get("explainer")["stages"]}
    anim = R.coverage("animation")
    assert anim["script"][:2] == [True, True] and len(anim["script"]) == 6
    assert R.coverage("long_explainer")["publish"] == [True, False, True, True]
    assert all(not any(v) for v in R.coverage("documentary").values())     # that line lists no review focus
