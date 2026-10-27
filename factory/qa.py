"""Post-render quality check: technical checks + a visual review of settled frames by Claude.

Technical (after WeAreNoCode verify-render): black runs, duration vs. the montage, loudness/true peak, frame 0 not black.
Visual (after whaleyxbt/claude-motion review-loop): one frame per text beat, ~0.35 s after it starts so motion has
settled, plus frame 0 and the last frame; Claude reviews them against a checklist and returns issues with fixes.
"""
import json, os, re, subprocess

from . import llm, media

from .config import ROOT
CHECKLIST = """- Frame 0 is a real image (it becomes the cover), not black or blank.
- One focal point per frame; text and important subjects don't collide.
- Safe zones for TikTok/Shorts UI: nothing important in the top ~12%, the bottom ~25% or the right ~12% (buttons).
- Every text line is readable when the frame is shrunk to phone width (size, contrast against the footage).
- Text is not clipped by the frame edge; no line runs wider than ~85% of the frame.
- Text shown at a 'settled' frame is fully visible (not still fading/animating) — otherwise the hold is too short.
- Consistent style: same element looks the same each time; accent colour only on key words.
- No strangers' faces prominently visible without a reason."""


def technical(path, expected=None):
    probe = media.probe_video(path)
    out = {"duration": round(probe["duration"], 2)}
    if expected:
        out["duration_ok"] = abs(probe["duration"] - expected) <= 0.1
    p = subprocess.run([media.FFMPEG, "-hide_banner", "-i", path, "-vf", "blackdetect=d=0.04:pix_th=0.08",
                        "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    out["black_runs"] = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", p.stderr)]
    m = re.search(r"Integrated loudness:\s+I:\s+([-\d.]+) LUFS.*?True peak:\s+Peak:\s+([-\d.]+) dBFS", p.stderr, re.S)
    if m:
        out["lufs"], out["true_peak_db"] = float(m.group(1)), float(m.group(2))
    problems = []
    if out.get("duration_ok") is False:
        problems.append(f"duration {out['duration']}s differs from the montage ({expected:.2f}s)")
    if any(a < 0.05 for a, _ in out["black_runs"]):
        problems.append("starts on a black frame (bad cover)")
    if [r for r in out["black_runs"] if r[0] >= 0.05]:
        problems.append(f"black frames at {[round(a, 2) for a, _ in out['black_runs'] if a >= 0.05]}")
    if out.get("true_peak_db", -99) > -1.0:
        problems.append(f"audio true peak {out['true_peak_db']} dBFS (target <= -1 dBFS)")
    fz = frozen_time(path)
    out["frozen"] = fz
    limit = max(1.0, probe["duration"] / 30)
    if fz["frozen_s"] > limit or fz["longest_hold_s"] > 1.2:
        problems.append(f"motion stalls: {fz['frozen_s']}s near-frozen (limit {limit:.1f}s), longest hold "
                        f"{fz['longest_hold_s']}s — add a slow push or cut sooner")
    fc = frame_checks(path)
    out["frames"] = fc
    if fc["flash_windows"]:
        problems.append(f"flashing: more than 3 flashes per second at {fc['flash_windows'][:4]} s (photosensitivity risk)")
    if fc["broken_frames"]:
        problems.append(f"possible broken/corrupt frames at {fc['broken_frames'][:4]} s")
    out["problems"] = problems
    return out


def frame_checks(path, fps=10):
    """Numeric checks on small grey frames (OpenCV-style, numpy only):
    flashes  luminance jumps > 20 % of the range; more than 3 inside any 1 s window is a photosensitivity risk (WCAG 2.3.1)
    broken   frames whose edge energy spikes > 4x their neighbours' (block corruption, a glitched or half-decoded frame)
    static   share of 1 s windows with almost no change: high on an explainer means it plays like a slideshow"""
    import numpy as np
    from .fxdetect import frames
    fr = frames(path, fps=fps, width=128, max_s=180)
    if len(fr) < fps:
        return {"flash_windows": [], "broken_frames": [], "static_share": 0.0}
    lum = fr.mean(axis=(1, 2))
    jumps = np.where(np.abs(np.diff(lum)) > 0.2)[0] / fps
    flash = sorted({round(float(t), 1) for t in jumps if ((jumps >= t) & (jumps < t + 1)).sum() > 3})
    edge = np.abs(np.diff(fr, axis=2)).mean(axis=(1, 2)) + np.abs(np.diff(fr, axis=1)).mean(axis=(1, 2))
    broken = []
    for i in range(1, len(edge) - 1):
        nb = (edge[i - 1] + edge[i + 1]) / 2
        if nb > 1e-3 and edge[i] > 4 * nb and edge[i] > 0.05:
            broken.append(round(i / fps, 2))
    diff = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    wins = [diff[k:k + fps].max() for k in range(0, len(diff) - fps + 1, fps)]
    static = round(float(np.mean([w < 0.004 for w in wins])), 2) if wins else 0.0
    return {"flash_windows": flash[:10], "broken_frames": broken[:10], "static_share": static}


def frozen_time(path, threshold=0.35, fps=10):
    """Near-frozen moments (motion-video-kit quality bar): frame diff below threshold, sampled at 10 fps.
    Target: total <= ~1 s per 30 s and no single hold > 0.6 s except the final CTA."""
    rows = media.motion_profile(path, fps=fps)
    frozen = [t for t, m, _ in rows[1:] if (m or 0) < threshold]
    longest, run, prev = 0.0, 0.0, None
    for t in frozen:
        run = run + 1 / fps if prev is not None and abs(t - prev - 1 / fps) < 1e-6 else 1 / fps
        longest, prev = max(longest, run), t
    return {"frozen_s": round(len(frozen) / fps, 1), "longest_hold_s": round(longest, 1),
            "first_frozen_at": [round(t, 1) for t in frozen[:20]]}


def beat_frames(path, beats, total, name, extra_times=()):
    times = sorted({0.0, round(max(0.0, total - 0.15), 2)} | {round(t, 2) for t in extra_times if 0 < t < total} |
                   {round(min((float(b.get("t0", 0)) + float(b.get("t1", total))) / 2, total - 0.05), 2)
                    for b in beats})[:16]  # mid-beat (settled) + transition midpoints (text-over-text checks)
    d = os.path.join(ROOT, "work", "qa", name)
    os.makedirs(d, exist_ok=True)
    files = []
    for t in times:
        f = os.path.join(d, f"t{t:06.2f}.jpg")
        subprocess.run([media.FFMPEG, "-v", "error", "-y", "-ss", str(t), "-i", path, "-frames:v", "1",
                        "-vf", "scale=360:-2", f], check=True)
        files.append((t, f))
    from PIL import Image, ImageDraw
    ims = [Image.open(f) for _, f in files]
    w, h = ims[0].size
    cols = min(6, len(ims))
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * (h + 22)), "black")
    dr = ImageDraw.Draw(sheet)
    for i, ((t, _), im) in enumerate(zip(files, ims)):
        x, y = (i % cols) * w, (i // cols) * (h + 22)
        sheet.paste(im, (x, y))
        dr.text((x + 4, y + h + 4), f"t={t:.2f}s", fill="yellow")
    sp = os.path.join(d, "sheet.jpg")
    sheet.save(sp, quality=85)
    return sp, [t for t, _ in files]


def review(path, idea, total, name, transitions=(), previous=None, model=None, size=(1080, 1920), notes=""):
    """`previous`: last round's visual issues — this round must verify each one (the Gauntlet ledger)."""
    tech = technical(path, total)
    sheet, times = beat_frames(path, idea.get("beats", []), total, name, extra_times=transitions)
    prev_block = ""
    if previous:
        prev_block = ("\nPrevious round's issues — for EACH, say whether it is fixed or still present, in "
                      "\"verification\": " + json.dumps([i.get("problem") for i in previous], ensure_ascii=False))
    beats = [{"t0": b.get("t0"), "t1": b.get("t1"), "text": (b.get("text") or "").replace("\\N", " / ")}
             for b in idea.get("beats", [])]
    w, h = size
    frame = f"{w}x{h}"
    where = ("a phone shows the full frame about 390 pt wide" if h > w else
             "a horizontal YouTube video, watched full-width on a phone or on a desktop")
    prompt = f"""Read the image {sheet}: frames of a {frame} video at times {times} (labelled under each tile),
taken in the middle of each text beat, after its entrance has settled, plus frames in the middle of scene transitions
(check those for text over text or titles spliced by the transition). Frame 0 is the cover. Intended text beats: {json.dumps(beats, ensure_ascii=False)}.
Scale note: each tile is shown at {360 / w:.2f}x of the real {frame} frame. Judge sizes relative to the frame
({where}), not in tile pixels. TikTok/Shorts safe zones apply only to vertical frames.
Review against this checklist and only report problems you can actually see:
{CHECKLIST}
- Lead subject fills a good part of the frame; no dead empty bands; frame 0 is a finished composition.
{notes}{prev_block}
You are an independent critic, not the builder: default to flagging, approval is earned.
Reply with ONLY JSON: {{"pass": true/false, "issues": [{{"time": 1.2, "severity": "critical|high|medium",
"problem": "...", "fix": "concrete change (text size/position/timing/shot)"}}],
"verification": [{{"issue": "...", "status": "fixed|still_present"}}], "summary": "one sentence"}}"""
    visual, meta = llm.ask(prompt, tools=("Read",), timeout=600, model=model)
    ok = not tech["problems"] and visual.get("pass", False) and not any(
        i.get("severity") == "critical" for i in visual.get("issues", []))
    return {"pass": ok, "technical": tech, "visual": visual, "sheet": sheet, "cost_usd": meta.get("cost_usd")}
