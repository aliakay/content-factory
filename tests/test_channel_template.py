"""Channel templates: a pilot film's format saved once, then every episode of the channel made from it."""
import json, os

import pytest

from factory import channels
from factory.hat import agent, channel as C, manifest, project as P, runner, shortplan as SP, tools as T

SCRIPT = {"title": "Why flames are orange", "hook": "A candle in space burns blue.",
          "lines": ["A candle in space burns blue.", "Soot glows orange on Earth.", "Gas burns clean and blue.",
                    "Which flame is hotter?"], "caption": "Orange is soot. Blue is clean.", "claims": []}
BOARD = {"palette": {"bg": "#101418", "ink": "#F2F0E9", "accent": "#FFD93D"},
         "type": {"display": "Anton", "body": "Inter Tight", "scale": {"display": 96}},
         "rules": [{"what": w, "says": "x"} for w in ("light", "type", "motion", "camera")], "style": None,
         "fingerprint": "fp1", "summary": "s"}
PLAN = {"concept": "one flame, two colours", "palette": BOARD["palette"], "global_css": ".w{color:#F2F0E9}",
        "kit": "title block, figure, label",
        "scenes": [{"id": "soot", "lines": [0, 1], "mechanism": "count_up", "shows": "the soot count climbs",
                    "camera": {"move": "push_in", "seconds": 1.5, "easing": "ease_out", "target": "the flame"},
                    "html": '<div class="w"><b data-e="1">soot</b></div>', "css": ".soot{}", "js": "T.start"},
                   {"id": "gas", "lines": [2, 3], "mechanism": "scale_compare", "shows": "the blue flame rises",
                    "camera": {"move": "pan_left", "seconds": 3, "easing": "ease_out", "target": "the burner"},
                    "html": '<div class="w"><b data-e="1">gas</b></div>', "css": "", "js": ""}], "summary": "s"}
PROPOSAL = {"concepts": [{"id": "a", "title": "t", "hook": "h", "structure": "hook -> soot -> gas -> question",
                          "look": "style.ink_wash"}], "chosen": "a", "seconds": 40, "look": "style.ink_wash",
            "techniques": ["look.night_palette"], "voice": {"tone": "calm", "pace": "measured"},
            "music": {"use": True, "source": "elevenlabs", "prompt": "soft koto"},
            "cost": {"credits": 2400, "lines": []}, "summary": "s"}


@pytest.fixture
def d(tmp_path, monkeypatch):
    monkeypatch.setattr(channels, "DIR", str(tmp_path / "channels"))
    return str(tmp_path / "projects")


def _pilot(d, tmp_path, music=True):
    pid = P.create("explainer", "Why flames are orange", video_lang="en", d=d,
                   extra={"eleven_account": "acc", "voice_id": "voiceFromProject1"})["id"]
    for name, art in (("script", SCRIPT), ("direction", BOARD), ("scene_plan", PLAN), ("proposal", PROPOSAL),
                      ("publish", {"caption": "Orange is soot?", "hashtags": ["#fire"]})):
        P.write_artifact(pid, name, art, d)
    assets = {"voice": {"voice_id": "voiceFromAssets12", "file": "v.mp3"}}
    if music:
        track = tmp_path / "track.mp3"
        track.write_bytes(b"ID3 not really music")
        assets["music"] = {"file": str(track), "prompt": "soft koto", "credits": 1600, "db": -22}
    P.write_artifact(pid, "assets", assets, d)
    p = P.load(pid, d)
    p["budget"] = {"credits": 2400, "lines": [{"kind": "tts", "credits": 800}, {"kind": "music", "credits": 1600}]}
    P.save(p, d)
    return pid


def _episode(d, tpl, title="How a heat pump works"):
    pid = P.create(C.LINE, title, video_lang="en", channel=tpl["channel"], d=d, extra={"ui_lang": "en"})["id"]
    C.attach(pid, tpl, d)
    return pid


def test_the_line_asks_three_times_and_reads_the_explainers_briefs():
    m = manifest.get(C.LINE)
    assert [s["id"] for s in m["stages"] if s["gate"]] == ["script", "animatic", "publish"]
    assert manifest.stage(m, "proposal")["run"] == "code" and manifest.stage(m, "proposal")["schema"] == "proposal_code"
    assert agent.skill(C.LINE, "script", {"video_lang": "en"}) == agent.skill("explainer", "script", {"video_lang": "en"})


def test_a_film_without_a_scene_plan_cannot_become_a_template(d):
    pid = P.create("explainer", "Half done", d=d)["id"]
    assert "script" in C.can_capture(pid, d)
    with pytest.raises(P.GateError):
        C.capture(pid, "howitworks", d=d)
    other = P.create("podcast", "Not this line", d=d)["id"]
    assert "explainer" in C.can_capture(other, d)


def test_capture_freezes_the_pilot_and_keeps_its_track_as_the_theme(d, tmp_path):
    pid = _pilot(d, tmp_path)
    tpl = C.capture(pid, "howitworks", name="How It Works", by="cem", d=d)
    assert C.load("howitworks") == tpl
    assert tpl["seconds"] == 40 and tpl["look"] == "style.ink_wash" and tpl["video_lang"] == "en"
    assert tpl["voice"]["voice_id"] == "voiceFromAssets12" and tpl["voice"]["tone"] == "calm"
    assert tpl["board"]["palette"] == BOARD["palette"] and "fingerprint" not in tpl["board"]
    assert tpl["design"]["global_css"] == PLAN["global_css"] and tpl["design"]["kit"] == PLAN["kit"]
    assert tpl["pilot"]["lines"] == SCRIPT["lines"] and tpl["structure"].startswith("hook ->")
    assert [sc["id"] for sc in tpl["library"]] == [pid[:3] + "-soot", pid[:3] + "-gas"] and tpl["library"][0]["html"]
    assert tpl["music"]["source"] == "channel" and os.path.isfile(os.path.join(channels.DIR, "howitworks", "theme.mp3"))
    assert tpl["credit_cap"] == 1000          # the narration's 800 with a quarter to spare; the theme costs nothing
    assert C.summary(tpl)["library"][0] == {"id": pid[:3] + "-soot", "mechanism": "count_up", "shows": "the soot count climbs"}
    assert "html" not in json.dumps(C.summary(tpl))


def test_a_new_track_each_time_is_priced_and_saving_again_keeps_notes(d, tmp_path):
    pid = _pilot(d, tmp_path)
    C.capture(pid, "howitworks", d=d)
    C.update("howitworks", credit_cap=5000, notes=["always end on a question", " "])
    tpl = C.capture(pid, "howitworks", music="new", d=d)
    assert tpl["music"] == {"use": True, "source": "elevenlabs", "prompt": "soft koto"}
    assert tpl["notes"] == ["always end on a question"] and tpl["credit_cap"] == 5000
    assert [x["kind"] for x in C.cost_lines(tpl, 600)] == ["tts", "music"]
    assert [x["kind"] for x in C.cost_lines({**tpl, "music": {"use": True, "source": "channel"}}, 600)] == ["tts"]
    assert C.update("howitworks", credit_cap=None)["credit_cap"] is None


def test_the_template_proposal_needs_no_model_and_locks_the_budget(d, tmp_path):
    tpl = C.capture(_pilot(d, tmp_path), "howitworks", name="How It Works", d=d)
    pid = _episode(d, tpl)
    P.start(pid, "research", d=d)
    P.finish(pid, "research", artifact={"insight": "x"}, d=d)
    P.start(pid, "proposal", d=d)
    cp = runner.execute(pid, "proposal", d)
    assert cp["status"] == "done", cp.get("error")
    art = P.read_artifact(pid, "proposal", d)
    assert T.validate_artifact("proposal_code", art) in (None, [])
    assert art["seconds"] == 40 and art["voice"]["voice_id"] == "voiceFromAssets12"
    assert art["music"]["source"] == "channel" and [x["kind"] for x in art["cost"]["lines"]] == ["tts"]
    assert P.load(pid, d)["budget"]["credits"] == art["cost"]["credits"] > 0      # no gate: locked on finish
    assert P.next_stage(pid, d) == ("run", "script")


def test_a_project_without_a_template_fails_with_the_reason(d):
    pid = P.create(C.LINE, "No template", d=d)["id"]
    with pytest.raises(P.GateError, match="no channel template"):
        C.proposal(pid, manifest.stage(manifest.get(C.LINE), "proposal"), d=d)


def test_the_script_gate_refuses_a_text_above_the_channels_cap(d, tmp_path):
    tpl = C.capture(_pilot(d, tmp_path), "howitworks", d=d)
    pid = _episode(d, tpl)
    P.write_artifact(pid, "script", {**SCRIPT, "lines": ["A very long line about heat pumps. " * 40]}, d)
    C.update("howitworks", credit_cap=50)                    # read live: the cap can change while a film is on its way
    with pytest.raises(P.GateError, match="cap is 50"):
        C.guard(pid, "script", d)
    C.update("howitworks", credit_cap=None)
    C.guard(pid, "script", d)
    C.guard(pid, "animatic", d)
    plain = P.create("explainer", "Not an episode", d=d)["id"]
    C.guard(plain, "script", d)


def test_the_direction_board_is_the_channels(d, tmp_path, monkeypatch):
    from factory.hat import direction as D
    monkeypatch.setattr(D, "draw", lambda board, title, out: out)
    tpl = C.capture(_pilot(d, tmp_path), "howitworks", name="How It Works", d=d)
    pid = _episode(d, tpl)
    P.write_artifact(pid, "proposal", {"look": "style.ink_wash", "seconds": 40}, d)
    out = C.direction(pid, manifest.stage(manifest.get(C.LINE), "direction"), d=d)
    board = out["artifact"]
    assert board["palette"] == BOARD["palette"] and board["type"]["display"] == "Anton"
    assert board["rules"] == BOARD["rules"] and board["fingerprint"] and "How It Works" in out["summary"]


def test_the_agents_task_carries_the_mould_and_the_standing_notes(d, tmp_path):
    tpl = C.capture(_pilot(d, tmp_path), "howitworks", name="How It Works", d=d)
    pid = _episode(d, tpl)
    C.add_note("howitworks", "never say 'basically'")
    m = manifest.get(C.LINE)
    text = C.brief(pid, manifest.stage(m, "script"), d)
    assert "How It Works" in text and "[0] A candle in space burns blue." in text and "40 seconds" in text
    assert "never say 'basically'" in text                  # added after the episode started: notes are read live
    assert "Orange is soot?" in C.brief(pid, manifest.stage(m, "publish"), d)
    assert C.brief(pid, manifest.stage(m, "scene_plan"), d) == ""
    plain = P.create("explainer", "Not an episode", d=d)["id"]
    assert C.brief(plain, manifest.stage(manifest.get("explainer"), "script"), d) == ""
    assert "Channel template: How It Works" in agent.task(pid, manifest.stage(m, "script"), d=d)


def test_the_design_pass_is_held_to_the_channels_design_system(d, tmp_path):
    tpl = C.capture(_pilot(d, tmp_path), "howitworks", name="How It Works", d=d)
    pid = _episode(d, tpl)
    script = {"title": "Heat pumps", "lines": ["A heat pump moves heat.", "It does not make it."]}
    P.write_artifact(pid, "direction", BOARD, d)
    seen = []

    def ask(prompt):
        seen.append(prompt)
        return {"concept": "moving heat", "palette": {"bg": "#ff0000"}, "global_css": "body{color:red}", "kit": "mine",
                "scenes": [{"id": "move", "lines": [0, 1], "brief": f"heat travels. like: {tpl['library'][0]['id']}",
                            "shows": "heat travels", "mechanism": "count_up", "camera": {"move": "push_in"}}]}

    s = manifest.stage(manifest.get(C.LINE), "scene_plan")
    art = SP.design(pid, s, script, BOARD, {}, d=d, ask=ask)
    assert art["palette"] == BOARD["palette"] and art["global_css"] == PLAN["global_css"] and art["kit"] == PLAN["kit"]
    assert "CHANNEL DESIGN SYSTEM (How It Works" in seen[0] and tpl["library"][0]["id"] in seen[0]
    prompt = SP._scene_prompt(pid, s, art, art["scenes"], script, d)
    assert "Approved scenes of this channel" in prompt and "soot</b>" in prompt
    plain = P.create("explainer", "Not an episode", d=d)["id"]
    assert C.design_system(plain, d) == {} and C.design_brief(plain, d) == "" and C.scene_library(plain, [], d) == ""


def test_a_kanal_note_is_kept_for_later_episodes(d, tmp_path):
    tpl = C.capture(_pilot(d, tmp_path), "howitworks", d=d)
    pid = _episode(d, tpl)
    assert C.standing("Kanal: rakamları her zaman büyük yaz") == "rakamları her zaman büyük yaz"
    assert C.standing("3. sahne çok hızlı") is None
    assert C.keep_note(pid, "kanal: rakamları her zaman büyük yaz", d) is True
    assert C.keep_note(pid, "3. sahne çok hızlı", d) is False
    assert C.load("howitworks")["notes"] == ["rakamları her zaman büyük yaz"]


def test_an_approved_episode_adds_its_scenes_to_the_library(d, tmp_path):
    tpl = C.capture(_pilot(d, tmp_path), "howitworks", d=d)
    pid = _episode(d, tpl)
    new = {**PLAN["scenes"][0], "id": "pump", "mechanism": "cause_chain"}
    same_kind = {**PLAN["scenes"][0], "id": "newsoot"}            # same mechanism and move as the pilot's: replaces it
    P.write_artifact(pid, "scene_plan", {"scenes": [new, same_kind]}, d)
    lib = [sc["id"] for sc in C.learn(pid, d)["library"]]
    assert lib == [pid[:3] + "-pump", pid[:3] + "-newsoot", tpl["library"][1]["id"]]
    assert C.load("howitworks")["films"] == [pid]
    assert C.learn(P.create("explainer", "Not an episode", d=d)["id"], d) is None


def test_a_batch_starts_its_next_topic_when_one_stops(d, tmp_path):
    tpl = C.capture(_pilot(d, tmp_path), "howitworks", d=d)
    ids = []
    for t in ("Topic one is here", "Topic two is here", "Topic three is here"):
        pid = P.create(C.LINE, t, d=d, extra={"batch": "b1"})["id"]
        C.attach(pid, tpl, d)
        ids.append(pid)
    queued = []
    runner.advance(ids[0], lambda k, a: queued.append(a), d=d)
    assert C.next_in_batch(ids[0], lambda k, a: queued.append(a), d) == ids[1]
    assert C.next_in_batch(ids[0], lambda k, a: queued.append(a), d) == ids[2]
    assert C.next_in_batch(ids[0], lambda k, a: queued.append(a), d) is None and len(queued) == 3
    single = P.create(C.LINE, "No batch at all", d=d)["id"]
    assert C.next_in_batch(single, lambda k, a: queued.append(a), d) is None


def test_the_theme_is_not_bought_again():
    from factory import licence
    from factory.hat import explainer as X
    assert X.themed({"source": "channel", "file": "data/channels/x/theme.mp3"})
    assert not X.themed({"source": "channel"}) and not X.themed({"source": "elevenlabs", "file": "a.mp3"})
    row = licence.made_entries({"music": {"file": "m.mp3", "source": "channel"}})[0]
    assert row["what"] == "Channel theme" and row["credit"] is False


def test_an_episode_script_is_written_by_sonnet():
    assert manifest.stage(manifest.get(C.LINE), "script")["model"] == "sonnet"
    assert manifest.stage(manifest.get("explainer"), "script")["model"] == "opus"      # the pilot keeps Opus
