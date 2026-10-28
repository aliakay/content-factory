#!/usr/bin/env python3
"""Talking-head renderer (engine "talk"): the creator's raw video -> jump-cut, reframed, captioned short.

Usage: talkcut.py spec.json [--preview]   -> out/<name>/<name>.mp4 + caption.txt (preview: work/preview/<name>.mp4)

Spec (compiled by factory/talk.compile_spec):
  source     raw video (never modified)            src_size [w, h]           fps 30 | 60
  segments   [{"in": s, "frames": n, "zoom": 1.0-1.25, "cx": 0..1, "cy": 0..1}]  picture AND audio of each piece are
             exactly n / fps seconds from the same in-point, so lip sync never drifts over many jump cuts
  words      [[word, start, end]] in output time (captions)      keys {word: key|danger}    accent "#rrggbb"
  hook       {text, accent, end, behind}   behind = between the footage and the speaker (subject matte, rembg) when
             available, else on top
  broll      [{start, end, kind, text, accent, label, items}]   code-built cutaways over the picture, voice continues
  cues       sound effects [{t, kind, gain_db}]   music {file, auto, gap}   voice_chain "room" | "clean"
  grade      natural | film | golden | moody | vivid   post {caption, hashtags, ...}
"""
import json, os, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from factory.config import ROOT, FFMPEG  # noqa: E402
from factory import audiofx  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "bin"))

ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}


def run(args):
    subprocess.run([FFMPEG, "-v", "error", "-y", *args], check=True)


def crop_box(src_w, src_h, W, H, zoom, cx, cy):
    """The source rectangle for a cover crop to W:H, zoomed in by `zoom` around the face (kept at ~40 % height)."""
    if src_w / src_h > W / H:
        ch, cw = src_h, src_h * W / H
    else:
        cw, ch = src_w, src_w * H / W
    cw, ch = cw / zoom, ch / zoom
    x = min(max(0, cx * src_w - cw / 2), src_w - cw)
    y = min(max(0, cy * src_h - ch * 0.4), src_h - ch)
    ev = lambda v: int(v) // 2 * 2  # noqa: E731
    return ev(cw), ev(ch), ev(x), ev(y)


def grade_filter(name):
    try:
        import stylecut
        return stylecut.GRADES.get(name or "film", "")
    except Exception:
        return ""


def pieces(spec, tmp, size, preview):
    src = os.path.join(ROOT, spec["source"])
    sw, sh = spec["src_size"]
    W, H = size
    fps = spec["fps"]
    grade = grade_filter(spec.get("grade"))
    enc = ["-preset", "veryfast", "-crf", "26"] if preview else ["-preset", "medium", "-crf", "16"]
    files = []
    for i, sg in enumerate(spec["segments"]):
        cw, ch, x, y = crop_box(sw, sh, *ASPECTS.get(spec.get("aspect", "9:16"), (1080, 1920)), sg["zoom"], sg["cx"], sg["cy"])
        vf = f"crop={cw}:{ch}:{x}:{y},scale={W}:{H}:flags=lanczos,fps={fps},setsar=1" + (f",{grade}" if grade else "")
        out = os.path.join(tmp, f"p{i:04d}.mp4")
        run(["-ss", f"{sg['in']:.4f}", "-i", src, "-frames:v", str(sg["frames"]), "-vf", vf, "-an", "-c:v", "libx264", *enc,
             "-pix_fmt", "yuv420p", "-video_track_timescale", str(fps * 1000), out])
        files.append(out)
    lst = os.path.join(tmp, "pieces.txt")
    open(lst, "w").write("".join(f"file '{f}'\n" for f in files))
    base = os.path.join(tmp, "base.mp4")
    run(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", base])
    ranges = [(sg["in"], sg["in"] + sg["frames"] / fps) for sg in spec["segments"]]
    voice = audiofx.concat_audio(src, ranges, os.path.join(tmp, "voice.wav"))
    return base, voice


def overlay(spec, tmp, size, total, layer, preview):
    W, H = size
    data = {"w": W, "h": H, "words": spec.get("words") or [], "keys": spec.get("keys") or {}, "accent": spec.get("accent"),
            "energy": (spec.get("captions") or {}).get("energy", "talk"), "hook": spec.get("hook") or {},
            "broll": spec.get("broll") or [], "layer": layer}
    jpath = os.path.join(tmp, f"overlay_{layer}.json")
    json.dump(data, open(jpath, "w"), ensure_ascii=False)
    out = os.path.join(tmp, f"overlay_{layer}.mov")
    page = os.path.join(ROOT, "motion", "templates", "talk_overlay.html") + "#spec=" + os.path.relpath(jpath, ROOT)
    fps = 15 if preview else 30
    extra = ["--scale=0.5"] if preview else []
    subprocess.run(["node", os.path.join(ROOT, "motion", "render.mjs"), page, out, f"{total:.3f}", str(fps), str(W), str(H), *extra],
                   check=True, cwd=os.path.join(ROOT, "motion"))
    return out


def main(spec_path, preview=False):
    spec = json.load(open(spec_path))
    name, total = spec["name"], spec["duration"]
    W, H = ASPECTS.get(spec.get("aspect", "9:16"), (1080, 1920))
    size = (W // 2, H // 2) if preview else (W, H)
    if preview:
        spec = dict(spec, fps=30)
    tmp = os.path.join(ROOT, "work", "talk", name + ("_preview" if preview else ""))
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    base, voice = pieces(spec, tmp, size, preview)
    hook = spec.get("hook") or {}
    matte = None
    if hook.get("text") and hook.get("behind"):
        try:   # text behind the speaker: segment the subject only where the hook shows
            from factory import matte as matte_mod
            matte = matte_mod.matte_video(base, os.path.join(tmp, "matte.mp4"), [(0, hook.get("end", 2) + 0.3)], spec["fps"])
        except Exception as e:
            print("hook behind the speaker: no matte,", type(e).__name__, e, flush=True)
    top_spec = dict(spec, hook=dict(hook, behind=bool(matte)))
    ov_top = overlay(top_spec, tmp, (W, H), total, "all", preview)
    inputs, chain, k = ["-i", base], ["[0:v]format=yuv420p[base]"], 1
    last = "[base]"
    if matte:
        ov_hook = overlay(spec, tmp, (W, H), total, "hook", preview)
        inputs += ["-i", ov_hook, "-i", matte]
        chain[0] = "[0:v]format=yuv420p,split[base][basecopy]"
        chain.append(f"[{k}:v]scale={size[0]}:{size[1]}[hk];[base][hk]overlay=0:0:format=auto[bh]")
        chain.append(f"[{k + 1}:v]format=gray,scale={size[0]}:{size[1]}[mt];[basecopy]format=yuva420p[bc];[bc][mt]alphamerge[subj];"
                     "[bh][subj]overlay=0:0:format=auto[bs]")
        last, k = "[bs]", k + 2
    inputs += ["-i", ov_top]
    chain.append(f"[{k}:v]scale={size[0]}:{size[1]}[ov];{last}[ov]overlay=0:0:format=auto,format=yuv420p[v]")
    silent = os.path.join(tmp, "silent.mp4")
    run([*inputs, "-filter_complex", ";".join(chain), "-map", "[v]", "-an", "-r", str(spec["fps"]), "-c:v", "libx264",
         "-preset", "veryfast" if preview else "slow", "-crf", "24" if preview else "16", "-pix_fmt", "yuv420p",
         "-t", f"{total:.3f}", silent])
    music = None
    if spec.get("music"):
        mu = spec["music"]
        music = {"file": os.path.join(ROOT, mu["file"]), "auto": mu.get("auto", True), "gap": mu.get("gap", 12.0),
                 "db": mu.get("db", -20)}
    from factory import sfx
    cues = sfx.clean_cues(spec.get("cues"), total, "subtle", per10=7)
    words = spec.get("words") or []
    audiofx.save_placed(name, cues, words, 0.0)
    mixed = os.path.join(tmp, "mixed.mp4")
    audiofx.mix(silent, mixed, total, voice={"file": voice, "start": 0.0}, music=music, cues=cues, words=words,
                voice_offset=0.0, chain=spec.get("voice_chain", "room"))
    out_dir = os.path.join(ROOT, "work", "preview") if preview else os.path.join(ROOT, "out", name)
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, f"{name}.mp4")
    run(["-i", mixed, "-c:v", "copy", "-af", f"loudnorm=I=-14:TP=-1.5:LRA=11,atrim=0:{total:.3f}", "-c:a", "aac", "-b:a", "192k",
         "-ar", "48000", "-t", f"{total:.3f}", "-movflags", "+faststart", dst])
    if spec.get("post") and not preview:
        import cinecut
        cinecut.write_caption(os.path.join(out_dir, "caption.txt"), spec["post"])
    print(f"{dst}  ({total:.2f}s, {len(spec['segments'])} cuts, {len(spec.get('broll') or [])} B-roll, {len(cues)} effects)")
    return dst, total


if __name__ == "__main__":
    main(sys.argv[1], preview="--preview" in sys.argv)
