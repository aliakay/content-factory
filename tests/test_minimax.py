"""MiniMax H3 clips (t508): a 480p draft, the final only after the creator approves it, all inside the budget."""
import json, os

import pytest

from factory.hat import explainer as X, minimax as M, project as P


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    from factory import llm
    def refuse(*a, **k):
        raise AssertionError("a test tried to call a real model")
    for name in ("ask_text", "ask", "ask_json"):
        if hasattr(llm, name):
            monkeypatch.setattr(llm, name, refuse)


@pytest.fixture
def d(tmp_path):
    return str(tmp_path / "projects")


def _project(d, credits=20000):
    pid = P.create("cinematic", "clips", d=d, aspect="9:16")["id"]
    if credits is not None:
        p = P.load(pid, d)
        p["budget"] = {"credits": credits}
        P.save(p, d)
    return pid


class Gen:
    """Stands in for eleven.video: records each call, returns a file and a cost per second."""
    def __init__(self, tmp_path, per_s=350.0, fail=False):
        self.calls, self.per_s, self.fail, self.tmp = [], per_s, fail, tmp_path

    def __call__(self, con, prompt, approved, seconds, account, aspect, flow_id, **k):
        self.calls.append({"prompt": prompt, "approved": approved, "seconds": seconds, "aspect": aspect, **k})
        if self.fail:
            raise RuntimeError("connector said no")
        f = self.tmp / f"clip{len(self.calls)}.mp4"
        f.write_bytes(b"\0" * 64)
        return str(f), self.per_s * seconds, flow_id or "flow1", f"node{len(self.calls)}"


def test_models_and_estimates_follow_resolution_and_inputs():
    assert M.model_for("480p") == M.MAX and M.model_for("768p") == M.MAX
    assert M.model_for("2K") == M.PLAIN and M.model_for("768p", refs=True) == M.PLAIN
    e = M.estimate(5, "768p")
    assert e["draft"]["model"] == M.MAX and e["draft"]["resolution"] == "480p"
    assert 1500 < e["draft"]["credits"] < 2000 and e["final"]["credits"] > e["draft"]["credits"]
    assert e["total"] == e["draft"]["credits"] + e["final"]["credits"]
    assert M.estimate(30, "2K")["final"]["seconds"] == 15 and M.estimate(1)["draft"]["seconds"] == 5
    assert M.rates()["480p"] and M.rates()["2K"] > M.rates()["768p"]


def test_new_checks_the_clip(d, tmp_path):
    pid = _project(d)
    with pytest.raises(M.ClipError, match="sentence"):
        M.new(pid, "boat", 5, d=d)
    with pytest.raises(M.ClipError, match="quality"):
        M.new(pid, "A paper boat drifts on a pond.", 5, "1080p", d=d)
    with pytest.raises(M.ClipError, match="not a file"):
        M.new(pid, "A paper boat drifts on a pond.", 5, start="../../etc/passwd", d=d)
    os.makedirs(P.path(pid, "refs", d=d))
    open(P.path(pid, "refs", "a.png", d=d), "wb").write(b"x")
    with pytest.raises(M.ClipError, match="cannot be combined"):
        M.new(pid, "A paper boat drifts on a pond.", 5, start="refs/a.png", refs=("refs/a.png",), d=d)
    c = M.new(pid, "A paper boat drifts on a pond.", 22, start="refs/a.png", d=d, user="ali")
    assert c["seconds"] == 15 and c["status"] == "new" and c["aspect"] == "9:16" and M.clips(pid, d) == [c]


def test_draft_then_final_only_after_the_creator_approves(d, tmp_path):
    pid = _project(d, 20000)
    gen = Gen(tmp_path)
    c = M.new(pid, "A paper boat drifts across a still pond at dawn, slow push-in.", 5, "768p", d=d)
    c = M.draft(pid, c["id"], d, gen=gen, con=object())
    call = gen.calls[0]
    assert c["status"] == "draft" and c["draft"]["credits"] == 1750 and c["draft"]["resolution"] == "480p"
    assert call["resolution"] == "480p" and call["model"] == M.MAX and call["rate_model"] == "minimax-h3-max@480p"
    assert call["approved"] == 20000 and not call["frame_aspect"]
    assert X.spent_credits(pid, d) == 1750 and X.remaining_budget(pid, d) == 18250
    with pytest.raises(M.ClipError, match="approves"):
        M.final(pid, c["id"], d, gen=gen, con=object())
    assert len(gen.calls) == 1
    M.approve(pid, c["id"], "ali", d)
    c = M.final(pid, c["id"], d, gen=gen, con=object())
    assert c["status"] == "final" and c["final"]["resolution"] == "768p" and gen.calls[1]["approved"] == 18250
    assert gen.calls[1]["prompt"] == call["prompt"] and M.spent(pid, d) == 3500
    with pytest.raises(M.ClipError):
        M.draft(pid, c["id"], d, gen=gen, con=object())


def test_a_remade_draft_counts_both_and_drops_the_approval(d, tmp_path):
    pid = _project(d)
    gen = Gen(tmp_path)
    c = M.new(pid, "A fox runs through snow, tracking shot.", 6, "2K", d=d)
    M.draft(pid, c["id"], d, gen=gen, con=object())
    M.approve(pid, c["id"], "ali", d)
    c = M.draft(pid, c["id"], d, gen=gen, con=object())
    assert c["draft"]["credits"] == 2 * 350 * 6 and c["status"] == "draft" and not c["approved_by"]
    M.approve(pid, c["id"], "ali", d)
    M.final(pid, c["id"], d, gen=gen, con=object())
    assert gen.calls[-1]["model"] == M.PLAIN and gen.calls[-1]["resolution"] == "2K"


def test_no_budget_no_clip_and_failures_are_kept(d, tmp_path):
    pid = _project(d, None)
    c = M.new(pid, "A paper boat drifts on a pond at dawn.", 5, d=d)
    with pytest.raises(P.GateError, match="budget"):
        M.draft(pid, c["id"], d, gen=Gen(tmp_path), con=object())
    pid = _project(d)
    c = M.new(pid, "A paper boat drifts on a pond at dawn.", 5, d=d)
    M.mark(pid, c["id"], "draft", d)
    with pytest.raises(RuntimeError):
        M.draft(pid, c["id"], d, gen=Gen(tmp_path, fail=True), con=object())
    c = M.get(pid, c["id"], d)
    assert c["status"] == "failed" and "connector said no" in c["error"] and not c["busy"] and M.spent(pid, d) == 0


def test_start_frame_is_uploaded_and_sets_the_aspect(d, tmp_path, monkeypatch):
    from factory import eleven
    pid = _project(d)
    os.makedirs(P.path(pid, "refs", d=d))
    open(P.path(pid, "refs", "a.png", d=d), "wb").write(b"x")
    monkeypatch.setattr(eleven, "new_flow", lambda account=None, name="": "flowS")
    ups = []
    monkeypatch.setattr(eleven, "upload", lambda path, flow, account=None: ups.append((os.path.basename(path), flow)) or "imgnode")
    gen = Gen(tmp_path)
    c = M.new(pid, "The drawing comes alive, the cat blinks.", 5, start="refs/a.png", d=d)
    c = M.draft(pid, c["id"], d, gen=gen, con=object())
    assert ups == [("a.png", "flowS")] and gen.calls[0]["inputs"] == {"imgnode": "the clip's start frame"}
    assert gen.calls[0]["frame_aspect"] and c["flow_id"] == "flowS"


def test_video_prompt_names_resolution_and_price_key(monkeypatch, tmp_path):
    from factory import credits, eleven
    seen = {}
    monkeypatch.setattr(eleven, "OUT", str(tmp_path))
    monkeypatch.setattr(eleven, "_account", lambda a: ("ali", {"type": "connector"}))
    monkeypatch.setattr(eleven, "_connector_context", lambda a: __import__("contextlib").nullcontext())
    monkeypatch.setattr(credits, "guard", lambda con, kind, model, units, approved, account="ali": seen.setdefault("guard", model))
    monkeypatch.setattr(credits, "record", lambda con, kind, model, *a, **k: seen.setdefault("record", model))
    monkeypatch.setattr(eleven, "_run", lambda prompt, tools, **k: (seen.setdefault("prompt", prompt) and
                                                                    {"url": "u", "credit_cost": 1744, "flow_id": "f", "node_id": "n"}, {}))
    monkeypatch.setattr(eleven, "_download", lambda url, ext, key: str(tmp_path / f"{key}.{ext}"))
    path, cost, flow, node = eleven.video(None, "a boat", 2000, 5, model="minimax-h3-max", resolution="480p",
                                          rate_model="minimax-h3-max@480p", inputs={"n1": "the clip's start frame"},
                                          frame_aspect=True)
    assert cost == 1744 and seen["guard"] == seen["record"] == "minimax-h3-max@480p"
    assert '"resolution": "480p"' in seen["prompt"] and "no aspect_ratio" in seen["prompt"]


def test_studio_clip_actions(d, tmp_path, monkeypatch):
    from studio import hat_api
    monkeypatch.setattr(P, "DIR", d)
    monkeypatch.setattr(hat_api, "_check", lambda pid: pid)
    monkeypatch.setattr(hat_api.accounts, "current", lambda: "ali")
    pid = _project(d)
    jobs = []
    q = lambda kind, arg: jobs.append((kind, json.loads(arg))) or len(jobs)
    out = hat_api.post(None, f"/api/hat/project/{pid}/clips",
                       {"action": "draft", "prompt": "A paper boat drifts on a pond at dawn.", "seconds": 6}, q)
    cid = out["clip"]
    assert jobs == [("minimax_draft", {"project": pid, "clip": cid})] and M.get(pid, cid)["busy"] == "draft"
    with pytest.raises(ValueError):
        hat_api.post(None, f"/api/hat/project/{pid}/clips", {"action": "redraft", "clip": cid}, q)
    M.draft(pid, cid, gen=Gen(tmp_path), con=object())
    card = hat_api.clips_view(pid)
    assert card["clips"][0]["draft"]["url"]
    assert card["left"] == 20000 - 2100 and card["clips"][0]["estimate"]["final"]["credits"]
    hat_api.post(None, f"/api/hat/project/{pid}/clips", {"action": "approve", "clip": cid}, q)
    c = M.get(pid, cid)
    assert jobs[-1][0] == "minimax_final" and c["approved_by"] == "ali" and c["busy"] == "final"
    assert "clips" in hat_api.project(pid)
    nb = _project(d, None)
    with pytest.raises(ValueError):
        hat_api.post(None, f"/api/hat/project/{nb}/clips", {"action": "draft", "prompt": "A paper boat on a pond."}, q)
