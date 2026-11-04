"""The character animation line: a short story acted by a few cartoon characters. Each character is drawn once
(a reference sheet), then a small pose library is drawn FROM that sheet, cut out of its plain background and rigged;
scenes are an empty background per place with the cut-out characters standing in it, switching poses line by line and
bouncing while they speak. The same pixels play the character in every scene, so it never changes face.
A later project can reuse a finished cast: project["cast_from"] = <that project's id> (no new sheets or poses for it).

  proposal          the story: characters, places, scenes with who says what in which pose; the cost -> proposal (gate)
  script            the lines with their speakers -> script (gate; a note rewrites the lines, same cast and places)
  character_design  per character a sheet and its poses, cut out -> characters (gate; "Mira: red scarf, not blue"
                    redraws her, "Mira: wave again" redraws one pose, "Mira: voice <voice id>" sets her voice)
  rig_plan          each pose trimmed, scaled to the character's height, mirrored for the right side; the motion -> rig_plan
  scene_plan        one empty background per place and a still of every scene -> plates (gate; "3: other" redraws the
                    place of scene 3, "3: Mira left" moves her)
  assets            one voice take per line, the music, the animated cut with captions -> assets (gate)
  edit              the timeline is recorded (no hand edit) -> edit
  compose           the final, technical QA, covers -> render
  publish           caption and hashtags -> publish (gate)
"""
import json, os, re, subprocess

from PIL import Image

from ..config import FFMPEG, ROOT
from . import project as P
from .documentary import _mix, _size
from .explainer import remaining_budget, _con, _rel   # noqa: F401
from .footage import _ui

WPS = {"tr": 2.3, "en": 2.5}
CHARS = 3                      # characters in a story
POSE_MAX = 5                   # poses a character's library holds (neutral always among them)
POSES = {"neutral": "standing relaxed, arms at the sides, calm face",
         "talk": "talking with an open mouth and one hand gesturing",
         "happy": "smiling broadly, arms slightly raised in joy",
         "sad": "sad, shoulders down, looking at the ground",
         "surprised": "surprised, eyes wide, mouth open, hands up",
         "angry": "angry, frowning, fists clenched",
         "think": "thinking, one hand on the chin, looking up",
         "point": "pointing forward with one arm outstretched",
         "wave": "waving hello with one raised hand",
         "walk": "walking, mid-stride"}
SIZES = {"small": 0.40, "medium": 0.50, "tall": 0.58}     # a character's height, a share of the frame's
FEET = 0.97                    # where they stand (a share of the frame's height)
SLOTS = {1: [0.5], 2: [0.3, 0.7], 3: [0.2, 0.5, 0.8]}
GAP, LEAD, TAIL = 0.25, 0.35, 0.6   # seconds between lines, before a scene's first line, after its last
BOUNCE = 0.022                 # a speaker's hop, a share of their height
BG_KEY = (217, 217, 217)       # the plain grey every pose is drawn on
SHEET_PROMPT = ("Character reference sheet of ONE character: full body, front view and three-quarter view side by side, "
                "neutral pose, plain light background, consistent proportions and outfit.")


def _ask(prompt):
    from .. import llm
    data, meta = llm.ask(prompt, tools=(), timeout=1200)
    return (data if isinstance(data, dict) else {}), float((meta or {}).get("cost_usd") or 0)


def _kebab(x):
    return re.sub(r"[^a-z0-9]+", "-", str(x or "").lower()).strip("-")[:24]


# --- the story ----------------------------------------------------------------------------------------------------

def clean_story(raw, fixed=None):
    """Shape a model-written story; `fixed` = a reused cast (its characters stay exactly as they are)."""
    raw = raw if isinstance(raw, dict) else {}
    if fixed:
        chars = [dict(c) for c in fixed]
    else:
        chars, seen = [], set()
        for c in raw.get("characters") or []:
            cid = _kebab(c.get("id") or c.get("name"))
            if not cid or cid in seen or not str(c.get("look") or "").strip():
                continue
            seen.add(cid)
            chars.append({"id": cid, "name": str(c.get("name") or cid).strip()[:30], "role": str(c.get("role") or "")[:80],
                          "look": str(c["look"]).strip()[:500], "personality": str(c.get("personality") or "")[:200],
                          "voice_hint": str(c.get("voice_hint") or "")[:120],
                          "size": c.get("size") if c.get("size") in SIZES else "medium"})
        chars = chars[:CHARS]
    ids = {c["id"] for c in chars}
    names = {c["name"].lower(): c["id"] for c in chars}
    places = {}
    for pl in raw.get("places") or []:
        pid_ = _kebab(pl.get("id"))
        if pid_ and str(pl.get("prompt") or "").strip() and pid_ not in places:
            places[pid_] = {"id": pid_, "prompt": str(pl["prompt"]).strip()[:500]}
    places = dict(list(places.items())[:6])
    scenes = []
    for sc in raw.get("scenes") or []:
        place = _kebab(sc.get("place"))
        if place not in places:
            continue
        cast = [x for x in (_kebab(c) for c in sc.get("cast") or []) if x in ids]
        lines = []
        for ln in sc.get("lines") or []:
            say = str(ln.get("say") or "").strip()
            if not say:
                continue
            who = _kebab(ln.get("who"))
            who = who if who in ids else names.get(str(ln.get("who") or "").lower(), "narrator")
            if who != "narrator" and who not in cast:
                if len(cast) >= CHARS:
                    who = "narrator"
                else:
                    cast.append(who)
            pose = ln.get("pose") if ln.get("pose") in POSES else ("talk" if who != "narrator" else "neutral")
            lines.append({"who": who, "say": say[:300], "pose": pose})
        if lines:
            scenes.append({"n": len(scenes) + 1, "place": place, "cast": list(dict.fromkeys(cast))[:CHARS], "lines": lines})
    scenes = scenes[:12]
    used = {s["place"] for s in scenes}
    return {"title": str(raw.get("title") or "").strip()[:80], "logline": str(raw.get("logline") or "").strip()[:240],
            "art_style": str(raw.get("art_style") or "").strip()[:700], "characters": chars,
            "places": [p for k, p in places.items() if k in used], "scenes": scenes,
            "music": {"use": (raw.get("music") or {}).get("use") is not False,
                      "prompt": str((raw.get("music") or {}).get("prompt") or "")[:300]},
            "caption": str(raw.get("caption") or "")[:1500],
            "hashtags": [str(t) for t in (raw.get("hashtags") or [])][:12]}


def poses_needed(story):
    """{character id: [poses]}: neutral first, then the poses its lines ask for, at most POSE_MAX."""
    out = {c["id"]: ["neutral"] for c in story["characters"]}
    for sc in story["scenes"]:
        for ln in sc["lines"]:
            if ln["who"] in out and ln["pose"] not in out[ln["who"]] and len(out[ln["who"]]) < POSE_MAX:
                out[ln["who"]].append(ln["pose"])
    return out


def pose_of(story, who, pose):
    """The pose a line plays (a pose that did not fit in the library plays as talk, else neutral)."""
    have = poses_needed(story).get(who) or ["neutral"]
    return pose if pose in have else ("talk" if "talk" in have else "neutral")


def _lines(story):
    return [ln for sc in story["scenes"] for ln in sc["lines"]]


def _seconds(story, lang):
    w = WPS.get(lang, 2.5)
    return round(sum(len(ln["say"].split()) / w + GAP for ln in _lines(story)) + len(story["scenes"]) * (LEAD + TAIL), 1)


def _cost(story, reused, lang):
    """Credits for the new sheets and poses, one background per place, a voice take per line and the music."""
    from .. import credits, eleven, formats, productions
    have = {c["id"]: c for c in reused or []}
    need = poses_needed(story)
    sheets = sum(1 for c in story["characters"] if not (have.get(c["id"], {}).get("sheet") or {}).get("file"))
    poses = sum(1 for cid, ps in need.items() for x in ps if not ((have.get(cid, {}).get("poses") or {}).get(x) or {}).get("cut"))
    secs = _seconds(story, lang)
    items = [{"kind": "image", "model": eleven.IMAGE_MODEL, "units": sheets, "unit": "img", "label": "character sheets"},
             {"kind": "image", "model": eleven.EDIT_MODEL, "units": poses, "unit": "img", "label": "poses"},
             {"kind": "image", "model": eleven.IMAGE_MODEL, "units": len(story["places"]), "unit": "img", "label": "backgrounds"},
             {"kind": "tts", "model": formats.VOICE_MODEL, "units": sum(len(ln["say"]) for ln in _lines(story)),
              "unit": "char", "label": "voices"}]
    if story["music"]["use"]:
        items.append({"kind": "music", "model": productions.MUSIC_MODEL, "units": round(secs + 1, 1), "unit": "s",
                      "label": "music"})
    items = [x for x in items if x["units"]]
    est = credits.estimate(items)
    return {"credits": est["total"], "lines": [{"label": x["label"], "credits": x["credits"] or 0} for x in est["lines"]],
            "unknown": est["unknown"]}, secs


SCHEMA = """{"title": "...", "logline": "<one sentence>",
 "art_style": "<ENGLISH, one paragraph locking the look: medium (e.g. 2D cartoon, thick clean outlines, flat colours with
   soft shading), palette of 4-6 named colours, light, mood; no artist or brand names; images never hold text>",
 "characters": [{"id": "<short-kebab-id>", "name": "...", "role": "...", "look": "<ENGLISH, FIXED: age, body, face, hair,
   skin, outfit with colours, one signature item>", "personality": "...", "voice_hint": "...", "size": "small|medium|tall"}],
 "places": [{"id": "<kebab-id>", "prompt": "<ENGLISH: the empty set, concrete, eye level; no people in it>"}],
 "scenes": [{"place": "<place id>", "cast": ["<character ids on screen>"],
   "lines": [{"who": "<character id or narrator>", "say": "<one sentence in the video language>", "pose": "<pose>"}]}],
 "music": {"use": true, "prompt": "<instrumental, mood, instruments, tempo>"},
 "caption": "<post caption>", "hashtags": ["#..."]}"""


def _prompt(p, note=None, cur=None, fixed=None, lines_only=False):
    lang = p.get("video_lang") or "en"
    lo, hi = 30, 90
    words = f"{round(lo * WPS.get(lang, 2.5))}-{round(hi * WPS.get(lang, 2.5))}"
    cast = (f"The cast is FIXED (reuse these characters exactly, by id): "
            f"{json.dumps([{k: c.get(k) for k in ('id', 'name', 'role', 'look', 'personality')} for c in fixed], ensure_ascii=False)}"
            if fixed else f"1-{CHARS} characters.")
    keep = ("Keep the title, art_style, characters and places exactly; rewrite only the scenes and their lines."
            if lines_only else "")
    return f"""You write a short cartoon story for a vertical video, acted by reusable 2D characters. Every character is
drawn once and then only switches between a few poses and hops while speaking; scenes are an empty background with
the characters standing side by side. So: few places, short spoken lines, acting through the poses, no fights, no
complex physical action, no crowds. The creator's story idea: <<<{p.get('brief') or ''}>>>
Video language: {lang} (every "say"). {cast} 2-5 places, 4-10 scenes, at most {CHARS} characters on screen per scene,
{words} spoken words in total. A narrator may carry the story; characters speak short, in-character lines. Line 1
is the hook. Poses: {', '.join(POSES)} (a character uses at most {POSE_MAX} different poses, neutral among them).
{keep}
{f"Current story (JSON): {json.dumps(cur, ensure_ascii=False)}" if cur else ""}
{f"The creator's note: <<<{note}>>>" if note else ""}
Reply ONLY JSON: {SCHEMA}"""


def _reused(p, d):
    """The finished cast of the project named in project["cast_from"], if any."""
    src = p.get("cast_from")
    if not src:
        return []
    try:
        art = P.read_artifact(src, "characters", d) or {}
    except Exception:   # noqa: BLE001 (a missing project reuses nothing)
        return []
    return art.get("characters") or []


def _story(pid, d):
    sc = P.read_artifact(pid, "script", d) or {}
    if sc.get("story"):
        return sc["story"]
    prop = P.read_artifact(pid, "proposal", d) or {}
    return ((prop.get("concepts") or [{}])[0]).get("story") or {}


def _names(story):
    return {c["id"]: c["name"] for c in story["characters"]}


def proposal(pid, s, note=None, d=None):
    p = P.load(pid, d)
    reused = _reused(p, d)
    cur = None
    if note:
        prev = P.read_artifact(pid, "proposal", d) or {}
        cur = ((prev.get("concepts") or [{}])[0]).get("story")
    data, usd = _ask(_prompt(p, note, cur, reused))
    story = clean_story(data, reused)
    if reused:
        story["art_style"] = next((c.get("art_style") for c in reused if c.get("art_style")), story["art_style"])
    if not story["characters"] or len(story["scenes"]) < 2:
        raise P.GateError("the story came back without characters or scenes; give a note and redo")
    lang = p.get("video_lang", "tr")
    cost, secs = _cost(story, reused, lang)
    ui = _ui(p)
    names = ", ".join(c["name"] for c in story["characters"])
    summary = {"tr": f"{story['title'] or p['title']}: {names}; {len(story['places'])} mekân, {len(story['scenes'])} sahne, "
                     f"~{secs:.0f} sn; ~{cost['credits']} kredi.",
               "en": f"{story['title'] or p['title']}: {names}; {len(story['places'])} places, {len(story['scenes'])} scenes, "
                     f"~{secs:.0f} s; ~{cost['credits']} credits."}[ui]
    lines = [ln["say"] for ln in _lines(story)]
    concept = {"id": "A", "title": story["title"] or p["title"], "hook": lines[0], "lines": lines,
               "structure": story["logline"], "look": "character", "key_frame": story["places"][0]["prompt"] if story["places"] else "",
               "characters": [{"id": c["id"], "name": c["name"], "look": c["look"]} for c in story["characters"]],
               "story": story}
    art = {"concepts": [concept], "chosen": "A", "seconds": secs, "voice": {"use": True}, "music": story["music"],
           "cost": cost, "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"usd": usd}}


def script(pid, s, note=None, d=None):
    """Who says what. A note rewrites the lines; the cast and the places stay (they were costed)."""
    p = P.load(pid, d)
    story, usd = _story(pid, d), 0.0
    if note:
        data, usd = _ask(_prompt(p, note, story, story["characters"], lines_only=True))
        new = clean_story({**story, "scenes": data.get("scenes") or []}, story["characters"])
        new["places"] = [pl for pl in story["places"] if pl["id"] in {sc["place"] for sc in new["scenes"]}]
        if len(new["scenes"]) < 2:
            raise P.GateError("the rewrite came back without scenes; try another note")
        story = {**story, "scenes": new["scenes"], "places": new["places"]}
    names = _names(story)
    out, speakers = [], []
    for ln in _lines(story):
        speakers.append(ln["who"])
        out.append(ln["say"] if ln["who"] == "narrator" else f"{names[ln['who']]}: {ln['say']}")
    ui = _ui(p)
    summary = {"tr": f"{len(out)} satır, {len(story['scenes'])} sahne; konuşanlar: "
                     f"{', '.join(sorted({names.get(x, 'anlatıcı') for x in speakers}))}.",
               "en": f"{len(out)} lines, {len(story['scenes'])} scenes; speakers: "
                     f"{', '.join(sorted({names.get(x, 'narrator') for x in speakers}))}."}[ui]
    art = {"title": story["title"], "hook": out[0], "lines": out, "speakers": speakers, "claims": [], "story": story,
           "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"usd": usd}}


# --- characters: sheet, poses, cut-outs ---------------------------------------------------------------------------

def cutout(src, out):
    """The character out of its plain background: the border-connected background-coloured area becomes transparent
    (rembg's mask is used too when its model is on this machine), then the picture is trimmed to the character."""
    img = Image.open(src).convert("RGB")
    w, h = img.size
    corners = [img.getpixel(xy) for xy in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))]
    bg = tuple(sorted(c[i] for c in corners)[1] for i in range(3))
    import numpy as np
    a = np.asarray(img).astype(int)
    dist = np.abs(a - np.array(bg)).sum(axis=2)
    from scipy import ndimage
    labels, _ = ndimage.label(dist < 60)
    edge = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))) - {0}
    alpha = Image.fromarray(((~np.isin(labels, list(edge))) * 255).astype("uint8"), "L")
    model = os.path.expanduser("~/.u2net/u2netp.onnx")
    if os.path.exists(model):
        try:
            from .. import matte
            m = matte.segment(img)
            alpha = Image.fromarray(np.minimum(np.asarray(alpha), np.asarray(m)).astype("uint8"), "L")
        except Exception:   # noqa: BLE001 (the colour key alone is enough on a plain background)
            pass
    from PIL import ImageFilter
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1))
    rgba = img.convert("RGBA")
    rgba.putalpha(alpha)
    box = alpha.point(lambda v: 255 if v > 24 else 0).getbbox()
    if not box:
        raise P.GateError("the pose came out empty after removing its background")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    rgba.crop(box).save(out)
    return out


def _rate(model):
    from .. import credits
    return credits.estimate([{"kind": "image", "model": model, "units": 1, "unit": "img"}])["total"] or 1


def _image(con, prompt, left, account, aspect, flow, refs=()):
    """One image inside what is left; returns (path, cost, flow, node)."""
    from .. import eleven
    rate = _rate(eleven.image_model(refs))
    if left < rate:
        raise P.GateError(f"the approved budget is used up ({left} credits left, an image costs ~{rate})")
    return eleven.image(con, prompt, min(left, rate + max(1, rate // 7)), account, aspect, flow, refs)


def _sheet_prompt(style, c):
    return f"{style} {SHEET_PROMPT} Character: {c['name']}, {c.get('role') or ''}. Look: {c['look']}. No text or labels in the image."


def _pose_prompt(style, c, pose, take=1):
    again = f" (take {take}: draw it again, same character)" if take > 1 else ""
    return (f"{style} The same character as in the reference image, exactly: {c['name']}: {c['look']}. ONE full-body "
            f"view, {POSES[pose]}, three-quarter view facing right, the whole body inside the frame with space around it, "
            f"on a plain flat light-grey background (#d9d9d9) with no floor, no shadow, no other characters and no "
            f"objects.{again} No text.")


def _design_notes(note, chars):
    """{character id: {"voice": id} | {"pose": name} | {"look": text}} from "Mira: ..." lines."""
    out = {}
    by = {c["name"].lower(): c["id"] for c in chars}
    by.update({c["id"]: c["id"] for c in chars})
    for m in re.finditer(r"([^\n:;]+?)\s*:\s*([^\n;]+)", note or ""):
        cid = by.get(m.group(1).strip().lower())
        if not cid:
            continue
        text = m.group(2).strip()
        v = re.match(r"(ses|voice)\s+(\S+)", text, re.I)
        if v:
            out.setdefault(cid, {})["voice"] = v.group(2)
            continue
        pose = next((x for x in POSES if re.search(rf"\b{x}\b", text, re.I)), None)
        if pose and re.search(r"\b(yeniden|tekrar|again|redo|redraw)\b", text, re.I):
            out.setdefault(cid, {}).setdefault("poses", []).append(pose)
        else:
            out.setdefault(cid, {})["look"] = text
    return out


def character_design(pid, s, note=None, d=None):
    from .. import accounts
    p = P.load(pid, d)
    story = _story(pid, d)
    prev = {c["id"]: c for c in (P.read_artifact(pid, "characters", d) or {}).get("characters") or []}
    prev = prev or {c["id"]: c for c in _reused(p, d)}
    need = poses_needed(story)
    style = story.get("art_style") or "2D cartoon, clean thick outlines, flat bright colours with soft shading."
    notes = _design_notes(note, story["characters"])
    acc = p.get("eleven_account") or accounts.default_eleven(p.get("created_by"))
    flow = (P.read_artifact(pid, "characters", d) or {}).get("flow") or next(
        (c.get("flow") for c in prev.values() if c.get("flow")), None)
    con, left, spent, drawn = _con(), remaining_budget(pid, d), 0.0, 0
    chars = []
    for c in story["characters"]:
        old = prev.get(c["id"]) or {}
        x = {**c, "look": old.get("look") or c["look"], "sheet": old.get("sheet") or {}, "poses": dict(old.get("poses") or {}),
             "voice_id": old.get("voice_id"), "art_style": style}
        ask = notes.get(c["id"]) or {}
        if ask.get("voice"):
            x["voice_id"] = ask["voice"]
        if ask.get("look"):                    # a new look: the sheet and every pose are drawn again
            x["look"] = f"{x['look']} Change: {ask['look']}"
            x["sheet"], x["poses"] = {}, {}
        for pose in ask.get("poses") or []:
            if pose in x["poses"]:
                x["poses"][pose] = {"take": x["poses"][pose].get("take", 1) + 1}
        if not x["sheet"].get("file"):
            path, cost, flow, node = _image(con, _sheet_prompt(style, x), left - round(spent), acc, "9:16", flow)
            x["sheet"] = {"file": _rel(path), "node_id": node}
            spent += cost
            drawn += 1
        for pose in need.get(c["id"]) or ["neutral"]:
            have = x["poses"].get(pose) or {}
            if have.get("cut") and os.path.exists(os.path.join(ROOT, have["cut"])):
                continue
            take = have.get("take", 1)
            path, cost, flow, node = _image(con, _pose_prompt(style, x, pose, take), left - round(spent), acc, "9:16",
                                            flow, [x["sheet"]["node_id"]] if x["sheet"].get("node_id") else [])
            cut = cutout(path, P.path(pid, "assets", "characters", f"{c['id']}_{pose}.png", d=d))
            x["poses"][pose] = {"file": _rel(path), "cut": _rel(cut), "node_id": node, "take": take}
            spent += cost
            drawn += 1
        x["flow"] = flow
        chars.append(x)
    ui = _ui(p)
    summary = {"tr": f"{len(chars)} karakter, {sum(len(c['poses']) for c in chars)} poz ({drawn} yeni çizim, {round(spent)} kredi). "
                     "Bir karakteri değiştirmek için \"Mira: atkısı kırmızı\", bir pozu yeniden çizmek için \"Mira: wave tekrar\", "
                     "sesi için \"Mira: ses <voice id>\" yaz.",
               "en": f"{len(chars)} characters, {sum(len(c['poses']) for c in chars)} poses ({drawn} new images, {round(spent)} credits). "
                     "To change a character write \"Mira: red scarf\", to redraw a pose \"Mira: wave again\", for the voice "
                     "\"Mira: voice <voice id>\"."}[ui]
    plates = [c["sheet"]["file"] for c in chars] + [v["cut"] for c in chars for v in c["poses"].values()]
    art = {"characters": chars, "flow": flow, "plates": plates, "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"credits": round(spent)}}


# --- rig ----------------------------------------------------------------------------------------------------------

def rig(cut, height, flip, out):
    """A pose scaled to the character's height (even sizes), mirrored when it stands right of centre."""
    img = Image.open(cut).convert("RGBA")
    w = max(2, round(img.width * height / img.height / 2) * 2)
    img = img.resize((w, height), Image.LANCZOS)
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    return out


def layout(cast, moves=None):
    """{character id: x} (a share of the frame's width): the scene's slots, moved by the creator's notes."""
    xs = dict(zip(cast, SLOTS.get(len(cast), SLOTS[3])))
    for cid, where in (moves or {}).items():
        if cid in xs:
            xs[cid] = {"left": 0.25, "center": 0.5, "right": 0.75}[where]
    return xs


def rig_plan(pid, s, note=None, d=None):
    p = P.load(pid, d)
    story = _story(pid, d)
    chars = {c["id"]: c for c in (P.read_artifact(pid, "characters", d) or {}).get("characters") or []}
    missing = [cid for cid, ps in poses_needed(story).items() for x in ps if not (chars.get(cid, {}).get("poses") or {}).get(x)]
    if missing:
        raise P.GateError("some poses are not drawn yet; finish the character design")
    W, H = _size(p)
    rigs = {}
    for cid, c in chars.items():
        height = round(H * SIZES.get(c.get("size"), SIZES["medium"]) / 2) * 2
        files = {}
        for pose, v in c["poses"].items():
            src = os.path.join(ROOT, v["cut"])
            for flip in (False, True):
                out = P.path(pid, "assets", "rig", f"{cid}_{pose}{'_r' if flip else ''}.png", d=d)
                files[f"{pose}{'_r' if flip else ''}"] = _rel(rig(src, height, flip, out))
        rigs[cid] = {"height": height, "feet": round(H * FEET), "files": files,
                     "talk": {"hop": round(height * BOUNCE, 1), "hz": 3.2}, "idle": {"sway": 3, "hz": 0.35}}
    ui = _ui(p)
    summary = {"tr": f"{len(rigs)} karakter rig'lendi: pozlar boylarına göre ölçeklendi, sağda duranlar ortaya döndü; "
                     "konuşan zıplar, dinleyen hafifçe salınır.",
               "en": f"{len(rigs)} characters rigged: poses scaled to their heights, the ones on the right turned to the "
                     "centre; a speaker hops, a listener sways gently."}[ui]
    return {"artifact": {"rigs": rigs, "summary": summary}, "summary": summary}


# --- scenes -------------------------------------------------------------------------------------------------------

def _bg_prompt(style, place, take=1):
    again = f" (take {take}: a fresh composition of the same place)" if take > 1 else ""
    return (f"{style} Background for a cartoon scene: {place['prompt']}. An EMPTY set: no people, no characters, no "
            f"animals; eye-level camera; open ground in the lower half where characters will stand.{again} No text, "
            "letters, logos or user-interface elements.")


def _scene_notes(note, story):
    """{scene n: {"other": True} | {"moves": {character id: left|center|right}}}"""
    by = {c["name"].lower(): c["id"] for c in story["characters"]}
    by.update({c["id"]: c["id"] for c in story["characters"]})
    where = {"sol": "left", "left": "left", "sağ": "right", "sag": "right", "right": "right", "orta": "center",
             "ortada": "center", "center": "center", "centre": "center"}
    out = {}
    for m in re.finditer(r"(\d+)\s*[:.)-]\s*([^\n;]+)", note or ""):
        n, text = int(m.group(1)), m.group(2).strip().lower()
        if re.fullmatch(r"(başka|baska|other|another|yeniden|again)", text):
            out.setdefault(n, {})["other"] = True
            continue
        for part in re.split(r",| ve | and ", text):
            w = part.split()
            if len(w) >= 2 and w[-1] in where and by.get(" ".join(w[:-1])):
                out.setdefault(n, {}).setdefault("moves", {})[by[" ".join(w[:-1])]] = where[w[-1]]
    return out


def _cover(src, size):
    W, H = size
    img = Image.open(src).convert("RGB")
    k = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
    x, y = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((x, y, x + W, y + H))


def still(bg, placed, size, out):
    """A scene's picture: the background with its characters standing in their first poses."""
    img = _cover(bg, size)
    for f, x, feet in placed:
        c = Image.open(f).convert("RGBA")
        img.paste(c, (round(x - c.width / 2), feet - c.height), c)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out, quality=88)
    return out


def _first_poses(story, sc):
    """Each cast member's pose at the scene's start: their first line's pose, else neutral."""
    out = {cid: "neutral" for cid in sc["cast"]}
    for ln in sc["lines"]:
        if ln["who"] in out and out[ln["who"]] == "neutral":
            out[ln["who"]] = pose_of(story, ln["who"], ln["pose"])
            break
    return out


def _pose_file(rg, pose, x):
    return os.path.join(ROOT, rg["files"][f"{pose}_r" if x > 0.5 else pose])


def scene_plan(pid, s, note=None, d=None):
    from .. import accounts
    p = P.load(pid, d)
    story = _story(pid, d)
    rigs = (P.read_artifact(pid, "rig_plan", d) or {}).get("rigs") or {}
    ch = P.read_artifact(pid, "characters", d) or {}
    cur = P.read_artifact(pid, "plates", d) or {}
    places = {k: dict(v) for k, v in (cur.get("places") or {}).items()}
    moves = {int(k): v for k, v in (cur.get("moves") or {}).items()}
    for n, x in _scene_notes(note, story).items():
        sc = next((sc for sc in story["scenes"] if sc["n"] == n), None)
        if not sc:
            continue
        if x.get("other") and sc["place"] in places:
            places[sc["place"]] = {"take": places[sc["place"]].get("take", 1) + 1}
        if x.get("moves"):
            moves[n] = {**moves.get(n, {}), **x["moves"]}
    style = story.get("art_style") or ""
    acc = p.get("eleven_account") or accounts.default_eleven(p.get("created_by"))
    con, left, spent, flow = _con(), remaining_budget(pid, d), 0.0, ch.get("flow")
    for pl in story["places"]:
        have = places.get(pl["id"]) or {}
        if have.get("file") and os.path.exists(os.path.join(ROOT, have["file"])):
            continue
        take = have.get("take", 1)
        path, cost, flow, node = _image(con, _bg_prompt(style, pl, take), left - round(spent), acc, p.get("aspect", "9:16"), flow)
        places[pl["id"]] = {"file": _rel(path), "node_id": node, "take": take}
        spent += cost
    size = _size(p)
    W, H = size
    rows = []
    for sc in story["scenes"]:
        xs = layout(sc["cast"], moves.get(sc["n"]))
        first = _first_poses(story, sc)
        placed = [(_pose_file(rigs[cid], first[cid], xs[cid]), xs[cid] * W, rigs[cid]["feet"]) for cid in sc["cast"]]
        pic = still(os.path.join(ROOT, places[sc["place"]]["file"]), placed, size,
                    P.path(pid, "plates", f"scene_{sc['n']}.jpg", d=d))
        rows.append({"n": sc["n"], "place": sc["place"], "cast": [{"id": cid, "x": xs[cid]} for cid in sc["cast"]],
                     "still": _rel(pic)})
    ui = _ui(p)
    summary = {"tr": f"{len(places)} mekân, {len(rows)} sahne ({round(spent)} kredi). Bir mekânı yeniden çizmek için "
                     "\"3: başka\", bir karakteri taşımak için \"3: Mira sol\" (sol/orta/sağ) yaz.",
               "en": f"{len(places)} places, {len(rows)} scenes ({round(spent)} credits). To redraw a place write "
                     "\"3: other\", to move a character \"3: Mira left\" (left/center/right)."}[ui]
    art = {"places": places, "moves": {str(k): v for k, v in moves.items()}, "scenes": rows,
           "plates": [r["still"] for r in rows], "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"credits": round(spent)}}


# --- sound and picture --------------------------------------------------------------------------------------------

def _dur(path):
    from ..config import FFPROBE
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def timeline(story, durs):
    """Line and scene times on the whole video: [{n, start, end, lines: [{at, end, who, pose, say}]}], total."""
    t, out, k = 0.0, [], 0
    for sc in story["scenes"]:
        start = t
        t += LEAD
        lines = []
        for ln in sc["lines"]:
            lines.append({"at": round(t, 3), "end": round(t + durs[k], 3), "who": ln["who"],
                          "pose": pose_of(story, ln["who"], ln["pose"]) if ln["who"] != "narrator" else None,
                          "say": ln["say"]})
            t += durs[k] + GAP
            k += 1
        t += TAIL - GAP
        out.append({"n": sc["n"], "start": round(start, 3), "end": round(t, 3), "lines": lines})
    return out, round(t, 3)


def _words(times, per=4):
    """Caption chunks of up to `per` words, timed inside their line (by length); a chunk never spans two speakers."""
    out = []
    for sc in times:
        for ln in sc["lines"]:
            ws = ln["say"].split()
            span, total = ln["end"] - ln["at"], sum(len(w) + 1 for w in ws)
            t = ln["at"]
            for i in range(0, len(ws), per):
                part = ws[i:i + per]
                dt = span * sum(len(w) + 1 for w in part) / total
                out.append([" ".join(part), round(t, 2), round(t + dt, 2)])
                t += dt
    return out


def _voice_track(takes, total, out):
    """The line takes placed at their times on one track."""
    ins, fc = [], []
    for i, (f, at) in enumerate(takes):
        ins += ["-i", f]
        fc.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=mono,adelay={round(at * 1000)}:all=1[a{i}]")
    fc.append("".join(f"[a{i}]" for i in range(len(takes))) + f"amix=inputs={len(takes)}:normalize=0,apad,atrim=0:{total}[v]")
    subprocess.run([FFMPEG, "-y", "-v", "error", *ins, "-filter_complex", ";".join(fc), "-map", "[v]", "-ar", "48000", out],
                   check=True, timeout=600)
    return out


def _spans(sc, cid, first, start, end):
    """[(pose, from, to)] for one character over a scene (scene-local seconds): a speaker takes its line's pose and
    keeps it until it speaks again."""
    pose, t0, out = first, 0.0, []
    for ln in sc["lines"]:
        if ln["who"] == cid and ln["pose"] != pose:
            at = ln["at"] - start
            if at > t0:
                out.append((pose, t0, at))
            pose, t0 = ln["pose"], at
    out.append((pose, t0, end - start))
    return out


def _scene_clip(bg, sc, cast, rigs, first, size, out, flip_pan=False):
    """One scene: the background panning slowly, the characters overlaid pose by pose, hopping while they speak."""
    W, H = size
    dur = sc["end"] - sc["start"]
    ins = ["-loop", "1", "-t", f"{dur:.3f}", "-i", bg]
    pw, ph = round(W * 1.08 / 2) * 2, round(H * 1.08 / 2) * 2
    x = f"(iw-ow)*(1-t/{dur:.3f})" if flip_pan else f"(iw-ow)*t/{dur:.3f}"
    fc = [f"[0:v]scale={pw}:{ph}:force_original_aspect_ratio=increase,crop={pw}:{ph},crop={W}:{H}:x='{x}':y='(ih-oh)/2',"
          f"fps=30,setsar=1,format=yuv420p[b0]"]
    cur, k = "[b0]", 1
    for c in cast:
        rg, xs = rigs[c["id"]], c["x"]
        talk = "+".join(f"between(t,{ln['at'] - sc['start']:.3f},{ln['end'] - sc['start']:.3f})"
                        for ln in sc["lines"] if ln["who"] == c["id"]) or "0"
        hop, hz = rg["talk"]["hop"], rg["talk"]["hz"]
        sway, shz = rg["idle"]["sway"], rg["idle"]["hz"]
        phase = (sum(map(ord, c["id"])) % 628) / 100
        for pose, a, b in _spans(sc, c["id"], first[c["id"]], sc["start"], sc["end"]):
            f = _pose_file(rg, pose, xs)
            w = Image.open(f).width
            ins += ["-loop", "1", "-t", f"{dur:.3f}", "-i", f]
            y = (f"{rg['feet'] - rg['height']}-{hop}*abs(sin(2*PI*{hz}*t))*({talk})"
                 f"+{sway}*sin(2*PI*{shz}*t+{phase:.2f})*(1-({talk}))")
            nxt = f"[b{k}]"
            fc.append(f"{cur}[{k}:v]overlay=x={round(xs * W - w / 2)}:y='{y}':eval=frame:"
                      f"enable='between(t,{a:.3f},{b:.3f})'{nxt}")
            cur, k = nxt, k + 1
    subprocess.run([FFMPEG, "-y", "-v", "error", *ins, "-filter_complex", ";".join(fc), "-map", cur, "-t", f"{dur:.3f}",
                    "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", "-an", out],
                   check=True, timeout=1800)
    return out


def _render(pid, d, a, final=False):
    p = P.load(pid, d)
    story = _story(pid, d)
    rigs = (P.read_artifact(pid, "rig_plan", d) or {}).get("rigs") or {}
    pl = P.read_artifact(pid, "plates", d) or {}
    rows = {r["n"]: r for r in pl.get("scenes") or []}
    size = _size(p)
    work = P.path(pid, "assets", "scenes", d=d)
    os.makedirs(work, exist_ok=True)
    pieces = []
    for i, sc in enumerate(a["timeline"]):
        ssc = next(x for x in story["scenes"] if x["n"] == sc["n"])
        bg = os.path.join(ROOT, pl["places"][ssc["place"]]["file"])
        pieces.append(_scene_clip(bg, sc, rows[sc["n"]]["cast"], rigs, _first_poses(story, ssc), size,
                                  os.path.join(work, f"scene_{sc['n']}.mp4"), flip_pan=i % 2 == 1))
    vid = P.path(pid, "assets", "cut.mp4", d=d)
    ins = [x for f in pieces for x in ("-i", f)]
    fc = "".join(f"[{i}:v]" for i in range(len(pieces))) + f"concat=n={len(pieces)}:v=1:a=0,fps=30[v]"
    subprocess.run([FFMPEG, "-y", "-v", "error", *ins, "-filter_complex", fc, "-map", "[v]", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "16", "-an", vid], check=True, timeout=1800)
    return _mix(vid, a, size, P.path(pid, "renders", "final.mp4" if final else "preview.mp4", d=d), final)


def assets(pid, s, note=None, d=None):
    """A voice take per line (each speaker its own voice), the music, then the animated cut with captions."""
    from .. import accounts, eleven, formats, productions
    p = P.load(pid, d)
    story = _story(pid, d)
    if not (P.read_artifact(pid, "plates", d) or {}).get("scenes"):
        raise P.GateError("no scenes yet; finish the scene plan")
    chars = {c["id"]: c for c in (P.read_artifact(pid, "characters", d) or {}).get("characters") or []}
    lang = p.get("video_lang", "tr")
    acc = p.get("eleven_account") or accounts.default_eleven(p.get("created_by"))
    narrator = p.get("voice_id") or formats.default_voice(lang, acc)
    con, left = _con(), remaining_budget(pid, d)
    lines = _lines(story)
    chars_total = max(1, sum(len(ln["say"]) for ln in lines))
    tts_left = left
    takes, durs, vcost = [], [], 0.0
    for ln in lines:
        vid = (chars.get(ln["who"]) or {}).get("voice_id") or narrator
        share = max(1, min(tts_left - round(vcost), round(left * len(ln["say"]) / chars_total) + 1))
        path, c = eleven.tts(con, ln["say"], vid, formats.VOICE_MODEL, approved=share, account=acc)
        vcost += c
        takes.append(path)
        durs.append(round(_dur(path), 3))
    times, total = timeline(story, durs)
    starts = [ln["at"] for sc in times for ln in sc["lines"]]
    vfile = _voice_track(list(zip(takes, starts)), total, P.path(pid, "assets", "voice.wav", d=d))
    voice = {"file": _rel(vfile), "takes": [_rel(t) for t in takes], "credits": round(vcost)}
    mus, mcost = None, 0.0
    if story["music"]["use"]:
        prompt = story["music"]["prompt"] or "playful light cartoon score, pizzicato strings and marimba"
        if "instrumental" not in prompt.lower():
            prompt = "Instrumental, no vocals. " + prompt
        if note:
            prompt += f" {note}"
        mpath, mcost = eleven.generate(con, "music", productions.MUSIC_MODEL, prompt,
                                       {"duration_seconds": round(total + 1, 1), "instrumental": True}, round(total + 1, 1),
                                       "s", ext="mp3", approved=max(0, left - round(vcost)), account=acc)
        mus = {"file": _rel(mpath), "prompt": prompt, "credits": round(mcost)}
    art = {"voice": voice, "music": mus, "duration": total, "timeline": times, "words": _words(times), "per": 1}
    prev = _render(pid, d, art)
    cost = round(vcost + mcost)
    ui = _ui(p)
    summary = {"tr": f"Animasyon hazır ({total:.0f} sn, {cost} kredi). Konuşan karakter zıplıyor mu, pozlar repliğe uyuyor mu?",
               "en": f"The animation is ready ({total:.0f} s, {cost} credits). Does the speaker hop, do the poses fit the lines?"}[ui]
    art.update(preview=_rel(prev), summary=summary)
    return {"artifact": art, "summary": summary, "cost": {"credits": cost}}


def edit(pid, s, note=None, d=None):
    p = P.load(pid, d)
    a = P.read_artifact(pid, "assets", d) or {}
    rows = [{"n": sc["n"], "at": sc["start"], "seconds": round(sc["end"] - sc["start"], 2), "lines": len(sc["lines"])}
            for sc in a.get("timeline") or []]
    P.decision(pid, "edit", "the timeline follows the voice takes; no hand edit", d=d)
    summary = {"tr": f"{len(rows)} sahnelik zaman çizelgesi kaydedildi.", "en": f"Timeline of {len(rows)} scenes recorded."}[_ui(p)]
    return {"artifact": {"timeline": rows, "summary": summary, "note": note}, "summary": summary}


def compose(pid, s, note=None, d=None):
    from .. import qa, thumbs
    p = P.load(pid, d)
    a = P.read_artifact(pid, "assets", d) or {}
    if not a.get("timeline"):
        raise P.GateError("no animation yet")
    out = _render(pid, d, a, final=True)
    tech = qa.technical(out, a["duration"])
    title = _story(pid, d).get("title") or p["title"]
    covers = thumbs.make(out, P.path(pid, "renders", d=d), title, p.get("aspect", "9:16"), lang=p.get("video_lang", "tr"))
    probs = tech.get("problems", [])
    summary = ({"tr": "Final hazır; teknik kontrol temiz.", "en": "Final ready; technical checks clean."} if not probs else
               {"tr": f"Final hazır; {len(probs)} teknik bulgu var.", "en": f"Final ready; {len(probs)} technical findings."})[_ui(p)]
    art = {"final": _rel(out), "qa": {"technical": tech, "pass": not probs}, "covers": [_rel(c) for c in covers],
           "summary": summary}
    return {"artifact": art, "summary": summary}


def publish(pid, s, note=None, d=None):
    p = P.load(pid, d)
    story = _story(pid, d)
    tags = [t if t.startswith("#") else "#" + t for t in story.get("hashtags") or []]
    ui = _ui(p)
    caption = (story.get("caption") or story.get("title") or p["title"]).strip()
    summary = {"tr": "Açıklama ve etiketler hazır.", "en": "Caption and hashtags ready."}[ui]
    art = {"caption": caption[:2200], "hashtags": tags or ["#animasyon"], "notes": "", "summary": summary}
    return {"artifact": art, "summary": summary}
