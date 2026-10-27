import json

import pytest

from factory import ideas, llm, media
from factory.store import connect


def test_extract_json_handles_fences_and_prose():
    assert llm.extract_json('Sure!\n```json\n{"a": [1, "}"]}\n```') == {"a": [1, "}"]}
    assert llm.extract_json('noise {"b": {"c": 2}} trailing') == {"b": {"c": 2}}
    with pytest.raises(llm.LLMError):
        llm.extract_json("no json here")


def test_best_segments_prefers_calm_stretches():
    rows = [(i / 10, 10.0 if 20 <= i < 40 else 1.0, 100.0) for i in range(80)]  # shaky 2-4 s
    segs = media.best_segments(rows, min_len=1.5)
    assert segs and all(not (s["start"] < 3.5 and s["end"] > 2.5) for s in segs)


def test_steady_clip_is_chunked():
    rows = [(i / 10, 0.4, 50.0) for i in range(300)]  # 30 s tripod shot
    segs = media.best_segments(rows, max_len=8, k=10)
    assert all(s["end"] - s["start"] <= 8.0 + 1e-6 for s in segs) and len(segs) >= 3


def test_places_group_by_day_and_distance(tmp_path):
    con = connect(str(tmp_path / "f.db"))
    a = media.assign_place(con, 47.4864, 11.0938, "2026-07-26")
    b = media.assign_place(con, 47.4801, 11.0980, "2026-07-26")   # ~0.8 km away
    c = media.assign_place(con, 47.4864, 11.0938, "2026-07-27")   # next day
    d = media.assign_place(con, 45.976, 9.2445, "2026-07-26")     # Lake Como
    assert a == b and a != c and a != d
    assert media.assign_place(con, None, None, "2026-07-26") is None


def _con_with_clips(tmp_path):
    con = connect(str(tmp_path / "f.db"))
    con.execute("INSERT INTO clips (clip_id, kind, duration, segments) VALUES ('V.MOV','video',10,'[]')")
    con.execute("INSERT INTO clips (clip_id, kind) VALUES ('P.JPG','photo')")
    return con


def test_sanitize_drops_unknown_clips_and_clamps(tmp_path):
    con = _con_with_clips(tmp_path)
    idea = {"shots": [{"clip_id": "V.MOV", "start": -3, "end": 99, "speed": 9, "transition": "spin", "punch": 1},
                      {"clip_id": "NOPE.MOV", "start": 0, "end": 2},
                      {"clip_id": "P.JPG", "dur": 30}],
            "beats": [{"t0": 0, "t1": 2, "type": "weird", "animation": "explode", "text": "x"}]}
    out = ideas.sanitize(con, idea)
    v, p = out["shots"]
    assert len(out["shots"]) == 2
    assert v["start"] == 0 and v["end"] == 10 and v["speed"] == 2.5 and v["transition"] == "fade" and v["punch"] == 0.15
    assert p["dur"] == 4.0
    assert out["beats"][0]["animation"] == "pop" and out["beats"][0]["type"] == "fact"


def test_counter_animation_counts_up_to_target():
    evs = ideas.beat_events({"t0": 1, "t1": 4, "type": "fact", "animation": "counter", "text": "2,962 m"}, 10)
    assert evs[-1]["text"].endswith("2,962 m") and not evs[0]["text"].endswith("2,962 m") and evs[-1]["end"] == 4


def test_typewriter_reveals_words():
    ev = ideas.beat_events({"t0": 0.5, "t1": 3, "type": "hook", "animation": "typewriter",
                            "text": "Your brain\\Nlies to you"}, 10)
    ev = [e for e in ev if e["style"] != "Draw"][0]
    assert ev["text"].count("\\k") == 5 and "\\N" in ev["text"]


def test_specs_map_photos_and_videos(tmp_path):
    idea = {"shots": [{"clip_id": "V.MOV", "start": 1, "end": 3, "speed": 1, "transition": "fade"},
                      {"clip_id": "P.JPG", "dur": 1.2, "transition": "slideleft", "punch": 0.1}],
            "beats": [{"t0": 0, "t1": 2, "type": "hook", "animation": "pop", "text": "Hi"}], "caption": "c"}
    m = ideas.to_specs(idea, "009_x")
    assert m["shots"][0]["video"] == [1, 3] and m["shots"][1]["photo"] == "raw/P.JPG"
    assert m["shots"][1]["trans"] == "slideleft" and "trans" not in m["shots"][0]
    r = ideas.render_spec(idea, "009_x", 4.0)
    texts = [e for e in r["events"] if e["style"] != "Draw"]
    assert r["input"] == "work/009_x_montage.mp4" and texts[0]["style"] == "Hook"
    assert any(e["style"] == "Draw" for e in r["events"])  # the hook sits on a panel


def test_reference_shot_stats():
    from factory.refs import shot_stats
    s = shot_stats([1.0, 2.5, 4.0], 6.0)
    assert s["shots"] == 4 and s["first_cut_s"] == 1.0 and s["avg_shot_s"] == 1.5
    assert shot_stats([], 7.0)["shots"] == 1


def test_sfx_plan_rules():
    from factory import sfx
    idea = {"beats": [{"t0": 0, "t1": 3, "type": "hook", "animation": "pop", "text": "x"},
                      {"t0": 3, "t1": 6, "type": "card", "animation": "slide", "text": "a\\Nb"},
                      {"t0": 6, "t1": 10, "type": "fact", "animation": "words", "text": "y"}]}
    montage = {"shots": [{}, {"trans": "slideleft", "xd": 0.25}, {"trans": "fade", "xd": 0.3}, {"trans": "slideup", "xd": 0.25}]}
    timing = {"starts": [0, 2.0, 4.5, 6.9], "total": 10}
    ev = sfx.plan(idea, montage, timing, "subtle")
    kinds = [e["kind"] for e in ev]
    assert "riser" in kinds and "hit" in kinds and kinds.count("hit") == 1
    assert all(b["t"] - a["t"] >= 0.6 or b["kind"] in ("riser", "hit") for a, b in zip(ev, ev[1:]))
    assert sfx.plan(idea, montage, timing, "off") == []
    r = sfx.to_render([e for e in ev if e["kind"] == "riser"])
    assert r and abs(r[0]["start"] + sfx.PEAKS["riser"] - r[0]["t"]) < 1e-6  # peak lands on t


def test_cover_rule_hook_visible_on_frame_zero():
    ev = [e for e in ideas.beat_events({"t0": 0, "t1": 2, "type": "hook", "animation": "words",
                                         "text": "Hi *there*"}, 10) if e["style"] != "Draw"]
    assert len(ev) == 1 and "\\alpha&HFF&\\blur" not in ev[0]["text"] and ev[0]["start"] == 0.0


def test_card_is_one_panel_with_lines():
    ev = ideas.beat_events({"t0": 2, "t1": 6, "type": "card", "animation": "slide",
                            "text": "1  Awe\\Nfeels big\\NPiff et al., 2015", "progress": [1, 3]}, 10)
    panels = [e for e in ev if e["style"] == "Draw" and "\\1c&H101010&" in e["text"]]
    assert len(panels) == 1 and any(e["style"] == "CardCite" for e in ev)
    assert sum(1 for e in ev if e["style"] == "Draw") == 5  # panel + accent rule + 3 dots (chapter card)


def test_beats_never_start_inside_a_transition():
    idea = {"beats": [{"t0": 0, "t1": 2.2, "type": "hook", "animation": "pop", "text": "a"},
                      {"t0": 2.2, "t1": 5, "type": "card", "animation": "slide", "text": "1  b"}]}
    r = ideas.render_spec(idea, "x", 5.0, transitions=[(2.1, 2.4)])
    card_starts = [e["start"] for e in r["events"] if e["style"] in ("CardText", "ChapterNum")]
    assert min(card_starts) >= 2.42 - 1e-6


def test_credit_estimate_ledger_and_cap(tmp_path, monkeypatch):
    from factory import credits
    monkeypatch.setattr(credits, "RATES_PATH", str(tmp_path / "rates.json"))
    con = connect(str(tmp_path / "f.db"))
    est = credits.estimate([{"kind": "tts", "model": "eleven_v4", "units": 200, "unit": "char", "label": "voice"},
                            {"kind": "video", "model": "heygen-avatar4", "units": 10, "unit": "s", "label": "avatar"}])
    assert est["total"] == round(73.67 / 64 * 200) and est["unknown"] == ["avatar"]   # unmeasured is never guessed
    credits.record(con, "video", "heygen-avatar4", 5, "s", 500.0)
    assert credits.rates()["video:heygen-avatar4"]["rate"] == 100.0                  # learned from the real run
    assert credits.month_spent(con) == 500.0
    assert credits.check_budget(con, 99_600)["ok"] is False


# ---------- explainer (topic -> voice -> code-rendered motion graphics) ----------
def _explainer_data():
    from factory import explainer
    lines = ["A new chip just dropped.", "It is ten times cheaper.", "One dollar in, five out.", "Would you use it?"]
    return explainer.sanitize({
        "title": "Chip", "header": "tech", "facts": [{"claim": "x", "source": "https://example.com"}],
        "voice": {"lines": lines},
        "scenes": [{"id": "hook", "lines": [0, 1], "elements": [{"type": "title", "text": "CHIP", "at": "dropped"}]},
                   {"id": "cta", "lines": [3, 3], "hide_captions": True,
                    "elements": [{"type": "cta", "question": "WOULD YOU LET IT RUN YOUR WORKDAY", "at": "Would"},
                                 {"type": "bogus", "text": "dropped by sanitize"}]}]}, "topic")


def test_explainer_sanitize_covers_all_lines():
    d = _explainer_data()
    assert [s["lines"] for s in d["scenes"]] == [[0, 2], [3, 3]]  # scenes cover every line, in order
    assert all(e["type"] != "bogus" for s in d["scenes"] for e in s["elements"])
    assert d["scenes"][1]["elements"][0]["question"].count("\n") <= 1  # CTA question wraps to at most 2 lines
    assert d["claims"] and d["aspect"] == "9:16" and d["shots"] == []


def test_explainer_compile_resolves_trigger_words():
    from factory import explainer, formats, productions as P
    d = _explainer_data()
    p = {"data": d, "name": "t", "format": "explainer_short"}
    spec, total, starts, _ = explainer.compile_spec(None, p, formats.get("explainer_short"), P.VO_START)
    assert starts[0] == 0 and starts[1] > 0 and spec["scenes"][-1]["end"] == total
    hook = spec["scenes"][0]["elements"][0]
    assert hook["at"] < 0  # first hook element is already on screen at frame 0 (cover)
    cta = spec["scenes"][1]["elements"][0]
    assert cta["at"] >= spec["scenes"][1]["start"]
    assert spec["words"] and spec["header"].startswith("TECH · ")


def test_explainer_16x9_spec_and_still(tmp_path, monkeypatch):
    import importlib.util, os
    from factory import explainer, formats, productions as P
    d = _explainer_data()
    d["aspect"] = "16:9"
    spec, *_ = explainer.compile_spec(None, {"data": d, "name": "t169", "format": "explainer_short"},
                                      formats.get("explainer_short"), P.VO_START)
    assert spec["aspect"] == "16:9"
    path = os.path.join(os.path.dirname(__file__), "..", "bin", "explainer.py")
    sp = importlib.util.spec_from_file_location("explainer_r", path)
    r = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(r)
    monkeypatch.setattr(r, "ROOT", str(tmp_path))
    f = tmp_path / "s.json"
    f.write_text(json.dumps(spec))
    out = r.main(str(f), stills=[1.0])
    from PIL import Image
    assert Image.open(out[0]).size == (1920, 1080)
    r.set_canvas("9:16")
    assert (r.W, r.H, r.CX) == (1080, 1920, 540)


def test_style_deep_tokens_and_approval_gate(tmp_path, monkeypatch):
    from factory import styles
    monkeypatch.setattr(styles, "DIR", str(tmp_path))
    roles = {"paper": False, "bg_top": "#0b0b12", "bg_bot": "#151530", "text": "#f5f5f5", "muted": "#9a9ab0",
             "accent": "#ff4d6d", "hot": "#ffb703", "hero": "#ffffff", "highlight": "#9be15d",
             "type": {"class": "condensed_display", "case": "as_is", "tracking": "wide"},
             "layout": {"cards": "square", "shadow": "soft", "grid": "bogus"},
             "motion": {"entrance": "rise", "pace": "fast", "transition": "cut"}}
    sid = styles.save_roles("night", roles)
    t = styles.get(sid)["theme"]
    assert t["FONT_DISPLAY"] == "Anton-Regular.ttf" and t["UPPER"] is False and t["RADIUS"] == 4
    assert list(t["HIGHLIGHT"]) == [155, 225, 93] and t["ENTRANCE"] == "rise" and t["POP_DUR"] == 0.18
    assert "GRID" not in t                                  # unknown values fall back to the look's default
    assert not styles.valid("custom:" + sid)                # drafts need the creator's approval
    styles.approve(sid)
    assert styles.valid("custom:" + sid)
    assert styles.pace_from({"cuts_per_s": 1.2, "motion_energy": 0.01}) == "fast"
    assert styles.pace_from({"cuts_per_s": 0.1, "motion_energy": 0.01}) == "calm"
