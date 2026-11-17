"""Bringing a finished outside-made video into the Studio (factory/imports.py)."""
import json
import os
import sqlite3
import subprocess

import pytest
from PIL import Image

from factory import channels, formats, imports, productions as P, series
from factory.config import FFMPEG
from factory.store import SCHEMA


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(channels, "DIR", str(tmp_path / "channels"))
    monkeypatch.setattr(channels, "ROOT", str(tmp_path))
    monkeypatch.setattr(imports, "ROOT", str(tmp_path))
    monkeypatch.setattr(series.credits, "month_spent", lambda *a, **k: 0, raising=False)
    c = sqlite3.connect(tmp_path / "t.db")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    P.ensure(c)
    channels.create(c, "Troia Production", {"lang": "en"})
    series.ensure(c)
    eps = [{"n": 1, "title": "The Tin Box"}, {"n": 2, "title": "Ink and Songs"}]
    c.execute("INSERT INTO series (channel_id, title, status, data) VALUES (?,?,?,?)",
              ("troia-production", "The Unopened Letter", "bible", json.dumps({"episodes": eps})))
    c.commit()
    return c


@pytest.fixture
def clip(tmp_path):
    p = tmp_path / "src" / "ep.mp4"
    p.parent.mkdir()
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "color=c=navy:s=320x180:d=1.5", "-f", "lavfi",
                    "-i", "sine=f=440:d=1.5", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(p)], check=True)
    return str(p)


def test_imported_format_is_never_offered_for_new_ideas():
    assert formats.get("imported")["voice"] is False
    assert "imported" not in {f["id"] for f in formats.offered()}


def test_import_places_the_file_and_links_the_episode(con, clip, tmp_path):
    cover = tmp_path / "cover.png"
    Image.new("RGB", (64, 36), (180, 40, 30)).save(cover)
    pid = imports.import_video(con, clip, "Episode 1: The Tin Box", "troia-production", series_id=1, episode=1,
                               thumbs=[str(cover)], note="hand-built")
    p = P.get(con, pid)
    assert p["format"] == "imported" and p["stage"] == "ready" and p["channel_id"] == "troia-production"
    assert p["data"]["aspect"] == "16:9" and p["data"]["kind"] == "imported"
    assert p["data"]["imported"]["duration"] == pytest.approx(1.5, abs=0.1)
    assert p["data"]["series"] == {"id": 1, "episode": 1, "title": "The Unopened Letter"}
    folder = tmp_path / "out" / p["output"]
    dst = folder / f"{p['output']}.mp4"
    assert dst.exists() and os.path.samefile(dst, clip)          # hard link, not a 300 MB copy
    assert Image.open(folder / "thumb_1.jpg").format == "JPEG"
    eps = series.get(con, 1)["data"]["episodes"]
    assert eps[0]["prod_id"] == pid and "prod_id" not in eps[1]
    assert [h["event"] for h in p["history"]] == ["içe aktarma"]


def test_import_with_url_is_published(con, clip, monkeypatch):
    seen = {}
    monkeypatch.setattr(imports.tracking, "add_post",
                        lambda c, url, out_name=None, prod_id=None: seen.update(url=url, prod=prod_id) or
                        c.execute("INSERT INTO posts (url, prod_id) VALUES (?,?)", (url, prod_id)).lastrowid)
    pid = imports.import_video(con, clip, "Ep 1", "troia-production", url="https://youtu.be/x")
    assert P.get(con, pid)["stage"] == "published" and seen == {"url": "https://youtu.be/x", "prod": pid}


@pytest.mark.parametrize("kw, msg", [
    ({"channel_id": "nope"}, "kanal bulunamadı"),
    ({"series_id": 1, "episode": 9}, "bölümü yok"),
    ({"title": "  "}, "başlık"),
])
def test_bad_input_is_refused_and_leaves_nothing(con, clip, tmp_path, kw, msg):
    args = {"title": "Ep", "channel_id": "troia-production", **kw}
    with pytest.raises(ValueError, match=msg):
        imports.import_video(con, clip, **args)
    assert con.execute("SELECT COUNT(*) FROM productions").fetchone()[0] == 0
    assert not (tmp_path / "out").exists()


def test_an_episode_is_linked_once(con, clip):
    imports.import_video(con, clip, "Ep 1", "troia-production", series_id=1, episode=1)
    with pytest.raises(ValueError, match="zaten"):
        imports.import_video(con, clip, "Ep 1 again", "troia-production", series_id=1, episode=1)


def test_missing_file_is_an_error(con, tmp_path):
    with pytest.raises(Exception, match="missing"):
        imports.import_video(con, str(tmp_path / "none.mp4"), "Ep", "troia-production")
