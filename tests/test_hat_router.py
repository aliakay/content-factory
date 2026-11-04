"""t604 line router: a brief in the creator's words -> the ready lines that can make it, kept honest by clean()."""
import copy

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
    assert out == {"understood": "", "fit": "none", "picks": [], "gap": "no ad line", "video_lang": None}
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
    monkeypatch.setattr(router, "suggest", lambda brief, lang: {"brief": brief, "lang": lang})
    out = hat_api._post(None, "/api/hat/suggest", {"brief": "bir reklam filmi istiyorum"}, lambda *a: 1)
    assert out == {"brief": "bir reklam filmi istiyorum", "lang": "tr"}
