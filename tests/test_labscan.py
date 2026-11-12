"""The lab scanner: fetch public video collections, store what is new, never duplicate on a second scan."""
import json
import sqlite3

import pytest

from factory import labscan, store

URLS = {s["id"]: s["url"] for s in labscan.sources()}


def _con(tmp_path):
    return store.connect(str(tmp_path / "lab.db"))


def _payloads(long_text=False):
    """One small payload per real source id, in its real shape (top-level list vs a list under a key)."""
    tail = (" kelime" * 400) if long_text else ""
    return {
        "yihui-opus55": json.dumps([
            {"slug": "ror-fly-1", "author": "R", "category": "explainer", "post_url": "https://x.test/1",
             "prompt": "  a   cocktail\nrecipe" + tail},
            {"slug": "twoclipping-2", "author": "T", "category": "motion", "post_url": "https://x.test/2",
             "prompt": "a UI morph"},
        ]),
        "opusvideo-claude": json.dumps({"schema_version": 4, "cases": [
            {"id": "111", "category": "product", "title": {"en": "Launch explainer", "zh-CN": "发布"},
             "description": {"en": "A 26-second launch video.", "zh-CN": "..."},
             "original_post_url": "https://x.test/111"}]}),
        "zhuyansen-opus55": json.dumps({"cases": [
            {"id": "222", "category": "art3d", "title": {"zh": "场景", "en": "Elaborate overnight scene"},
             "original_post_url": "https://x.test/222", "prompt": None}]}),
    }


def _fetch(payloads, broken=()):
    def get(url):
        for sid, u in URLS.items():
            if u == url:
                if sid in broken:
                    raise OSError("network is down")
                return payloads[sid]
        raise KeyError(url)
    return get


def test_sources_are_the_three_collections():
    got = labscan.sources()
    assert [s["id"] for s in got] == ["yihui-opus55", "opusvideo-claude", "zhuyansen-opus55"]
    for s in got:
        assert s["format"] == "json" and s["url"].startswith("https://raw.githubusercontent.com/")
        assert set(s["map"]) == {"key", "title", "url", "category", "text"}


def test_first_scan_inserts_and_the_second_inserts_nothing(tmp_path):
    con = _con(tmp_path)
    first = labscan.scan(con, _fetch(_payloads()))
    assert first == {"sources": 3, "seen": 4, "new": 4, "errors": []}
    second = labscan.scan(con, _fetch(_payloads()))
    assert second["new"] == 0 and second["seen"] == 4 and second["errors"] == []
    rows = labscan.cases(con, status="new")
    assert len(rows) == 4 and [r["id"] for r in rows] == sorted(r["id"] for r in rows)


def test_a_failing_source_is_reported_and_the_others_still_run(tmp_path):
    con = _con(tmp_path)
    out = labscan.scan(con, _fetch(_payloads(), broken={"opusvideo-claude"}))
    assert out["sources"] == 3 and out["new"] == 3 and len(out["errors"]) == 1
    assert "opusvideo-claude" in out["errors"][0] and "OSError" in out["errors"][0]
    assert {r["source"] for r in labscan.cases(con)} == {"yihui-opus55", "zhuyansen-opus55"}


def test_a_broken_payload_is_reported_without_stopping_the_scan(tmp_path):
    con = _con(tmp_path)
    payloads = _payloads()
    payloads["zhuyansen-opus55"] = json.dumps({"cases": "not a list"})
    out = labscan.scan(con, _fetch(payloads))
    assert out["new"] == 3 and len(out["errors"]) == 1 and "not a list" in out["errors"][0]


def test_fields_are_mapped_flattened_and_excerpted(tmp_path):
    con = _con(tmp_path)
    labscan.scan(con, _fetch(_payloads(long_text=True)))
    rows = {r["key"]: r for r in labscan.cases(con, limit=50)}
    assert rows["ror-fly-1"]["url"] == "https://x.test/1"
    assert rows["ror-fly-1"]["category"] == "explainer"
    assert rows["ror-fly-1"]["title"] == "R"                     # no title field: author fallback
    assert rows["ror-fly-1"]["text"].startswith("a cocktail recipe")
    assert "\n" not in rows["ror-fly-1"]["text"] and len(rows["ror-fly-1"]["text"]) == 600
    assert rows["111"]["title"] == "Launch explainer"            # {en, zh-CN} flattens to English
    assert rows["111"]["text"] == "A 26-second launch video."
    assert rows["222"]["title"] == "Elaborate overnight scene"
    assert rows["222"]["text"] == ""                            # no description and a null prompt


def test_the_key_falls_back_to_the_url_then_a_title_hash(tmp_path):
    con = _con(tmp_path)
    payloads = _payloads()
    payloads["zhuyansen-opus55"] = json.dumps({"cases": [
        {"title": "No id but a post url", "original_post_url": "https://x.test/333"},
        {"title": "No id and no post url", "category": "misc"}]})
    out = labscan.scan(con, _fetch(payloads))
    assert out["new"] == 5
    keys = sorted(r["key"] for r in labscan.cases(con) if r["source"] == "zhuyansen-opus55")
    assert "https://x.test/333" in keys and len(keys) == 2
    hashed = [k for k in keys if k.startswith("h:")]
    assert len(hashed) == 1 and len(hashed[0]) == 18


def test_mark_and_cases_filter(tmp_path):
    con = _con(tmp_path)
    labscan.scan(con, _fetch(_payloads()))
    new = labscan.cases(con)
    assert labscan.mark(con, [new[0]["id"], new[1]["id"]], "distilled") == 2
    assert [r["id"] for r in labscan.cases(con, status="distilled")] == [new[0]["id"], new[1]["id"]]
    assert len(labscan.cases(con)) == 2 and len(labscan.cases(con, status="all")) == 4
    assert labscan.cases(con, status="ignored") == []
    assert labscan.cases(con, status="new", limit=1)[0]["id"] == new[2]["id"]
    assert labscan.mark(con, [], "ignored") == 0
    assert labscan.mark(con, [new[2]["id"]], "ignored") == 1
    with pytest.raises(ValueError, match="status"):
        labscan.mark(con, [new[3]["id"]], "eaten")


def test_cases_and_rows_carry_the_stored_shape(tmp_path):
    con = _con(tmp_path)
    labscan.scan(con, _fetch(_payloads()))
    row = labscan.cases(con)[0]
    assert set(row) == {"id", "source", "key", "title", "url", "category", "text", "seen_at", "status"}
    assert row["status"] == "new" and row["seen_at"]


def test_the_cli_prints_the_scan_result(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(labscan, "scan", lambda: {"sources": 3, "seen": 4, "new": 1, "errors": []})
    labscan.main()
    assert json.loads(capsys.readouterr().out) == {"sources": 3, "seen": 4, "new": 1, "errors": []}


def test_scan_opens_and_closes_its_own_connection(tmp_path, monkeypatch):
    db = str(tmp_path / "auto.db")
    opened = []
    real_connect = store.connect

    def connect():
        con = real_connect(db)
        opened.append(con)
        return con

    monkeypatch.setattr(labscan.store, "connect", connect)
    out = labscan.scan(fetch=_fetch(_payloads()))
    assert out["new"] == 4 and len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")                    # scan closed the connection it opened
    check = real_connect(db)
    try:
        assert check.execute("SELECT COUNT(*) FROM lab_cases").fetchone()[0] == 4
    finally:
        check.close()
