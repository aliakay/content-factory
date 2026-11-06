"""A Studio shared by two people: who started a production and who did each step, and the home-screen shortcut."""
import json, os, sqlite3

import pytest

from factory import accounts, credits, productions as P
from factory.store import SCHEMA


@pytest.fixture
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "t.db")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    P.ensure(c)
    credits.ensure(c)
    return c


@pytest.fixture
def two_users(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    f.write_text(json.dumps({"secret": "x", "users": {"cem": {"name": "Cem", "role": "owner"},
                                                       "ali": {"name": "Ali", "role": "member"}}}))
    monkeypatch.setattr(accounts, "USERS", str(f))


def test_labels_only_when_more_than_one_person_logs_in(tmp_path, monkeypatch, two_users):
    assert accounts.shared() and accounts.name_of("ali") == "Ali" and accounts.name_of(None) == ""
    f = tmp_path / "one.json"
    f.write_text(json.dumps({"secret": "x", "users": {"cem": {"name": "Cem", "role": "owner"}}}))
    monkeypatch.setattr(accounts, "USERS", str(f))
    assert not accounts.shared()


def test_production_keeps_who_started_it_and_who_did_each_step(con, two_users):
    with accounts.as_user("ali"):
        pid = P.create(con, "explainer_short", {"title": "t"})
    p = P.get(con, pid)
    assert p["data"]["created_by"] == "ali" and p["history"][0]["by"] == "ali"
    with accounts.as_user("cem"):   # Cem approves Ali's production
        P.save(con, p, "onay", "fikir onaylandı")
    assert P.get(con, pid)["history"][-1]["by"] == "cem"


def test_studio_shows_names_in_the_list_and_the_history(con, two_users):
    from studio import server
    with accounts.as_user("ali"):
        pid = P.create(con, "explainer_short", {"title": "t"})
    with accounts.as_user("cem"):
        P.save(con, P.get(con, pid), "onay", "")
    p = P.get(con, pid)
    assert server.prod_summary(con, p)["by"] == "Ali"
    hist = server.production_detail(con, pid)["history"]
    assert [h["by"] for h in hist] == ["Ali", "Cem"]


def test_home_screen_files_are_public_and_served():
    from studio import server
    here = os.path.dirname(server.__file__)
    for path in server.PUBLIC_STATIC:
        assert os.path.isfile(os.path.join(here, path[len("/static/"):])), path
    m = json.load(open(os.path.join(here, "manifest.webmanifest")))
    assert m["start_url"] == "/" and m["display"] == "standalone"
    assert {i["src"] for i in m["icons"]} <= server.PUBLIC_STATIC
    assert "/static/manifest.webmanifest" in server.LOGIN_PAGE and "apple-touch-icon" in server.LOGIN_PAGE
