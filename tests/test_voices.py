"""Voice suggestions: 2-3 mixed narrators per language with samples, kind detection, cache, adoption."""
import json

import pytest

from factory import voices


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(voices, "CACHE", str(tmp_path / "sug.json"))


def test_turkish_gets_three_mixed_voices_with_samples():
    out = voices.suggest("tr", "ad")
    assert len(out) == 3 and len({v["voice_id"] for v in out}) == 3
    assert out[0]["name"] == "Orçun Togan"              # best match for an ad
    assert {v["gender"] for v in out} >= {"male", "female"}   # not three near-identical voices
    assert all(v["sample"] and v["sample"].startswith("/media/assets/voice_samples/") for v in out)


def test_kind_changes_the_order():
    assert voices.suggest("tr", "explainer")[0]["name"] == "Doğa"


def test_language_without_seed_falls_back_to_the_default_narrator():
    out = voices.suggest("de")
    assert len(out) == 1 and out[0]["voice_id"]
    assert voices.stale("de")


def test_cached_library_voices_join_the_pool(tmp_path, monkeypatch):
    monkeypatch.setattr(voices, "_fetch", lambda v: str(tmp_path / (v["voice_id"] + ".mp3")))
    json.dump({"de": {"at": 9e12, "voices": [
        {"voice_id": "deF" * 7, "name": "Hans", "gender": "male", "kinds": ["ad"], "note": "x"},
        {"voice_id": "deG" * 7, "name": "Greta", "gender": "female", "kinds": ["ad"], "note": "y"}]}},
        open(voices.CACHE, "w"))
    out = voices.suggest("de", "ad")
    assert {v["name"] for v in out} == {"Hans", "Greta"} and not voices.stale("de")
    assert voices.known("deG" * 7)["language"] == "de"


@pytest.mark.parametrize("text,mode,kind", [("Kiralık 5+1 daire", "", "ad"), ("", "documentary", "story"),
                                            ("nasıl yapılır", "", "explainer"), ("komik anı", "", "social")])
def test_kind_for(text, mode, kind):
    assert voices.kind_for(text, mode) == kind


def test_adopt_adds_to_owner_profile_without_a_check_call(tmp_path, monkeypatch):
    prof = tmp_path / "prof.json"
    monkeypatch.setattr(voices.formats, "PROFILE", str(prof))
    monkeypatch.setattr("factory.accounts.eleven", lambda aid: {"type": "connector", "owner": "ali"})
    assert voices.adopt("ali", "c9eIhSvMHBxtYhLX4oBt")
    assert json.load(open(prof))["voices"][0]["name"] == "Orçun Togan"
    assert not voices.adopt("ali", "unknownvoiceid1234")
    monkeypatch.setattr("factory.accounts.eleven", lambda aid: {"type": "apikey", "key": "k"})
    assert not voices.adopt("x", "c9eIhSvMHBxtYhLX4oBt")


def test_discover_pick_and_v1_creation_go_v2_only(tmp_path, monkeypatch):
    import json, sqlite3
    from factory import discover
    from factory.store import SCHEMA
    from studio import server
    con = sqlite3.connect(tmp_path / "t.db"); con.row_factory = sqlite3.Row
    con.executescript(SCHEMA); discover.ensure(con)
    con.execute("INSERT INTO disc_runs (run_id) VALUES (1)") if False else None
    con.execute("INSERT INTO disc_cards (run_id, category, status, title, data) VALUES (1,'tr_gundem','new','t',?)",
                (json.dumps({"title": "Konu", "hook": "h", "why": "w", "lang": "tr"}),))
    con.commit()
    seen = {}
    monkeypatch.setattr(server.hat_api, "post", lambda c, path, b, q: seen.update(path=path, b=b) or {"id": "001-konu"})
    monkeypatch.setattr(server.discover, "brief_for", lambda card: "brief text")
    H = server.Handler.__new__(server.Handler)
    out = H.post(con, "/api/discover/card/1/pick", {"lang": "tr"})
    assert out == {"id": "001-konu"} and seen["b"]["line"] == "explainer" and seen["b"]["video_lang"] == "tr"
    assert con.execute("SELECT status, prod_job FROM disc_cards").fetchone()[:] == ("picked", "001-konu")
    for path in ("/api/generate", "/api/plan", "/api/plan/3/start"):
        with pytest.raises(ValueError, match="v1"):
            H.post(con, path, {})
