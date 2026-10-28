"""Reference-styled productions: the idea schema additions and the compiler to a bin/stylecut.py spec.

A production is "styled" when it carries a `look` (it was made with reference videos attached). Cuts land on a
beat grid: the generated music's real beats when there is a music take, else a plain grid at look.bpm so a sound
added in the app at that tempo still lines up.
"""
import os

from . import beats as beatmod

from .config import ROOT
LAYERS = ("title_serif", "title_bold", "scramble", "editorial", "words", "quote", "pin", "hook", "caption", "window", "html")
ENTERS = ("cut", "flash", "dip", "whip", "glitch", "tiles", "mask", "match", "object", "zoom")
MASK_SHAPES = ("circle", "iris", "band", "split", "strips", "bars", "luma", "custom")
GRADES = ("natural", "film", "golden", "moody", "vivid", "mono")
FRAMES = ("full", "letterbox", "scope")

RULES = """
Reference-styled edit (the creator attached reference videos; reproduce their EDIT with the creator's own clips):
- Follow the attached recipes: frame, grade, grain, pace, transitions and the kinds of text layers they use, and
  their style_rules. Never copy the references' words; write original lines for the creator's footage.
- Cuts land on the music: give each shot a whole number of beats ("beats") at look.bpm. Fast montage parts
  2 beats per shot, breathing moments 4-8 beats. The opening shot carries the title card ("title_card"; the
  idea's own "title" stays a plain working title string).
- Text layers available: title_serif (kicker + big serif title, travel "Vol./Summer" cards), title_bold (one or two
  chunky words that pop, e.g. "GO."), scramble (thin caps title that decodes), editorial (stacked heavy sans, 2-6
  words), words (one motivational line that flows in word by word, needs >= 2.5 s), quote (small italic serif line),
  pin (location pin + place name, for per-place shots), hook (bold two-line hook at the top), caption (small
  lowercase subtitle). Keep it to the layer kinds the references use; 0 or 1 layer per shot.
- "push" 0.02-0.06 gives a slow push-in; "enter": "flash", "dip", "whip" (motion-smear pan), "glitch" (block
  mosaic) or "tiles" (rectangular patches of the new shot open over the old one, faint grid: the Dolomites glitch-block
  look) where the reference uses that kind of transition. MATCH THE REFERENCE: if its recipe or unsupported list
  mentions block/tile/glitch transitions use "tiles" on roughly the same share of cuts (most cuts after the opening
  hold in the Dolomites reference), not "cut" everywhere.
- PACING: copy the reference's shot-length profile (recipe pace, avg_shot_s, style_rules): e.g. a quick opening pair,
  one long hold, then bursts of 1-3 beats. Never give every shot the same number of beats.
- The creator's own notes beat the recipe: keep look.frame as in the current version (e.g. full vertical) unless the
  creator asks to change it; the reference decides transitions, pace, grade and layers, not a different canvas.
- A music prompt for an instrumental track that fits the reference feel and look.bpm (the creator may generate it
  with ElevenLabs Music after a credit estimate, or add a sound in the app instead).
"""

SCHEMA_ADD = """Additional fields for styled ideas:
 "look": {"frame": "full|letterbox|scope", "grade": "natural|film|golden|moody|vivid|mono", "grain": 0.3,
          "vignette": 0.4, "bpm": 100},
 "title_card": {"type": "title_serif|title_bold|scramble|editorial", "text": "Lake Como", "kicker": "Vol. 1 · Euro Summer",
                "sub": "optional small line", "dur": 3.0},
 "outro": {"type": "...", "text": "...", "kicker": "...", "dur": 2.5} or null,
 each shot also: "beats": 2, "push": 0.03, "enter": "cut|flash|dip|whip|glitch|tiles",
                 "layer": {"type": "pin|quote|words|hook|caption|title_bold|editorial|scramble", "text": "..."} or null
 "music": {"prompt": "instrumental ..., ~100 BPM, mood", "bpm": 100}"""


def apply_recipes(d, recipes):
    """Deterministic guard on top of the Claude edit: when a reference uses block/tile transitions and the edit
    still cuts hard everywhere, put "tiles" on most cuts after the opening hold (never on the first two shots or
    the shot after a flash), and make equal-length shots follow the reference's rhythm (long hold, then bursts)."""
    uses_tiles = any("tiles" in ((r.get("recipe") or {}).get("transitions") or []) for r in recipes)
    shots = d.get("shots") or []
    if uses_tiles and len(shots) >= 4 and sum(s.get("enter") == "tiles" for s in shots) < max(2, len(shots) // 3):
        k = 0
        for i, s in enumerate(shots):
            if i < 2 or s.get("enter") in ("flash", "dip", "whip", "glitch"):
                continue
            k += 1
            if k % 3 != 0:  # two of every three eligible cuts
                s["enter"] = "tiles"
    if len(shots) >= 5 and len({s.get("beats") for s in shots}) == 1:
        pattern = [2, 2, 8] + [2, 3, 2, 4, 2, 6]
        for i, s in enumerate(shots):
            s["beats"] = pattern[i % len(pattern)] if i < len(pattern) else 2 + (i % 3)
    return d


def sanitize(d):
    look = d.get("look") or {}
    d["look"] = {"frame": look.get("frame") if look.get("frame") in FRAMES else "letterbox",
                 "grade": look.get("grade") if look.get("grade") in GRADES else "film",
                 "grain": max(0.0, min(float(look.get("grain") or 0.3), 1.0)),
                 "vignette": max(0.0, min(float(look.get("vignette") or 0.3), 1.0)),
                 "bpm": max(70.0, min(float(look.get("bpm") or 100), 180.0))}
    for k in ("title_card", "outro"):
        t = d.get(k)
        if not (isinstance(t, dict) and t.get("type") in LAYERS and t.get("text")):
            d[k] = None
        else:
            t["dur"] = max(1.5, min(float(t.get("dur") or 3.0), 6.0))
    for s in d.get("shots", []):
        s["beats"] = max(1, min(int(s.get("beats") or 2), 16))
        s["push"] = max(0.0, min(float(s.get("push") or 0.0), 0.08))
        s["enter"] = s.get("enter") if s.get("enter") in ENTERS else "cut"
        m = s.get("mask")
        if s["enter"] == "mask":
            m = m if isinstance(m, dict) and m.get("shape") in MASK_SHAPES else {"shape": "circle"}
            if m["shape"] == "custom" and not _safe_expr(m.get("expr")):
                m = {"shape": "circle"}
            s["mask"] = {k: m[k] for k in ("shape", "dur", "angle", "center", "n", "soft", "line", "expr") if k in m}
        else:
            s.pop("mask", None)
        r = s.get("ramp")
        if isinstance(r, dict) and (r.get("in") or r.get("out")):
            s["ramp"] = {"in": max(0.0, min(float(r.get("in") or 0), 0.8)), "out": max(0.0, min(float(r.get("out") or 0), 0.8)),
                         "x": max(2.0, min(float(r.get("x") or 5), 10.0))}
        else:
            s.pop("ramp", None)
        s["leak"] = bool(s.get("leak"))
        _picture_fx(s)
        a = s.get("audio")
        if isinstance(a, dict) and (a.get("lead") or a.get("tail")):   # J-cut / L-cut
            s["audio"] = {"lead": max(0.0, min(float(a.get("lead") or 0), 1.5)),
                          "tail": max(0.0, min(float(a.get("tail") or 0), 1.5))}
        else:
            s.pop("audio", None)
        lay = s.get("layer")
        s["layer"] = lay if isinstance(lay, dict) and lay.get("type") in LAYERS and (lay.get("text") or lay.get("html")) else None
        if s["layer"] is not None:
            s["layer"]["behind"] = bool(s["layer"].get("behind"))
    m = d.get("music")
    d["music"] = m if isinstance(m, dict) and m.get("prompt") else None
    return d


def _num(v, lo, hi, default):
    try:
        return max(lo, min(float(v), hi))
    except (TypeError, ValueError):
        return default


def _picture_fx(s):
    """Keep the per-shot picture effects (freeze, vertigo, chroma, frame_break) only in their clamped shape."""
    f = s.get("freeze")
    if isinstance(f, dict):
        s["freeze"] = {"at": _num(f.get("at"), 0.0, 10.0, 0.8), "dur": _num(f.get("dur"), 0.2, 3.0, 0.8),
                       "flash": bool(f.get("flash", True)), "mono": bool(f.get("mono", True)),
                       "punch": _num(f.get("punch"), 0.0, 0.2, 0.06)}
    else:
        s.pop("freeze", None)
    v = s.get("vertigo")
    if isinstance(v, dict):
        s["vertigo"] = {"amount": _num(v.get("amount"), 0.05, 0.6, 0.3), "inward": bool(v.get("inward")),
                        "r": _num(v.get("r"), 0.1, 0.6, 0.3)}
    else:
        s.pop("vertigo", None)
    c = s.get("chroma")
    if isinstance(c, dict):
        col = str(c.get("color") or "0x00d000")
        s["chroma"] = {"bg": str(c.get("bg") or "prev"), "sim": _num(c.get("sim"), 0.01, 0.5, 0.16),
                       "blend": _num(c.get("blend"), 0.0, 0.5, 0.08), "spill": "blue" if c.get("spill") == "blue" else "green",
                       "color": col if all(ch in "0123456789abcdefABCDEFx#" for ch in col) else "0x00d000"}
    else:
        s.pop("chroma", None)
    b = s.get("frame_break")
    if isinstance(b, dict):
        box = b.get("box")
        ok = isinstance(box, list) and len(box) == 4 and all(isinstance(x, (int, float)) for x in box)
        s["frame_break"] = {"box": [_num(x, 0.0, 1.0, 0.5) for x in box] if ok else [0.1, 0.3, 0.8, 0.4],
                            "border": int(_num(b.get("border"), 0, 60, 14)), "bg": "black" if b.get("bg") == "black" else "blur",
                            "color": b.get("color") if str(b.get("color", "")).lstrip("#").isalnum() else "white"}
    else:
        s.pop("frame_break", None)


def _safe_expr(e):
    import sys
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import stylecut
    return stylecut.safe_expr(e or "")


def cut_times(d, n_shots):
    """Shot start times + total: whole beats per shot on the music take's beats, or on a grid at look.bpm."""
    take = d.get("music_take")
    per = [s.get("beats", 2) for s in d["shots"]]
    if take and take.get("beats"):
        b = list(take["beats"])
        need = sum(per) + 1
        if len(b) < need:  # extend the detected beats with the track's tempo
            step = 60.0 / take.get("bpm", d["look"]["bpm"])
            b += [b[-1] + step * (i + 1) for i in range(need - len(b))]
        first = b[0] if b[0] < 0.6 else 0.0
        marks, k = [0.0], 0
        for p in per:
            k += p
            marks.append(b[k] - first if k < len(b) else marks[-1] + p * 60.0 / take.get("bpm", 100))
        return marks[:-1], marks[-1]
    step = 60.0 / d["look"]["bpm"]
    marks = [0.0]
    for p in per:
        marks.append(marks[-1] + p * step)
    return marks[:-1], marks[-1]


def compile_spec(con, p, fmt, line_times=None, voice_file=None, vo_start=0.15):
    """data -> (stylecut spec, total, starts, warnings)."""
    d = p["data"]
    clips = {r["clip_id"]: dict(r) for r in con.execute("SELECT clip_id, path, kind, duration, fps FROM clips")}
    shots = [dict(s) for s in d["shots"]]
    warn = []
    if voice_file and line_times:
        # spoken styled videos: the voice decides the cut points, the beat grid only rounds them
        total = line_times[-1]["end"] + vo_start + (d.get("tail_s") or 2.5)
        starts, last = [0.0], 0.0
        for s in shots[1:]:
            k = s.get("at_line")
            t = line_times[k]["start"] + vo_start - 0.1 if isinstance(k, int) and k < len(line_times) else None
            if t is not None and t > last + 0.8:  # compare with the last real anchor, not a gap
                starts.append(t)
                last = t
            else:
                starts.append(None)
        known = [i for i, t in enumerate(starts) if t is not None] + [len(shots)]
        bounds = starts + [total]
        for a, b in zip(known, known[1:]):
            for i in range(a + 1, b):
                bounds[i] = bounds[a] + (bounds[b] - bounds[a]) * (i - a) / (b - a)
        starts = bounds[:-1]
    else:
        starts, total = cut_times(d, len(shots))
    durs = [(starts[i + 1] if i + 1 < len(starts) else total) - starts[i] for i in range(len(shots))]
    out = []
    for k, s in enumerate(shots):
        c = clips.get(s["clip_id"])
        if not c:
            warn.append(f"{s['clip_id']} yok")
            continue
        rel = os.path.relpath(c["path"], ROOT)
        nxt = shots[k + 1].get("enter") if k + 1 < len(shots) else None
        base = {"push": s.get("push", 0.0), "enter": s.get("enter", "cut"), "focus": s.get("focus", [0.5, 0.5]),
                "exit": nxt if nxt in ("whip", "glitch", "zoom") else "cut"}
        for key in ("mask", "ramp", "audio", "freeze", "vertigo", "frame_break"):
            if s.get(key):
                base[key] = s[key]
        if s.get("chroma"):   # green screen: the background is another clip of this video (or the previous shot)
            bgc = clips.get(s["chroma"]["bg"])
            base["chroma"] = dict(s["chroma"], bg=os.path.relpath(bgc["path"], ROOT) if bgc else "prev")
        if s.get("leak"):
            base["leak"] = True
        if c["kind"] == "video":
            speed = s.get("speed", 1.0)
            need = durs[k] * speed
            a = s.get("in", 0.0)
            if a + need > c["duration"]:
                a = max(0.0, c["duration"] - need)
            if c["duration"] < need and (c["fps"] or 0) >= 50:
                speed = max(0.5, c["duration"] / durs[k])
                need = durs[k] * speed
            if c["duration"] < need:
                warn.append(f"çekim {k + 1} kısa: {c['duration']:.1f} s klip {durs[k]:.1f} s yere")
                need = c["duration"]
            out.append({"video": rel, "in": round(a, 3), "out": round(a + need, 3), "speed": round(speed, 3), **base})
        else:
            out.append({"photo": rel, "dur": round(durs[k], 3), **base})
    layers = []
    if d.get("title_card"):
        t = d["title_card"]
        end = min(total - 0.1, max(t["dur"], starts[1] if len(starts) > 1 else t["dur"]))
        layers.append({"type": t["type"], "start": 0.0 if t["type"] == "window" else 0.25, "end": round(end, 2),
                       "text": t["text"], "kicker": t.get("kicker"), "sub": t.get("sub"), "pos": t.get("pos", "center"),
                       **{k: t[k] for k in ("html", "css", "js", "font", "color") if t.get(k)}})
    busy_until = layers[-1]["end"] if layers else 0
    for k, s in enumerate(shots):
        lay = s.get("layer")
        if not lay or k >= len(starts):
            continue
        a = max(starts[k] + 0.08, busy_until + 0.05)
        need = {"words": 0.38 * len((lay.get("text") or "").split()) + 1.0, "title_bold": 1.6, "editorial": 2.2}.get(lay["type"], 1.0)
        end = starts[k] + durs[k] - 0.05
        j = k
        while end - a < need and j + 1 < len(shots):  # long layers run over the next cut, like the references
            j += 1
            end = starts[j] + durs[j] - 0.05
        if end - a < 0.6:
            continue
        pos = lay.get("pos") or ("below_band" if lay["type"] in ("pin", "quote") and d["look"]["frame"] != "full"
                                 else "lower" if lay["type"] in ("pin", "caption") else "center")
        layers.append({"type": lay["type"], "start": round(a, 2), "end": round(end, 2), "text": lay.get("text", ""),
                       "kicker": lay.get("kicker"), "pos": pos,
                       **{k: lay[k] for k in ("html", "css", "js", "font", "color", "behind") if lay.get(k)}})
        busy_until = end if lay["type"] not in ("pin", "caption") else busy_until
    if d.get("outro"):
        o = d["outro"]
        layers.append({"type": o["type"], "start": round(max(0.3, total - o["dur"]), 2), "end": round(total - 0.1, 2),
                       "text": o["text"], "kicker": o.get("kicker"), "sub": o.get("sub"), "pos": o.get("pos", "center"),
                       **{k: o[k] for k in ("html", "css", "js", "font", "color") if o.get(k)}})
    if voice_file and line_times:
        for k, ln in enumerate((d.get("voice") or {}).get("lines", [])):
            if k < len(line_times):
                layers.append({"type": "caption", "start": round(line_times[k]["start"] + vo_start, 2),
                               "end": round(line_times[k]["end"] + vo_start + 0.25, 2), "text": ln,
                               "pos": "below_band" if d["look"]["frame"] != "full" else "lower"})
    spec = {"name": p["name"] or "draft", "aspect": d.get("aspect", "9:16"), "frame": d["look"]["frame"],
            "look": {k: d["look"][k] for k in ("grade", "grain", "vignette")}, "shots": out, "layers": layers}
    take = d.get("music_take")
    if take:
        spec["music"] = {"file": take["file"], "db": -3, "fade_out": 1.5}
        spec["ambient_db"] = -12
    if d.get("mute_clips"):
        spec["ambient_db"] = -90
    if voice_file:
        spec["voice"] = {"file": voice_file, "start": vo_start}
    elif not take:
        warn.append(f"müzik yok: kesmeler {d['look']['bpm']:.0f} BPM ızgarasında, uygulamada bu tempoda bir ses ekle")
    lo, hi = fmt["duration"]
    if not lo - 3 <= total <= hi + 6:
        warn.append(f"süre {total:.1f} s, format aralığı {lo}-{hi} s")
    return spec, round(total, 2), [round(s, 2) for s in starts], warn


def snap_info(path):
    b = beatmod.beats(path)
    return {"bpm": b["bpm"], "beats": b["beats"], "duration": b["duration"]}
