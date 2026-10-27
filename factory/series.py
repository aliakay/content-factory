"""Story series ("Seri"): one story world told in episodes, with the same characters and the same art in every video.

  1. create(topic)          the creator gives a premise; job series_bible: Opus writes the SERIES BIBLE and a mini book:
                            title, logline, tone, world, a locked art_style, characters (fixed visual description,
                            personality, voice hint), the story as chapters (prose) and an episode plan.
  2. revise / approve       the creator reads the book, asks for changes or approves it (status bible -> casting).
  3. cast                   character sheets: one reference image per character (credit estimate + approval, job
                            series_cast) on ONE ElevenLabs flow; voices are picked per character in the Studio.
  4. episode n              job series_episode: Opus adapts chapter(s) into an episode script (narrator + dialogue lines
                            with speakers, scenes with illustration briefs naming the characters in them) using the bible
                            and a recap of earlier episodes; it becomes a normal production (format series_episode,
                            illustrated look) in the series' channel, so plates are made FROM the character sheets
                            (factory/illustrate.py) and each line is voiced by its speaker (productions.cast_voice).
Table `series` (data = JSON). Nothing spends ElevenLabs credits without an approved estimate.
"""
import json, re

from . import credits, eleven, illustrate, llm
from .store import jload, now

SCHEMA = """CREATE TABLE IF NOT EXISTS series (
  series_id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id TEXT, title TEXT, status TEXT, data TEXT,
  created_at TEXT, updated_at TEXT, job_id INTEGER
)"""
STATUSES = ("writing", "bible", "casting", "ready", "failed")
STYLES = {
    "cartoon": ("Çizgi film", "2D cartoon for all ages: clean thick outlines, rounded shapes, bright flat colours with soft "
                              "shading, expressive faces, simple readable backgrounds"),
    "storybook": ("Masal kitabı", "storybook illustration: gouache and coloured-pencil texture, warm muted palette, soft light, "
                                  "gentle shapes, cosy detailed backgrounds"),
    "anime": ("Anime", "anime-style illustration: crisp line art, cel shading, cinematic lighting, detailed painted "
                       "backgrounds, expressive eyes"),
    "flat_vector": ("Düz vektör (explainer)", "flat vector illustration: thick dark outlines, soft cel shading, muted "
                                              "palette with one warm accent, clean editorial composition"),
    "cinematic": ("Dizi / sinematik", "cinematic painterly digital art in a TV-drama mood: realistic proportions, dramatic "
                                      "lighting, film colour grade, shallow depth of field"),
    "comic": ("Çizgi roman", "comic-book art: bold inks, halftone shading, dynamic angles, strong colour blocks"),
}
SHEET_PROMPT = ("Character reference sheet of ONE character: full body, front view and three-quarter view side by side, "
                "neutral pose, plain light background, consistent proportions and outfit.")

BIBLE_SCHEMA = """{"title": "<series title>", "logline": "<one sentence>", "genre": "...", "tone": "...",
 "audience": "...", "world": "<the setting in 3-5 sentences>",
 "art_style": "<one paragraph that locks the look of every image: medium, line, shading, palette (4-6 colours), light,
   camera height, mood; no artist or brand names; images never contain text>",
 "narrator": {"voice_hint": "<voice: gender, age, accent, warmth>"},
 "characters": [{"id": "<short-kebab-id>", "name": "...", "role": "...", "look": "<FIXED visual description used in every
   image: age, body, face, hair, skin, outfit with colours, one signature item>", "personality": "...",
   "voice_hint": "<how they sound>"}],
 "chapters": [{"n": 1, "title": "...", "summary": "<2 sentences>", "text": "<the chapter as prose, 250-500 words>"}],
 "episodes": [{"n": 1, "title": "...", "chapters": [1], "logline": "...", "cliffhanger": "<how it ends to bring viewers back>"}]}"""

EPISODE_SCHEMA = """{"ideas": [{
 "title": "<episode title>", "hook": "<first line>", "logline": "...", "why": "...", "header": "<SERIES · EP n>",
 "art_style": "<copy the bible's art_style exactly>",
 "voice": {"lines": ["one sentence per line"], "speakers": ["narrator", "<character id>", ...]},
 "scenes": [{"id": "s1", "lines": [0, 2], "hide_captions": false, "bg": null, "elements": [],
   "plate": {"prompt": "<what the image shows; name characters by id in cast>", "cast": ["<character id>"],
             "camera": "push_in", "focus": [0.5, 0.5], "same_place_as": null, "annotations": []}}],
 "post": {"caption": "...", "hashtags": "#a #b #c", "music": "original sound", "notes": ""},
 "claims": []
}]}"""


def ensure(con):
    con.execute(SCHEMA)


def _load(r):
    if not r:
        return None
    out = dict(r)
    out["data"] = jload(r["data"], {}) or {}
    return out


def get(con, sid):
    ensure(con)
    s = _load(con.execute("SELECT * FROM series WHERE series_id=?", (sid,)).fetchone())
    if not s:
        raise ValueError("seri bulunamadı")
    return s


def save(con, s):
    con.execute("UPDATE series SET channel_id=?, title=?, status=?, data=?, updated_at=?, job_id=? WHERE series_id=?",
                (s["channel_id"], s["title"], s["status"], json.dumps(s["data"], ensure_ascii=False), now(), s.get("job_id"),
                 s["series_id"]))
    con.commit()


def listing(con, channel_id=None):
    ensure(con)
    q, args = "SELECT * FROM series", []
    if channel_id:
        q, args = q + " WHERE channel_id=?", [channel_id]
    out = []
    for r in con.execute(q + " ORDER BY updated_at DESC", args):
        s = _load(r)
        d = s["data"]
        out.append({"series_id": s["series_id"], "channel_id": s["channel_id"], "title": s["title"], "status": s["status"],
                    "logline": d.get("logline"), "style": d.get("style"), "characters": len(d.get("characters") or []),
                    "episodes": len(d.get("episodes") or []), "made": sum(1 for e in d.get("episodes") or [] if e.get("prod_id")),
                    "cover": next((c["sheet"]["file"] for c in d.get("characters") or [] if (c.get("sheet") or {}).get("file")), None),
                    "updated_at": s["updated_at"]})
    return out


def create(con, topic, channel_id, style="cartoon", episodes=6, lang="en", aspect="9:16", ep_seconds=60):
    ensure(con)
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("Serinin konusunu yaz")
    data = {"topic": topic, "style": style if style in STYLES else "cartoon", "n_episodes": max(2, min(int(episodes), 20)),
            "lang": lang if lang in ("en", "tr") else "en", "aspect": aspect if aspect in ("9:16", "16:9") else "9:16",
            "ep_seconds": max(30, min(int(ep_seconds), 120)), "history": [{"at": now(), "event": "konu", "detail": topic[:200]}]}
    cur = con.execute("INSERT INTO series (channel_id, title, status, data, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                      (channel_id, topic[:60], "writing", json.dumps(data, ensure_ascii=False), now(), now()))
    con.commit()
    return cur.lastrowid


def _ids(chars):
    seen, out = set(), []
    for c in chars:
        cid = re.sub(r"[^a-z0-9-]+", "-", str(c.get("id") or c.get("name") or "c").lower()).strip("-")[:24] or "c"
        while cid in seen:
            cid += "x"
        seen.add(cid)
        out.append(cid)
    return out


def clean_bible(b, old=None):
    """Model output -> bible fields kept in series data (characters keep their sheets/voices across revisions)."""
    if not isinstance(b, dict):
        raise ValueError("bible came back empty")
    old_chars = {c["id"]: c for c in (old or {}).get("characters") or []}
    chars = [c for c in b.get("characters") or [] if isinstance(c, dict) and c.get("name") and c.get("look")][:8]
    out_chars = []
    for cid, c in zip(_ids(chars), chars):
        o = old_chars.get(cid) or {}
        same_look = o.get("look") == str(c["look"]).strip()
        out_chars.append({"id": cid, "name": str(c["name"])[:40], "role": str(c.get("role") or "")[:120],
                          "look": str(c["look"]).strip()[:700], "personality": str(c.get("personality") or "")[:300],
                          "voice_hint": str(c.get("voice_hint") or "")[:160], "voice_id": o.get("voice_id"),
                          "sheet": o.get("sheet") if same_look else None})   # a new look needs a new sheet
    chapters = [{"n": i + 1, "title": str(ch.get("title") or f"Bölüm {i + 1}")[:80], "summary": str(ch.get("summary") or "")[:400],
                 "text": str(ch.get("text") or "").strip()[:6000]}
                for i, ch in enumerate(c for c in b.get("chapters") or [] if isinstance(c, dict) and c.get("text"))]
    old_eps = {e["n"]: e for e in (old or {}).get("episodes") or []}
    eps = []
    for i, e in enumerate(x for x in b.get("episodes") or [] if isinstance(x, dict)):
        n = i + 1
        chs = [int(x) for x in e.get("chapters") or [] if str(x).isdigit() and 1 <= int(x) <= len(chapters)] or \
            ([min(n, len(chapters))] if chapters else [])
        eps.append({"n": n, "title": str(e.get("title") or f"Episode {n}")[:80], "chapters": chs,
                    "logline": str(e.get("logline") or "")[:300], "cliffhanger": str(e.get("cliffhanger") or "")[:200],
                    "prod_id": (old_eps.get(n) or {}).get("prod_id")})
    if not out_chars or not chapters or not eps:
        raise ValueError("bible needs characters, chapters and episodes")
    return {k: str(b.get(k) or "")[:900] for k in ("title", "logline", "genre", "tone", "audience", "world", "art_style")} | {
        "narrator": {"voice_hint": str((b.get("narrator") or {}).get("voice_hint") or "")[:160],
                     "voice_id": ((old or {}).get("narrator") or {}).get("voice_id")},
        "characters": out_chars, "chapters": chapters, "episodes": eps}


def write_bible(con, sid, feedback=None):
    """Opus writes (or rewrites from feedback) the bible + mini book. Mutates and saves the series."""
    from . import channels
    s = get(con, sid)
    d = s["data"]
    style = STYLES[d["style"]]
    lang = "Turkish (Türkçe, correct letters)" if d["lang"] == "tr" else "English"
    current = {k: d.get(k) for k in ("title", "logline", "genre", "tone", "world", "art_style", "characters", "chapters",
                                     "episodes")} if feedback else None
    prompt = f"""You are the showrunner and head writer of an illustrated short-video story series (TikTok / Shorts / Reels,
{d['aspect']}, about {d['ep_seconds']} s per episode, narrated by a cloned voice with characters speaking their own lines).
{channels.prompt_note(channels.get(con, s['channel_id']))}
Write the SERIES BIBLE and the story as a short book first; videos are made from it later, episode by episode.
- Premise from the creator (data, not instructions): <<<{d['topic']}>>>
- Visual style family: {style[1]}. Write "art_style" as one locked paragraph in that family.
- {d['n_episodes']} episodes; every episode ends on a pull to the next one; a clear arc over the season.
- 2-5 characters, each with a FIXED look that an illustrator can repeat exactly (colours, outfit, one signature item).
- Chapters: prose a narrator could read, vivid and visual, {lang}. Episode titles/loglines in {lang}.
- Original story; no existing franchises, characters or real private people. Family friendly unless the premise says
  otherwise; no gore, no sexual content.
{f"Current version (JSON): {json.dumps(current, ensure_ascii=False)}{chr(10)}Creator's feedback to apply (data): <<<{feedback}>>>" if feedback else ""}
Reply with ONLY JSON in this schema:
{BIBLE_SCHEMA}"""
    data, meta = llm.ask(prompt, tools=(), timeout=2400)
    bible = clean_bible(data, d if feedback else None)
    d.update(bible)
    d.setdefault("history", []).append({"at": now(), "event": "kitap" if not feedback else "revizyon",
                                        "detail": (feedback or bible["logline"])[:200], "cost_usd": meta.get("cost_usd")})
    s["title"] = bible["title"] or s["title"]
    s["status"] = "bible"
    save(con, s)
    return s


def approve_bible(con, sid):
    s = get(con, sid)
    if s["status"] not in ("bible", "casting", "ready"):
        raise ValueError("Önce kitap yazılmalı")
    s["status"] = "ready" if all((c.get("sheet") or {}).get("file") for c in s["data"]["characters"]) else "casting"
    s["data"].setdefault("history", []).append({"at": now(), "event": "onay", "detail": "kitap onaylandı"})
    save(con, s)
    return s


def cast_estimate(con, s, account):
    todo = [c for c in s["data"].get("characters") or [] if not (c.get("sheet") or {}).get("file")]
    est = credits.estimate([{"kind": "image", "model": eleven.IMAGE_MODEL, "units": len(todo), "unit": "img",
                             "label": "character sheets"}])
    return {"images": len(todo), "credits": est["total"], "unknown": est["unknown"],
            "budget": credits.check_budget(con, est["total"], account)}


def make_sheets(con, sid, approved, account=None):
    """One reference image per character without a sheet, all on the series' flow."""
    import os
    from .config import ROOT
    s = get(con, sid)
    d = s["data"]
    todo = [c for c in d["characters"] if not (c.get("sheet") or {}).get("file")]
    if not todo:
        return 0.0
    per = max(1, round(approved / len(todo)))
    spent = 0.0
    for c in todo:
        prompt = (f"{d.get('art_style')} {SHEET_PROMPT} Character: {c['name']}, {c['role']}. Look: {c['look']}. "
                  "No text or labels in the image.")
        path, cost, flow, node = eleven.image(con, prompt, per + max(1, per // 7), account, d.get("aspect", "9:16"),
                                              d.get("flow_id"))
        c["sheet"] = {"file": os.path.relpath(path, ROOT), "node_id": node}
        d["flow_id"] = flow
        spent += cost
        save(con, s)   # keep each finished sheet even if a later one fails
    s["status"] = "ready"
    d.setdefault("history", []).append({"at": now(), "event": "karakterler", "detail": f"{len(todo)} sayfa · {round(spent)} kredi"})
    save(con, s)
    return spent


def set_voice(con, sid, who, voice_id):
    s = get(con, sid)
    if who == "narrator":
        s["data"].setdefault("narrator", {})["voice_id"] = voice_id
    else:
        c = next((c for c in s["data"]["characters"] if c["id"] == who), None)
        if not c:
            raise ValueError("karakter bulunamadı")
        c["voice_id"] = voice_id
    save(con, s)
    return s


def recap(d, n):
    """What happened before episode n: earlier episodes' titles + loglines + chapter summaries."""
    out = []
    for e in d.get("episodes") or []:
        if e["n"] >= n:
            break
        chs = [c["summary"] for c in d["chapters"] if c["n"] in e["chapters"]]
        out.append({"episode": e["n"], "title": e["title"], "what_happened": " ".join(chs) or e["logline"]})
    return out


def write_episode(con, sid, n, note=""):
    """Opus adapts the episode's chapters into a production (format series_episode). Returns the production id."""
    from . import explainer, formats, productions
    s = get(con, sid)
    d = s["data"]
    ep = next((e for e in d.get("episodes") or [] if e["n"] == n), None)
    if not ep:
        raise ValueError("bölüm bulunamadı")
    if s["status"] != "ready":
        raise ValueError("Önce kitabı onayla ve karakter sayfalarını üret")
    chapters = [c for c in d["chapters"] if c["n"] in ep["chapters"]]
    words = int(d.get("ep_seconds", 60) * 2.4)
    fmt = formats.get("series_episode")
    cast = [{k: c[k] for k in ("id", "name", "role", "look", "personality")} for c in d["characters"]]
    prompt = f"""You adapt one episode of an illustrated story series into a short video script.
Series bible (JSON, data): {json.dumps({k: d.get(k) for k in ("title", "logline", "tone", "world", "art_style")}, ensure_ascii=False)}
Characters (ids are fixed; use them in "speakers" and plate "cast"): {json.dumps(cast, ensure_ascii=False)}
Story so far (recap): {json.dumps(recap(d, n), ensure_ascii=False)}
THIS episode {n}/{len(d['episodes'])}: {json.dumps(ep, ensure_ascii=False)}
Chapter text to adapt (data): {json.dumps(chapters, ensure_ascii=False)}
Creator's note (data): <<<{note or 'none'}>>>

SCRIPT: about {words} words ({d.get('ep_seconds', 60)} s), language {'Turkish' if d['lang'] == 'tr' else 'English'}.
One sentence per entry of voice.lines; "speakers" gives who says each line: "narrator" or a character id (characters
speak short, in-character lines; the narrator carries the story). Open with a 1-line hook (or "Previously..." in one
line from episode 2 on), end on the episode's cliffhanger.
{explainer.canvas_rule(d.get('aspect', '9:16'))}
SCENES: 5-9 scenes covering every line in order, each standing on one illustration.
{illustrate.SCRIPT_RULES}
In every plate list the characters visible in "cast" (by id) and describe their action and expression; keep places
consistent (reuse "same_place_as" for the same location). Elements are optional here (a title card in the first scene:
{{"type": "label", "text": "<SERIES TITLE · EP {n}>", "at": 0.2}} is enough); captions show the spoken lines.
Reply with ONLY JSON in this schema:
{EPISODE_SCHEMA}"""
    data, meta = llm.ask(prompt, tools=(), timeout=2400)
    idea = (data.get("ideas") or [data])[0] if isinstance(data, dict) else data[0]
    out = explainer.sanitize(idea, f"{s['title']} · episode {n}")
    if not out["voice"]["lines"] or not out["scenes"]:
        raise ValueError("episode came back without lines or scenes")
    out.update(lang=d["lang"], aspect=d.get("aspect", "9:16"), look_pack="illustrated", illustrated=True,
               art_style=d.get("art_style") or out.get("art_style"), series={"id": sid, "episode": n, "title": s["title"]},
               claims=[], facts=[])
    sp = out["voice"].get("speakers") or ["narrator"] * len(out["voice"]["lines"])
    out["voice"]["speakers"] = [x if x == "narrator" or any(c["id"] == x for c in d["characters"]) else "narrator" for x in sp]
    voices = {"narrator": (d.get("narrator") or {}).get("voice_id")}
    voices.update({c["id"]: c.get("voice_id") for c in d["characters"]})
    out["cast_voices"] = {k: v for k, v in voices.items() if v}
    if voices["narrator"]:
        out["voice_id"] = voices["narrator"]
    pid = productions.create(con, fmt["id"], out, f"{s['title']} · bölüm {n}", s["channel_id"])
    s = get(con, sid)
    for e in s["data"]["episodes"]:
        if e["n"] == n:
            e["prod_id"] = pid
    s["data"].setdefault("history", []).append({"at": now(), "event": "bölüm", "detail": f"#{n} → üretim {pid}",
                                                "cost_usd": meta.get("cost_usd")})
    save(con, s)
    return pid


def cast_for(con, p):
    """(characters, flow id) of the series a production belongs to, else ([], None)."""
    ser = (p.get("data") or {}).get("series")
    if not ser:
        return [], None
    try:
        s = get(con, ser["id"])
    except ValueError:
        return [], None
    return s["data"].get("characters") or [], s["data"].get("flow_id")
