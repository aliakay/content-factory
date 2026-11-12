"""The novelty brief: variety computed in code from the v2 projects' history, and where it binds (proposal gate,
direction board, scene design + gate). No model, no render: the designer is an injected fake."""
import pytest

from factory import capabilities, memory as M, recipes
from factory.hat import direction, manifest, project as P, shortplan as SP, tools as T

STYLES = [{"id": s, "name": s.replace("_", " ").title(), "tr": s} for s in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf")]


def _card(cid, fam):
    return {"id": cid, "family": fam, "name": {"tr": cid, "en": cid.title()}, "use": {"tr": "u", "en": f"use {cid}"},
            "call": f"FX.{cid.split('.')[1]}()", "timing": {"tr": "t", "en": "t"}, "pitfalls": {"tr": ["p"], "en": ["p"]},
            "seconds": 3, "demo": "D('x')"}


CARDS = [_card(f"{f}.{n}", f) for f in ("text", "data", "lineart", "three") for n in ("one", "two", "three")]


@pytest.fixture(autouse=True)
def world(monkeypatch):
    """Seven styles and four recipe families, two of them brand new: nothing here depends on the real library."""
    monkeypatch.setattr(capabilities, "_film_styles", lambda own=True: STYLES)
    monkeypatch.setattr(recipes, "cards", lambda: CARDS)
    monkeypatch.setattr(recipes, "get", lambda cid: next((c for c in CARDS if c["id"] == cid), None))


@pytest.fixture
def d(tmp_path):
    return str(tmp_path / "projects")


def _film(d, n, style=None, look=None, mechs=(), moves=(), recipes_=(), published=True, title=None):
    pid = P.create("explainer", title or f"film {n}", d=d)["id"]
    p = P.load(pid, d)
    p.update(num=n, created_at=f"2026-11-{n:02d}T10:00:00+00:00")
    P.save(p, d)
    P.write_artifact(pid, "proposal", {"look": look or (f"style.{style}" if style else ""), "concepts": []}, d)
    if style:
        P.write_artifact(pid, "direction", {"style": style, "palette": {"bg": f"#10{n:02d}10"}}, d)
    if mechs:
        P.write_artifact(pid, "scene_plan", {"palette": {"bg": f"#10{n:02d}10"}, "scenes": [
            {"id": f"s{i}", "lines": [i, i], "mechanism": m, "shows": f"thing {n}{i} moves",
             "camera": {"move": moves[i % len(moves)], "seconds": 2 + i, "easing": "ease_out", "target": "the figure"},
             "recipes": list(recipes_) if i == 1 else []} for i, m in enumerate(mechs)]}, d)
    return pid


def test_no_history_means_an_empty_brief(d):
    b = M.novelty_brief(d=d)
    assert b == {"styles": [], "families": [], "recipes": [], "avoid": [], "text": ""}


def test_the_brief_is_least_recently_used_and_discovers_new_families(d):
    _film(d, 1, style="alpha")
    _film(d, 2, style="bravo", mechs=("hook_question", "cause_chain", "flow", "cta_end"), moves=("push_in", "pan_left"),
          recipes_=("text.one",))
    _film(d, 3, style="alpha", mechs=("hook_question", "cause_chain", "timeline", "cta_end"), moves=("push_in", "tilt_up"),
          recipes_=("data.one",))
    b = M.novelty_brief(d=d)
    assert set(b) == {"styles", "families", "recipes", "avoid", "text"}
    assert "style:alpha" in b["avoid"]                                   # the last film's look, and used twice of three
    assert "mechanism:cause_chain" in b["avoid"] and "mechanism:hook_question" not in b["avoid"]   # the hook is not "overused"
    assert "move:push_in" in b["avoid"]
    assert b["styles"][:5] == ["golf", "foxtrot", "echo", "delta", "charlie"]    # never used: the newest additions first
    assert "alpha" not in b["styles"]
    assert b["families"][:2] == ["three", "lineart"]                     # never used families, newest first: no hard-coding
    assert b["recipes"][0].split(".")[0] in ("three", "lineart") and "text.one" not in b["recipes"] and len(b["recipes"]) == 6
    assert "style.golf" in b["text"] and "three.one" in b["text"] and b["text"].count("\n") <= 4


def test_a_used_recipe_leaves_the_list_and_a_style_comes_back_after_its_turn(d):
    for n, s in enumerate(("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf"), 1):
        _film(d, n, style=s)
    b = M.novelty_brief(d=d)
    assert "style:golf" in b["avoid"] and b["styles"][0] == "alpha"      # the longest ago comes first


def test_old_productions_mirrored_in_projects_count_by_their_style(d):
    pid = P.create("explainer", "old", d=d)["id"]
    P.write_artifact(pid, "legacy", {"prod_id": 3, "data": {"recipe": {"techniques": ["style.charlie", "sound.event_sfx"]}}}, d)
    assert [(f["kind"], f["look"], f["legacy"]) for f in M.films(d=d)] == [("style", "charlie", True)]
    assert "style:charlie" in M.novelty_brief(d=d)["avoid"]


def test_a_grammar_is_a_look_too(d):
    _film(d, 1, look="finance")
    assert "grammar:finance" in M.novelty_brief(d=d)["avoid"]


# ---------------------------------------------------------------- the creator can always override

def test_naming_a_look_in_the_brief_or_a_gate_note_yields(d):
    _film(d, 1, style="alpha")
    pid = P.create("explainer", "yeni", brief="Bravo Style olsun", d=d)["id"]
    b = M.project_brief(pid, d)
    assert b["yielded"] == "style:bravo" and b["styles"] == ["bravo"] and b["recipes"] == [] and "yields" in b["text"]
    pid2 = P.create("explainer", "yeni2", d=d)["id"]
    assert not M.project_brief(pid2, d).get("yielded")
    cp = P.checkpoint(pid2, "proposal", d)
    cp.update(status="awaiting_approval", note="stil: kurzgesagt")
    P._write_cp(pid2, cp, d)
    assert M.project_brief(pid2, d)["yielded"] == "grammar:kurzgesagt"
    cp["note"] = "novelty: off"
    P._write_cp(pid2, cp, d)
    assert M.project_brief(pid2, d)["yielded"] == "off"


def test_the_brief_is_frozen_per_project(d):
    _film(d, 1, style="alpha")
    pid = P.create("explainer", "yeni", d=d)["id"]
    first = M.project_brief(pid, d)
    _film(d, 2, style="bravo")                                           # a newer film finishes meanwhile
    assert M.project_brief(pid, d) == first and P.read_artifact(pid, "novelty", d)["brief"]["styles"]


# ---------------------------------------------------------------- binding 1: the proposal

def test_the_proposal_gate_refuses_the_old_look_and_takes_a_fresh_one():
    brief = {"styles": ["golf", "echo"], "avoid": ["style:alpha"], "recipes": [], "families": [], "text": "x"}
    bad = M.proposal_problems({"look": "style.alpha", "chosen": "a", "concepts": []}, brief)
    assert bad and "style.golf" in bad[0]
    assert M.proposal_problems({"look": "finance"}, brief)
    assert not M.proposal_problems({"look": "style.echo"}, brief)
    assert not M.proposal_problems({"look": "style.alpha"}, {**brief, "yielded": "style:alpha"})
    assert not M.proposal_problems({"look": "style.alpha"}, {})


def test_the_memory_and_catalog_tools_carry_the_brief(d, monkeypatch):
    from factory import store
    import sqlite3
    monkeypatch.setattr(store, "connect", lambda *a, **k: sqlite3.connect(":memory:"))
    _film(d, 1, style="alpha", look="style.alpha")
    pid = P.create("explainer", "yeni", d=d)["id"]
    ctx = T.Ctx(pid, "proposal", d)
    got = T.TOOLS["memory"]["fn"](ctx)
    assert got["novelty"]["styles"] and got["recent"][0]["techniques"] == ["style.alpha"]
    assert not any(u.startswith("style.") for u in got["unexplored"])
    rows = T.TOOLS["catalog"]["fn"](ctx, "topic")
    fresh = [r["id"] for r in rows if r.get("use_now")]
    assert fresh == rows_ids(rows)[:len(fresh)]                          # the fresh styles lead the list


def rows_ids(rows):
    return [r["id"] for r in rows]


def test_submit_proposal_is_refused_for_a_repeated_look(d):
    _film(d, 1, style="alpha")
    pid = P.create("explainer", "yeni", d=d)["id"]
    ctx = T.Ctx(pid, "proposal", d)
    three = [{"id": i, "structure": f"s{i}"} for i in "abc"]
    assert T._meaning(ctx, "proposal", {"concepts": three, "chosen": "a", "look": "style.alpha"})
    assert not T._meaning(ctx, "proposal", {"concepts": three, "chosen": "a", "look": "style.golf"})


# ---------------------------------------------------------------- binding 2: the direction board

def test_the_board_takes_the_least_used_style_when_the_look_is_not_one(d, monkeypatch):
    _film(d, 1, style="alpha")
    pid = P.create("explainer", "yeni", d=d)["id"]
    P.write_artifact(pid, "proposal", {"look": "finance"}, d)
    board = direction.build(pid, d)
    assert board["style"] == "golf" and board["chosen_by"] == "novelty brief"
    assert direction.build(pid, d)["fingerprint"] == board["fingerprint"]          # same project, same board
    P.write_artifact(pid, "proposal", {"look": "style.delta"}, d)                  # a style in the proposal is kept
    assert direction.build(pid, d)["style"] == "delta" and "chosen_by" not in direction.build(pid, d)


def test_a_named_look_is_the_creators_not_the_briefs(d):
    _film(d, 1, style="alpha")
    pid = P.create("explainer", "yeni", brief="make it Echo please", d=d)["id"]
    P.write_artifact(pid, "proposal", {"look": "finance"}, d)
    assert direction.build(pid, d)["style"] == "echo"
    pid2 = P.create("explainer", "yeni2", brief="kurzgesagt tarzı: stil: kurzgesagt", d=d)["id"]
    P.write_artifact(pid2, "proposal", {"look": "kurzgesagt"}, d)
    assert direction.build(pid2, d)["style"] is None                             # a grammar is not a film style: the scheme


# ---------------------------------------------------------------- binding 3: the scene plan

SCRIPT = {"title": "t", "lines": ["panel hemen bitti", "fatura şişti", "sayaç durdu"]}
BOARD = {"palette": {"bg": "#101418", "ink": "#F2F0E9", "accent": "#FFD93D"}, "type": {"display": "Anton", "body": "Inter Tight"},
         "rules": [{"what": w, "says": "x"} for w in ("light", "type", "motion", "camera")], "fingerprint": "fp1"}


def _brief_scene(i, recipes_=None):
    return {"id": f"s{i}", "lines": [i, i], "brief": "b", "shows": f"a figure {i} climbs on the wall",
            "mechanism": ["count_up", "scale_compare", "reveal"][i], "camera": {
                "move": ["zoom_to", "pan_right", "tilt_down"][i], "seconds": [1.5, 3.5, 2.5][i], "easing": "ease_out", "target": "the figure"},
            **({"recipes": recipes_} if recipes_ and i == 1 else {})}


def _scene(sc):
    return {**{k: sc[k] for k in ("id", "lines", "mechanism", "shows", "camera")}, "html": f'<div class="w"><b data-e="1">{sc["id"]}</b></div>',
            "css": "", "js": ""}


def _project(d):
    pid = P.create("explainer", "güneş", d=d)["id"]
    P.write_artifact(pid, "script", SCRIPT, d)
    P.write_artifact(pid, "direction", BOARD, d)
    return pid


def _stage():
    return manifest.stage(manifest.get("explainer"), "scene_plan")


def _asker(design_recipes, prompts):
    n = {"design": 0}

    def ask(prompt):
        prompts.append(prompt)
        if "the design system only" in prompt:
            n["design"] += 1
            recs = design_recipes(n["design"])
            return {"concept": "c", "palette": BOARD["palette"], "global_css": "", "kit": "k",
                    "scenes": [_brief_scene(i, recs) for i in range(3)]}
        ids = [i for i in range(3) if f'"id": "s{i}"' in prompt]
        return {"scenes": [_scene(_brief_scene(i)) for i in ids]}
    ask.n = n
    return ask


def test_the_design_prompt_leads_with_the_brief_and_the_scene_prompt_with_the_card(d):
    _film(d, 1, style="alpha", mechs=("hook_question", "cause_chain", "cta_end"), moves=("push_in",))
    pid = _project(d)
    prompts = []
    SP.build(pid, _stage(), d=d, ask=_asker(lambda n: ["three.one"], prompts))
    design = next(p for p in prompts if "the design system only" in p)
    assert "NOVELTY BRIEF" in design and "three.one — Three.One: use three.one" in design and "at least one scene" in design
    assert design.index("NOVELTY BRIEF") < design.index("PROPOSED CAMERA DECK")
    scene = next(p for p in prompts if "the design system only" not in p and '"id": "s1"' in p)
    assert "RECIPE CARDS" in scene and "RECIPE three.one" in scene and "FX.one()" in scene
    assert scene.index("RECIPE three.one") < scene.index("Palette:")
    plan = P.read_artifact(pid, "scene_plan", d)
    assert next(s for s in plan["scenes"] if s["id"] == "s1")["recipes"] == ["three.one"]


def test_a_design_that_ignores_the_brief_is_sent_back_once_and_then_passes(d):
    _film(d, 1, style="alpha", mechs=("hook_question", "cause_chain", "cta_end"), moves=("push_in",))
    pid = _project(d)
    prompts = []
    ask = _asker(lambda n: None if n == 1 else ["lineart.two"], prompts)
    SP.build(pid, _stage(), d=d, ask=ask)
    assert ask.n["design"] == 2
    assert "none of this film's required under-used recipes" in [p for p in prompts if "the design system only" in p][1]


def test_a_design_that_never_complies_fails_before_a_scene_is_drawn(d):
    _film(d, 1, style="alpha", mechs=("hook_question", "cause_chain", "cta_end"), moves=("push_in",))
    pid = _project(d)
    prompts = []
    with pytest.raises(SP.ShortError, match="required under-used recipes"):
        SP.build(pid, _stage(), d=d, ask=_asker(lambda n: ["text.one"], prompts))      # text.one is not in the brief
    assert all("the design system only" in p for p in prompts)                         # no scene was ever drawn


def test_the_gate_refuses_a_plan_that_repeats_the_previous_film(d):
    prev = _film(d, 1, style="alpha", mechs=("hook_question", "cause_chain", "cta_end"), moves=("zoom_to", "pan_right", "tilt_down"))
    pid = _project(d)
    brief = M.project_brief(pid, d)
    plan = {"palette": {"bg": "#101401"}, "scenes": [
        {**_scene(_brief_scene(i)), "mechanism": ["hook_question", "cause_chain", "cta_end"][i],
         "recipes": [brief["recipes"][0]],
         "camera": {"move": ["zoom_to", "pan_right", "tilt_down"][i], "seconds": 2 + i, "easing": "ease_out", "target": "the figure"}}
        for i in range(3)]}
    got = M.plan_problems(plan, brief, pid=pid, d=d)
    assert len(got) == 1 and "previous film's signature" in got[0] and "film 1" in got[0]
    plan["scenes"][1]["mechanism"], plan["scenes"][2]["mechanism"] = "scale_compare", "reveal"
    plan["scenes"][0]["camera"]["move"], plan["scenes"][1]["camera"]["move"] = "orbit", "tilt_up"
    assert not M.plan_problems(plan, brief, pid=pid, d=d)
    assert not M.plan_problems(plan | {"scenes": []}, {**brief, "yielded": "off"}, pid=pid, d=d)     # a yielded brief checks nothing
    assert prev


def test_submit_artifact_gate_on_a_plan_uses_the_same_check(d):
    _film(d, 1, style="alpha", mechs=("hook_question", "cause_chain", "cta_end"), moves=("push_in",))
    pid = _project(d)
    ctx = T.Ctx(pid, "scene_plan", d)
    scenes = [_scene(_brief_scene(i)) for i in range(3)]
    found = T.novelty_plan_problems(ctx, {"scenes": scenes})
    assert found and "required under-used recipes" in found[0]
    scenes[1]["recipes"] = [M.project_brief(pid, d)["recipes"][0]]
    assert not T.novelty_plan_problems(ctx, {"scenes": scenes})
