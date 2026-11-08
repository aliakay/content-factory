"""The direction board: the look of the film decided once, as a picture, before a single scene is drawn.

A proposal says the look in a sentence ("risograph print, heavy type, one ink at a time") and the scene plan has to
turn that sentence into a palette, a type pairing, a light, a texture and a set of motion rules — scene by scene, by
an agent that sees the sentence and nothing else. Every scene then makes the same decisions slightly differently, and
the film looks assembled rather than directed.

This stage makes those decisions once and shows them: a board (a PNG drawn here, no browser and no credits) with the
palette, the type at four sizes, the light and texture rules, the motion rules and the references the research
gathered. The scene plan reads the board as its brief and has to keep to it; the creator approves the look at a gate
before any scene exists. The palette comes from the chosen film style's own card when there is one, and from a
deterministic scheme keyed on the project otherwise, so the same project always gets the same board.
"""
import hashlib, json, os

from ..config import ROOT
from . import project as P

# Hand-made schemes for projects whose look is not a catalogue film style: bg, ink, muted, accent, accent2, hot.
SCHEMES = (
    {"bg": "#101418", "ink": "#F2F0E9", "muted": "#8C949B", "accent": "#FFD93D", "accent2": "#4CC9F0", "hot": "#FF5C5C"},
    {"bg": "#F4EEE2", "ink": "#1B1B1B", "muted": "#7A7368", "accent": "#0078BF", "accent2": "#FF48B0", "hot": "#E4572E"},
    {"bg": "#0B1B2B", "ink": "#EAF2F8", "muted": "#7E93A6", "accent": "#F4A261", "accent2": "#2A9D8F", "hot": "#E76F51"},
    {"bg": "#1A1423", "ink": "#F5EFE6", "muted": "#9A8FA6", "accent": "#E9C46A", "accent2": "#7B2CBF", "hot": "#EF476F"},
    {"bg": "#12100E", "ink": "#EDE6DB", "muted": "#8A8279", "accent": "#C8FF3D", "accent2": "#FF6B35", "hot": "#FF3D7F"},
    {"bg": "#E8E4D9", "ink": "#22201C", "muted": "#6E6A61", "accent": "#D7263D", "accent2": "#1B998B", "hot": "#F46036"},
)
FONT_DIR = os.path.join(ROOT, "fonts")
DEFAULT_FONTS = {"display": "Inter Tight", "body": "Inter Tight"}
W, H = 1080, 1800


def _hex(c, fallback="#888888"):
    import re
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(c or "").strip())
    return "#" + m.group(1) if m else fallback


def _lum(c):
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _sat(c):
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return max(r, g, b) - min(r, g, b)


def _tokens(colors):
    """A style palette (ground first) -> tokens; luminance and saturation choose ink and accents."""
    cols = [_hex(c) for c in colors if c] or ["#101418", "#F2F0E9"]
    # Style cards list the ground first. Keeping that explicit choice avoids turning warm paper into the accent.
    bg = cols[0]
    rest = [c for c in cols[1:] if c != bg] or cols
    ink = min(rest, key=_lum) if _lum(bg) >= 0.5 else max(rest, key=_lum)
    rest = [c for c in cols if c not in (bg, ink)] or cols
    by_sat = sorted(rest, key=_sat, reverse=True)
    accent = by_sat[0]
    accent2 = by_sat[1] if len(by_sat) > 1 else accent
    return {"bg": bg, "ink": ink, "muted": _mix(bg, ink, 0.55), "accent": accent, "accent2": accent2,
            "hot": by_sat[2] if len(by_sat) > 2 else accent2, "capInk": ink, "capStroke": bg, "capActive": accent}


def _mix(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def _style(prop):
    """The film style behind the proposal's look (id `style.<id>`), or None."""
    look = str((prop or {}).get("look") or "")
    sid = look[6:] if look.startswith("style.") else look
    if not sid:
        return None
    from .. import filmstyles
    return filmstyles.get(sid)


def _scheme(pid, p):
    h = int(hashlib.sha1(f"{pid}|{p.get('title') or ''}".encode("utf-8")).hexdigest(), 16)
    return SCHEMES[h % len(SCHEMES)]


def palette(pid, p, prop):
    """The board's palette tokens: the film style's own card when the look is one, else a stable scheme."""
    st = _style(prop)
    card = (st or {}).get("card") or {}
    cols = card.get("palette") or []
    return _tokens(cols) if len(cols) >= 3 else _scheme(pid, p)


def fonts(prop):
    """The type pairing: the style's fonts when it names them, else the factory's default pair."""
    st = _style(prop) or {}
    card = st.get("card") or {}
    named = [_font_family(str(x)) for x in (card.get("fonts") or []) if x]
    if named:
        return {"display": named[0], "body": named[1] if len(named) > 1 else DEFAULT_FONTS["body"]}
    return dict(DEFAULT_FONTS)


def _font_family(name):
    """Style cards may write a face and weight ("Montserrat 900"); CSS pairing stores the family name only."""
    import re
    return re.sub(r"\s+(?:[1-9]00|regular|bold|black|light|medium)$", "", name.strip(), flags=re.I)


def rules(prop):
    """The four rules a scene must keep to: light, texture, motion, restraint. The style's own words when there is a
    style, else the studio's defaults. Each is one short line the designer can act on."""
    st = _style(prop) or {}
    out = []
    if st:
        out.append({"what": "light", "says": _first(st.get("colour"), "one ground, one accent, the accent is the point")})
        out.append({"what": "type", "says": _first(st.get("type"), "one display face, one body face, nothing else")})
        out.append({"what": "motion", "says": _first(st.get("motion"), "one primary move a scene, easing carries meaning")})
        out.append({"what": "camera", "says": _first(st.get("camera"), "name the move, its seconds and what it lands on")})
    else:
        out += [{"what": "light", "says": "one ground colour, one accent for the point; no gradients for their own sake"},
                {"what": "type", "says": "one display face, one body face, three to five sizes from the scale"},
                {"what": "motion", "says": "one primary move a scene; the accent marks the new thing, nothing else"},
                {"what": "camera", "says": "name the move, its seconds, its easing and what it lands on"}]
    out.append({"what": "restraint", "says": "spend the big move, the colour flip and the sound once; the rest is quiet"})
    return out


def _first(text, fallback):
    """The first sentence of a style's prose, short enough to be a rule."""
    s = str(text or "").strip()
    if not s:
        return fallback
    for sep in (". ", "; "):
        if sep in s:
            s = s.split(sep)[0]
            break
    return (s[:150] + "…") if len(s) > 150 else s


def references(pid, prop, research):
    """The visual references the board points at: the research's own list, plus the style it borrows grammar from."""
    st = _style(prop)
    out = [str(x) for x in (research or {}).get("visual_refs") or []][:4]
    if st:
        out.insert(0, f"{st['name']}: {st.get('essence', '')[:140]}")
    return out


# ---------------------------------------------------------------- the board picture

def _font_file(name):
    """The bundled font file whose name matches a family, or the default pair's file."""
    want = "".join(str(name or "").lower().split())
    for f in sorted(os.listdir(FONT_DIR)) if os.path.isdir(FONT_DIR) else []:
        if not f.lower().endswith(".ttf"):
            continue
        stem = "".join(f.lower().split("-")[0].split("[")[0].split())
        if want and (want in "".join(f.lower().split()) or stem == want):
            return os.path.join(FONT_DIR, f)
    return os.path.join(FONT_DIR, "InterTight[wght].ttf")


def draw(board, title, out):
    """The board as a PNG: reference frame, palette, type, light/texture studies, rules and references."""
    from PIL import Image, ImageDraw
    from .. import thumbs
    pal, typ = board["palette"], board["type"]
    im = Image.new("RGB", (W, H), pal["bg"])
    d = ImageDraw.Draw(im)
    disp = thumbs._font(_font_file(typ["display"]), 76)
    body = thumbs._font(_font_file(typ["body"]), 30)
    label = thumbs._font(_font_file(typ["body"]), 22)
    y = 64
    d.text((64, y), "YÖN PANOSU", font=label, fill=pal["accent"])
    y += 34
    for line in thumbs.wrap_lines(d, str(title or "").split(), disp, W - 128, maxlines=2):
        d.text((64, y), line, font=disp, fill=pal["ink"])
        y += 82
    y += 20
    style = board.get("style")
    has_sample = False
    if style:
        try:
            from ..filmstyles import preview_file
            ref = preview_file(style)
            if os.path.isfile(ref):
                from PIL import Image
                sample = Image.open(ref).convert("RGB")
                sample.thumbnail((360, 202), getattr(Image, "Resampling", Image).LANCZOS)
                d.text((64, y), "LOOK SAMPLE · STUDIO STYLE PREVIEW", font=label, fill=pal["muted"])
                y += 30
                im.paste(sample, (64, y))
                d.rectangle((63, y - 1, 65 + sample.width, y + sample.height + 1), outline=pal["muted"], width=2)
                y += sample.height + 20
                has_sample = True
        except (OSError, ValueError):
            pass
    if not has_sample:
        d.text((64, y), "FRAME SAMPLE · BOARD TOKENS", font=label, fill=pal["muted"])
        y += 30
        sample = Image.new("RGB", (360, 202), pal["bg"])
        sd = ImageDraw.Draw(sample)
        sd.rectangle((0, 0, 359, 202), outline=pal["muted"], width=2)
        sd.rectangle((24, 26, 336, 176), fill=pal["ink"])
        sd.rectangle((24, 26, 42, 176), fill=pal["accent"])
        sd.ellipse((240, 48, 318, 126), fill=pal["accent2"])
        sd.rectangle((67, 60, 210, 72), fill=pal["muted"])
        sd.rectangle((67, 91, 236, 111), fill=pal["accent"])
        sd.rectangle((67, 130, 188, 139), fill=pal["muted"])
        im.paste(sample, (64, y))
        y += sample.height + 20

    # A tiny, repeatable light and surface study makes these rules visible before a scene is drawn.
    d.text((64, y), "LIGHT / SURFACE", font=label, fill=pal["muted"])
    y += 30
    tile_w, tile_h = 174, 72
    light = Image.new("RGB", (tile_w, tile_h), pal["bg"])
    lp = light.load()
    ac = tuple(int(pal["accent"][i:i + 2], 16) for i in (1, 3, 5))
    bg = tuple(int(pal["bg"][i:i + 2], 16) for i in (1, 3, 5))
    for yy in range(tile_h):
        for xx in range(tile_w):
            strength = max(0.0, 1.0 - (((xx - tile_w * 0.36) / (tile_w * 0.9)) ** 2
                                       + ((yy - tile_h * 0.40) / (tile_h * 1.3)) ** 2)) * 0.55
            lp[xx, yy] = tuple(round(bg[i] * (1 - strength) + ac[i] * strength) for i in range(3))
    surface = Image.new("RGB", (tile_w, tile_h), pal["bg"])
    sd = ImageDraw.Draw(surface)
    spacing = 9
    dot = pal["muted"]
    for yy in range(5, tile_h, spacing):
        for xx in range(5, tile_w, spacing):
            sd.ellipse((xx, yy, xx + 1, yy + 1), fill=dot)
    d.text((64, y), "LIGHT", font=label, fill=pal["accent2"])
    d.text((64 + tile_w + 24, y), "SURFACE", font=label, fill=pal["accent2"])
    im.paste(light, (64, y + 30))
    im.paste(surface, (64 + tile_w + 24, y + 30))
    y += tile_h + 50
    d.text((64, y), "PALET", font=label, fill=pal["muted"])
    y += 34
    keys = ("bg", "ink", "muted", "accent", "accent2", "hot")
    bw = (W - 128 - 5 * 12) // len(keys)
    for i, k in enumerate(keys):
        x = 64 + i * (bw + 12)
        d.rectangle([x, y, x + bw, y + 96], fill=pal[k], outline=pal["muted"])
        d.text((x, y + 104), pal[k].upper(), font=label, fill=pal["ink"])
    y += 156
    d.text((64, y), "TİPOGRAFİ", font=label, fill=pal["muted"])
    y += 34
    for role, size in (("display", 64), ("h1", 48), ("body", 30), ("label", 22)):
        f = thumbs._font(_font_file(typ["display"] if role in ("display", "h1") else typ["body"]), size)
        d.text((64, y), f"{role} · {size}px · {typ['display'] if role in ('display', 'h1') else typ['body']}",
               font=f, fill=pal["ink"])
        y += size + 18
    y += 12
    d.text((64, y), "KURALLAR", font=label, fill=pal["muted"])
    y += 32
    for r in board["rules"]:
        d.text((64, y), r["what"].upper(), font=label, fill=pal["accent2"])
        for line in thumbs.wrap_lines(d, str(r["says"]).split(), body, W - 260, maxlines=2):
            d.text((230, y), line, font=body, fill=pal["ink"])
            y += 36
        y += 8
    if board["references"]:
        y += 8
        d.text((64, y), "REFERANSLAR", font=label, fill=pal["muted"])
        y += 32
        for ref in board["references"][:4]:
            for line in thumbs.wrap_lines(d, str(ref).split(), body, W - 128, maxlines=1):
                d.text((64, y), "· " + line, font=body, fill=pal["muted"])
                y += 36
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out, quality=92)
    return out


# ---------------------------------------------------------------- the stage

def build(pid, d=None):
    """The board for this project as data (no file written): palette, type, rules, references, fingerprint."""
    from .. import typography
    p = P.load(pid, d)
    prop = P.read_artifact(pid, "proposal", d) or {}
    research = P.read_artifact(pid, "research", d) or {}
    pal = palette(pid, p, prop)
    board = {"palette": pal, "type": {**fonts(prop), "scale": typography.scale(p.get("aspect", "9:16"))},
             "rules": rules(prop), "references": references(pid, prop, research),
             "style": (_style(prop) or {}).get("id")}
    board["fingerprint"] = hashlib.sha256(json.dumps(board, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    return board


def run(pid, s, note=None, d=None):
    """The stage: build the board, draw it, record it. A note is a direction change: it is kept as the board's note and
    the board is redrawn with the palette/fonts the note names, if it names any."""
    p = P.load(pid, d)
    board = build(pid, d)
    if note:
        board = _apply_note(board, note)
    ui = p.get("ui_lang") if p.get("ui_lang") in ("tr", "en") else "tr"
    img = P.path(pid, "renders", "direction.png", d=d)
    draw(board, P.load(pid, d).get("title") or pid, img)
    board["image"] = os.path.relpath(img, ROOT)
    st = board.get("style")
    board["summary"] = {"tr": f"Yön panosu hazır: {board['type']['display']} + {board['type']['body']}"
                              f"{f' · {st} stilinden' if st else ''}. Palet ve kurallar sahne planına geçecek.",
                        "en": f"Direction board ready: {board['type']['display']} + {board['type']['body']}"
                              f"{f' · from the {st} style' if st else ''}. The palette and rules go to the scene plan."}[ui]
    P.decision(pid, "direction", st or "scheme", d=d, palette=board["palette"], fonts=board["type"],
               reason="film style card" if st else "deterministic scheme from the project")
    return {"artifact": board, "summary": board["summary"], "cost": {"credits": 0, "usd": 0.0}}


def _apply_note(board, note):
    """A note that names hex colours or a font changes the board; anything else is kept as the note and changes nothing
    yet (the creator can send it again with the words they want)."""
    import re
    cols = re.findall(r"#?[0-9a-fA-F]{6}\b", note)
    if len(cols) >= 2:
        board["palette"] = _tokens(cols)
        board["note"] = note
    fam = re.search(r"(?:font|yazı|yazi|tipografi)\s*[:=]?\s*([A-Za-z][\w ]{2,30})", note, re.I)
    if fam:
        board["type"]["display"] = board["type"]["body"] = fam.group(1).strip()
        board["note"] = note
    if "note" not in board:
        board["note"] = note
    board["fingerprint"] = hashlib.sha256(
        json.dumps({k: v for k, v in board.items() if k != "note"}, sort_keys=True, ensure_ascii=False)
        .encode()).hexdigest()[:12]
    return board


def problems(plan, board=None, d=None):
    """What `submit_artifact` refuses on a scene plan drawn against an approved board: a colour the board does not have
    and a type family it does not name. No board (a line without the stage) means nothing to check."""
    if not isinstance(board, dict) or not board.get("palette"):
        return []
    import re
    allowed = {str(v).lower() for v in board["palette"].values() if str(v).startswith("#")}
    pal = (plan or {}).get("palette") or {}
    vals = [str(v).lower() for v in (pal.values() if isinstance(pal, dict) else pal) if str(v).startswith("#")]
    scene_text = "\n".join(str(sc.get(k) or "") for sc in (plan or {}).get("scenes") or []
                            for k in ("css", "html", "js"))
    scene_text += "\n" + str((plan or {}).get("global_css") or "")
    vals += [c.lower() for c in re.findall(r"#[0-9a-fA-F]{3,8}\b", scene_text)]
    extra = [c for c in vals if c not in allowed and c not in ("#000000", "#ffffff", "#000", "#fff")]
    out = []
    if extra:
        out.append(f"the palette uses {', '.join(sorted(set(extra))[:4])}, which the approved direction board does not "
                   f"have ({', '.join(sorted(allowed))}): keep to the board, or send a note back to it")
    fams = {str(f).strip().lower() for f in [board["type"].get("display"), board["type"].get("body")] if f}
    generic = {"sans-serif", "serif", "monospace", "system-ui", "inherit", "cursive", "fantasy"}
    text = scene_text
    named = set()
    for raw in re.findall(r"font-family\s*:\s*([^;}\n]+)", text, re.I):
        for fam in raw.split(","):
            key = _font_family(fam.strip().strip("\"'")).lower()
            if key and key not in generic and not key.startswith("var("):
                named.add(key)
    fams = {_font_family(f).lower() for f in fams}
    unknown = sorted(named - fams)
    if unknown:
        out.append(f"the scenes set type in {', '.join(unknown)}, which the board's pairing does not include "
                   f"({', '.join(sorted(fams))}): use the pairing")
    return out


def brief(p=None):
    """The board as the scene plan's brief: empty when the line has no board (the stage is optional per line)."""
    if not isinstance(p, dict) or not p.get("id"):
        return ""
    board = P.read_artifact(p["id"], "direction", None) or {}
    if not board.get("palette"):
        return ""
    pal = ", ".join(f"{k} {v}" for k, v in board["palette"].items())
    typ = board.get("type") or {}
    rules = "\n".join(f"- {r['what']}: {r['says']}" for r in board.get("rules") or [])
    refs = "\n".join(f"- {r}" for r in board.get("references") or []) or "- (none recorded)"
    return (f"DIRECTION BOARD (approved; keep to it)\n"
            f"Palette tokens: {pal}\nType: {typ.get('display')} for display, {typ.get('body')} for body; sizes "
            f"{typ.get('scale')}\nRules:\n{rules}\nReferences:\n{refs}\n"
            f"The creator approved this board at its gate: the scenes are drawn in it, and a scene that leaves the "
            f"palette or the type pairing is a note back to the board, not a new look.")
