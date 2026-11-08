"""The attribution ledger: every asset in the film, what it is, who made it, under which licence, and the credit it owes.

`stock.py` already refuses NC / ND and records the author, licence and source page of every image it hands out, and
`archive.py` does the same for footage. What was missing is the step that makes the promise true: nothing collected
those records per project, so a film could ship a CC BY-SA photograph and never credit it.

`entries()` reads the project itself, not a declaration: it scans the scene plan's HTML for the stock files actually
placed on screen, matches each one against the stock cache, and adds the assets the assets stage generated (voice,
music, a locally composed score) and the fonts the design uses. `missing()` names an asset whose licence is unknown
(a file that was placed by hand, not through `stock_search`); `block()` is the credit text for the description; and
`guard()` refuses the publish gate while an asset is unlicensed or a credit the licence requires is not in the
description.
"""
import json, os, re
from urllib.parse import unquote, urlsplit

from .config import ROOT

STOCK_DIR = "assets/stock"
CREDIT_REQUIRED = re.compile(r"cc[- ]by|by[- ]sa|licenses?/by(?:-sa)?/|attribution|share[- ]alike", re.I)
PUBLIC_DOMAIN = re.compile(r"^(cc0|public domain|pd)\b|creativecommons\.org/publicdomain/", re.I)
FILE = re.compile(r"assets/stock/[\w.-]+", re.I)
SFX = re.compile(r"/?assets/sfx/[\w.-]+", re.I)
SFX_CALL = re.compile(r"\bFX\.sfx\(\s*['\"]([a-z0-9_-]+)['\"]", re.I)
FX_MUSIC_CALL = re.compile(r"\bFX\.music\(\s*['\"]([a-z0-9_-]+)['\"]", re.I)
FONTFACE = re.compile(r"@font-face\s*\{[^}]*?font-family\s*:\s*[\"']?([^;\"'}]+)[\"']?[^}]*?url\(\s*[\"']?([^\"')]+)[\"']?\s*\)",
                      re.I | re.S)
FAMILY = re.compile(r"font-family\s*:\s*([^;}\n]+)", re.I)
MEDIA_SRC = re.compile(r"<(?:img|video|audio|source|track)\b[^>]*?\bsrc\s*=\s*(['\"])(.*?)\1", re.I | re.S)
CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I | re.S)


def _stock_cache():
    try:
        with open(os.path.join(ROOT, "data", "stock_cache.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _cache_by_file():
    out = {}
    for hit in _stock_cache().values():
        if isinstance(hit, dict) and hit.get("file"):
            out[os.path.normpath(hit["file"])] = hit
    return out


def _plan_text(plan):
    return "\n".join(str(sc.get(k) or "") for sc in plan.get("scenes") or [] for k in ("html", "css", "js")) \
        + "\n" + str(plan.get("global_css") or "")


def stock_entries(plan):
    """The stock images the plan actually places, from the scene HTML, joined with the cache's author/licence/page.

    An image the cache does not know (placed by hand) comes back with `licence: None`, which `missing()` reports."""
    by_file, out = _cache_by_file(), []
    seen = set()
    for rel in FILE.findall(_plan_text(plan) or ""):
        rel = os.path.normpath(rel.lstrip("/"))
        if rel in seen:
            continue
        seen.add(rel)
        hit = by_file.get(rel) or {}
        lic = hit.get("license") or hit.get("licence")
        out.append({"kind": "image", "file": rel, "what": hit.get("title") or os.path.basename(rel),
                    "author": hit.get("author") or "", "licence": lic or None,
                    "url": hit.get("url") or "", "page": hit.get("url") or "",
                    "credit": bool(lic) and bool(CREDIT_REQUIRED.search(lic)) and not PUBLIC_DOMAIN.match(lic)})
    for item in plan.get("stock") or []:            # a plan may declare its picks instead of embedding them
        if isinstance(item, dict) and item.get("file") and os.path.normpath(item["file"]) not in seen:
            seen.add(os.path.normpath(item["file"]))
            lic = item.get("license") or item.get("licence")
            out.append({"kind": "image", "file": os.path.normpath(item["file"]), "what": item.get("title") or "",
                        "author": item.get("author") or "", "licence": lic or None, "url": item.get("url") or "",
                        "page": item.get("url") or "",
                        "credit": bool(lic) and bool(CREDIT_REQUIRED.search(lic)) and not PUBLIC_DOMAIN.match(lic)})
    return out


def untracked_media(plan, known=()):
    """Media URLs embedded directly in scene code that bypass the stock/archive selectors."""
    text = _plan_text(plan)
    known = {os.path.normpath(unquote(urlsplit(str(x)).path).lstrip("/")) for x in known if x}
    refs = [x for _, x in MEDIA_SRC.findall(text)] + [x for _, x in CSS_URL.findall(text)]
    out, seen = [], set()
    for raw in refs:
        raw = str(raw or "").strip()
        if not raw or raw.startswith(("#", "data:", "about:")):
            continue
        bits = urlsplit(raw)
        rel = os.path.normpath(unquote(bits.path).lstrip("/"))
        if rel in known or rel.startswith(("fonts/", "assets/stock/", "assets/sfx/")):
            continue
        key = bits.geturl()
        if key in seen:
            continue
        seen.add(key)
        external = bits.scheme in ("http", "https")
        supplied = rel.startswith(f"projects/{plan.get('project_id')}/") and os.path.isfile(os.path.join(ROOT, rel))
        out.append({"kind": "embedded media", "file": raw, "what": os.path.basename(bits.path) or raw,
                    "author": "creator-supplied" if supplied else "unknown",
                    "licence": "creator-supplied; rights asserted by uploader" if supplied else None,
                    "url": raw if external else "", "page": raw if external else "", "credit": False})
    return out


def builtin_sfx(plan):
    """Synthesised factory SFX used by the final scene code (no external recording or attribution)."""
    text = _plan_text(plan) or ""
    seen, out = set(), []
    files = SFX.findall(text) + [f"factory-sfx:{x}" for x in SFX_CALL.findall(text)] \
        + [f"factory-music:{x}" for x in FX_MUSIC_CALL.findall(text)]
    for raw in files:
        rel = os.path.normpath(raw.lstrip("/"))
        if rel in seen:
            continue
        seen.add(rel)
        what = rel.split(":", 1)[-1] if ":" in rel else os.path.basename(rel)
        out.append({"kind": "sound effect" if "music:" not in rel else "sound cue", "file": rel, "what": what,
                    "author": "Content Factory", "licence": "synthesised in-house, royalty-free",
                    "url": "", "page": "", "credit": False})
    return out


def made_entries(assets):
    """The sound this project made or bought: a locally composed score, an ElevenLabs voice or track."""
    out, voice, music = [], (assets or {}).get("voice") or {}, (assets or {}).get("music")
    if voice.get("file"):
        out.append({"kind": "voice", "file": voice["file"], "what": f"Voice ({voice.get('voice_id') or 'narrator'})",
                    "author": "ElevenLabs", "licence": "generated for this video on the account's plan", "url": "",
                    "page": "", "credit": False})
    if music and music.get("file"):
        if music.get("source") == "composer":
            out.append({"kind": "music", "file": music["file"], "what": "Original score", "author": "composed here",
                        "licence": "made for this video", "url": "", "page": "", "credit": False})
        else:
            out.append({"kind": "music", "file": music["file"], "what": "Music track", "author": "ElevenLabs",
                        "licence": "generated for this video on the account's plan", "url": "", "page": "",
                        "credit": False})
    for clip in (assets or {}).get("clips") or []:
        if isinstance(clip, dict) and clip.get("file"):
            model = clip.get("model") or "ElevenLabs video generation"
            out.append({"kind": "video", "file": clip["file"], "what": clip.get("prompt") or clip.get("shows") or "Generated clip",
                        "author": model, "licence": "generated for this video on the account's plan", "url": "",
                        "page": "", "credit": False})
    avatar = (assets or {}).get("avatar")
    if isinstance(avatar, dict) and avatar.get("file"):
        out.append({"kind": "video", "file": avatar["file"], "what": "Generated presenter video",
                    "author": avatar.get("model") or "ElevenLabs", "licence": "generated for this video on the account's plan",
                    "url": "", "page": "", "credit": False})
    for frame in (assets or {}).get("frames") or []:
        if isinstance(frame, dict) and frame.get("file"):
            out.append({"kind": "image", "file": frame["file"], "what": frame.get("prompt") or "Generated image",
                        "author": "ElevenLabs", "licence": "generated for this video on the account's plan",
                        "url": "", "page": "", "credit": False})
    return out


def plate_entries(pid, d=None):
    """Generated plates and open-archive clips attached to a project's scene plan."""
    from .hat import project as P
    art = P.read_artifact(pid, "plates", d) or {}
    out = []
    for frame in art.get("frames") or []:
        if not isinstance(frame, dict) or not frame.get("file"):
            continue
        out.append({"kind": "image", "file": frame["file"], "what": frame.get("prompt") or "Generated keyframe",
                    "author": "ElevenLabs", "licence": "generated for this video on the account's plan",
                    "url": "", "page": "", "credit": False})
    for file in art.get("plates") or []:
        if isinstance(file, str) and file:
            out.append({"kind": "image", "file": file, "what": os.path.basename(file), "author": "Content Factory",
                        "licence": "generated for this video on the account's plan", "url": "", "page": "",
                        "credit": False})
    for beat in art.get("beats") or []:
        clip = beat.get("clip") if isinstance(beat, dict) else None
        if not isinstance(clip, dict) or not clip.get("file"):
            continue
        lic = clip.get("license") or clip.get("licence")
        url = clip.get("page") or clip.get("url") or ""
        out.append({"kind": "footage", "file": clip["file"], "what": clip.get("title") or clip.get("source") or "Archive footage",
                    "author": clip.get("author") or clip.get("source") or "unknown", "licence": lic,
                    "url": url, "page": url,
                    "credit": bool(lic) and bool(CREDIT_REQUIRED.search(lic)) and not PUBLIC_DOMAIN.match(lic)})
    return out


def source_entries(pid, d=None):
    """Creator-supplied source media referenced by the selected cut, plus a screen capture if one was used."""
    from .hat import project as P
    from .store import connect
    ids = set()
    for name in ("shot_list", "cut_plan"):
        art = P.read_artifact(pid, name, d) or {}
        for shot in art.get("shots") or []:
            cid = shot.get("clip_id") or shot.get("clip")
            if isinstance(cid, str) and cid:
                ids.add(cid)
    p = P.load(pid, d)
    prod_ids = {p.get("current_prod")}
    proposal = P.read_artifact(pid, "proposal", d) or {}
    chosen = next((c for c in proposal.get("concepts") or []
                   if isinstance(c, dict) and c.get("id") == proposal.get("chosen")), None)
    if not p.get("current_prod") and chosen:
        prod_ids.add(chosen.get("prod_id"))
    prod_ids.discard(None)
    con = None
    out = []
    try:
        con = connect()
        from . import productions
        for prod_id in prod_ids:
            try:
                row = productions.get(con, prod_id)
                ids.update(s.get("clip_id") for s in (row.get("data") or {}).get("shots") or [] if s.get("clip_id"))
            except Exception:
                continue
        for cid in sorted(ids):
            row = con.execute("SELECT clip_id,path,kind,album,description FROM clips WHERE clip_id=?", (cid,)).fetchone()
            if not row:
                out.append({"kind": "source clip", "file": str(cid), "what": str(cid), "author": "unknown",
                            "licence": None, "url": "", "page": "", "credit": False})
                continue
            if str(row["album"] or "").startswith("gen:"):
                # Generated clips are recorded with their model and file in the assets artifact.
                continue
            path = os.path.relpath(row["path"], ROOT) if row["path"] else str(cid)
            out.append({"kind": row["kind"] or "source clip", "file": path,
                        "what": row["description"] or os.path.basename(path), "author": "creator-supplied",
                        "licence": "creator-supplied; rights asserted by uploader", "url": "", "page": "",
                        "credit": False})
    except Exception:
        recorded = {r.get("what") for r in out}
        for cid in sorted(ids):
            if cid not in recorded:
                out.append({"kind": "source clip", "file": str(cid), "what": str(cid), "author": "unknown",
                            "licence": None, "url": "", "page": "", "credit": False})
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass
    capture = P.read_artifact(pid, "capture", d) or {}
    file = capture.get("file")
    if isinstance(file, str) and file:
        out.append({"kind": "screen recording", "file": file, "what": capture.get("title") or "Recorded screen",
                    "author": "creator-supplied", "licence": "creator-supplied; rights asserted by uploader",
                    "url": "", "page": "", "credit": False})
    return out


def fonts(plan):
    """The bundled fonts the design names (from the shell's @font-face table), as files, for the ledger's record.

    They need no on-screen credit and they ship with the factory, so they are recorded, never required."""
    try:
        shell = open(os.path.join(ROOT, "motion", "templates", "explainer_shell.html"), encoding="utf-8").read()
    except OSError:
        return []
    table = {fam.strip().lower(): url for fam, url in FONTFACE.findall(shell)}
    text = _plan_text(plan)
    used, out = set(), []
    generic = {"sans-serif", "serif", "monospace", "system-ui", "inherit", "cursive", "fantasy"}
    for raw in FAMILY.findall(text):
        for fam in re.split(r"[,]", raw):
            key = fam.strip().strip("\"'").lower()
            if not key or key in generic or key.startswith("var(") or key in used:
                continue
            used.add(key)
            if key in table:
                out.append({"kind": "font", "file": table[key].lstrip("/"), "what": fam.strip().strip("\"'"),
                            "author": "Google Fonts", "licence": "SIL Open Font License 1.1 (fonts/)", "url": "",
                            "page": "", "credit": False})
            else:
                out.append({"kind": "font", "file": "font-family:" + fam.strip().strip("\"'"),
                            "what": fam.strip().strip("\"'"), "author": "unknown", "licence": None,
                            "url": "", "page": "", "credit": False})
    return out


def entries(pid, d=None):
    """Every media asset of the project with its licence record."""
    from .hat import project as P
    plan = P.read_artifact(pid, "scene_plan", d) or {}
    assets = P.read_artifact(pid, "assets", d) or {}
    stocks, sfx, typefaces = stock_entries(plan), builtin_sfx(plan), fonts(plan)
    plates, made, sources = plate_entries(pid, d), made_entries(assets), source_entries(pid, d)
    known = [r.get("file") for r in stocks + sfx + plates + made + sources + typefaces]
    plan = {**plan, "project_id": pid}
    rows = stocks + untracked_media(plan, known) + sfx + plates + made + sources + typefaces
    unique, seen = [], set()
    for row in rows:
        key = os.path.normpath(str(row.get("file") or row.get("url") or row.get("what") or ""))
        if key and key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def missing(rows):
    """Assets whose licence is unknown: nothing may ship with one of these."""
    return [r for r in rows if not r.get("licence")]


def required(rows):
    """Assets whose licence demands a credit line in the description."""
    return [r for r in rows if r.get("credit")]


def block(rows, lang="tr"):
    """The credit text for the description: one line per asset that owes a credit, in the video's language."""
    need = required(rows)
    if not need:
        return ""
    head = "Varlıklar" if lang == "tr" else "Assets"
    lines = [f"{head}:"]
    for r in need:
        who = r.get("author") or ("bilinmiyor" if lang == "tr" else "unknown")
        lines.append(f"- {r['what']} · {who} · {r['licence']}" + (f" · {r['url']}" if r.get("url") else ""))
    return "\n".join(lines)


def summary(rows, lang="tr"):
    n = len(rows)
    cred = len(required(rows))
    miss = len(missing(rows))
    if lang == "tr":
        s = f"{n} varlık kayıtlı, {cred} tanesi künye istiyor."
        return s + (f" {miss} varlığın lisansı bilinmiyor." if miss else " Lisansı bilinmeyen varlık yok.")
    s = f"{n} assets on record, {cred} need a credit line."
    return s + (f" {miss} have no known licence." if miss else " Every asset has a known licence.")


def guard(pid, sid, d=None):
    """Refuse the publish gate while an asset has no licence, or a credit the licence requires is not in the
    description. Runs only on the publish stage; every other stage returns immediately."""
    from .hat import manifest, project as P
    p = P.load(pid, d)
    if manifest.stage(manifest.get(p["line"]), sid)["artifact"] != "publish":
        return None
    rows = entries(pid, d)
    miss = missing(rows)
    lang = p.get("video_lang") or "tr"
    if miss:
        head = {"tr": "Lisans defteri: şu varlıkların lisansı bilinmiyor, yayın kapısı geçilemez:",
                "en": "Licence ledger: these assets have no known licence; the publish gate cannot pass:"}[
            p.get("ui_lang") if p.get("ui_lang") in ("tr", "en") else "tr"]
        raise P.GateError(head + "\n" + "\n".join(f"- {r['file']}" for r in miss))
    need = required(rows)
    if not need:
        return rows
    art = P.read_artifact(pid, "publish", d) or {}
    text = str(art.get("credits") or "")
    absent = [r for r in need if (r.get("what") or "")[:24] not in text and (r.get("url") or "")[:24] not in text]
    if absent:
        ui = p.get("ui_lang") if p.get("ui_lang") in ("tr", "en") else "tr"
        head = {"tr": f"Lisans defteri: {len(absent)} varlığın künyesi açıklamada yok, kapı geçilemez. Ekle:",
                "en": f"Licence ledger: {len(absent)} credit line(s) missing from the description; the gate cannot pass. Add:"}[ui]
        raise P.GateError(head + "\n" + block(need, lang))
    return rows


def write_credits(pid, d=None, rows=None):
    """Write the complete per-film attribution ledger next to the rendered video; return a factory-relative path."""
    from .hat import project as P
    rows = entries(pid, d) if rows is None else rows
    p = P.load(pid, d)
    lang = p.get("video_lang") or "tr"
    path = P.path(pid, "renders", "credits.txt", d=d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    title = p.get("title") or pid
    lines = [title, "=" * min(72, max(12, len(title)))]
    if not rows:
        lines += ["No external or generated media assets were recorded." if lang == "en"
                  else "Harici veya üretilmiş medya varlığı kaydedilmedi."]
    else:
        for r in rows:
            lines.append(" · ".join(str(x) for x in (r.get("what"), r.get("author"), r.get("licence")) if x)
                         + (f" · {r.get('url')}" if r.get("url") else "")
                         + f" [{r.get('kind') or 'asset'}]")
    lines += ["", block(rows, lang) or ("No separate attribution line is required." if lang == "en"
                                        else "Ayrı bir künye satırı gerekmiyor.")]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return os.path.relpath(path, ROOT)


def brief(p=None):
    return ("ATTRIBUTION (binding)\n"
            "Call `attribution` before you submit: it lists every asset in the film with its licence and the credit "
            "text it owes. Put that text in `credits` (one line per asset, author and licence and source URL). "
            "An asset with no known licence blocks the gate; so does a required credit that is missing here.")
