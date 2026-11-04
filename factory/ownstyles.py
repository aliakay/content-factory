"""The creator's own film styles, made in five steps and kept next to the library's twelve (factory/filmstyles.py):

  1 start   from one of the library's styles (or one of your own) to change it, or from a blank page
  2 plan    one question at a time: look, colours, title and body fonts, motion, sound, what to avoid, texture;
            each answer starts from the base style's card, so changing a style is editing what is already there
  3 brand   brand colours (they lead the accents), a logo (stamped on the sample frame), recurring characters
  4 sample  one frame drawn by the motion engine: the base style's scene with your colours and fonts swapped in
            (a blank start gets a plain template), finished with the texture's film post and the logo (no credits)
  5 approve the style joins the library as "style.own_<name>": proposal gates offer it, the explainer's edit stage
            takes its post, the designer gets it as the film style bible (brand colours and characters included)

The answers are the creator's own words: nothing is rewritten by a model. Any change after the sample makes the
style a draft again until a new sample is drawn and approved. Files: data/own_styles/<id>/style.json, sample.jpg.
"""
import json, os, re, shutil, time

from .config import ROOT

DIR = os.path.join(ROOT, "data", "own_styles")
STEPS = ("start", "plan", "brand", "sample", "approve")
FONTS = ("Inter Tight", "Montserrat", "Poppins", "Anton", "DM Serif Display", "Playfair Display",
         "Cormorant Garamond", "Instrument Serif", "Shrikhand", "Monoton")
TEXTURES = {"clean": {}, "grain": {"grain": 0.3}, "paper": {"grain": 0.2, "vignette": 0.2},
            "film": {"grain": 0.7, "flicker": True, "weave": True, "vignette": 0.4},
            "mono": {"grain": 0.5, "vignette": 0.45, "mono": True}, "glow": {"bloom": 0.3, "grain": 0.15}}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO_EXT = (".png", ".jpg", ".jpeg", ".webp")

# (id, step, kind, TR question, EN question). kind: text | colors | font | texture | logo | characters
QUESTIONS = (
    ("look", "plan", "text", "Nasıl görünsün? Zemin, biçimler, ışık; bir iki cümle.",
     "What should it look like? Ground, shapes, light; a sentence or two."),
    ("palette", "plan", "colors", "Renkler: 3-6 renk, ilki zemin, ikincisi yazı, sonra vurgular (#rrggbb).",
     "Colours: 3-6, the first is the ground, the second the type, then accents (#rrggbb)."),
    ("title_font", "plan", "font", "Başlık yazı tipi", "Title font"),
    ("body_font", "plan", "font", "Metin yazı tipi", "Body font"),
    ("motion", "plan", "text", "Nasıl hareket etsin?", "How should it move?"),
    ("sound", "plan", "text", "Nasıl duyulsun? Çalgılar, tempo, doku.", "How should it sound? Instruments, tempo, texture."),
    ("avoid", "plan", "text", "Nelerden kaçınalım?", "What should it never do?"),
    ("texture", "plan", "texture", "Film dokusu", "Film texture"),
    ("brand_colors", "brand", "colors", "Marka renklerin (isteğe bağlı): vurgu renklerinin başına geçer.",
     "Your brand colours (optional): they lead the accent colours."),
    ("logo", "brand", "logo", "Logo (isteğe bağlı, PNG/JPG): örnek karenin köşesine basılır.",
     "Logo (optional, PNG/JPG): stamped in the corner of the sample frame."),
    ("characters", "brand", "characters", "Tekrar eden karakterler (isteğe bağlı): satır başına \"Ad: görünüş\".",
     "Recurring characters (optional): one per line, \"Name: look\"."),
)
Q = {q[0]: q for q in QUESTIONS}
OPTIONAL = {"brand_colors", "logo", "characters"}
TEXTURE_NAMES = {"clean": ("Temiz", "Clean"), "grain": ("Gren", "Grain"), "paper": ("Kâğıt", "Paper"),
                 "film": ("Eski film", "Old film"), "mono": ("Siyah-beyaz", "Black and white"), "glow": ("Parıltı", "Glow")}


class StyleError(ValueError):
    pass


def _err(tr, en, ui="tr"):
    return StyleError(en if ui == "en" else tr)


def _path(sid, *parts):
    if not re.fullmatch(r"own_[a-z0-9_]{1,40}", sid or ""):
        raise StyleError("bad style id")
    return os.path.join(DIR, sid[4:], *parts)


def sample_file(sid):
    return _path(sid, "sample.jpg")


def load(sid):
    try:
        return json.load(open(_path(sid, "style.json"), encoding="utf-8"))
    except (OSError, ValueError):
        raise StyleError(f"no style '{sid}'") from None


def _save(st):
    os.makedirs(_path(st["id"]), exist_ok=True)
    st["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = _path(st["id"], "style.json.tmp")
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, _path(st["id"], "style.json"))
    return st


def listing():
    out = []
    for name in sorted(os.listdir(DIR)) if os.path.isdir(DIR) else []:
        try:
            out.append(load("own_" + name))
        except StyleError:
            pass
    return out


def approved():
    """Approved own styles in the library's film style shape (capabilities._film_styles adds them)."""
    return [_as_film_style(st) for st in listing() if st["status"] == "approved"]


def _slug(name):
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").translate(tr).lower()).strip("_")[:30]
    return s or "stil"


def _base(base):
    """The style to start from: a library style, an own style, or None for a blank page."""
    if not base or base == "blank":
        return None
    from . import capabilities
    for s in capabilities._film_styles():
        if s["id"] == base:
            return s
    raise StyleError(f"no style '{base}' to start from")


def _family(font):
    """'Montserrat 900' / 'Cormorant italic' -> the library font family it names, or None."""
    f = (font or "").lower()
    for fam in sorted(FONTS, key=len, reverse=True):
        if f.startswith(fam.lower()) or (fam.lower().startswith(f.split(" ")[0]) and len(f.split(" ")[0]) > 4):
            return fam
    return None


def create(name, base=None, user=None, ui="tr"):
    """Step 1: a draft from a base style (its card fills every answer) or from a blank page."""
    name = (name or "").strip()[:40]
    if len(name) < 2:
        raise _err("Stiline bir ad ver.", "Give your style a name.", ui)
    b = _base(base)
    sid = "own_" + _slug(name)
    n = 2
    while os.path.exists(_path(sid)):
        sid = f"own_{_slug(name)[:27]}_{n}"
        n += 1
    a = {k: "" for k in Q}
    a.update(palette=["#f4f1ea", "#151515", "#e4572e"], title_font="Inter Tight", body_font="Inter Tight",
             texture="clean", brand_colors=[], logo="", characters=[])
    if b:
        c = b.get("card") or {}
        words = c.get(ui) or c.get("tr") or {}
        fams = [x for x in (_family(f) for f in c.get("fonts") or []) if x]
        a.update(look=words.get("look", ""), motion=words.get("motion", ""), sound=words.get("sound", ""),
                 avoid=words.get("avoid", ""), palette=list(c.get("palette") or a["palette"]),
                 title_font=fams[0] if fams else "Inter Tight", body_font=fams[-1] if fams else "Inter Tight",
                 texture=_nearest_texture(b.get("post") or {}))
        if b.get("own"):     # changing one of your own: its brand comes along
            a.update(brand_colors=list((b.get("brand") or {}).get("colors") or []),
                     characters=list((b.get("brand") or {}).get("characters") or []))
    st = {"id": sid, "name": name, "base": b["id"] if b else "blank", "base_palette": list((b or {}).get("card", {}).get("palette") or []),
          "base_fonts": list((b or {}).get("card", {}).get("fonts") or []), "status": "draft", "step": "plan",
          "answers": a, "by": user, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if b and b.get("own") and (b.get("brand") or {}).get("logo"):
        src = os.path.join(ROOT, b["brand"]["logo"])
        if os.path.isfile(src):
            os.makedirs(_path(sid), exist_ok=True)
            dst = _path(sid, "logo" + os.path.splitext(src)[1].lower())
            shutil.copyfile(src, dst)
            a["logo"] = os.path.relpath(dst, ROOT)
    return _save(st)


def _nearest_texture(post):
    if post.get("mono"):
        return "mono"
    if post.get("flicker") or post.get("weave"):
        return "film"
    if post.get("bloom"):
        return "glow"
    if post.get("vignette"):
        return "paper"
    return "grain" if post.get("grain") else "clean"


def _colors(v, ui):
    items = v if isinstance(v, list) else re.split(r"[\s,;]+", str(v or ""))
    out = []
    for x in (str(i).strip() for i in items):
        if not x:
            continue
        x = x if x.startswith("#") else "#" + x
        if not HEX.match(x):
            raise _err(f"Renk {x} geçersiz; #rrggbb yaz.", f"Colour {x} is not valid; write #rrggbb.", ui)
        out.append(x.lower())
    return out


def _characters(v):
    rows = v if isinstance(v, list) else str(v or "").splitlines()
    out = []
    for r in rows:
        if isinstance(r, dict):
            name, look = str(r.get("name") or "").strip(), str(r.get("look") or "").strip()
        else:
            name, _, look = str(r).partition(":")
            name, look = name.strip(), look.strip()
        if name:
            out.append({"name": name[:40], "look": look[:300]})
    return out[:6]


def answer(sid, qid, value, ui="tr"):
    """Step 2-3: one answer. A change after the sample makes the style a draft again."""
    st = load(sid)
    if qid not in Q:
        raise StyleError(f"no question '{qid}'")
    kind = Q[qid][2]
    if kind == "text":
        v = str(value or "").strip()[:600]
        if not v:
            raise _err("Bu soruyu boş bırakma.", "Don't leave this one empty.", ui)
    elif kind == "colors":
        v = _colors(value, ui)
        if qid == "palette" and not 3 <= len(v) <= 6:
            raise _err("3 ile 6 arası renk yaz.", "Write 3 to 6 colours.", ui)
        v = v[:4] if qid == "brand_colors" else v
    elif kind == "font":
        if value not in FONTS:
            raise _err("Listeden bir yazı tipi seç.", "Pick a font from the list.", ui)
        v = value
    elif kind == "texture":
        if value not in TEXTURES:
            raise StyleError("unknown texture")
        v = value
    elif kind == "logo":
        v = str(value or "")
        if v:
            src = os.path.join(ROOT, v)
            if not re.fullmatch(r"raw/logo/[\w.-]+", v) or not v.lower().endswith(LOGO_EXT) or not os.path.isfile(src):
                raise _err("Önce logoyu yükle.", "Upload the logo first.", ui)
            os.makedirs(_path(sid), exist_ok=True)
            for old in os.listdir(_path(sid)):
                if old.startswith("logo."):
                    os.remove(_path(sid, old))
            dst = _path(sid, "logo" + os.path.splitext(v)[1].lower())
            shutil.copyfile(src, dst)
            v = os.path.relpath(dst, ROOT)
    else:
        v = _characters(value)
    if st["answers"].get(qid) != v:
        st["answers"][qid] = v
        if st["status"] in ("sampled", "approved"):
            st["status"] = "draft"
    st["step"] = Q[qid][1] if st["step"] in ("plan", "brand") else st["step"]
    return _save(st)


def palette(st):
    """The palette the style uses: the plan's ground and type, then the brand colours as the leading accents, then
    the plan's other accents; no repeats, at most six."""
    a = st["answers"]
    plan = list(a.get("palette") or [])
    out = []
    for c in plan[:2] + list(a.get("brand_colors") or []) + plan[2:]:
        if c.lower() not in out:
            out.append(c.lower())
    return out[:6]


def missing(st):
    return [k for k in Q if k not in OPTIONAL and not st["answers"].get(k)]


# ---------------------------------------------------------------- step 4: the sample frame

def _swap(text, pairs):
    """Replace every 'old' with its 'new' at once (no chained replacements), case-insensitive."""
    pairs = [(o, n) for o, n in pairs if o and n and o.lower() != n.lower()]
    if not pairs:
        return text
    rx = re.compile("|".join(re.escape(o) for o, _ in sorted(pairs, key=lambda p: -len(p[0]))), re.I)
    m = {o.lower(): n for o, n in pairs}
    return rx.sub(lambda x: m[x.group(0).lower()], text)


def _template(st):
    p = palette(st)
    bg, ink, acc = p[0], p[1], p[2]
    acc2 = p[3] if len(p) > 3 else p[2]
    tf, bf = st["answers"]["title_font"], st["answers"]["body_font"]
    name = json.dumps(st["name"], ensure_ascii=False)
    js = f"""
E('left:-160px;top:980px;width:900px;height:900px;border-radius:50%;background:{acc2};opacity:.9');
E('left:560px;top:1180px;width:620px;height:620px;background:{acc};transform:rotate(12deg)');
E('left:90px;top:260px;right:90px;font:400 150px/0.95 "{tf}";font-weight:800;color:{ink}', {name});
E('left:90px;top:640px;width:280px;height:18px;background:{acc}');
E('left:90px;top:720px;width:640px;font:400 46px/1.3 "{bf}";color:{ink};opacity:.85', 'Bir fikir, bir kare, bir ses.');
tl.from(root.children[1], {{x: 300, duration: 1.2, ease: 'power2.out'}}, 0);"""
    return {"seconds": 3, "css": f"position:absolute;inset:0;background:{bg}", "js": js.strip()}


def scene(st):
    """The base style's scene with this style's colours and fonts swapped in; a blank start gets the template."""
    if st["base"] == "blank" or st["base"].startswith("own_"):
        return _template(st)
    from . import filmstyles
    try:
        sc = json.load(open(os.path.join(filmstyles.DIR, st["base"] + ".json"), encoding="utf-8"))
    except OSError:
        return _template(st)
    new = palette(st)
    old = st.get("base_palette") or []
    pairs = [(o, new[i % len(new)]) for i, o in enumerate(old)]
    fams = [x for x in (_family(f) for f in st.get("base_fonts") or []) if x]
    if fams:
        pairs.append((fams[0], st["answers"]["title_font"]))
        if len(fams) > 1:
            pairs.append((fams[-1], st["answers"]["body_font"]))
    return {**sc, "css": _swap(sc["css"], pairs), "js": _swap(sc["js"], pairs)}


def render_sample(sid):
    """Draw the sample frame (headless motion engine + the texture's film post + the logo). No credits."""
    st = load(sid)
    gone = missing(st)
    if gone:
        raise StyleError("unanswered: " + ", ".join(gone))
    from . import filmstyles
    a = st["answers"]
    logo = os.path.join(ROOT, a["logo"]) if a.get("logo") else None
    filmstyles.draw(scene(st), TEXTURES[a["texture"]], sample_file(sid), "own_" + sid[4:], logo=logo)
    st = load(sid)
    st["status"], st["step"] = "sampled", "approve"
    return _save(st)


def approve(sid, by=None, ui="tr"):
    """Step 5: the drawn style joins the library."""
    st = load(sid)
    if st["status"] != "sampled" or not os.path.exists(sample_file(sid)):
        raise _err("Önce örnek kareyi çiz ve bak.", "Draw the sample frame and look at it first.", ui)
    st.update(status="approved", step="approve", approved_by=by, approved=time.strftime("%Y-%m-%dT%H:%M:%S"))
    _save(st)
    from . import capabilities
    capabilities.register_style(_as_film_style(st))
    return st


def delete(sid):
    load(sid)
    shutil.rmtree(_path(sid))
    from . import capabilities
    capabilities.CAPS.pop("style." + sid, None)


def _as_film_style(st):
    a = st["answers"]
    p = palette(st)
    chars = a.get("characters") or []
    brand = {"colors": a.get("brand_colors") or [], "logo": a.get("logo") or "", "characters": chars}
    brand_txt = "; ".join(x for x in (
        ("brand colours " + ", ".join(brand["colors"]) + " are the leading accents") if brand["colors"] else "",
        ("the brand logo appears small in a corner of the closing frame") if brand["logo"] else "",
        ("recurring characters: " + "; ".join(f"{c['name']} ({c['look']})" for c in chars)) if chars else "") if x)
    words = {"look": a["look"], "type": f"{a['title_font']} / {a['body_font']}", "motion": a["motion"],
             "sound": a["sound"], "avoid": a["avoid"]}
    return {"id": st["id"], "name": st["name"], "tr": st["name"], "own": True, "base": st["base"],
            "essence": a["look"], "not": a["avoid"], "colour": "palette " + ", ".join(p) + " (ground, type, accents)",
            "type": f"titles in {a['title_font']}, body in {a['body_font']}", "motion": a["motion"], "sound": a["sound"],
            **({"composition": brand_txt} if brand_txt else {}), "post": TEXTURES[a["texture"]],
            "card": {"palette": p, "fonts": [a["title_font"], a["body_font"]], "tr": words, "en": words}, "brand": brand}


def view(st, ui="tr"):
    """One style for the Studio's five-step page: the questions in the UI language with the current answers."""
    i = 1 if ui == "en" else 0
    from . import filmstyles
    f = sample_file(st["id"])
    return {**{k: st.get(k) for k in ("id", "name", "base", "status", "step", "created", "updated")},
            "steps": list(STEPS), "palette": palette(st), "missing": missing(st),
            "sample": (f"/media/filmstyles/{st['id']}.jpg?v={int(os.path.getmtime(f))}") if os.path.exists(f) else None,
            "logo": bool(st["answers"].get("logo")),
            "questions": [{"id": q[0], "step": q[1], "kind": q[2], "q": q[3 + i], "value": st["answers"].get(q[0]),
                           "optional": q[0] in OPTIONAL} for q in QUESTIONS],
            "fonts": list(FONTS), "textures": [{"id": k, "name": v[i]} for k, v in TEXTURE_NAMES.items()],
            "bases": [{"id": s["id"], "name": filmstyles.card(s, ui)["name"]} for s in filmstyles._all()]}
