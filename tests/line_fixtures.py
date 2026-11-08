"""Valid stage artifacts for the production-line tests, and a stand-in for the stage agents.

The line manager's gates are real rules: a script must pass the hook rule and the cold test, a scene plan needs its
camera, mechanism and subject, a direction board must exist before a scene is drawn, and the animatic must move in its
first two seconds. A flow test should not restate all of that, so the defaults here are one small, honest film that
passes every rule; a test that cares about a field overrides just that field.
"""
BOARD = {"palette": {"bg": "#101418", "ink": "#F2F0E9", "accent": "#FFD93D"},
         "type": {"display": "Anton", "body": "Inter Tight"},
         "rules": [{"what": "light", "says": "one hard key, no fill"},
                   {"what": "texture", "says": "8% grain, no gradients"},
                   {"what": "motion", "says": "one move per scene, never a still"},
                   {"what": "type", "says": "display at 5vw, body at 2vw"}],
         "summary": "one board"}


def board():
    return dict(BOARD, palette=dict(BOARD["palette"]), rules=[dict(r) for r in BOARD["rules"]])


def script(note=None):
    """A script the hook rule and the cold test both accept: line 1 names the title's subject with its figure."""
    lines = ["İstanbul krizi 3 günde bitti", "Depolar boşaldı, musluklar kapandı", "Sayaç 40 günü gösteriyor"]
    if note:
        lines[1] = str(note)
    return {"title": "İstanbul krizi", "hook": lines[0], "lines": lines, "claims": [], "summary": "s"}


def plan(scenes=None):
    """A scene plan drawn in BOARD's palette, with the camera, mechanism and subject every check asks for."""
    return {"concept": "c", "palette": dict(BOARD["palette"]), "global_css": "", "summary": "s",
            "scenes": scenes or [
                {"id": "hook", "lines": [0, 0], "html": '<div><h1>İstanbul 3 gün</h1></div>',
                 "shows": "the istanbul reservoir level dropping in three steps", "mechanism": "count_up",
                 "camera": {"move": "push_in", "seconds": 1.5, "easing": "ease_out", "target": "the level mark"}},
                {"id": "end", "lines": [1, 2], "html": '<div><p>Sayaç 40 gün</p></div>',
                 "shows": "the sayaç counter stopping at forty days", "mechanism": "scale_compare",
                 "camera": {"move": "pan_left", "seconds": 2.0, "easing": "ease_in_out", "target": "the counter"}}]}


def direction():
    return dict(board(), summary="s")


def animatic():
    return {"file": "draft.mp4", "duration": 3.0, "motion": {"still_share": 0.1, "holds": []}, "summary": "s"}


def publish():
    return {"caption": "Bir film?", "hashtags": ["#a"], "credits": "", "summary": "s"}


def artifact(stage, note=None):
    """A valid artifact for a stage a test did not script: the flow tests care about the line, not the content."""
    art = stage.get("artifact") or stage["id"]
    if art in ("script", "long_script"):
        return script(note)
    if art == "direction":
        return direction()
    if art == "scene_plan":
        return plan()
    if art == "animatic":
        return animatic()
    if art == "publish":
        return publish()
    return {"ok": stage["id"], "note": note}


def cold_evidence(pid, d, name="script"):
    """What the agent's `cold_test` call leaves behind: a passing verdict about these exact lines."""
    from factory import coldtest
    from factory.hat import project as P
    art = P.read_artifact(pid, name, d) or {}
    P.write_artifact(pid, "cold_read", {"fingerprint": coldtest.fingerprint(art),
                                        "result": {"ok": True, "one_sentence": str(art.get("title") or "")}}, d)


def fake_line(monkeypatch, outputs, fail_on=()):
    """Stand in for the stage agent and the code steps: each stage returns outputs[sid] (or a valid default)."""
    from factory.hat import project as P, runner

    def fake_agent(pid, s, note=None, d=None):
        if s["id"] in fail_on:
            raise RuntimeError(f"{s['id']} broke")
        out = outputs.get(s["id"])
        out = (out(note) if callable(out) else out) if out else {"artifact": artifact(s, note)}
        art = out.get("artifact") if isinstance(out, dict) else None
        if isinstance(art, dict) and art.get("hook") and art.get("lines"):
            # the agent ran `cold_test` before submitting: its verdict is about exactly these lines
            from factory import coldtest
            P.write_artifact(pid, "cold_read", {"fingerprint": coldtest.fingerprint(art),
                                                 "result": {"ok": True, "one_sentence": str(art.get("title") or "")}}, d)
        return out
    import sys, types
    import factory.hat
    fake = types.SimpleNamespace(run_stage=fake_agent)
    monkeypatch.setitem(sys.modules, "factory.hat.agent", fake)
    monkeypatch.setattr(factory.hat, "agent", fake, raising=False)   # `from . import agent` reads the package first
    monkeypatch.setattr(runner, "_code_step", lambda call: fake_agent)
    # the determinism gate renders the plan twice in a real browser; it has its own tests (test_motion_life)
    monkeypatch.setattr(runner, "_verify_scene_determinism", lambda pid, sid, d=None: None)
    return runner
