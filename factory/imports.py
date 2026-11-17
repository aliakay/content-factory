"""Bring a finished video made outside the Studio's lines into the Studio as a production.

A hand-built episode (e.g. work/auto/unopened_ep1, rendered with bin/htmlmotion.py) has no production row, so the
Studio does not list it. import_video() gives it one: format "imported", stage "ready" (or "published" with a post URL),
the file placed where the Studio serves finished videos (out/<name>/<name>.mp4, hard-linked when possible so a
300 MB master is not copied), optional cover images as thumb_*.jpg, and, for a series episode, the episode's
prod_id link. Nothing here spends credits.
"""
import os
import shutil

from . import channels, fftools, productions as P, series, tracking
from .config import ROOT

FORMAT = "imported"


def _place(src, dst):
    """Hard-link src to dst (same filesystem), else copy. Returns "link" or "copy"."""
    if os.path.exists(dst):
        if os.path.samefile(src, dst):
            return "link"
        raise ValueError(f"already exists: {os.path.relpath(dst, ROOT)}")
    try:
        os.link(src, dst)
        return "link"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def _jpeg(src, dst):
    from PIL import Image
    try:
        im = Image.open(src)
        im.load()
    except Exception as e:
        raise ValueError(f"kapak okunamadı: {os.path.basename(src)}") from e
    im.convert("RGB").save(dst, "JPEG", quality=90)


def import_video(con, path, title, channel_id, series_id=None, episode=None, url=None, thumbs=(), lang=None,
                 note="", source=None):
    """Register a finished video. Returns the new production id."""
    path = os.path.abspath(path)
    m = fftools.measure(path)                      # raises on a missing or unreadable file
    if not m.get("video"):
        raise ValueError("dosyada video yok")
    title = str(title or "").strip()
    if not title:
        raise ValueError("başlık boş olamaz")
    if not channels.get(con, channel_id):
        raise ValueError(f"kanal bulunamadı: {channel_id}")
    ser = None
    if series_id is not None:
        s = series.get(con, int(series_id))
        if s["channel_id"] != channel_id:
            raise ValueError("seri bu kanala ait değil")
        eps = {e["n"]: e for e in s["data"].get("episodes") or []}
        if episode is None or int(episode) not in eps:
            raise ValueError("serinin bu bölümü yok")
        if eps[int(episode)].get("prod_id"):
            raise ValueError(f"bölüm {episode} zaten üretim {eps[int(episode)]['prod_id']} ile bağlı")
        ser = {"id": s["series_id"], "episode": int(episode), "title": s["title"]}
    for t in thumbs or ():
        if not os.path.isfile(t):
            raise ValueError(f"kapak bulunamadı: {t}")

    w, h = m.get("width") or 0, m.get("height") or 0
    ch = channels.get(con, channel_id)
    data = {"title": title, "kind": "imported", "aspect": "16:9" if w >= h else "9:16",
            "lang": lang or (ch.get("lang") if isinstance(ch, dict) else None) or "en", "voice": None, "shots": [],
            "imported": {"source": source or (os.path.relpath(path, ROOT) if path.startswith(ROOT + os.sep) else path),
                         "duration": m["duration"], "width": w, "height": h, "size": m.get("size"), "note": note}}
    if ser:
        data["series"] = ser
    pid = P.create(con, FORMAT, data, note or "hazır video", channel_id)
    p = P.get(con, pid)
    p["history"] = [{"at": p["history"][0]["at"], "event": "içe aktarma",
                     "detail": f"{os.path.basename(path)} · {m['duration']:.1f} s", "by": p["history"][0].get("by")}]
    name = P.assign_name(con, p)
    folder = os.path.join(ROOT, "out", name)
    os.makedirs(folder, exist_ok=True)
    try:
        how = _place(path, os.path.join(folder, name + ".mp4"))
        for i, t in enumerate(thumbs or (), 1):   # the Studio lists thumb_*.jpg as cover images
            _jpeg(t, os.path.join(folder, f"thumb_{i}.jpg"))
    except Exception:
        con.execute("DELETE FROM productions WHERE prod_id=?", (pid,))
        con.commit()
        shutil.rmtree(folder, ignore_errors=True)
        raise
    p["output"], p["stage"] = name, "ready"
    p["data"]["imported"]["placed"] = how
    P.save(con, p)
    if ser:
        s = series.get(con, ser["id"])
        for e in s["data"]["episodes"]:
            if e["n"] == ser["episode"]:
                e["prod_id"] = pid
        series.save(con, s)
    if url:
        post_id = tracking.add_post(con, url, out_name=name, prod_id=pid)
        con.execute("UPDATE posts SET channel_id=? WHERE post_id=?", (channel_id, post_id))
        p = P.get(con, pid)
        p["stage"] = "published"
        P.save(con, p, "yayın", url)
    return pid
