"""Export package (t505): a finished video handed over for other tools, free (no credits), as a background job.

`build(pid, items)` writes renders/export-<stamp>/ and a zip of it:
  video.mp4      the final, always
  subtitles.srt  short cues (<=42 characters) from the word timing: the voice alignment for the HTML engine's lines,
                 a local whisper pass on the final for the others; none for a silent video
  stems/         mix.wav for every line; voice.wav, music.wav, sfx.wav on the video's timeline for the HTML engine
  frames/        one PNG per scene (the scene's settled moment) from the final, or six spread over a video without scenes
  preview.gif    the first seconds as a small looping GIF
  timeline.fcpxml, timeline.edl
                 the video cut at its scenes for Final Cut / Resolve / Premiere: FCPXML with scene markers and the
                 stems as connected audio, a CMX 3600 EDL with one event per scene (media referenced next to the file)
  alpha.mov      the graphics on a transparent background (ProRes 4444, HTML engine only, takes a full render; off by
                 default)
"""
import glob, json, os, re, shutil, subprocess, time, zipfile
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

from .config import FFMPEG, FFPROBE, ROOT
from .hat import manifest, project as P

ITEMS = ("srt", "stems", "frames", "gif", "timeline", "alpha")
DEFAULT = ("srt", "stems", "frames", "gif", "timeline")
FPS = 30
SRT_CHARS = 42
GIF_SECONDS = 6

NAMES = {
    "srt": {"tr": "Altyazı (SRT)", "en": "Subtitles (SRT)"},
    "stems": {"tr": "Ses kanalları (stem)", "en": "Audio stems"},
    "frames": {"tr": "Sahne kareleri (PNG)", "en": "Scene frames (PNG)"},
    "gif": {"tr": "Önizleme GIF'i", "en": "Preview GIF"},
    "timeline": {"tr": "Kurgu dosyası (FCPXML, EDL)", "en": "Edit timeline (FCPXML, EDL)"},
    "alpha": {"tr": "Şeffaf video (ProRes 4444)", "en": "Transparent video (ProRes 4444)"},
}


class ExportError(ValueError):
    pass


def _abs(rel):
    return rel if os.path.isabs(rel) else os.path.join(ROOT, rel)


def final(pid, d=None):
    """The newest stage artifact's final video (absolute path) or None."""
    for s, _ in reversed(P.stages(pid, d)):
        art = P.read_artifact(pid, s.get("artifact") or s["id"], d) or {}
        if art.get("final") and os.path.exists(_abs(art["final"])):
            return _abs(art["final"])
    return None


def html_engine(pid, d=None):
    """True when the line renders HTML scenes with factory.hat.explainer (scene timing, stems, alpha are known)."""
    line = manifest.get(P.load(pid, d)["line"])
    return (any(str(s.get("call", "")).startswith("factory.hat.explainer:") for s in line["stages"])
            and bool(P.read_artifact(pid, "scene_plan", d)))


def available(pid, d=None):
    """The items this project can export."""
    return [i for i in ITEMS if i != "alpha" or html_engine(pid, d)]


def duration(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ---------------------------------------------------------------- timing

def scenes(pid, d=None):
    """[{id, start, end}] of the HTML engine's scenes, else []."""
    if not html_engine(pid, d):
        return []
    from .hat import explainer
    return [{"id": s["id"], "start": s["start"], "end": s["end"]} for s in explainer.spec(pid, None, d)["scenes"]]


def words(pid, video, d=None):
    """[(word, start, end)] on the video's timeline, or [] for a silent video."""
    if html_engine(pid, d):
        from .hat import explainer
        if not explainer.narrated(P.read_artifact(pid, "script", d)):
            return []
        sp = explainer.spec(pid, None, d)
        vs = sp["voice_start"]
        return [(str(w[0]), float(w[1]) + vs, float(w[2]) + vs) for w in sp["words"]]
    from . import talk
    p = P.load(pid, d)
    return [(w[0], w[1], w[2]) for w in talk.transcribe(video, p.get("video_lang", "tr")) if str(w[0]).strip()]


def cues(ws, chars=SRT_CHARS, gap=0.6, most=4.0):
    """Words -> subtitle cues [(start, end, text)]: break at a sentence end, a pause, the length or the time limit."""
    out, cur = [], []
    for w in ws:
        if cur and (len(" ".join(x[0] for x in cur + [w])) > chars or w[1] - cur[-1][2] > gap or w[2] - cur[0][1] > most
                    or re.search(r"[.!?…]$", cur[-1][0])):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    res = []
    for i, c in enumerate(out):
        a, b = c[0][1], max(c[-1][2], c[0][1] + 0.8)
        if i + 1 < len(out):
            b = min(b, out[i + 1][0][1] - 0.02)
        res.append((round(a, 3), round(max(b, a + 0.2), 3), " ".join(x[0] for x in c)))
    return res


def _ts(t, sep=","):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def srt(cs):
    return "".join(f"{i}\n{_ts(a)} --> {_ts(b)}\n{text}\n\n" for i, (a, b, text) in enumerate(cs, 1))


# ---------------------------------------------------------------- timelines

def _tc(t, fps=FPS):
    f = int(round(t * fps))
    return f"{f // (3600 * fps):02d}:{f // (60 * fps) % 60:02d}:{f // fps % 60:02d}:{f % fps:02d}"


def edl(title, scs, total, media="video.mp4"):
    """CMX 3600, one event per scene: the final cut at its scene boundaries (record = source)."""
    scs = scs or [{"id": "video", "start": 0.0, "end": total}]
    rows = [f"TITLE: {re.sub(r'[^A-Za-z0-9 _.-]', '', title)[:60] or 'video'}", "FCM: NON-DROP FRAME", ""]
    for i, s in enumerate(scs, 1):
        a, b = _tc(s["start"]), _tc(s["end"])
        rows += [f"{i:03d}  AX       V     C        {a} {b} {a} {b}", f"* FROM CLIP NAME: {media}", f"* COMMENT: {s['id']}"]
        if i < len(scs):
            rows.append("")
    return "\n".join(rows) + "\n"


def _r(t, fps=FPS):
    return f"{int(round(t * fps))}/{fps}s"


def fcpxml(title, folder, size, total, scs, stems=()):
    """FCPXML 1.10: the final on the spine with a marker per scene, the stems as connected audio under it. Media are
    referenced by absolute file URLs of the export folder (relink if the folder moves)."""
    w, h = size
    url = lambda name: "file://" + quote(os.path.join(os.path.abspath(folder), name))
    res = [f'<format id="r1" frameDuration="1/{FPS}s" width="{w}" height="{h}"/>',
           f'<asset id="r2" name="video" start="0s" duration="{_r(total)}" hasVideo="1" hasAudio="1" format="r1" '
           f'audioSources="1" audioChannels="2"><media-rep kind="original-media" src={quoteattr(url("video.mp4"))}/></asset>']
    conn = []
    for k, name in enumerate(stems, 3):
        res.append(f'<asset id="r{k}" name={quoteattr(name)} start="0s" duration="{_r(total)}" hasAudio="1" audioSources="1" '
                   f'audioChannels="2"><media-rep kind="original-media" src={quoteattr(url("stems/" + name + ".wav"))}/></asset>')
        role = {"voice": "dialogue", "music": "music"}.get(name, "effects")
        conn.append(f'<asset-clip ref="r{k}" lane="-{k - 2}" offset="0s" name={quoteattr(name)} duration="{_r(total)}" '
                    f'start="0s" audioRole="{role}"/>')
    marks = [f'<marker start="{_r(s["start"])}" duration="1/{FPS}s" value={quoteattr(s["id"])}/>' for s in scs]
    t = escape(title)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.10">\n<resources>\n'
            + "\n".join(res) + f'\n</resources>\n<library>\n<event name="{t}">\n<project name="{t}">\n'
            f'<sequence format="r1" duration="{_r(total)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">\n'
            f'<spine>\n<asset-clip ref="r2" offset="0s" name="video" duration="{_r(total)}" start="0s" format="r1" tcFormat="NDF">\n'
            + "\n".join(marks + conn) + "\n</asset-clip>\n</spine>\n</sequence>\n</project>\n</event>\n</library>\n</fcpxml>\n")


# ---------------------------------------------------------------- the package

def _frames(video, times, out):
    os.makedirs(out, exist_ok=True)
    files = []
    for i, (name, t) in enumerate(times, 1):
        f = os.path.join(out, f"{i:02d}-{re.sub(r'[^A-Za-z0-9_-]', '_', name)}.png")
        subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", f], check=True)
        files.append(f)
    return files


def _gif(video, out, wide):
    w = 480 if wide else 360
    subprocess.run([FFMPEG, "-y", "-v", "error", "-t", str(GIF_SECONDS), "-i", video, "-filter_complex",
                    f"fps=12,scale={w}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer",
                    "-loop", "0", out], check=True)
    return out


def build(pid, items=DEFAULT, d=None, log=print):
    """Write the package; returns {folder, zip, files, notes}."""
    items = [i for i in items if i in available(pid, d)]
    video = final(pid, d)
    if not video:
        raise ExportError("no final video yet")
    p = P.load(pid, d)
    out = P.path(pid, "renders", f"export-{time.strftime('%Y%m%d-%H%M%S')}", d=d)
    os.makedirs(out, exist_ok=True)
    shutil.copy(video, os.path.join(out, "video.mp4"))
    total = duration(video)
    scs = scenes(pid, d)
    notes, stem_names = [], []
    aspect = p.get("aspect") or "9:16"
    size = (1920, 1080) if aspect == "16:9" else (1080, 1920)
    if "srt" in items:
        log("subtitles")
        cs = cues(words(pid, video, d))
        if cs:
            open(os.path.join(out, "subtitles.srt"), "w", encoding="utf-8").write(srt(cs))
        else:
            notes.append("silent")
    if "stems" in items:
        log("stems")
        sd = os.path.join(out, "stems")
        os.makedirs(sd, exist_ok=True)
        subprocess.run([FFMPEG, "-y", "-v", "error", "-i", video, "-vn", "-c:a", "pcm_s16le", "-ar", "48000",
                        os.path.join(sd, "mix.wav")], check=False)
        if html_engine(pid, d):
            from .hat import explainer
            sp = explainer._render_spec(pid, P.read_artifact(pid, "scene_plan", d), d, True)
            made = explainer._htmlmotion().stems(sp, P.path(pid, "work", "final", "cues.json", d=d), sd)
            stem_names = [n for n in ("voice", "music", "sfx") if n in made]
    if "frames" in items:
        log("frames")
        times = ([(s["id"], s["start"] + (s["end"] - s["start"]) * 0.7) for s in scs] if scs else
                 [(f"t{i + 1}", total * (i + 0.5) / 6) for i in range(6)])
        _frames(video, [(n, min(t, max(0.0, total - 0.05))) for n, t in times], os.path.join(out, "frames"))
    if "gif" in items:
        log("gif")
        _gif(video, os.path.join(out, "preview.gif"), aspect == "16:9")
    if "timeline" in items:
        log("timeline")
        title = p.get("title") or pid
        open(os.path.join(out, "timeline.edl"), "w", encoding="utf-8").write(edl(title, scs, total))
        open(os.path.join(out, "timeline.fcpxml"), "w", encoding="utf-8").write(fcpxml(title, out, size, total, scs, stem_names))
    if "alpha" in items:
        log("alpha (a full render)")
        from .hat import explainer
        sp = explainer._render_spec(pid, P.read_artifact(pid, "scene_plan", d), d, True)
        b = os.path.join(out, ".bundle.json")
        json.dump(explainer._htmlmotion().make_bundle(sp, explainer.design(P.read_artifact(pid, "scene_plan", d))),
                  open(b, "w", encoding="utf-8"), ensure_ascii=False)
        explainer._htmlmotion().alpha(b, os.path.join(out, "alpha.mov"), sp["duration"])
        os.remove(b)
    files = sorted(os.path.relpath(f, out) for f in glob.glob(os.path.join(out, "**", "*"), recursive=True) if os.path.isfile(f))
    z = out + ".zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(os.path.join(out, f), os.path.join(os.path.basename(out), f))
    meta = {"at": P.now(), "items": items, "files": files, "notes": notes, "zip": os.path.basename(z)}
    json.dump(meta, open(os.path.join(out, ".export.json"), "w", encoding="utf-8"), ensure_ascii=False)
    P.event(pid, "export", d=d, folder=os.path.basename(out), items=items)
    return {"folder": out, "zip": z, "files": files, "notes": notes}


def exports(pid, d=None):
    """Past packages, newest first: [{folder, zip, at, items, files, notes, size}]."""
    out = []
    for f in sorted(glob.glob(P.path(pid, "renders", "export-*", ".export.json", d=d)), reverse=True):
        m = json.load(open(f, encoding="utf-8"))
        folder = os.path.dirname(f)
        z = os.path.join(os.path.dirname(folder), m.get("zip", ""))
        out.append(dict(m, folder=folder, zip=z if os.path.exists(z) else None,
                        size=os.path.getsize(z) if os.path.exists(z) else 0))
    return out
