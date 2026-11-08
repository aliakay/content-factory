"""The animatic stage: the draft film, what it can prove, and the note it sends back to its cause."""
import array, json, os, subprocess, wave

import pytest

from factory.hat import animatic as A
from factory.hat import manifest, project as P, runner

PLAN = {"concept": "test", "palette": {"bg": "#14232B", "ink": "#EDF1E8"}, "summary": "s",
        "scenes": [{"id": "hook", "lines": [0, 0], "html": "<div></div>"},
                   {"id": "end", "lines": [1, 1], "html": "<div></div>"}]}


@pytest.fixture
def d(tmp_path):
    return str(tmp_path / "projects")


def _stage(sid):
    return manifest.stage(manifest.get("explainer"), sid)


def _run(pid, sid, d, artifact=None):
    P.start(pid, sid, d=d)
    P.finish(pid, sid, artifact if artifact is not None else {"ok": sid}, d=d)


def _done(pid, sid, d):
    _run(pid, sid, d)
    if P.checkpoint(pid, sid, d)["status"] == "awaiting_approval":
        P.approve(pid, sid, d=d)


# ---------------------------------------------------------------- which stage a note belongs to

def test_route_sends_the_note_to_its_cause():
    assert A.route("sahne 3 çok kısa") == "scene_plan"
    assert A.route("3. sahnede kesme yok") == "scene_plan"
    assert A.route("the cut into the last shot is abrupt") == "scene_plan"
    assert A.route("metin çok uzun") == "script"
    assert A.route("the words are too fast") == "script"
    assert A.route("Sahne 2'nin metni uzun") == "scene_plan"     # the subject of the sentence wins
    assert A.route("olmamış, baştan") == "script"                # nothing specific: the words are the default
    assert A.route("METİN ÇOK UZUN") == "script"                 # Turkish caps fold like lower case


def test_a_note_never_renders(d, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a note must not spend a render")
    monkeypatch.setattr(A, "_capture", boom)
    pid = P.create("explainer", "t", d=d)["id"]
    out = A.run(pid, _stage("animatic"), note="sahne 3 çok kısa", d=d)
    assert out["revise"] == {"stage": "scene_plan", "note": "sahne 3 çok kısa"}
    assert out["review"]["verdict"] == "fix" and "sahne planına" in out["summary"]


# ---------------------------------------------------------------- the free click track

def test_the_click_track_lands_on_the_lines_and_the_scenes(tmp_path):
    sp = {"duration": 3.0, "voice_start": 0.15,
          "line_times": [{"start": 0.0, "end": 1.0}, {"start": 1.2, "end": 2.0}],
          "scenes": [{"id": "a", "start": 0.0}, {"id": "b", "start": 1.6}]}
    p = A._click_track(str(tmp_path / "clicks.wav"), sp)
    with wave.open(p) as w:
        assert w.getnchannels() == 2 and w.getframerate() == 48000 and w.getsampwidth() == 2
        assert w.getnframes() == int(3.0 * 48000) + 1
        frames = w.readframes(w.getnframes())
    samples = array.array("h")
    samples.frombytes(frames)

    def peak(t):
        i = int(t * 48000) * 2
        return max(abs(x) for x in samples[i:i + int(0.04 * 48000) * 2])
    assert peak(0.15) > 1000        # the first line starts 0.15 s in
    assert peak(1.35) > 1000        # the second line, at its own start + the voice start
    assert peak(1.60) > 1000        # the second scene
    assert peak(0.60) == 0          # nothing between the marks


def test_the_clicks_mux_onto_a_silent_render(tmp_path):
    from factory import audiofx, media
    if not os.path.exists(media.FFMPEG):
        pytest.skip("no ffmpeg here")
    silent, out = str(tmp_path / "s.mp4"), str(tmp_path / "o.mp4")
    subprocess.run([media.FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "color=black:s=32x32:d=2:r=15",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", silent], check=True)
    sp = {"duration": 2.0, "voice_start": 0.0, "line_times": [{"start": 0.0, "end": 1.0}],
          "scenes": [{"id": "a", "start": 0.0}]}
    audiofx.mix(silent, out, 2.0, extra_audio={"file": A._click_track(str(tmp_path / "c.wav"), sp), "db": -18})
    probe = json.loads(subprocess.check_output(
        [media.FFPROBE, "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", out]))
    assert "audio" in [s["codec_type"] for s in probe["streams"]]
    assert abs(media.probe_video(out)["duration"] - 2.0) < 0.2


# ---------------------------------------------------------------- the artifact

def test_the_artifact_carries_timing_scenes_and_no_credits(d, monkeypatch, tmp_path):
    pid = P.create("explainer", "t", d=d)["id"]
    P.write_artifact(pid, "script", {"lines": ["Avrupa gazı yüz avroyu aştı.", "Takip et."]}, d)
    P.write_artifact(pid, "scene_plan", PLAN, d)
    drawn = str(tmp_path / "animatic.mp4")
    open(drawn, "wb").close()
    seen = {}
    monkeypatch.setattr(A, "_capture", lambda pid, sp, plan, d=None: (seen.update(sp=sp), drawn)[1])
    monkeypatch.setattr(A, "_motion", lambda path: {"still_share": 0.05, "longest_hold_s": 0.3, "cuts_per_10s": 3.0,
                                                    "frozen_s": 0.0, "holds": []})
    out = A.run(pid, _stage("animatic"), d=d)
    art = out["artifact"]
    assert art["fps"] == 15 and art["timing"] == "draft" and art["duration"] > 0
    assert [s["id"] for s in art["scenes"]] == ["hook", "end"]
    assert art["scenes"][0]["words"] == 5 and art["scenes"][0]["seconds"] > 0
    assert out["cost"] == {"credits": 0, "usd": 0.0} and out["review"]["verdict"] == "pass"
    assert seen["sp"]["sound"] == {"sfx": False}          # the click track is the only sound: nothing paid
    assert not [f for f in art["flags"] if f["code"] == "line_uncovered"]


def test_a_failed_measurement_is_not_a_failed_animatic(d, monkeypatch, tmp_path):
    pid = P.create("explainer", "t", d=d)["id"]
    P.write_artifact(pid, "script", {"lines": ["a b", "c d"]}, d)
    P.write_artifact(pid, "scene_plan", PLAN, d)
    drawn = str(tmp_path / "animatic.mp4")
    open(drawn, "wb").close()

    def no_ffmpeg(path):
        raise RuntimeError("no ffmpeg here")
    monkeypatch.setattr(A, "_capture", lambda pid, sp, plan, d=None: drawn)
    monkeypatch.setattr(A, "_motion", lambda path: {"still_share": None, "longest_hold_s": None, "holds": [],
                                                    "frozen_s": None, "error": "no ffmpeg here"})
    out = A.run(pid, _stage("animatic"), d=d)
    assert out["artifact"]["motion"]["error"] == "no ffmpeg here" and out["artifact"]["scenes"]


def test_no_scene_plan_is_a_gate_error(d):
    pid = P.create("explainer", "t", d=d)["id"]
    P.write_artifact(pid, "script", {"lines": ["a b"]}, d)
    with pytest.raises(P.GateError, match="scene plan"):
        A.run(pid, _stage("animatic"), d=d)


# ---------------------------------------------------------------- what it can prove

def test_scene_rows_flag_short_scenes_and_impossible_pace():
    sp = {"lang": "tr", "duration": 10.0,
          "line_times": [{"start": 0.0, "end": 0.8}, {"start": 0.8, "end": 1.8}],
          "scenes": [{"id": "a", "lines": [0, 0], "start": 0.0, "end": 0.8},
                     {"id": "b", "lines": [1, 1], "start": 0.8, "end": 10.0}]}
    rows = A.scene_rows(sp, {"lines": ["bir", "bir iki üç dört beş altı"]})
    assert rows[0]["seconds"] == 0.8 and rows[0]["flags"] == ["short"]
    assert rows[1]["words"] == 6 and rows[1]["spoken"] == 1.0 and rows[1]["wps"] == 6.0
    assert rows[1]["flags"] == ["fast"]                      # six words in one second cannot be spoken


def test_the_tail_and_the_lead_in_do_not_look_slow():
    sp = {"lang": "tr", "duration": 9.0,
          "line_times": [{"start": 0.0, "end": 1.0}, {"start": 1.3, "end": 2.1}],
          "scenes": [{"id": "a", "lines": [0, 0], "start": 0.0, "end": 1.3},
                     {"id": "b", "lines": [1, 1], "start": 1.3, "end": 9.0}]}
    rows = A.scene_rows(sp, {"lines": ["bir iki üç", "dört beş"]})
    assert all(not r["flags"] for r in rows)                 # padding is not dead air


def test_flags_name_every_fault_with_a_number(d):
    pid = P.create("explainer", "t", d=d)["id"]
    sp = {"lang": "tr", "duration": 12.0, "timing": "draft",
          "line_times": [{"start": 0.0, "end": 4.0}],
          "scenes": [{"id": "a", "lines": [0, 0], "start": 0.0, "end": 11.5}]}
    script = {"lines": ["bir", "iki", "üç"]}
    rows = A.scene_rows(sp, script)
    flags = A.flags_of(pid, sp, rows, {"holds": [[0.0, 1.5]], "still_share": 0.1}, script, d)
    codes = {f["code"] for f in flags}
    assert {"scene_long", "dead_air", "line_uncovered", "hook_slow", "hook_still"} <= codes
    assert all(f["message"] and f["level"] in ("warn", "info") for f in flags)
    assert {f["code"] for f in flags if f["scene"] == "a"} == {"scene_long", "dead_air"}


def test_a_slideshow_is_flagged(d):
    pid = P.create("explainer", "t", d=d)["id"]
    sp = {"lang": "tr", "duration": 6.0, "timing": "draft", "line_times": [{"start": 0.0, "end": 1.0}],
          "scenes": [{"id": "a", "lines": [0, 0], "start": 0.0, "end": 6.0}]}
    flags = A.flags_of(pid, sp, A.scene_rows(sp, {"lines": ["bir"]}), {"still_share": 0.62, "holds": []}, {"lines": ["bir"]}, d)
    assert [f for f in flags if f["code"] == "slideshow"]


def test_duration_far_from_the_approved_proposal_is_reported(d):
    pid = P.create("explainer", "t", d=d)["id"]
    P.write_artifact(pid, "proposal", {"seconds": 60}, d)
    sp = {"lang": "tr", "duration": 30.0, "timing": "draft", "line_times": [{"start": 0.0, "end": 1.0}],
          "scenes": [{"id": "a", "lines": [0, 0], "start": 0.0, "end": 5.0}]}
    flags = A.flags_of(pid, sp, A.scene_rows(sp, {"lines": ["bir"]}), {"holds": []}, {"lines": ["bir"]}, d)
    assert [f for f in flags if f["code"] == "duration_off"]


# ---------------------------------------------------------------- revise moves the line back

def test_revise_moves_the_line_back_and_stales_what_came_after(d):
    pid = P.create("explainer", "t", d=d)["id"]
    for sid in ("research", "proposal", "script", "scene_plan"):
        _done(pid, sid, d)
    _run(pid, "animatic", d)
    assert P.next_stage(pid, d) == ("gate", "animatic")
    P.revise(pid, "scene_plan", "sahne 3 çok kısa", by="animatic", d=d)
    cp = P.checkpoint(pid, "scene_plan", d)
    assert cp["status"] == "pending" and cp["note"] == "sahne 3 çok kısa" and cp["revisions"] == 1
    assert P.checkpoint(pid, "animatic", d)["status"] == "stale"
    assert P.next_stage(pid, d) == ("run", "scene_plan")
    assert any(e["kind"] == "revise" for e in P.tail(pid, d=d))


def test_revise_refuses_what_it_cannot_do(d):
    pid = P.create("explainer", "t", d=d)["id"]
    _done(pid, "research", d)
    with pytest.raises(P.GateError, match="no work"):
        P.revise(pid, "script", "x", d=d)                   # nothing made there yet
    with pytest.raises(P.GateError, match="needs a note"):
        P.revise(pid, "research", "  ", d=d)
    P.start(pid, "proposal", d=d)
    with pytest.raises(P.GateError, match="running"):
        P.revise(pid, "research", "x", d=d)                 # a stage is running


def test_revise_has_the_same_revision_budget_as_feedback(d):
    pid = P.create("explainer", "t", d=d)["id"]
    _done(pid, "research", d)
    _done(pid, "proposal", d)
    for i in range(P.MAX_REVISIONS):
        P.revise(pid, "proposal", f"tur {i}", d=d)
        _done(pid, "proposal", d)
    with pytest.raises(P.GateError, match="revisions"):
        P.revise(pid, "proposal", "bir daha", d=d)


# ---------------------------------------------------------------- the line manager follows it

class Q:
    """A job queue that runs each job at once, like the real worker would."""
    def __init__(self, runner_, d):
        self.runner, self.d, self.jobs = runner_, d, []

    def __call__(self, kind, arg):
        self.jobs.append((kind, arg))
        self.runner.run_job(arg, self, d=self.d)
        return len(self.jobs)


def test_the_line_follows_a_note_the_animatic_sends_back(d, monkeypatch):
    import sys, types, factory.hat

    def fake_agent(pid, s, note=None, d=None):
        return {"artifact": {"ok": s["id"], "note": note}}

    def fake_animatic(pid, s, note=None, d=None):
        return {"revise": {"stage": A.route(note), "note": note}} if note else {"artifact": {"ok": "animatic"}}

    fake = types.SimpleNamespace(run_stage=fake_agent)
    monkeypatch.setitem(sys.modules, "factory.hat.agent", fake)
    monkeypatch.setattr(factory.hat, "agent", fake, raising=False)
    monkeypatch.setattr(runner, "_code_step",
                        lambda call: fake_animatic if call.endswith("animatic:run") else fake_agent)
    pid = P.create("explainer", "t", d=d)["id"]
    q = Q(runner, d)
    runner.advance(pid, q, d=d)
    for sid in ("proposal", "script", "scene_plan"):
        runner.approve(pid, sid, q, d=d)
    assert P.next_stage(pid, d) == ("gate", "animatic")
    assert runner.feedback(pid, "animatic", "metin çok uzun", q, d=d) == ("gate", "script")
    assert P.read_artifact(pid, "script", d)["note"] == "metin çok uzun"
    assert P.checkpoint(pid, "script", d)["revisions"] == 1
    assert P.checkpoint(pid, "scene_plan", d)["status"] == "stale"
    assert P.checkpoint(pid, "animatic", d)["status"] == "stale"


def test_the_manifest_runs_the_animatic_before_the_voice(d):
    ids = [s["id"] for s in manifest.get("explainer")["stages"]]
    assert ids.index("scene_plan") < ids.index("animatic") < ids.index("assets")
    s = manifest.stage(manifest.get("explainer"), "animatic")
    assert s["run"] == "code" and s["gate"] and s["call"] == "factory.hat.animatic:run"
    assert s["artifact"] == "animatic" and s["name"]["tr"] == "Animatik"
