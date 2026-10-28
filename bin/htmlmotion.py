"""Renderer for Opus-designed explainers (engine "html"): the scenes are HTML/CSS/GSAP written per topic by
factory/motiondesign.py, shown in motion/templates/explainer_shell.html and captured frame by frame by
motion/render.mjs (headless Chromium). Same contract as bin/explainer.py: main(spec_path, preview, stills).
Spec (compiled by factory/explainer.compile_spec): the explainer spec plus engine "html", design (path), line_times.
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
            "scenes": scenes, "duration": spec["duration"], "w": w, "h": h}


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


def shots(bundle_path, times, outdir):
    """PNGs of the given moments (free, ~seconds) + the page's JS errors."""
    r = _node(bundle_path, outdir, 1, ["--opaque", "--shots=" + ",".join(str(t) for t in times)])
    errs = sorted({ln for ln in (r.stderr or "").splitlines() if "error" in ln.lower()})
    paths = [os.path.join(outdir, f) for f in sorted(os.listdir(outdir)) if f.startswith("shot_")] if os.path.isdir(outdir) else []
    return paths, errs[:12]


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
    r = _node(bundle, silent, round(total, 3), ["--opaque", "--scale=0.5"] if preview else ["--opaque"], 15 if preview else 30)
    if r.returncode or not os.path.exists(silent):
        raise RuntimeError("html render failed: " + (r.stderr or "")[-400:])
    dst = os.path.join(out_dir, f"{name}.mp4")
    cmd, inputs, chain, mix = [FFMPEG, "-y", "-v", "error", "-i", silent], 1, [], None
    if spec.get("voice"):
        ms = int(spec["voice"].get("start", 0) * 1000)
        cmd += ["-i", os.path.join(ROOT, spec["voice"]["file"])]
        chain.append(f"[{inputs}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms},apad,atrim=0:{total:.3f}[vo]")
        mix, inputs = "[vo]", inputs + 1
    if spec.get("music"):
        mu = spec["music"]
        cmd += ["-i", os.path.join(ROOT, mu["file"])]
        chain.append(f"[{inputs}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={mu.get('db', -20)}dB,apad,"
                     f"atrim=0:{total:.3f},afade=t=in:d=0.5,afade=t=out:st={max(0, total - 1.5):.3f}:d=1.5[mus]")
        chain.append((f"{mix}[mus]amix=inputs=2:normalize=0[mx]" if mix else "[mus]anull[mx]"))
        mix = "[mx]"
    if mix:
        chain.append(f"{mix}loudnorm=I=-14:TP=-1.5:LRA=11,atrim=0:{total:.3f}[a]")
        cmd += ["-filter_complex", ";".join(chain), "-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    cmd += ["-c:v", "copy", "-t", f"{total:.3f}", "-movflags", "+faststart", dst]
    subprocess.run(cmd, check=True)
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
