"""Reference Lab: learn editing style from example videos the creator supplies (saved/screen-recorded files).

Measured locally: duration, scene cuts, shot lengths. Described by Claude from frames at the cuts: hook, text
style and placement, transitions, structure, loop, and concrete style rules for our editor.
Platform videos are never downloaded here — only files the creator provides.
"""
import json, os, re, statistics, subprocess

from . import llm, media
from .store import jload, now

from .config import ROOT
REFS = os.path.join(ROOT, "refs")
STRIPS = os.path.join(ROOT, "work", "refstrips")

SCHEMA = """CREATE TABLE IF NOT EXISTS ref_videos (
  ref_id TEXT PRIMARY KEY, path TEXT, duration REAL, cuts TEXT, shot_stats TEXT, strip TEXT,
  profile TEXT, note TEXT, analyzed_at TEXT, described_at TEXT
)"""


def ensure(con):
    con.execute(SCHEMA)


def detect_cuts(path, ratio=4.0, floor=6.0, window=15, min_gap=0.25):
    """Hard cuts: frame change far above its local median (a same-framing jump cut is several times
    the median), local peak only, at least `min_gap` s apart. Method after the WeAreNoCode teardown notes."""
    import numpy as np
    rows = media.motion_profile(path, fps=30)
    t = np.array([r[0] for r in rows])
    d = np.array([r[1] or 0 for r in rows])
    cuts, last = [], -1e9
    for i in range(1, len(d) - 1):
        lo, hi = max(0, i - window), min(len(d), i + window + 1)
        med = float(np.median(np.r_[d[lo:i], d[i + 1:hi]])) if hi - lo > 1 else 0.0
        if d[i] >= max(floor, ratio * med) and d[i] >= d[i - 1] and d[i] >= d[i + 1] and t[i] - last >= min_gap:
            cuts.append(round(float(t[i]), 2))
            last = t[i]
    return cuts


def shot_stats(cuts, duration):
    edges = [0.0] + [c for c in cuts if 0.05 < c < duration - 0.05] + [duration]
    shots = [round(b - a, 2) for a, b in zip(edges, edges[1:]) if b - a > 0.05]
    return {"shots": len(shots), "avg_shot_s": round(statistics.mean(shots), 2) if shots else None,
            "median_shot_s": round(statistics.median(shots), 2) if shots else None,
            "first_cut_s": shots[0] if shots else None, "cuts_per_10s": round(10 * (len(shots) - 1) / duration, 1)
            if duration else None}


def frame_strip(path, ref_id, times):
    """Frames at the given times, tiled left→right, for Claude to read."""
    os.makedirs(STRIPS, exist_ok=True)
    out = os.path.join(STRIPS, f"{ref_id}.jpg")
    expr = "+".join(f"lt(prev_pts*TB\\,{t})*gte(pts*TB\\,{t})" for t in times)
    subprocess.run([media.FFMPEG, "-v", "error", "-y", "-i", path, "-vf",
                    f"select='{expr}',scale=200:-2,tile={len(times)}x1:padding=3", "-frames:v", "1", "-vsync", "vfr", out],
                   check=True)
    return out


def analyze(con):
    ensure(con)
    if not os.path.isdir(REFS):
        return 0
    done = {r["ref_id"] for r in con.execute("SELECT ref_id FROM ref_videos")}
    n = 0
    for name in sorted(os.listdir(REFS)):
        path = os.path.join(REFS, name)
        if media.kind_of(path) != "video" or name in done:
            continue
        dur = media.probe_video(path)["duration"]
        cuts = detect_cuts(path)
        stats = shot_stats(cuts, dur)
        times = sorted({0.2, min(1.0, dur / 2)} | {round(c + 0.15, 2) for c in cuts[:9]} | {round(dur - 0.3, 2)})
        times = [t for t in times if 0 <= t < dur][:12]
        strip = frame_strip(path, name, times)
        con.execute("INSERT OR REPLACE INTO ref_videos (ref_id, path, duration, cuts, shot_stats, strip, analyzed_at) "
                    "VALUES (?,?,?,?,?,?,?)", (name, path, dur, json.dumps(cuts), json.dumps({**stats, "frame_times": times}),
                                              strip, now()))
        con.commit()
        n += 1
        print(f"ref {name}: {dur:.1f}s · {stats['shots']} shots · avg {stats['avg_shot_s']}s", flush=True)
    return n


PROFILE_SCHEMA = """{"hook": {"first_text": "...", "pattern": "curiosity_gap|contrarian|list_preview|confession|story_opener|question|bold_claim|other",
  "text_on_first_frame": true},
 "text": {"density": "words on screen at once", "position": "top/middle/bottom", "font_feel": "e.g. serif on paper card",
  "case": "sentence/ALL CAPS", "colours": "...", "treatment": "box/outline/shadow/highlight words", "animation": "static/pop/typewriter/..."},
 "pacing": {"rhythm": "...", "matches_measured_cuts": "comment on the measured shot stats"},
 "transitions": ["hard cut", "..."],
 "visual": {"footage": "what kind of background / footage", "grade": "colour look", "overlays": ["stickers, emojis, progress bars ..."]},
 "structure": [{"t": "0-2s", "what": "..."}],
 "loop": "how the end connects to the start (or not)",
 "why_it_might_work": "hypothesis only",
 "style_rules": ["5-8 concrete, reproducible rules for our editor (text size/position/timing, cut length, transitions)"],
 "fit_with_travel_footage": "how to reproduce this with the creator's own travel clips"}"""


def describe(con):
    ensure(con)
    rows = [dict(r) for r in con.execute("SELECT * FROM ref_videos WHERE described_at IS NULL")]
    for r in rows:
        st = jload(r["shot_stats"], {})
        prompt = f"""Read the image {r['strip']}. It shows frames from a reference short video at these timestamps (s):
{st.get('frame_times')}. Measured: duration {r['duration']:.1f}s, shot stats {json.dumps({k: v for k, v in st.items() if k != 'frame_times'})}.
Describe ONLY what is visible in the frames plus the measurements; mark anything you infer as a guess.
Do not transcribe long passages of the creator's text — summarise the style instead.
Reply with ONLY JSON in this schema:
{PROFILE_SCHEMA}"""
        data, meta = llm.ask(prompt, tools=("Read",), timeout=600, model="sonnet")
        con.execute("UPDATE ref_videos SET profile=?, described_at=? WHERE ref_id=?",
                    (json.dumps(data, ensure_ascii=False), now(), r["ref_id"]))
        con.commit()
        print(f"profiled {r['ref_id']} · cost ${meta.get('cost_usd') or 0:.3f}", flush=True)
    return len(rows)


def style_context(con, limit=6):
    """Style rules from the most recent references, for idea generation."""
    ensure(con)
    out = []
    for r in con.execute("SELECT ref_id, duration, shot_stats, profile FROM ref_videos WHERE profile IS NOT NULL "
                         "ORDER BY described_at DESC LIMIT ?", (limit,)):
        p, st = jload(r["profile"], {}), jload(r["shot_stats"], {})
        out.append({"ref": r["ref_id"], "duration": round(r["duration"], 1), "avg_shot_s": st.get("avg_shot_s"),
                    "hook_pattern": (p.get("hook") or {}).get("pattern"), "text": p.get("text"),
                    "style_rules": p.get("style_rules"), "fit": p.get("fit_with_travel_footage")})
    return out


# ---------- reference library for the Studio (themes, edit recipes, per-production references) ----------
LIBRARY_DIRS = [REFS, os.path.join(ROOT, "referance videolar - gezi vlog manzara motivasyon ")]
THEMES = ("gezi", "vlog", "manzara", "motivasyon", "diğer")
GRIDS = os.path.join(ROOT, "work", "refgrids")
REF_PHOTO_EXT = (".jpg", ".jpeg", ".png", ".webp")


def ref_kind(path):
    """'video' or 'photo' for a reference file (a photo carries the look: grade, framing, type design; no pacing)."""
    e = os.path.splitext(path)[1].lower()
    return "photo" if e in REF_PHOTO_EXT else media.kind_of(path)


LAYER_TYPES = ("title_serif", "title_bold", "scramble", "editorial", "words", "quote", "pin", "hook", "caption")

RECIPE_SCHEMA = """{"theme": "gezi|vlog|manzara|motivasyon|diğer",
 "title": "3-5 word name for this style, e.g. 'Euro Summer title card'",
 "summary": "two sentences: what the edit does and why it feels the way it does",
 "recipe": {"frame": "full|letterbox|scope (16:9 band = letterbox, 2.39:1 = scope)",
   "grade": "natural|film|golden|moody|vivid|mono", "grain": 0.0, "vignette": 0.0,
   "pace": "beat|calm", "avg_shot_s": 1.2, "transitions": ["cut", "flash", "dip"],
   "layers": [{"type": "title_serif|title_bold|scramble|editorial|words|quote|pin|hook|caption",
               "when": "intro|per_place|per_shot|throughout|outro", "example": "short paraphrase, not a transcript"}],
   "music": "kind of track and tempo feel", "voice": "none|voiceover|captions"},
 "unsupported": ["visible techniques our editor cannot reproduce yet (e.g. 3D globe flyover, text behind subject)"],
 "style_rules": ["5-8 concrete rules to reproduce it with the creator's own footage"],
 "fit_with_travel_footage": "one sentence"}"""


def ensure_library(con):
    ensure(con)
    cols = {r[1] for r in con.execute("PRAGMA table_info(ref_videos)")}
    for col in ("theme", "title", "bpm", "grid", "recipe", "source", "kind"):
        if col not in cols:
            con.execute(f"ALTER TABLE ref_videos ADD COLUMN {col} TEXT")
    con.commit()


def grid_image(path, ref_id, dur):
    """Frames at 2 fps (1 fps for long videos), 10 per row, so Claude can read cut rhythm and text animation."""
    os.makedirs(GRIDS, exist_ok=True)
    fps = 2 if dur <= 30 else 1
    rows = min(6, int(dur * fps / 10) + 1)
    out = os.path.join(GRIDS, re.sub(r"[^\w.-]", "_", ref_id) + ".jpg")
    subprocess.run([media.FFMPEG, "-v", "error", "-y", "-i", path, "-vf",
                    f"fps={fps},scale=180:-2,tile=10x{rows}:padding=2", "-frames:v", "1", out], check=True)
    return out


def photo_image(path, ref_id):
    """A reference photo is its own 'grid': one image, long side capped so Claude reads colour and type design."""
    os.makedirs(GRIDS, exist_ok=True)
    out = os.path.join(GRIDS, re.sub(r"[^\w.-]", "_", ref_id) + ".jpg")
    subprocess.run([media.FFMPEG, "-v", "error", "-y", "-i", path, "-vf", "scale='min(1280,iw)':-2", "-frames:v", "1",
                    out], check=True)
    return out


def scan_library(con):
    """Measure every new reference video in the library folders (cuts, shots, tempo, frame grid)."""
    ensure_library(con)
    done = {r["path"] for r in con.execute("SELECT path FROM ref_videos")}
    n = 0
    for d in LIBRARY_DIRS:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            path = os.path.join(d, name)
            kind = ref_kind(path)
            if kind not in ("video", "photo") or path in done or name.endswith(".part"):
                continue
            if kind == "photo":
                try:
                    dur, cuts, stats, bpm = 0.0, [], {"shots": 1, "avg_shot_s": None}, None
                    grid = photo_image(path, name)
                except Exception as e:
                    print(f"skip {name}: {e}", flush=True)
                    continue
            else:
                try:
                    dur = media.probe_video(path)["duration"]
                except Exception as e:  # half-uploaded file: try again next scan
                    print(f"skip {name}: {e}", flush=True)
                    continue
                cuts = detect_cuts(path)
                stats = shot_stats(cuts, dur)
                try:
                    from . import beats
                    bpm = beats.beats(path)["bpm"]
                except Exception:
                    bpm = None
                grid = grid_image(path, name, dur)
            ref_id = name if not con.execute("SELECT 1 FROM ref_videos WHERE ref_id=?", (name,)).fetchone() \
                else f"{os.path.basename(d)}/{name}"
            con.execute("""INSERT INTO ref_videos (ref_id, path, duration, cuts, shot_stats, grid, bpm, source,
                           analyzed_at, kind) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (ref_id, path, dur, json.dumps(cuts), json.dumps(stats), grid, bpm,
                         "upload" if d == REFS else "folder", now(), kind))
            try:  # theme chosen at upload time in the Studio
                theme = json.load(open(os.path.join(REFS, ".themes.json"))).get(name) if d == REFS else None
            except (OSError, ValueError):
                theme = None
            if theme:
                con.execute("UPDATE ref_videos SET theme=? WHERE ref_id=?", (theme, ref_id))
            con.commit()
            n += 1
            print(f"ref {name}: {dur:.1f}s · {stats['shots']} shots · avg {stats['avg_shot_s']}s · {bpm} BPM", flush=True)
    return n


def describe_recipes(con, model="sonnet"):
    """Claude reads each new reference's frame grid and writes an edit recipe in our editor's vocabulary."""
    ensure_library(con)
    rows = [dict(r) for r in con.execute("SELECT * FROM ref_videos WHERE recipe IS NULL AND grid IS NOT NULL")]
    for r in rows:
        st = jload(r["shot_stats"], {})
        fps = 2 if (r["duration"] or 0) <= 30 else 1
        if r.get("kind") == "photo":
            prompt = f"""Read the image {r['grid']}. It is ONE reference photo or still (a frame, poster, thumbnail or
screenshot of a design the creator likes) used as a STYLE reference for short travel videos. Describe the LOOK so our
editor can reproduce it with the creator's own footage: framing (full/letterbox/scope), colour grade
(natural/film/golden/moody/vivid/mono), grain, vignette, and the text design if any (type style and placement; map to
the layer types {", ".join(LAYER_TYPES)}). There is no pacing, cut or music information in a photo: set pace "calm",
avg_shot_s null, transitions [], music "" and voice "none" unless the image clearly shows otherwise; do not invent them.
Ignore app interface and usernames. Summarise any text, never transcribe long passages. Reply with ONLY JSON:
{RECIPE_SCHEMA}"""
        else:
          prompt = f"""Read the image {r['grid']}. It is a grid of frames from a reference short video the creator saved
(a phone screen recording: ignore the Instagram/TikTok interface, buttons, usernames and ads; also ignore frames that
show the phone's control centre or an ad before/after the video). Frames are {1 / fps:g} s apart, left to right,
top to bottom. Measured: duration {r['duration']:.1f}s, cuts {json.dumps(jload(r['cuts'], [])[:40])},
shot stats {json.dumps(st)}, music tempo ≈ {r['bpm']} BPM.
Describe the EDIT (framing, colour grade, pacing, transitions, text design and timing, music feel) so our editor can
reproduce the style with the creator's own travel footage. Our editor can do: frame full/letterbox/scope; grades
natural/film/golden/moody/vivid/mono with grain and vignette; hard cuts, white flash, dip to black, whip pan smear,
glitch mosaic, "tiles" (rectangular patches of the next shot opening over the current one with a faint grid); slow push-in;
speed changes; text layers {", ".join(LAYER_TYPES)}. List anything else you see under "unsupported".
Summarise the creator's text, never transcribe long passages. Reply with ONLY JSON:
{RECIPE_SCHEMA}"""
        try:
            data, meta = llm.ask(prompt, tools=("Read",), timeout=600, model=model)
        except llm.LLMError as e:
            print(f"recipe failed for {r['ref_id']}: {e}", flush=True)
            continue
        theme = data.get("theme") if data.get("theme") in THEMES else "diğer"
        con.execute("UPDATE ref_videos SET recipe=?, theme=COALESCE(theme, ?), title=COALESCE(title, ?), "
                    "described_at=? WHERE ref_id=?", (json.dumps(data, ensure_ascii=False), theme, data.get("title"),
                                                      now(), r["ref_id"]))
        con.commit()
        print(f"recipe {r['ref_id']}: {data.get('title')} ({theme})", flush=True)
    return len(rows)


def library(con):
    ensure_library(con)
    out = []
    for r in con.execute("SELECT * FROM ref_videos WHERE grid IS NOT NULL ORDER BY theme, analyzed_at"):
        d = dict(r)
        d["recipe"] = jload(d["recipe"], None)
        d["shot_stats"] = jload(d["shot_stats"], {})
        d.pop("profile", None)
        d.pop("cuts", None)
        out.append(d)
    return out


import re

BLOCKISH = re.compile(r"glitch|block|tile|mosaic|pixel|patch", re.I)


def normalize_recipe(rec):
    """Effects the editor learned after a recipe was written: block/tile/glitch transitions listed as unsupported
    (or only mentioned in the rules) become the supported "tiles" transition, so old recipes improve by themselves."""
    rec = json.loads(json.dumps(rec))
    inner = rec.setdefault("recipe", {}) or {}
    text = " ".join([*(rec.get("unsupported") or []), *(rec.get("style_rules") or []), rec.get("summary") or "",
                     *(inner.get("transitions") or [])])
    if BLOCKISH.search(text):
        tr = [t for t in (inner.get("transitions") or []) if t != "tiles"]
        inner["transitions"] = tr + ["tiles"]
        rec["unsupported"] = [u for u in (rec.get("unsupported") or []) if not re.search(r"glitch|block|tile|mosaic|grid", u, re.I)]
    rec["recipe"] = inner
    return rec


def recipes_for(con, ref_ids):
    """The recipes of the references attached to a production, for the idea / revision prompts."""
    if not ref_ids:
        return []
    ensure_library(con)
    q = f"SELECT ref_id, title, theme, duration, bpm, shot_stats, recipe FROM ref_videos WHERE ref_id IN " \
        f"({','.join('?' * len(ref_ids))})"
    out = []
    for r in con.execute(q, list(ref_ids)):
        rec = normalize_recipe(jload(r["recipe"], {}) or {})
        out.append({"ref": r["ref_id"], "title": r["title"], "theme": r["theme"], "duration": round(r["duration"], 1),
                    "bpm": r["bpm"], "avg_shot_s": (jload(r["shot_stats"], {}) or {}).get("avg_shot_s"),
                    "recipe": rec.get("recipe"), "style_rules": rec.get("style_rules"),
                    "unsupported": rec.get("unsupported")})
    return out
