"""t604 line router: a brief in the creator's words -> the ready lines that can make it, kept honest by clean()."""
import copy
import os

import pytest

from factory.hat import manifest, router


def _ready_ids():
    return {m["id"] for m in manifest.all_lines().values() if m["status"] == "ready"}


def test_cards_hold_only_ready_lines_with_their_limits():
    cards = router._cards("tr")
    assert {c["id"] for c in cards} == _ready_ids()
    cine = next(c for c in cards if c["id"] == "cinematic")
    assert any("3" in x for x in cine["limits"])
    assert all(isinstance(c["limits"], list) for c in cards)


def test_clean_keeps_known_lines_once_and_at_most_three():
    cards = router._cards("en")
    ids = [c["id"] for c in cards]
    data = {"understood": "x", "fit": "good", "video_lang": "tr",
            "picks": [{"line": "nope", "fit": "good"}, {"line": ids[0], "fit": "good", "seconds": "9999"},
                      {"line": ids[0], "fit": "good"}] + [{"line": i, "fit": "weird", "seconds": 1} for i in ids[1:5]]}
    out = router.clean(data, cards)
    assert [p["line"] for p in out["picks"]] == ids[:3]
    assert out["picks"][0]["seconds"] == 900 and out["picks"][1]["seconds"] == 5
    assert out["picks"][1]["fit"] == "partial"
    assert out["fit"] == "good" and out["gap"] == "" and out["video_lang"] == "tr"


def test_clean_is_honest_about_fit():
    cards = router._cards("en")
    out = router.clean({"fit": "good", "gap": "g", "picks": [{"line": cards[0]["id"], "fit": "partial"}]}, cards)
    assert out["fit"] == "partial" and out["gap"] == "g"         # "good" overall needs a good first pick
    out = router.clean({"fit": "good", "picks": [{"line": "unknown"}]}, cards)
    assert out["fit"] == "none" and out["picks"] == []
    assert router.clean("not json", cards)["fit"] == "none"


def test_fixed_frame_line_keeps_its_aspect():
    cards = router._cards("en")
    fixed = next((c for c in cards if c.get("aspect")), None)
    if not fixed:
        pytest.skip("no ready line with a fixed frame")
    out = router.clean({"picks": [{"line": fixed["id"], "fit": "good", "aspect": "9:16" if fixed["aspect"] != "9:16" else "16:9"}]}, cards)
    assert out["picks"][0]["aspect"] == fixed["aspect"]


def test_suggest_asks_once_with_the_brief_and_validates_length():
    seen = {}

    def ask(prompt, **kw):
        seen["prompt"], seen["kw"] = prompt, kw
        return {"fit": "none", "picks": [], "gap": "no ad line"}, {}

    out = router.suggest("A 30 second ad for my phone shop", "en", ask=ask)
    assert "A 30 second ad for my phone shop" in seen["prompt"] and seen["kw"]["tools"] == ()
    assert out == {"understood": "", "fit": "none", "picks": [], "gap": "no ad line", "images_seen": "", "video_lang": None}
    with pytest.raises(ValueError):
        router.suggest("short", "tr", ask=ask)
    with pytest.raises(ValueError):
        router.suggest("x" * (router.MAX_BRIEF + 1), "en", ask=ask)


def test_limits_are_optional_but_checked():
    m = copy.deepcopy(manifest.all_lines()["cinematic"])
    vocab = manifest.stage_vocab(manifest.DIR)
    m["limits"] = {"tr": "not a list", "en": []}
    with pytest.raises(manifest.ManifestError):
        manifest.validate(m, vocab)
    del m["limits"]
    manifest.validate(m, vocab)
    assert manifest.localize(m, "en")["limits"] == []


def test_api_routes_to_the_router(monkeypatch):
    from studio import hat_api
    monkeypatch.setattr(hat_api, "lang", lambda: "tr")
    monkeypatch.setattr(router, "suggest", lambda brief, lang, imgs=None: {"brief": brief, "lang": lang, "imgs": imgs})
    out = hat_api._post(None, "/api/hat/suggest", {"brief": "bir reklam filmi istiyorum", "images": ["raw/brief/a.jpg"]},
                        lambda *a: 1)
    assert out == {"brief": "bir reklam filmi istiyorum", "lang": "tr", "imgs": ["raw/brief/a.jpg"]}


@pytest.fixture
def brief_img(monkeypatch, tmp_path):
    monkeypatch.setattr(router, "ROOT", str(tmp_path))
    (tmp_path / "raw" / "brief").mkdir(parents=True)

    def make(name="shop_1.jpg"):
        (tmp_path / "raw" / "brief" / name).write_bytes(b"\xff\xd8x")
        return f"raw/brief/{name}"
    return make


def test_images_only_uploaded_brief_files_and_at_most_six(brief_img):
    a = brief_img()
    assert router.images([a, a], "en") == [a]
    for bad in (["raw/avatar/x.jpg"], ["raw/brief/../secret.jpg"], ["raw/brief/missing.jpg"], ["raw/brief/x.txt"]):
        with pytest.raises(ValueError):
            router.images(bad, "tr")
    with pytest.raises(ValueError):
        router.images([brief_img(f"p{i}.png") for i in range(router.MAX_IMAGES + 1)], "en")


def test_suggest_with_images_lets_the_model_read_them(brief_img):
    a = brief_img()
    seen = {}

    def ask(prompt, **kw):
        seen["prompt"], seen["kw"] = prompt, kw
        cards = router._cards("tr")
        return {"fit": "good", "images_seen": "a phone shop front",
                "picks": [{"line": cards[0]["id"], "fit": "good", "images_use": "on screen as they are"}]}, {}

    out = router.suggest("Dükkânım için 30 saniyelik bir reklam", "tr", ask=ask, imgs=[a])
    assert seen["kw"]["tools"] == ("Read",) and router.os.path.join(router.ROOT, a) in seen["prompt"]
    assert out["images_seen"] == "a phone shop front" and out["picks"][0]["images_use"] == "on screen as they are"


def test_project_keeps_the_router_images_and_the_agent_sees_them(brief_img, monkeypatch):
    from factory.hat import agent
    from factory.hat import project as P
    a = brief_img()
    monkeypatch.setattr(P, "load", lambda pid, d=None: {"line": "explainer", "ui_lang": "tr", "video_lang": "tr",
                                                         "aspect": "9:16", "images": [a]})
    monkeypatch.setattr(P, "read_artifact", lambda *a, **k: None)
    monkeypatch.setattr(agent, "skill", lambda *a, **k: "")
    from factory import proof, sceneedit
    monkeypatch.setattr(proof, "brief", lambda *a, **k: "")
    monkeypatch.setattr(sceneedit, "brief", lambda *a, **k: "")
    s = manifest.get("explainer")["stages"][0]
    text = agent.task("x", s)
    assert "## The creator's images" in text and a in text


def test_attached_videos_are_accepted_and_shown_as_stills(tmp_path, monkeypatch):
    import shutil, subprocess
    from factory.config import FFMPEG
    if not shutil.which(FFMPEG) and not os.path.exists(FFMPEG):
        pytest.skip("no ffmpeg")
    monkeypatch.setattr(router, "ROOT", str(tmp_path))
    d = tmp_path / "raw" / "brief"
    d.mkdir(parents=True)
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=d=2:s=160x90:r=10", str(d / "clip_1.mp4")], check=True)
    (d / "a.jpg").write_bytes(b"x")
    assert router.images(["raw/brief/clip_1.mp4", "raw/brief/a.jpg"]) == ["raw/brief/clip_1.mp4", "raw/brief/a.jpg"]
    seen = router.sees(["raw/brief/clip_1.mp4", "raw/brief/a.jpg"])
    assert len(seen) == router.FRAMES + 1 and "clip_1.mp4" in seen[0][1] and seen[-1][1] == ""
    assert all(os.path.exists(p) for p, _ in seen[:-1] + seen[-1:])
    assert "[frame 1/4" in router.listing(["raw/brief/clip_1.mp4"])
    with pytest.raises(ValueError):
        router.images(["raw/brief/../../etc/passwd.mp4"])
