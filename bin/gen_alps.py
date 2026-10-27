#!/usr/bin/env python3
"""Animated text layer for the '2 days in the Bavarian Alps' itinerary edit.

Reads work/alps2days_montage.json (shot start times) and writes specs/006_alps_2days_itinerary.json
for render.py: animated route map from real GPS points, sliding location pins, DAY stamps,
an altitude counter and a save-this CTA.
"""
import json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from factory.config import ROOT  # noqa: E402
FPS = 30
m = json.load(open(f"{ROOT}/work/alps2days_montage.json"))
S, T = m["starts"], m["total"]
ev = []


def add(start, end, style, text, layer=1, fade=""):
    ev.append({"start": round(start, 3), "end": round(end, 3), "style": style, "text": text,
               "layer": layer, "fade": fade})


# ---------- map ----------
STOPS = [  # name, lat, lon, label alignment (ASS \an) and label offset
    ("KOCHEL", 47.6577, 11.3723, 6, (-26, 0)),
    ("WALCHENSEE", 47.5945, 11.3191, 6, (-26, 0)),
    ("ZUGSPITZE", 47.4211, 10.9856, 8, (0, 22)),
    ("EIBSEE", 47.4605, 10.9861, 2, (0, -22)),
    ("GARMISCH", 47.4864, 11.0938, 2, (0, -24)),
    ("PARTNACHKLAMM", 47.4697, 11.1172, 8, (40, 22)),
]
LAT0, LAT1, LON0, LON1 = 47.40, 47.68, 10.93, 11.42
BX, BY, BW, BH = 110, 760, 860, 728


def proj(lat, lon):
    return BX + (lon - LON0) / (LON1 - LON0) * BW, BY + (LAT1 - lat) / (LAT1 - LAT0) * BH


PTS = [proj(lat, lon) for _, lat, lon, _, _ in STOPS]
SEG = [math.dist(PTS[i], PTS[i + 1]) for i in range(len(PTS) - 1)]
TOTAL_LEN = sum(SEG)


def partial(frac):
    """Points of the route polyline up to `frac` of its length."""
    target, pts = frac * TOTAL_LEN, [PTS[0]]
    for i, L in enumerate(SEG):
        if target >= L:
            pts.append(PTS[i + 1])
            target -= L
        else:
            a, b = PTS[i], PTS[i + 1]
            pts.append((a[0] + (b[0] - a[0]) * target / L, a[1] + (b[1] - a[1]) * target / L))
            break
    return pts


def line_path(pts):
    # forward then back along the same points: zero-area shape, so \bord draws an open polyline
    seq = pts + pts[-2::-1]
    return "m " + " l ".join(f"{x:.1f} {y:.1f}" for x, y in seq)


def circle(r):
    k = 0.5523 * r
    return (f"m 0 {-r} b {k} {-r} {r} {-k} {r} 0 b {r} {k} {k} {r} 0 {r} "
            f"b {-k} {r} {-r} {k} {-r} 0 b {-r} {-k} {-k} {-r} 0 {-r}")


LINE = "{\\an7\\pos(0,0)\\p1\\bord6\\shad0\\blur0.8\\1a&HFF&\\3c&H00E1FF&}"
DIM = "{\\an7\\pos(0,0)\\p1\\bord0\\shad0\\1c&H000000&\\1a&H68&}m 0 0 l 1080 0 l 1080 1920 l 0 1920"


def map_layer(t0, t1, animate):
    """Dim + route + dots + labels between t0 and t1. If animate, draw the route progressively."""
    add(t0, t1, "Draw", DIM, layer=0, fade="{\\fad(200,150)}")
    draw0, draw1 = t0 + 0.35, t0 + 1.45
    reach = []  # time each stop is reached
    acc = 0.0
    for i in range(len(PTS)):
        reach.append(draw0 + (acc / TOTAL_LEN) * (draw1 - draw0) if animate else t0 + 0.1)
        if i < len(SEG):
            acc += SEG[i]
    if animate:
        n = round((draw1 - draw0) * FPS)
        for k in range(1, n + 1):
            f = 1 - (1 - k / n) ** 2  # ease-out
            a = draw0 + (k - 1) / FPS
            b = draw0 + k / FPS if k < n else t1
            add(a, b, "Draw", LINE + line_path(partial(f)), layer=1,
                fade="" if k < n else "{\\fad(0,150)}")
    else:
        add(t0 + 0.1, t1, "Draw", LINE + line_path(PTS), layer=1, fade="{\\fad(250,150)}")
    for (name, _, _, an, (dx, dy)), (x, y), t in zip(STOPS, PTS, reach):
        pop = "\\fscx0\\fscy0\\t(0,140,\\fscx130\\fscy130)\\t(140,240,\\fscx100\\fscy100)"
        add(t, t1, "Draw", f"{{\\an5\\pos({x:.0f},{y:.0f})\\p1\\bord5\\3c&H00E1FF&\\1c&HFFFFFF&{pop}}}"
            + circle(11), layer=2, fade="{\\fad(0,150)}")
        add(t + 0.05, t1, "MapLabel", f"{{\\an{an}\\pos({x + dx:.0f},{y + dy:.0f})}}{name}", layer=2,
            fade="{\\fad(160,150)}")


POP = "\\fscx40\\fscy40\\t(0,160,\\fscx112\\fscy112)\\t(160,260,\\fscx100\\fscy100)"

# intro: title + animated route
map_layer(0.0, S[1] + 0.1, animate=True)
add(0.0, S[1] + 0.1, "Title", f"{{\\an8\\pos(540,300){POP}}}2 DAYS IN THE", layer=3, fade="{\\fad(0,150)}")
add(0.12, S[1] + 0.1, "TitleBig", f"{{\\an8\\pos(540,365){POP}}}BAVARIAN ALPS", layer=3,
    fade="{\\fad(0,150)}")


# location pins
def pin(t0, t1, place, when):
    slide = lambda y, d: f"\\an7\\move(-560,{y},70,{y},{d},{d + 230})"
    add(t0, t1, "Pin", f"{{{slide(300, 0)}}}{place}", layer=3, fade="{\\fad(0,120)}")
    add(t0, t1, "PinSub", f"{{{slide(400, 70)}}}{when}", layer=3, fade="{\\fad(0,120)}")


def stamp(t0, text):
    add(t0, t0 + 1.1, "Stamp", f"{{\\pos(540,900){POP}}}{text}", layer=4, fade="{\\fad(0,220)}")


def fact(t0, t1, text, style="Fact", y=720):
    add(t0, t1, style, f"{{\\an8\\pos(540,{y})\\fscx70\\fscy70\\t(0,150,\\fscx100\\fscy100)}}{text}",
        layer=3, fade="{\\fad(0,150)}")


stamp(S[1] + 0.05, "DAY 1")
pin(S[1] + 0.1, S[2] + 0.1, "KOCHEL", "SAT · 07:53")
pin(S[2] + 0.1, S[3] + 0.1, "WALCHENSEE", "SAT · 08:46")
pin(S[3] + 0.1, S[5] + 0.1, "ZUGSPITZE", "SAT · 12:43")
fact(S[3] + 0.25, S[4] + 0.05, "the cable car\\Nhas a glass floor")

# altitude counter on the summit shot
c0, c1 = S[4] + 0.15, S[4] + 1.05
n = round((c1 - c0) * FPS)
for k in range(1, n + 1):
    v = round(2962 * (1 - (1 - k / n) ** 3))
    a, b = c0 + (k - 1) / FPS, (c0 + k / FPS if k < n else S[5] + 0.05)
    tag = "\\pos(540,880)" + ("\\t(0,120,\\fscx115\\fscy115)\\t(120,220,\\fscx100\\fscy100)" if k == n else "")
    add(a, b, "Counter", f"{{{tag}}}{v:,} m", layer=3, fade="" if k < n else "{\\fad(0,150)}")
add(c1, S[5] + 0.05, "Title", "{\\an8\\pos(540,975)}GERMANY'S HIGHEST POINT", layer=3, fade="{\\fad(150,150)}")

pin(S[5] + 0.1, S[8] + 0.05, "EIBSEE", "SAT · 15:36")
fact(S[6] + 0.1, S[7] + 0.6, "one way to cool down…")
dive = S[7] + 0.55
fact(dive, S[8] + 0.05, "I JUMPED IN.", style="FactBig", y=720)

stamp(S[8] + 0.05, "DAY 2")
pin(S[8] + 0.1, S[10] + 0.1, "GARMISCH", "SUN · 07:42")
add(S[9] + 0.1, S[10] + 0.05, "Vlog", "morning, neighbours", layer=3, fade="{\\fad(120,100)}")
pin(S[10] + 0.1, S[12] + 0.1, "PARTNACH RIVER", "SUN · 08:52")
pin(S[12] + 0.1, S[16] + 0.05, "PARTNACHKLAMM", "SUN · 09:22")
fact(S[13] + 0.2, S[14] + 0.1, "carved by\\Nthis river")
add(S[14] + 0.1, S[16] + 0.05, "Vlog", "this place is unreal", layer=3, fade="{\\fad(120,100)}")

# outro: full map again + CTA, so the loop back to the intro feels seamless
map_layer(S[16] + 0.1, T, animate=False)
add(S[16] + 0.25, T, "Title", f"{{\\an8\\pos(540,300){POP}}}SAVE THIS FOR", layer=3, fade="{\\fad(0,0)}")
add(S[16] + 0.35, T, "TitleBig", f"{{\\an8\\pos(540,365){POP}}}YOUR TRIP", layer=3, fade="{\\fad(0,0)}")

spec = {
    "name": "006_alps_2days_itinerary",
    "input": "work/alps2days_montage.mp4",
    "speed": 1.0, "zoom": 0.0, "audio_volume": 0.35,
    "events": ev,
    "post": {
        "series": "Vlog (itinerary)",
        "caption": "2 days in the Bavarian Alps 🏔️ cable car with a glass floor, Germany's highest peak, "
                   "a lake jump and a gorge carved by a river.\nSave this for your trip 📌 Which stop would you pick?",
        "hashtags": "#bavaria #zugspitze #partnachklamm #germanytravel #itinerary",
        "location": "Garmisch-Partenkirchen, Bavaria",
        "music": "an upbeat trending sound around 120 BPM (the cuts land on a 0.5 s rhythm); "
                 "keep the original sound at 0–10%",
        "notes": "Stops in order: Kochel (Sat 07:53), Walchensee (08:46), Zugspitze cable car + summit 2,962 m (12:43), "
                 "Eibsee (15:36), Garmisch (Sun 07:42), Partnach river (08:52), Partnachklamm (09:22). "
                 "Times are the real capture times from the clips.",
    },
}
json.dump(spec, open(f"{ROOT}/specs/006_alps_2days_itinerary.json", "w"), ensure_ascii=False, indent=1)
print(f"events: {len(ev)}  total: {T:.2f}s")
