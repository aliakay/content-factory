"""The avatar presenter line's code side: a script spoken by a presenter image (Creatify Aurora by default), with
captions burned in. The presenter is the creator's uploaded portrait (project["portrait"], under raw/avatar/), a photo
already saved in their ElevenLabs account (project["presenter_asset"]), or a generated one.

  idea        the script, the presenter and the cost (voice, portrait, avatar seconds) -> proposal (gate)
  script      the lines -> script (gate; feedback rewrites them, nothing is paid)
  scene_plan  the presenter image on a fresh flow (generated, uploaded or the saved photo) -> plates (gate)
  assets      the voice, its word timing, the voice uploaded next to the presenter, the talking video, a captioned
              preview -> assets (gate; a note changes how the presenter moves and redoes only the video)
  edit        nothing to decide by hand: captions and loudness are fixed
  compose     the final with captions, technical QA and covers -> render
  publish     the caption, hashtags and the AI-content label reminder -> publish (gate)
Avatar prices are not in the learned rates until the first real run, so an unknown price reserves AVATAR_CEILING
credits a second in the budget; the guard never lets it spend more than what is left of the approval.
"""
import json, os, re, shutil, subprocess

from ..config import FFMPEG, ROOT
from . import project as P
from .explainer import remaining_budget, _con, _rel   # noqa: F401
from .footage import _ui

AVATAR_CEILING = 1500          # credits a second reserved for an avatar model with no learned price yet
WPS = {"tr": 2.3, "en": 2.5}
PORTRAIT_MODEL = "gpt-image-2"


def _ask(prompt):
    from .. import llm
    data, meta = llm.ask(prompt, tools=(), timeout=900)
    return (data if isinstance(data, dict) else {}), float((meta or {}).get("cost_usd") or 0)


def _portrait(p):
    src = p.get("portrait") or ""
    if not src:
        return None
    full = os.path.realpath(os.path.join(ROOT, src))
    if not full.startswith(os.path.realpath(os.path.join(ROOT, "raw", "avatar")) + os.sep) or not os.path.isfile(full):
        raise P.GateError("the presenter portrait is not an uploaded file (raw/avatar/)")
    return full


def _source(p):
    return "upload" if p.get("portrait") else "saved" if p.get("presenter_asset") else "generate"


def _model(p):
    from . import media
    return p.get("avatar_model") if media.get(p.get("avatar_model") or "") else "creatify-aurora"


def _seconds(lines, lang):
    return round(len(" ".join(lines).split()) / WPS.get(lang, 2.5) + 1.0, 1)


def _cost(p, lines, presenter_prompt):
    from .. import credits, formats
    text = " ".join(lines)
    secs = _seconds(lines, p.get("video_lang", "tr"))
    model = _model(p)
    items = [{"kind": "tts", "model": formats.VOICE_MODEL, "units": len(text), "unit": "char", "label": "voice"}]
    if _source(p) == "generate":
        items.append({"kind": "image", "model": PORTRAIT_MODEL, "units": 1, "unit": "img", "label": "presenter"})
    items.append({"kind": "video", "model": model, "units": secs, "unit": "s", "label": f"avatar · {secs:.0f} s · {model}"})
    est = credits.estimate(items)
    lines_out = []
    for x in est["lines"]:
        c = x["credits"]
        if c is None and x["kind"] == "video":
            c = round(AVATAR_CEILING * secs)            # reserved ceiling, not a price
        lines_out.append({"label": x["label"] + (" (ceiling)" if x["credits"] is None else ""), "credits": c or 0})
    return {"credits": sum(x["credits"] for x in lines_out), "lines": lines_out, "unknown": est["unknown"]}, secs


def _script_prompt(p, note, cur=None):
    return f"""You write scripts for a digital presenter who speaks straight to camera in a vertical short video
(announcement, intro, training, news-style explainer). The creator's brief: <<<{p.get('brief') or ''}>>>
Video language: {p.get('video_lang') or 'en'} (write every line in it). 15-60 s spoken. Short spoken sentences, one
idea per line, no stage directions, no emoji, numbers written as people say them. Line 1 is the hook.
{f"Current script (JSON): {json.dumps(cur, ensure_ascii=False)}" if cur else ""}
{f"The creator's note: <<<{note}>>>" if note else ""}
Reply ONLY JSON: {{"title": "...", "hook": "...", "lines": ["..."], "presenter": "a still-portrait prompt for the
presenter: who, age range, clothing, setting, light; front-facing, head and shoulders, looking into the lens, mouth
closed, no text", "caption": "post caption", "hashtags": ["#..."]}}"""


def idea(pid, s, note=None, d=None):
    """The script and presenter, priced. A note rewrites them."""
    p = P.load(pid, d)
    if _source(p) == "upload":
        _portrait(p)
    data, usd = _ask(_script_prompt(p, note))
    lines = [str(x).strip() for x in data.get("lines") or [] if str(x).strip()]
    if len(lines) < 2:
        raise P.GateError("the script came back empty; give a note and redo")
    cost, secs = _cost(p, lines, data.get("presenter"))
    src = _source(p)
    look = {"upload": {"tr": "senin portren", "en": "your portrait"}, "saved": {"tr": "kayıtlı fotoğrafın", "en": "your saved photo"},
            "generate": {"tr": "üretilecek sunucu", "en": "a generated presenter"}}[src][_ui(p)]
    concept = {"id": "A", "title": data.get("title") or lines[0][:60], "hook": data.get("hook") or lines[0],
               "structure": f"{len(lines)} lines · ~{secs:.0f} s · {_model(p)}", "look": look,
               "key_frame": data.get("presenter") or "", "lines": lines,
               "post": {"caption": data.get("caption") or "", "hashtags": data.get("hashtags") or []}}
    summary = {"tr": f"Sunucu ({look}) ~{secs:.0f} sn konuşacak; ~{cost['credits']} kredi.",
               "en": f"The presenter ({look}) speaks ~{secs:.0f} s; ~{cost['credits']} credits."}[_ui(p)]
    if cost["unknown"]:
        summary += {"tr": " Avatar fiyatı henüz bilinmiyor: tavan ayrıldı, ilk gerçek çalışma gerçek fiyatı kaydeder.",
                    "en": " The avatar price is not known yet: a ceiling is reserved; the first real run records the price."}[_ui(p)]
    art = {"concepts": [concept], "chosen": "A", "seconds": secs, "look": look, "voice": {"use": True},
           "music": {"use": False}, "presenter": data.get("presenter") or "", "cost": cost, "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"usd": usd}}


def script(pid, s, note=None, d=None):
    p = P.load(pid, d)
    prop = P.read_artifact(pid, "proposal", d) or {}
    c = (prop.get("concepts") or [{}])[0]
    cur = P.read_artifact(pid, "script", d) if note else None
    lines, title, usd = (cur or {}).get("lines") or c.get("lines") or [], c.get("title") or "", 0.0
    post = c.get("post") or {}
    if note:
        data, usd = _ask(_script_prompt(p, note, cur={"title": title, "lines": lines}))
        new = [str(x).strip() for x in data.get("lines") or [] if str(x).strip()]
        if len(new) >= 2:
            lines, title = new, data.get("title") or title
    if not lines:
        raise P.GateError("no script yet")
    secs = _seconds(lines, p.get("video_lang", "tr"))
    cost, _ = _cost(p, lines, prop.get("presenter"))
    left = remaining_budget(pid, d)
    summary = {"tr": f"{len(lines)} satır, ~{secs:.0f} sn.", "en": f"{len(lines)} lines, ~{secs:.0f} s."}[_ui(p)]
    if cost["credits"] > left:
        summary += {"tr": f" Onaylı bütçeyi ({left}) aşıyor: kısalt.", "en": f" Above the approved budget ({left}): shorten it."}[_ui(p)]
    art = {"title": title, "hook": lines[0], "lines": lines, "claims": [], "caption": post.get("caption") or "",
           "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"usd": usd}}


def scene_plan(pid, s, note=None, d=None):
    """The presenter image on a fresh flow (the voice joins it at the next stage)."""
    from .. import eleven
    con, p = _con(), P.load(pid, d)
    prop = P.read_artifact(pid, "proposal", d) or {}
    src, cost, files = _source(p), 0.0, []
    acc = p.get("eleven_account")
    if src == "generate":
        prompt = (prop.get("presenter") or "a friendly presenter, head and shoulders, plain studio background") + \
                 ". Photorealistic, front-facing, looking into the lens, mouth closed, even soft light, no text."
        if note:
            prompt += f" {note}"
        path, cost, flow, node = eleven.image(con, prompt, remaining_budget(pid, d), acc, p.get("aspect", "9:16"),
                                              model=PORTRAIT_MODEL)
    else:
        flow = eleven.new_flow(acc, name=f"avatar {pid}")
        if src == "upload":
            path = _portrait(p)
            node = eleven.upload(path, flow, acc)
        else:
            path, node = None, eleven.asset_node(p["presenter_asset"], flow, "image", acc)
    if path:
        out = P.path(pid, "plates", "presenter" + os.path.splitext(path)[1].lower(), d=d)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copy2(path, out)
        files.append(_rel(out))
    summary = {"tr": "Sunucu hazır. Yüz önden, ağız kapalı ve iyi aydınlık mı? Değilse not yaz.",
               "en": "The presenter is ready. Front-facing, mouth closed, well lit? If not, write a note."}[_ui(p)]
    art = {"concept": prop.get("presenter") or "", "plates": files, "presenter": {"flow": flow, "node": node, "source": src},
           "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"credits": round(cost)}}


def _ass_time(t):
    h, rest = divmod(max(0.0, t), 3600)
    m, s = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def captions(words, size=(1080, 1920), per=4):
    """An ASS subtitle file body: the spoken words in chunks of `per`, low on the frame, bold with an outline."""
    w, h = size
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginV
Style: Cap,Montserrat,{round(h * 0.034)},&H00FFFFFF,&H00000000,&H64000000,-1,6,0,2,{round(h * 0.2)}

[Events]
Format: Layer, Start, End, Style, Text
"""
    rows = []
    for i in range(0, len(words), per):
        part = words[i:i + per]
        end = words[i + per][1] if i + per < len(words) else part[-1][2] + 0.4
        text = " ".join(str(x[0]) for x in part).replace("{", "(").replace("}", ")")
        rows.append(f"Dialogue: 0,{_ass_time(part[0][1])},{_ass_time(end)},Cap,{text}")
    return head + "\n".join(rows) + "\n"


def _burn(src, words, out, aspect="9:16", final=False):
    """Fit the talking video to the canvas, burn the captions in, level the voice (-14 LUFS)."""
    from ..formats import ASPECTS
    w, h = ASPECTS.get(aspect, (1080, 1920))
    ass = os.path.splitext(out)[0] + ".ass"
    open(ass, "w").write(captions(words, (w, h)))
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,"
          f"subtitles='{ass.replace(chr(39), '')}'")
    cmd = [FFMPEG, "-y", "-v", "error", "-i", src, "-vf", vf, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
           "-c:v", "libx264", "-preset", "medium" if final else "veryfast", "-crf", "18" if final else "26",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    return out


def assets(pid, s, note=None, d=None):
    """Voice -> word timing -> voice on the presenter's flow -> the talking video -> a captioned preview."""
    from .. import accounts, eleven, formats, productions
    con, p = _con(), P.load(pid, d)
    script = P.read_artifact(pid, "script", d) or {}
    plate = (P.read_artifact(pid, "plates", d) or {}).get("presenter") or {}
    if not plate.get("node"):
        raise P.GateError("no presenter yet; redo the scene plan")
    lines = script.get("lines") or []
    lang = p.get("video_lang", "tr")
    acc = p.get("eleven_account") or accounts.default_eleven(p.get("created_by"))
    voice_id = p.get("voice_id") or formats.default_voice(lang, acc)
    vpath, vcost = eleven.tts(con, " ".join(lines), voice_id, formats.VOICE_MODEL, approved=remaining_budget(pid, d),
                              account=acc)
    times, dur, words = productions.align(vpath, lines, lang)
    audio = eleven.upload(vpath, plate["flow"], acc)
    prompt = "The presenter speaks to camera, natural head movement and blinking, steady framing."
    if note:
        prompt += f" {note}"
    apath, acost = eleven.avatar(con, plate["node"], audio, plate["flow"], round(dur + 0.5, 1),
                                 max(0, remaining_budget(pid, d) - round(vcost)), acc, p.get("aspect", "9:16"),
                                 _model(p), prompt)
    raw = P.path(pid, "renders", "avatar.mp4", d=d)
    os.makedirs(os.path.dirname(raw), exist_ok=True)
    shutil.copy2(apath, raw)
    prev = _burn(raw, words, P.path(pid, "renders", "preview.mp4", d=d), p.get("aspect", "9:16"))
    total = round(vcost + acost)
    summary = {"tr": f"Sunucu konuştu ({dur:.0f} sn, {total} kredi). Dudaklar sesle uyuyor mu? Hareket için not yaz "
                     f"(yalnız video yeniden üretilir, kredi harcar).",
               "en": f"The presenter spoke ({dur:.0f} s, {total} credits). Do the lips match? Write a note on the "
                     f"movement (only the video is redone; spends credits)."}[_ui(p)]
    art = {"voice": {"file": _rel(vpath), "voice_id": voice_id, "duration": dur, "credits": round(vcost),
                     "line_times": times, "words": [list(w) for w in words]},
           "avatar": {"file": _rel(raw), "model": _model(p), "credits": round(acost)}, "music": None,
           "preview": _rel(prev), "summary": summary}
    return {"artifact": art, "summary": summary, "cost": {"credits": total}}


def edit(pid, s, note=None, d=None):
    P.decision(pid, "edit", "captions in 4-word chunks, voice levelled to -14 LUFS", d=d)
    return {"artifact": {"sound": {"level": "full"}, "summary": "", "note": note}, "summary": ""}


def compose(pid, s, note=None, d=None):
    from .. import qa, thumbs
    p = P.load(pid, d)
    a = P.read_artifact(pid, "assets", d) or {}
    if not (a.get("avatar") or {}).get("file"):
        raise P.GateError("no avatar video yet")
    out = _burn(os.path.join(ROOT, a["avatar"]["file"]), a["voice"]["words"], P.path(pid, "renders", "final.mp4", d=d),
                p.get("aspect", "9:16"), final=True)
    tech = qa.technical(out, a["voice"]["duration"])
    title = (P.read_artifact(pid, "script", d) or {}).get("title") or p["title"]
    covers = thumbs.make(out, P.path(pid, "renders", d=d), title, p.get("aspect", "9:16"), lang=p.get("video_lang", "tr"))
    probs = tech.get("problems", [])
    summary = ({"tr": "Final hazır; teknik kontrol temiz.", "en": "Final ready; technical checks clean."} if not probs else
               {"tr": f"Final hazır; {len(probs)} teknik bulgu var.", "en": f"Final ready; {len(probs)} technical findings."})[_ui(p)]
    art = {"final": _rel(out), "qa": {"technical": tech, "pass": not probs}, "covers": [_rel(c) for c in covers],
           "summary": summary}
    return {"artifact": art, "summary": summary}


def publish(pid, s, note=None, d=None):
    p = P.load(pid, d)
    c = ((P.read_artifact(pid, "proposal", d) or {}).get("concepts") or [{}])[0]
    post = c.get("post") or {}
    tags = post.get("hashtags") or []
    tags = tags.split() if isinstance(tags, str) else [t if t.startswith("#") else "#" + t for t in tags]
    notes = {"tr": "Yapay zekâ ile üretilmiş bir sunucu: TikTok'ta \"Yapay zekâ ile oluşturuldu\" etiketini aç.",
             "en": "An AI-generated presenter: turn on TikTok's \"AI-generated content\" label."}[_ui(p)]
    summary = {"tr": "Açıklama ve etiketler hazır; yapay zekâ etiketini unutma.",
               "en": "Caption and hashtags ready; remember the AI label."}[_ui(p)]
    art = {"caption": post.get("caption") or c.get("title") or p["title"], "hashtags": tags or ["#ai"], "notes": notes,
           "summary": summary}
    return {"artifact": art, "summary": summary}
