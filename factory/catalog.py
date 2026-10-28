"""The technique catalogue as a page the creator can browse: every technique with what it does and, where it can be
shown, a short demo clip drawn by the studio's own motion engine (motion/templates/fxlib.js, rendered headless: no
Claude and no ElevenLabs cost). The creator pins techniques from here into the composer ("bunu kullan") or leaves the
choice to the planner ("Opus seçsin"); factory/planner.py honours the pins.

Demos are rendered once into work/catalog/<id>.mp4 by the job "catalog_demos" (python -m factory.catalog renders them
by hand); a technique without a demo shows its description, and a film style its bible.
"""
import json, os, subprocess, sys, time

from . import capabilities
from .config import ROOT

DIR = os.path.join(ROOT, "work", "catalog")
PALETTE = {"bg": "#0f1220", "ink": "#f4efe6", "muted": "#9aa3b5", "accent": "#ffb347", "accent2": "#7c5cff",
           "paper": "#f3eee3", "hot": "#ff5a5f"}
BG = "position:absolute;inset:0;background:var(--bg)"

# id -> (seconds, scene js[, css][, extra bundle fields]). Each demo is one small scene that shows the technique doing
# its job; times are seconds from 0. Captions are off unless the demo is about captions.
DEMOS = {
    "look.code_characters": (4, """
const a = FX.stickman(root, {x: 380, y: 1300, h: 460, color: '#f4efe6'}), b = FX.stickman(root, {x: 720, y: 1300, h: 420, color: '#ffb347', pose: 'wave'});
FX.alive(a, {look: [[0.5, 1, 0]]}); FX.alive(b, {look: [[0.8, -1, 0]]});
a.walk(0.2, 1.4, 120); FX.act(a, [[1.8, 'stand'], [2.2, 'point'], [4, 'point']]); FX.wave(tl, b, 0.6, 1.8);"""),
    "look.acting": (5, """
const m = FX.stickman(root, {x: 540, y: 1300, h: 520, color: '#f4efe6'});
FX.emotions(tl, m, [[0, 'neutral'], [1.2, 'surprised'], [2.6, 'thinking'], [3.8, 'idea']]);"""),
    "look.alive": (6, """
const svg = FX.svg(root, 1080, 1920);
FX.el(svg, 'rect', {x: 0, y: 1380, width: 1080, height: 540, fill: '#1b2236'});
const kid = FX.character(root, {x: 470, y: 1420, h: 640, hat: '#f4a6b8', style: 'pigtails'});
FX.alive(kid, {look: [[0.4, 1, 0.2], [2.2, -0.8, -0.3], [3.6, 0, 0]], cheek: [[0, 0], [3.8, 0], [4.1, 1, 'out'], [6, 1]], talk: [[4.4, 5.4]]});
FX.act(kid, [[0, 'stand'], [1.5, 'stand'], [2.0, 'point'], [3.2, 'point'], [3.6, 'stand'], [4.2, 'wave'], [6, 'wave']]);
FX.hop(kid, 3.7, {h: 50}); FX.wave(tl, kid, 4.3, 1.6);"""),
    "look.living_world": (6, """
const svg = FX.svg(root, 1080, 1920);
FX.el(svg, 'rect', {x: 0, y: 1300, width: 1080, height: 620, fill: '#1e3b2f'});
const stem = FX.el(svg, 'g', {}); FX.el(stem, 'path', {d: 'M300 1330 C296 1200 312 1120 300 1000', stroke: '#5fa35a', 'stroke-width': 14, fill: 'none'});
const top = FX.el(stem, 'g', {}); FX.el(top, 'ellipse', {cx: 330, cy: 1000, rx: 60, ry: 24, fill: '#7fd16f'});
FX.sway([stem, top], {pivot: [300, 1330], deg: 3, grow: 1.4});
FX.el(svg, 'rect', {x: 700, y: 1180, width: 40, height: 150, fill: '#eee', rx: 6});
const fl = FX.el(svg, 'ellipse', {cx: 720, cy: 1140, rx: 22, ry: 48, fill: '#ffb347'}); FX.flicker(fl);
FX.steam(root, {x: 540, y: 1230}); FX.el(svg, 'rect', {x: 490, y: 1230, width: 100, height: 90, rx: 10, fill: '#ddd'});
FX.weather(root, {kind: 'snow', n: 70}); FX.ripples(root, {x: 540, y: 1650, r: 160});"""),
    "look.kinetic_type": (5.6, """
FX.charge(tl, root, 0, 0.7);
FX.kinetic(tl, root, 0.7, {style: 'punch3d', text: 'THE CITY', until: 1.75, fx: 'punch'});
FX.kinetic(tl, root, 1.75, {style: 'slam', text: 'HAS NEW', until: 2.8, ground: 'var(--accent)', color: 'var(--bg)'});
FX.kinetic(tl, root, 2.8, {style: 'stack', text: ['VERY BIG', 'NEIGHBOURS.'], until: 3.85, ground: 'var(--paper)', color: '#14120e'});
FX.cutRun(tl, root, 3.85, ['NO', 'TIMELINE.', 'NO', 'PLUGINS.', 'JUST', 'CODE.']);""", "", {"bpm": 172}),
    "look.picture_alive": (4.5, """
FX.picture(tl, root, 0, 4.5, {src: '/work/catalog/picture.png', words: [[0.4, 'MONSTERS'], [1.8, 'NEXT DOOR.', 'var(--accent)']],
  cutIns: [[3.2, 1.6, [0.5, 0.4], 0.6]], tint: 0.25, weather: 'rain'});"""),
    "look.motion_blur": (3, """
const w = FX.kinetic(tl, root, 0.3, {style: 'punch3d', text: 'FAST', until: 3, fx: 'punch'});
for (const [t, d] of [[1.2, 1], [1.8, -1], [2.4, 1]]) { FX.whip(tl, w.el, t, {dir: d}); FX.whipIn(tl, w.el, t + 0.18, {dir: -d}); }""",
                          "", {"blur": 4}),
    "look.story_hud": (4, """
FX.hud(root, {label: 'NIGHT 1', place: 'GAS STATION', times: [[0, '2:17 AM'], [1.6, '2:41 AM'], [3, '3:05 AM']]});
const m = FX.stickman(root, {x: 540, y: 1350, h: 440, color: '#f4efe6'}); FX.alive(m, {look: [[1, -1, 0], [2.4, 1, 0]]});"""),
    "look.night_palette": (4, """
const svg = FX.svg(root, 1080, 1920);
FX.el(svg, 'rect', {x: 340, y: 700, width: 400, height: 560, fill: '#1a2033', stroke: '#2c3550', 'stroke-width': 8});
const m = FX.stickman(root, {x: 540, y: 1300, h: 400, color: '#3a4560'}); FX.alive(m);
FX.rule(tl, root, 1.4, 3, 'NEVER OPEN\\nTHE DOOR', {y: 360});"""),
    "story.rules_arc": (5, """
const r1 = FX.rule(tl, root, 0.3, 1, 'KILL THE\\nBIG LIGHTS', {y: 380});
const m = FX.stickman(root, {x: 540, y: 1350, h: 440, color: '#f4efe6'}); FX.alive(m, {look: [[0.8, 0, -0.6], [3.2, 1, 0]]});
const d = FX.lightsOut(tl, root, 1.8, {keep: true}); FX.lightsOn(tl, d, 2.9);
tl.to(r1, {opacity: 0, duration: 0.2}, 2.8); FX.rule(tl, root, 3.1, 3, 'NEVER OPEN\\nTHE DOOR', {y: 380});
FX.emotions(tl, m, [[0, 'neutral'], [2.0, 'scared'], [3.4, 'nervous']]);"""),
    "look.ui_rebuild": (4.5, """
const ph = FX.phone(root, {w: 560, x: 540, y: 300, html: `<div style="padding:70px 34px;font:600 34px Inter Tight;color:#111">
  <div style="font:800 52px Inter Tight">Balance</div><div style="font:900 96px Inter Tight;margin:20px 0">$1,240</div>
  <div style="background:#eee;border-radius:22px;padding:28px;margin-top:30px">Groceries <b style="float:right">-$42</b></div>
  <div style="background:#eee;border-radius:22px;padding:28px;margin-top:16px">Salary <b style="float:right;color:#1a8f4a">+$2,100</b></div>
  <div class="cta" style="background:#111;color:#fff;border-radius:40px;padding:30px;text-align:center;margin-top:50px">Send</div></div>`});
tl.fromTo(ph.el, {y: 120, opacity: 0}, {y: 0, opacity: 1, duration: 0.6}, 0.2);
FX.tap(tl, root, 2.2, [540, 1180]); FX.alert(tl, ph, 3, {app: 'Bank', title: 'Sent', body: '$50 to Alex'});""", "background:#e9e6df"),
    "look.kinetic_headline": (4.5, """
const h = document.createElement('div'); h.style.cssText = 'position:absolute;left:80px;right:80px;top:300px;font:800 92px/1.05 Inter Tight;color:var(--ink)'; root.appendChild(h);
h.innerHTML = ['Your', '<i style="font-family:Instrument Serif;font-weight:400;color:var(--accent)">brain</i>', 'deletes', 'this'].map((w) => `<span style="display:inline-block">${w}</span>`).join('<span> </span>');
tl.fromTo([...h.children].filter((c) => c.textContent.trim()), {opacity: 0, y: 18, filter: 'blur(14px)'}, {opacity: 1, y: 0, filter: 'blur(0px)', duration: 0.55, stagger: 0.22}, 0.3);
FX.checklist(tl, root, 1.8, ['Names', 'Faces', 'Why you walked in'], {y: 900});"""),
    "look.paper_dots": (4, """
const h = document.createElement('div'); h.textContent = 'THE HIDDEN COST'; h.style.cssText = 'position:absolute;left:80px;top:420px;font:900 110px/1 Inter Tight;color:#1a1a1a'; root.appendChild(h);
FX.rise(tl, h, 0.3); FX.highlight(tl, h, 1.2, {color: '#ff6b3d'});
FX.chart(tl, root, 1.8, {type: 'bar', data: [3, 5, 9], labels: ['2019', '2022', '2025'], x: 140, y: 900, w: 800, h: 600});""",
                         "background:#efe9df radial-gradient(#0002 2px, transparent 2px) 0 0/34px 34px"),
    "look.break_the_old": (4, """
const card = document.createElement('div'); card.textContent = 'OLD WAY'; card.style.cssText = 'position:absolute;left:190px;top:760px;width:700px;height:400px;border-radius:30px;background:#2a3147;color:#fff;font:900 110px/400px Inter Tight;text-align:center'; root.appendChild(card);
FX.slash(tl, root, 1.4, [160, 1180, 920, 720]); FX.shatter(tl, card, 1.7);"""),
    "look.choice_ending": (4, """FX.choice(tl, root, 0.3, {q: 'Would you stay?', a: 'STAY', b: 'RUN'}); FX.flipCard(tl, root, 2.6, 'PART 1', 'PART 2', {y: 1450});"""),
    "look.logo_end": (3, """
const l = document.createElement('div'); l.textContent = 'ACME'; l.style.cssText = 'position:absolute;left:0;right:0;top:820px;text-align:center;font:900 200px Inter Tight;color:var(--ink)'; root.appendChild(l);
tl.fromTo(l, {scale: 1.4, opacity: 0}, {scale: 1, opacity: 1, duration: 0.5, ease: 'expo.out'}, 0.8); FX.sfx('logo_hit', 0.8);"""),
    "look.handmade": (4, """
FX.boil(root, {px: 3});
const m = FX.stickman(root, {x: 540, y: 1350, h: 460, color: '#222', twos: true}); FX.alive(m); FX.act(m, [[0, 'stand'], [1, 'shrug'], [2.4, 'shrug'], [3, 'stand']]);
FX.doodle(tl, root, 0.4, 'M200 600 Q540 400 880 600', {T, color: '#222'});""", "background:#f6f1e6"),
    "look.set3d": (4, """
const set = FX.set3d(root, T, {lens: 35, light: 'night_interior', fog: '#0b1020'});
set.room([8, 3, 6], '#3a4058'); set.box([1.6, 0.8, 0.9], [0, 0, -1], '#6b5a48'); set.practical([1.5, 1.6, -1.5], '#ffd59a', 1.6);
set.dolly([0, 1.6, 6], [0, 1.4, 3.6], [0, 1, -1]);"""),
    "look.caused_transitions": (4, """
const a = document.createElement('div'); a.style.cssText = 'position:absolute;inset:0;background:var(--accent)'; root.appendChild(a);
const b = document.createElement('div'); b.style.cssText = 'position:absolute;inset:0;background:var(--accent2)'; root.appendChild(b); b.style.opacity = 0;
FX.iris(tl, root, 0.2, [0.5, 0.5]); FX.brushWipe(tl, root, 1.6); tl.set(b, {opacity: 1}, 2.0); FX.colorFlood(tl, root, 3, '#14120e', {z: 5});"""),
    "captions.word_mid": (4, "", "", {"captions": {"mode": "word", "pos": "mid"}, "say": "Imagine you are alone in the store tonight"}),
    "captions.color_roles": (4, "", "", {"captions": {"mode": "chunk", "keys": {"store": "key", "tonight": "key", "blood": "danger", "never": "danger"}},
                                         "say": "Never open the store door tonight there is blood"}),
    "captions.energy": (4, "", "", {"captions": {"mode": "chunk", "energy": "high"}, "say": "Stop scrolling this changes how you sleep tonight"}),
    "edit.motion_broll": (3.5, """
const n = document.createElement('div'); n.style.cssText = 'position:absolute;left:0;right:0;top:640px;text-align:center;font:900 260px Inter Tight;color:var(--accent)'; root.appendChild(n);
const w = document.createElement('div'); w.innerHTML = '<i style="font-family:Instrument Serif">faster</i> replies'; w.style.cssText = 'position:absolute;left:0;right:0;top:1000px;text-align:center;font:500 110px Inter Tight;color:var(--ink)'; root.appendChild(w);
FX.countUp(tl, n, 0.2, 3, {suffix: 'x', dur: 0.8}); FX.rise(tl, w, 0.7); FX.boxLabel(tl, root, 1.6, [0.12, 0.3, 0.76, 0.32], 'RESULT');"""),
}
DEMOS["story.beat_film"] = DEMOS["look.kinetic_type"]   # the kinetic demo is the beat film's look


def demo_file(cid):
    return os.path.join(DIR, cid.replace("/", "_") + ".mp4")


def _bundle(cid):
    t = list(DEMOS[cid])
    dur, js, css, extra = t[0], t[1], (t[2] if len(t) > 2 else ""), (t[3] if len(t) > 3 else {})
    words = []
    if extra.get("say"):    # a caption demo: evenly timed words
        ws = extra["say"].split()
        step = (dur - 0.6) / len(ws)
        words = [{"w": w, "s": round(0.3 + i * step, 3), "e": round(0.3 + (i + 0.85) * step, 3)} for i, w in enumerate(ws)]
    return {"palette": PALETTE, "global_css": "", "words": words, "duration": dur, "w": 1080, "h": 1920, "lang": "en",
            "captions": extra.get("captions") or {}, **({"bpm": extra["bpm"], "beat0": 0} if extra.get("bpm") else {}),
            "scenes": [{"id": "demo", "start": 0, "end": dur, "hide_captions": not words, "lines_t": [],
                        "html": "", "css": css or BG, "js": js or ""}]}, dur, extra


def _picture():
    """The stand-in key art for the picture demo (a gradient with a window), drawn once."""
    p = os.path.join(DIR, "picture.png")
    if not os.path.exists(p):
        from .config import FFMPEG
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i",
                        "gradients=s=1600x1200:c0=0x2a4d8f:c1=0xf2a541:x0=0:y0=0:x1=1600:y1=1200,"
                        "drawbox=x=600:y=380:w=400:h=440:c=0xffe7b0@0.85:t=fill", "-frames:v", "1", p], check=True)


def render(cid, force=False):
    """Render one demo clip (quarter-ish size, 24 fps, silent). -> path or None."""
    if cid not in DEMOS:
        return None
    out = demo_file(cid)
    if os.path.exists(out) and not force:
        return out
    os.makedirs(DIR, exist_ok=True)
    _picture()
    b, dur, extra = _bundle(cid)
    bpath = os.path.join(DIR, cid.replace("/", "_") + ".json")
    json.dump(b, open(bpath, "w"))
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import htmlmotion
    flags = ["--opaque", "--scale=0.4"] + ([f"--blur={extra['blur']}"] if extra.get("blur") else [])
    t0 = time.time()
    r = htmlmotion._node(bpath, out, dur, flags, 24)
    if r.returncode or not os.path.exists(out):
        raise RuntimeError(f"demo {cid}: " + (r.stderr or "")[-300:])
    if not extra.get("blur"):   # how heavy this technique's frames are on this machine (catalog render estimates);
        from . import renderspeed   # a blurred demo is left out: its cost is the blur samples, counted on their own
        renderspeed.record("demo:" + cid, round(dur * 24), time.time() - t0)
    return out


def render_all(ids=None, force=False):
    done, failed = [], []
    for cid in ids or list(DEMOS):
        try:
            render(cid, force)
            done.append(cid)
        except Exception as e:
            failed.append(f"{cid}: {str(e)[:120]}")
            print(failed[-1], flush=True)
    try:   # then measure this machine's full-size speed, so every card can say how long 30 s would take
        from . import renderspeed
        m = renderspeed.calibrate()
        print(f"render speed: {m['per_capture']:.3f} s/frame, start-up {m['startup']:.1f} s", flush=True)
    except Exception as e:
        failed.append(f"calibration: {str(e)[:120]}")
    return done, failed


def listing(kind=None):
    """Every technique for the catalog page: label, area, what it does, where it applies, its demo clip if rendered."""
    from . import renderspeed
    styles = {"style." + s["id"]: s for s in capabilities._film_styles()}
    out = []
    for cid, v in capabilities.CAPS.items():
        if v.get("always") or (kind and kind not in v["kinds"]):
            continue
        f = demo_file(cid)
        st = styles.get(cid)
        eta = renderspeed.estimate(30, [cid]) if "topic" in v["kinds"] else None
        out.append({"id": cid, "tr": v["tr"], "area": v["area"], "area_tr": capabilities.AREAS[v["area"]], "what": v["what"],
                    "kinds": list(v["kinds"]), "shape": bool(v.get("shape")), "style": bool(v.get("style")),
                    "demo": ("/media/work/catalog/" + os.path.basename(f) + f"?v={int(os.path.getmtime(f))}") if os.path.exists(f) else None,
                    "can_demo": cid in DEMOS,
                    **({"eta": {**eta, "preview": renderspeed.label(eta["preview_s"]), "final": renderspeed.label(eta["final_s"])}} if eta else {}),
                    **({"bible": {k: st.get(k) for k in ("colour", "motion", "type", "sound") if st.get(k)}} if st else {})})
    return out


def missing():
    return [c for c in DEMOS if not os.path.exists(demo_file(c))]


if __name__ == "__main__":
    d, f = render_all(sys.argv[1:] or None, force=bool(sys.argv[1:]))
    print(f"{len(d)} demos, {len(f)} failed")
