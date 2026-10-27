"""Channels: seeding + filing of old productions, edits, brand layer, merged formats."""
import json, sqlite3

import pytest
from PIL import Image

from factory import channels, formats, productions as P
from factory.store import SCHEMA


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(channels, "DIR", str(tmp_path / "channels"))
    monkeypatch.setattr(channels, "ROOT", str(tmp_path))
    c = sqlite3.connect(tmp_path / "t.db")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    c.execute(P.SCHEMA)   # an old database: productions without channel_id
    for kind in ("explainer", None):
        c.execute("INSERT INTO productions (format, title, stage, data, history) VALUES (?,?,?,?,?)",
                  ("explainer_short" if kind else "cinematic_calm", "old", "ready", json.dumps({"kind": kind}), "[]"))
    c.commit()
    P.ensure(c)
    return c


def test_seed_files_old_productions(con):
    ids = [c["id"] for c in channels.listing(con)]
    assert ids == ["seyahat", "bilgi"]
    rows = {r["format"]: r["channel_id"] for r in con.execute("SELECT format, channel_id FROM productions")}
    assert rows == {"explainer_short": "bilgi", "cinematic_calm": "seyahat"}
    assert channels.listing(con)[0]["counts"] == {"ready": 1}


def test_create_update_delete_moves_productions(con):
    c = channels.create(con, "Psikoloji Kanalı", {"mode": "topic", "lang": "tr"})
    assert c["id"] == "psikoloji-kanali" and c["mode"] == "topic" and c["lang"] == "tr"
    c = channels.update(con, c["id"], {"watermark": {"corner": "br", "size": 0.5}, "handles": {"tiktok": "@psi", "x": "no"}})
    assert c["watermark"]["corner"] == "br" and c["watermark"]["size"] == 0.25 and c["handles"] == {"tiktok": "@psi"}
    with pytest.raises(ValueError):
        channels.update(con, c["id"], {"color": "red"})
    con.execute("UPDATE productions SET channel_id=? WHERE format='explainer_short'", (c["id"],))
    assert channels.delete(con, c["id"], "bilgi") == "bilgi"
    assert con.execute("SELECT channel_id FROM productions WHERE format='explainer_short'").fetchone()[0] == "bilgi"


def test_brand_needs_a_logo_and_can_be_switched_off(con, tmp_path):
    p = P.get(con, 1)
    assert channels.brand(con, p) is None
    buf = tmp_path / "l.png"
    Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(buf)
    channels.set_logo(con, p["channel_id"], buf.read_bytes(), "logo.png")
    b = channels.brand(con, p)
    assert b["logo"].endswith("logo.png") and b["watermark"]["on"]
    p["data"]["brand"] = False
    assert channels.brand(con, p) is None
    with pytest.raises(ValueError):
        channels.set_logo(con, p["channel_id"], b"not an image", "logo.png")


def test_new_production_gets_the_channel_for_its_mode(con):
    pid = P.create(con, "explainer_short", {"kind": "explainer", "title": "x"})
    assert P.get(con, pid)["channel_id"] == "bilgi"
    pid = P.create(con, "cinematic_calm", {"title": "y"}, channel_id="seyahat")
    assert P.get(con, pid)["channel_id"] == "seyahat"
    assert "CHANNEL: Seyahat" in channels.prompt_note(channels.get(con, "seyahat"))


def test_merged_formats_stay_valid_but_are_not_offered():
    offered = {f["id"] for f in formats.offered()}
    assert "day_vlog" not in offered and "this_looks_unreal" not in offered
    assert formats.get("day_vlog")["merged_into"] == "story_vo" and formats.canonical("day_vlog") == "story_vo"
    assert {f["mode"] for f in formats.offered()} == {"footage", "topic", "series"}
    assert formats.get("facts_listicle")["status"] == "ready"
