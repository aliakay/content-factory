"""The Lab: distill stores ideas and refuses repeats, the static scan refuses every forbidden pattern, build proves a
card with code (and rejects a bad one after two repairs), approve/reject touch both the DB and the card file, a lab
card is hidden from the designer until approved, and lessons stay at twelve lines.

No browser, no model, no network: every model call is a fake and the render/frame steps are stubbed, except in one
manual end-to-end check (see docs/LAB.md).
"""
import os
import sqlite3
import types

import pytest
import yaml

from factory import embed, lab, recipes


@pytest.fixture(autouse=True)
def hash_backend(monkeypatch):
    monkeypatch.setattr(embed, "_backend", "hash")          # deterministic, no model download in tests


@pytest.fixture
def con(tmp_path, monkeypatch):
    """A throwaway database and throwaway card/helper/work folders."""
    for name, sub in (("SRC", "recipes"), ("JS", "templates"), ("WORK", "work")):
        monkeypatch.setattr(lab, name, str(tmp_path / sub))
    monkeypatch.setattr(lab, "LOG", str(tmp_path / "work" / "lab.log"))
    monkeypatch.setattr(lab, "LESSONS", str(tmp_path / "lessons.md"))
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    lab._con(db)
    yield db
    db.close()


def case(i, text="a camera move over a wall of screens", cat="motion"):
    return {"id": i, "source": "r/AfterEffects", "key": f"k{i}", "title": "Wall of screens", "url": "https://x/y",
            "category": cat, "text": text, "seen_at": "2026-01-01T00:00:00Z", "status": "new"}


def fake_scan(cases):
    calls = []

    def _scan(con=None, fetch=None):
        calls.append("scan")
        return {"sources": 2, "seen": len(cases), "new": len(cases), "errors": []}

    def _cases(con=None, status="new", limit=50):
        calls.append(status)
        return [c for c in cases if c["status"] == status][:limit]

    def _mark(con, ids, status):
        calls.append((tuple(ids), status))
        for c in cases:
            if c["id"] in ids:
                c["status"] = status

    def _sources():
        return [{"id": "r/AfterEffects", "kind": "reddit", "count": 2}]

    m = types.ModuleType("factory.labscan")
    m.scan, m.cases, m.mark, m.sources = _scan, _cases, _mark, _sources
    return m


def install(monkeypatch, mod):
    import factory
    monkeypatch.setitem(__import__("sys").modules, "factory.labscan", mod)
    monkeypatch.setattr(factory, "labscan", mod, raising=False)


CARD = {
    "name": {"tr": "Nokta nabzı", "en": "Dot pulse"},
    "use": {"tr": "Tek bir noktayı vurgulamak.", "en": "Stressing one point on a dark screen."},
    "call": "FX.lab.pulse(tl, root, 0.2, {x: 540, y: 900, color: '#2ee6c5'})",
    "timing": {"tr": "Nabız 1.2 s.", "en": "The pulse takes 1.2 s."},
    "pitfalls": {"tr": ["Nokta kenara çok yaklaşmasın."], "en": ["Keep the dot away from the edges."]},
    "seconds": 2.0,
    "demo": "const d = D('<div></div>', 'left:500px;top:860px;width:80px;height:80px;border-radius:50%;background:#2ee6c5');\n"
            "tl.to(d, {scale: 6, opacity: 0, duration: 1.2}, 0.2);",
}


def card_yaml(cid, **over):
    return yaml.safe_dump({"id": cid, **CARD, **over}, sort_keys=False, allow_unicode=True)


def fake_ask(*answers):
    """A model that hands out the given answers in order (each a dict, or an exception to raise)."""
    box = list(answers)
    seen = []

    def _ask(prompt, tools=(), model=None):
        seen.append(prompt)
        a = box.pop(0) if len(box) > 1 else box[0]
        if isinstance(a, Exception):
            raise a
        return a, {}
    _ask.prompts = seen
    return _ask


def stub_render(calls=None, boom_on=None):
    def _render(cid, out):
        if boom_on and boom_on in cid:
            raise RuntimeError("page error: tween target undefined")
        (calls if calls is not None else []).append((cid, out))
        return out
    return _render


def stub_frames(flip=False):
    def _frames(path, times):
        # two different clips must differ: `flip` makes the second render's stills different
        tail = "b" if (flip and path.endswith("-2.mp4")) else "a"
        return [{"t": t, "sha": f"{i}{tail}", "mean": 40.0, "std": 60.0, "diff": 0.0 if i == 0 else 8.0}
                for i, t in enumerate(times)]
    return _frames


# ---------------------------------------------------------------- distill

def test_distill_stores_ideas_marks_cases_and_dedupes(con, monkeypatch):
    cases = [case("c1"), case("c2")]
    install(monkeypatch, fake_scan(cases))
    ask = fake_ask({"candidates": [
        {"id": "camera.screen_dive", "family": "camera", "name": {"tr": "Ekrana dalış", "en": "Dive into a screen"},
         "shows": "The camera flies into one screen of a wall.", "why_new": "Our wall cards stay flat.",
         "source_case_ids": ["c1"]},
        # repeats an existing card word for word: embedding says no
        {"id": "living.rain_again", "family": "living", "name": {k: recipes.get("living.rain")["name"][k]
                                                                 for k in recipes.LANGS},
         "shows": recipes.get("living.rain")["use"]["en"], "why_new": "same move", "source_case_ids": ["c2"]},
        # unknown family: dropped by the schema check
        {"id": "nope.thing", "family": "nope", "name": {"tr": "x", "en": "y"}, "shows": "x", "why_new": "y",
         "source_case_ids": ["c2"]},
    ]})
    out = lab.distill(ask=ask, con=con)
    assert out["ideas"] == ["camera.screen_dive"]
    assert any("repeats the card living.rain" in d for d in out["dropped"])
    assert any("invalid candidate" in d for d in out["dropped"])
    row = lab.candidate("camera.screen_dive", con)
    assert row["status"] == "idea" and row["family"] == "camera" and row["sources"] == ["c1"]
    assert all(c["status"] == "distilled" for c in cases)
    assert ask.prompts and "untrusted third-party text" in ask.prompts[0]
    assert "<case id=\"c1\"" in ask.prompts[0]           # the cases are fenced data


def test_rejected_ids_never_come_back(con, monkeypatch):
    install(monkeypatch, fake_scan([case("c9")]))
    lab._save(con, "camera.screen_dive", family="camera", name_tr="x", name_en="y", shows="s", why_new="w",
              status="rejected", reason="too close to camera.push_in")
    ask = fake_ask({"candidates": [{"id": "camera.screen_dive", "family": "camera", "name": {"tr": "x", "en": "y"},
                                    "shows": "s", "why_new": "w", "source_case_ids": ["c9"]}]})
    out = lab.distill(ask=ask, con=con)
    assert out["ideas"] == [] and "already known or already refused" in out["dropped"][0]
    assert lab.candidate("camera.screen_dive", con)["status"] == "rejected"


# ---------------------------------------------------------------- static scan

@pytest.mark.parametrize("bad", lab.FORBIDDEN)
def test_static_scan_refuses_every_forbidden_pattern(bad):
    assert lab.scan_code("const a = 1;\n" + bad + "('x');") == [bad]


def test_static_scan_passes_a_clean_demo():
    assert lab.scan_code(CARD["demo"] + "\ntl.to(root, {x: 10});") == []


# ---------------------------------------------------------------- build

def test_build_with_a_good_card_ends_candidate(con):
    lab._save(con, "text.dot_pulse", family="text", name_tr="Nokta nabzı", name_en="Dot pulse", shows="s",
              why_new="w", status="idea")
    ask = fake_ask({"card_yaml": card_yaml("text.dot_pulse"), "helper_js": ""})
    row = lab.build("text.dot_pulse", ask=ask, con=con, render=stub_render(), frames=stub_frames())
    assert row["status"] == "candidate" and row["reason"] is None
    assert {c["name"] for c in row["checks"]} == {"problems", "static", "render", "budget", "deterministic",
                                                  "not_blank", "moves"}
    assert all(c["ok"] for c in row["checks"])
    saved = yaml.safe_load(open("%s/text.dot_pulse.yaml" % lab.SRC, encoding="utf-8"))
    assert saved["id"] == "text.dot_pulse" and saved["status"] == "candidate" and saved["demo"] == CARD["demo"]
    assert len(ask.prompts) == 1


def test_build_repairs_twice_then_rejects_a_bad_card(con):
    lab._save(con, "text.dot_pulse", family="text", name_tr="Nokta", name_en="Dot", shows="s", why_new="w",
              status="idea")
    ask = fake_ask({"card_yaml": card_yaml("text.dot_pulse", call=""), "helper_js": ""})   # no call field: problems
    row = lab.build("text.dot_pulse", ask=ask, con=con, render=stub_render(), frames=stub_frames())
    assert row["status"] == "rejected" and "call" in row["reason"]
    assert len(ask.prompts) == 3                          # the first card + two repairs
    assert "FAILED THESE CODE CHECKS" in ask.prompts[1] and "FAILED THESE CODE CHECKS" in ask.prompts[2]
    saved = yaml.safe_load(open("%s/text.dot_pulse.yaml" % lab.SRC, encoding="utf-8"))
    assert saved["status"] == "rejected"


def test_build_refuses_randomness_and_a_different_second_render(con):
    lab._save(con, "text.dot_pulse", family="text", name_tr="Nokta", name_en="Dot", shows="s", why_new="w",
              status="idea")
    bad = {"card_yaml": card_yaml("text.dot_pulse", demo=CARD["demo"] + "\nconst r = Math.random();"), "helper_js": ""}
    ask = fake_ask(bad)
    row = lab.build("text.dot_pulse", ask=ask, con=con, render=stub_render(), frames=stub_frames(flip=True))
    detail = {c["name"]: c for c in row["checks"]}
    assert row["status"] == "rejected"
    assert not detail["static"]["ok"] and "Math.random" in detail["static"]["detail"]
    assert "the two renders differ" in detail["deterministic"]["detail"]


def test_build_gives_up_when_the_render_fails(con):
    lab._save(con, "text.dot_pulse", family="text", name_tr="Nokta", name_en="Dot", shows="s", why_new="w",
              status="idea")
    ask = fake_ask({"card_yaml": card_yaml("text.dot_pulse"), "helper_js": ""})
    row = lab.build("text.dot_pulse", ask=ask, con=con, render=stub_render(boom_on="dot_pulse"),
                    frames=stub_frames())
    assert row["status"] == "rejected"
    assert "render failed" in row["reason"] or "page error" in row["reason"]


# ---------------------------------------------------------------- approve / reject

def test_approve_and_reject_change_the_db_and_the_card_file(con):
    for cid in ("text.dot_pulse", "text.other"):
        lab._save(con, cid, family="text", name_tr="Nokta", name_en="Dot", shows="s", why_new="w", status="candidate",
                  checks=[{"name": "render", "ok": True, "detail": ""}])
        os.makedirs(lab.SRC, exist_ok=True)
        open("%s/%s.yaml" % (lab.SRC, cid), "w", encoding="utf-8").write(card_yaml(cid, status="candidate"))
    lab.approve("text.dot_pulse", con)
    assert lab.candidate("text.dot_pulse", con)["status"] == "active"
    assert yaml.safe_load(open("%s/text.dot_pulse.yaml" % lab.SRC))["status"] == "active"
    lab.reject("text.other", "already covered by text.rise_mask", con)
    row = lab.candidate("text.other", con)
    assert row["status"] == "rejected" and "rise_mask" in row["reason"]
    assert yaml.safe_load(open("%s/text.other.yaml" % lab.SRC))["status"] == "rejected"


def test_only_a_proven_candidate_with_a_plain_id_can_be_approved_or_rejected(con):
    lab._save(con, "text.idea_only", family="text", name_tr="a", name_en="a", shows="s", why_new="w", status="idea")
    lab._save(con, "text.failed", family="text", name_tr="a", name_en="a", shows="s", why_new="w", status="candidate",
              checks=[{"name": "render", "ok": True, "detail": ""}, {"name": "moves", "ok": False, "detail": ""}])
    for cid in ("text.idea_only", "text.failed", "text.never_seen"):
        with pytest.raises(ValueError):
            lab.approve(cid, con)
    for cid in ("../camera", "text/../../x", "", "camera.push_in.yaml"):      # the id becomes a file name
        with pytest.raises(ValueError):
            lab.reject(cid, "x", con)
        with pytest.raises(ValueError):
            lab.approve(cid, con)
    assert lab.candidate("../camera", con) is None


# ---------------------------------------------------------------- recipes.py visibility

def test_lab_cards_are_hidden_from_the_designer_until_approved(tmp_path, monkeypatch):
    monkeypatch.setattr(recipes, "LAB", str(tmp_path / "lab"))
    os.makedirs(tmp_path / "lab")
    card = {"id": "text.hidden_move", **CARD, "status": "candidate"}
    open(tmp_path / "lab" / "text.hidden_move.yaml", "w", encoding="utf-8").write(
        yaml.safe_dump(card, sort_keys=False, allow_unicode=True))
    monkeypatch.setattr(recipes, "_cache", {"key": None, "cards": None})
    assert recipes.get("text.hidden_move") is not None          # the card is loaded (render/check need it)
    assert "text.hidden_move" not in recipes.index("en")
    assert "text.hidden_move" not in recipes.card_text(["text.hidden_move"])
    assert "text.hidden_move" not in [c["id"] for c in recipes.listing("en")["cards"]]
    assert "text.rise_mask" in recipes.index("en")              # every hand-written card stays visible
    card["status"] = "active"
    open(tmp_path / "lab" / "text.hidden_move.yaml", "w", encoding="utf-8").write(
        yaml.safe_dump(card, sort_keys=False, allow_unicode=True))
    monkeypatch.setattr(recipes, "_cache", {"key": None, "cards": None})
    assert "text.hidden_move" in recipes.index("en") and recipes.problems(recipes.cards()) == []


# ---------------------------------------------------------------- lessons

def test_lessons_are_deduped_and_capped(tmp_path, monkeypatch):
    from factory.hat import reviewstats
    advice = [{"stage": "scene_plan" if i % 2 else "render",
               "line": f"- the gate refused {i} times: finding {i % 30}"} for i in range(40)]
    monkeypatch.setattr(reviewstats, "advice", lambda d=None: advice)
    monkeypatch.setattr(reviewstats, "report", lambda d=None, limit=8: {
        "projects": 3, "rejections": [], "reviews": {},
        "stages": [{"stage": "render", "runs": 4, "avg_min": 9.4, "max_min": 12.0},
                   {"stage": "script", "runs": 4, "avg_min": 0.4, "max_min": 0.9}]})
    out = lab.lessons(projects=str(tmp_path), out=str(tmp_path / "lessons.md"))
    text = open(tmp_path / "lessons.md", encoding="utf-8").read()
    rules = [ln for ln in text.splitlines() if ln.startswith("- ")]
    assert len(rules) == lab.LESSON_MAX                          # 12: the cap holds
    assert len(set(rules)) == len(rules)
    assert rules[0] == "- [render] Slowest stage: 9.4 min on average over 4 runs; budget the fix rounds in."
    assert "script" not in text                                  # 0.4 min is not evidence
    assert len(out["lines"]) <= lab.LESSON_MAX
    # rewritten from scratch: a second run with no evidence leaves no old rule behind
    monkeypatch.setattr(reviewstats, "advice", lambda d=None: [])
    monkeypatch.setattr(reviewstats, "report", lambda d=None, limit=8: {"projects": 0, "rejections": [], "reviews": {},
                                                                       "stages": []})
    lab.lessons(projects=str(tmp_path), out=str(tmp_path / "lessons.md"))
    assert "finding 7" not in open(tmp_path / "lessons.md", encoding="utf-8").read()


# ---------------------------------------------------------------- run

def test_run_never_raises_on_one_failing_step(con, monkeypatch, tmp_path):
    cases = [case("c1")]
    mod = fake_scan(cases)
    mod.scan = lambda con=None, fetch=None: (_ for _ in ()).throw(RuntimeError("no network"))
    install(monkeypatch, mod)
    ask_d = fake_ask({"candidates": [{"id": "camera.screen_dive", "family": "camera",
                                      "name": {"tr": "Dalış", "en": "Dive"}, "shows": "s", "why_new": "w",
                                      "source_case_ids": ["c1"]}]})
    ask_b = fake_ask({"card_yaml": card_yaml("camera.screen_dive"), "helper_js": ""})
    out = lab.run(build_k=2, con=con, ask_distill=ask_d, ask_build=ask_b, render=stub_render(),
                  frames=stub_frames(), projects=str(tmp_path))
    assert out["scan"]["error"] == "no network"
    assert out["build"][0]["id"] == "camera.screen_dive" and out["build"][0]["status"] == "candidate"
    assert "lines" in out["lessons"]
