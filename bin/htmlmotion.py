"""Renderer for Opus-designed explainers (engine "html"): the scenes are HTML/CSS/GSAP written per topic by
factory/motiondesign.py, shown in motion/templates/explainer_shell.html and captured frame by frame by
motion/render.mjs (headless Chromium). Same contract as bin/explainer.py: main(spec_path, preview, stills).
Spec (compiled by factory/explainer.compile_spec): the explainer spec plus engine "html", design (path), line_times,
optional captions ({mode: chunk|word, pos: low|mid, keys: {word: key|danger}}) and sound ({sfx: bool, level}).

Sound: scenes declare their own sound effects and music moments next to the animation (FX.sfx / FX.music in fxlib.js);
render.mjs --cues hands them back after setup and factory/audiofx.mix puts each sound on its frame (never over a word),
cuts the music out and back in on the story events and lines the track's drop up with FX.music("drop", t).
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from factory.config import ROOT, FFMPEG  # noqa: E402
MOTION = os.path.join(ROOT, "motion")
SHELL = "/motion/templates/explainer_shell.html"
ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}


def make_bundle(spec, design):
    """Design (static: css/html/js per scene) + this spec's timing -> the JSON the shell loads."""
    vs = spec.get("voice_start", 0)
    words = [{"w": w, "s": round(s + vs, 3), "e": round(e + vs, 3)} for w, s, e in spec["words"]]
    lt = spec.get("line_times") or []
    scenes = []
    for sc in spec["scenes"]:
        d = design["scenes"].get(sc["id"]) or {}
        a, b = sc["lines"]
        scenes.append({"id": sc["id"], "start": sc["start"], "end": sc["end"], "hide_captions": sc.get("hide_captions", False),
                       "html": d.get("html", ""), "css": d.get("css", ""), "js": d.get("js", ""),
                       "lines_t": [{"start": round(x["start"], 3), "end": round(x["end"], 3)} for x in lt[a:b + 1]]})
    w, h = ASPECTS.get(spec.get("aspect", "9:16"), ASPECTS["9:16"])
    return {"palette": design["meta"].get("palette") or {}, "global_css": design.get("global_css", ""), "words": words,
            "scenes": scenes, "duration": spec["duration"], "w": w, "h": h, "captions": spec.get("captions") or {},
            "lang": spec.get("lang", "en"),   # sets <html lang>: CSS uppercase then maps i -> İ in Turkish
            **beat_grid(spec)}


def beat_grid(spec):
    """The music's tempo and where its beats fall in the video, for FX.B(k) (kinetic type on the beat): the drop lands
    on the drop line when the spec asks for it (audiofx.place_music), so beat 0 = the drop; otherwise the track starts
    at 0 and beat 0 = its first beat. Measured once per music file (a .beats.json next to it)."""
    mu = spec.get("music") or {}
    path = os.path.join(ROOT, mu["file"]) if mu.get("file") else None
    if not path or not os.path.exists(path):
        return {}
    side = path + ".beats.json"
    try:
        g = json.load(open(side))
    except (OSError, ValueError):
        try:
            from factory import beats
            b = beats.beats(path)
            g = {"bpm": b["bpm"], "first": b["beats"][0] if b["beats"] else 0.0}
            json.dump(g, open(side, "w"))
        except Exception:
            return {}
    if not g.get("bpm"):
        return {}
    return {"bpm": g["bpm"], "beat0": round(mu["drop_at"] if mu.get("drop_at") is not None else g.get("first", 0.0), 3)}


def write_bundle(spec, design):
    out = os.path.join(ROOT, "work", "auto", spec["name"])
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "bundle.json")
    json.dump(make_bundle(spec, design), open(path, "w"), ensure_ascii=False)
    return path


def _node(page_hash_bundle, out, dur, extra, fps=30):
    page = os.path.join(MOTION, "templates", "explainer_shell.html")
    rel = "/" + os.path.relpath(page_hash_bundle, ROOT)
    try:
        b = json.load(open(page_hash_bundle))
        w, h = b.get("w", 1080), b.get("h", 1920)
    except (OSError, ValueError):
        w, h = 1080, 1920
    cmd = ["node", os.path.join(MOTION, "render.mjs"), f"{page}#b={rel}", out, str(dur), str(fps), str(w), str(h), *extra]
    return subprocess.run(cmd, cwd=MOTION, capture_output=True, text=True)


def shots(bundle_path, times, outdir, lint=False):
    """PNGs of the given moments (free, ~seconds) + the page's JS errors (+ the lint file of text boxes if lint)."""
    extra = ["--opaque", "--shots=" + ",".join(str(t) for t in times)]
    lint_path = os.path.join(os.path.dirname(os.path.abspath(bundle_path)), "lint.json") if lint else None
    if lint_path:
        extra.append("--lint=" + lint_path)
    r = _node(bundle_path, os.path.abspath(outdir), 1, extra)
    errs = sorted({ln for ln in (r.stderr or "").splitlines() if "error" in ln.lower()})
    paths = [os.path.join(outdir, f) for f in sorted(os.listdir(outdir)) if f.startswith("shot_")] if os.path.isdir(outdir) else []
    return (paths, errs[:12], lint_path) if lint else (paths, errs[:12])


def readcheck(bundle_path):
    """Visible texts every 0.2 s + the timeline's motion lint (render.mjs --readcheck) -> dict."""
    out = os.path.join(os.path.dirname(os.path.abspath(bundle_path)), "readcheck.json")
    try:
        dur = json.load(open(bundle_path)).get("duration", 30)
    except (OSError, ValueError):
        dur = 30
    _node(bundle_path, "/dev/null", round(dur, 2), ["--opaque", "--readcheck=" + out])
    return json.load(open(out))


def post_vf(fx, preview=False):
    """Film texture after capture (a film style's post): bloom, grain, flicker, gate weave, vignette, mono / sepia. Done
    in ffmpeg because grain or glow drawn in the page makes every frame slow and incompressible. '' = nothing to do."""
    fx = fx or {}
    vf = []
    if fx.get("bloom"):      # the bright parts glow: a blurred copy of the highlights screened back on (kinetic hits, neon)
        a = min(1.0, float(fx["bloom"]))
        vf.append(f"split[bl_a][bl_b];[bl_b]curves=all='0/0 0.62/0 1/1',gblur=sigma={10 if preview else 22}[bl_g];"
                  f"[bl_a][bl_g]blend=all_mode=screen:all_opacity={0.25 + 0.5 * a:.2f}")
    if fx.get("mono"):
        vf.append("hue=s=0")
    if fx.get("sepia"):
        vf.append("colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131")
    if fx.get("weave"):      # the frame drifts a pixel or two like film in a gate
        vf.append("scale=iw*1.01:ih*1.01,crop=iw/1.01:ih/1.01:(iw-ow)/2+1.5*sin(t*11):(ih-oh)/2+1.2*sin(t*7.3)")
    if fx.get("flicker"):
        vf.append("eq=brightness='0.025*sin(2*PI*t*9)+0.015*sin(2*PI*t*3.7)':eval=frame")
    if fx.get("vignette"):
        vf.append(f"vignette=angle={0.35 + 0.5 * min(1.0, float(fx['vignette'])):.2f}")
    if fx.get("grain"):
        vf.append(f"noise=alls={max(2, int(float(fx['grain']) * 22))}:allf=t")
    return ",".join(vf)


def sound_plan(cues_path, spec, total):
    """Scene cues -> (sfx cues, music settings) for audiofx.mix. Music events: "cut" silences the track until the next
    "back" (or the end); "drop" is where the track's drop should land."""
    from factory import sfx
    try:
        c = json.load(open(cues_path))
    except (OSError, ValueError):
        c = {}
    snd = spec.get("sound") or {}
    cues = sfx.clean_cues(c.get("sfx"), total, snd.get("level", "full")) if snd.get("sfx", True) else []
    mutes, drop, open_at = [], None, None
    for ev in sorted(c.get("music") or [], key=lambda e: e.get("t", 0)):
        a, t = ev.get("action"), float(ev.get("t", 0))
        if a == "cut" and open_at is None:
            open_at = t
        elif a == "back" and open_at is not None:
            mutes.append([open_at, t])
            open_at = None
        elif a == "drop" and drop is None:
            drop = t
    if open_at is not None:
        mutes.append([open_at, total + 1])
    return cues, mutes, drop


def main(path, preview=False, stills=None):
    spec = json.load(open(path))
    design = json.load(open(os.path.join(ROOT, spec["design"])))
    name, total = spec["name"], spec["duration"]
    bundle = write_bundle(spec, design)
    if stills:
        out = os.path.join(ROOT, "work", "explainer", name)
        os.makedirs(out, exist_ok=True)
        return shots(bundle, stills, out)[0]
    out_dir = os.path.join(ROOT, "work", "preview") if preview else os.path.join(ROOT, "out", name)
    os.makedirs(out_dir, exist_ok=True)
    silent = os.path.join(ROOT, "work", "auto", name, "silent.mp4")
    cues_path = os.path.join(ROOT, "work", "auto", name, "cues.json")
    blur = [] if preview or not spec.get("motion_blur") else [f"--blur={int(spec['motion_blur'])}"]   # real sub-frame blur, final only
    r = _node(bundle, silent, round(total, 3), (["--opaque", "--scale=0.5"] if preview else ["--opaque"]) + blur + ["--cues=" + cues_path],
              15 if preview else 30)
    if r.returncode or not os.path.exists(silent):
        raise RuntimeError("html render failed: " + (r.stderr or "")[-400:])
    dst = os.path.join(out_dir, f"{name}.mp4")
    from factory import audiofx
    cues, mutes, drop = sound_plan(cues_path, spec, total)
    voice = dict(spec["voice"], file=os.path.join(ROOT, spec["voice"]["file"])) if spec.get("voice") else None
    music = None
    if spec.get("music"):
        mu = spec["music"]
        music = {"file": os.path.join(ROOT, mu["file"]), "db": mu.get("db", -20), "mutes": mutes + (mu.get("mutes") or []),
                 "seek": mu.get("seek", 0), "delay": mu.get("delay", 0), "drop_t": mu.get("drop_t")}
        if drop is not None or mu.get("drop_at") is not None:
            music = audiofx.place_music(music, drop if drop is not None else mu["drop_at"])
    vs = spec.get("voice_start", 0)
    words = spec.get("words") or []        # relative to the voice file, which starts at voice_start
    audiofx.save_placed(name, cues, words, vs)
    mixed = os.path.join(ROOT, "work", "auto", name, "mixed.mp4")
    audiofx.mix(silent, mixed, total, voice=voice, music=music, cues=cues, words=words, voice_offset=vs,
                chain=spec.get("voice_chain"))
    vpost = post_vf(spec.get("post_fx"), preview)
    vcodec = ["-vf", vpost, "-c:v", "libx264", "-preset", "veryfast" if preview else "medium", "-crf", "24" if preview else "17",
              "-tune", "grain", "-pix_fmt", "yuv420p"] if vpost else ["-c:v", "copy"]
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", mixed, *vcodec, "-af",
                    f"loudnorm=I=-14:TP=-1.5:LRA=11,atrim=0:{total:.3f}", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-t", f"{total:.3f}", "-movflags", "+faststart", dst] if (voice or music or cues) else
                   [FFMPEG, "-y", "-v", "error", "-i", mixed, *vcodec, "-an", dst], check=True)
    print(f"sound: {len(cues)} effects, {len(mutes)} music cut(s)" + (f", drop on {drop:.2f}s" if drop is not None else ""), flush=True)
    if spec.get("post") and not preview:
        sys.path.insert(0, os.path.join(ROOT, "bin"))
        import cinecut
        cinecut.write_caption(os.path.join(out_dir, "caption.txt"), spec["post"])
    print(f"{dst}  ({total:.2f}s)")
    return dst, total


if __name__ == "__main__":
    args = sys.argv[1:]
    stills = None
    if "--still" in args:
        i = args.index("--still")
        stills = [float(x) for x in args[i + 1:]]
        args = args[:i]
    main(args[0], preview="--preview" in args, stills=stills)
