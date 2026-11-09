"""The typography system: one scale, one hierarchy per scene, and lines short enough to read on a phone.

`layoutlint` already measures the things that make text unreadable in the frame: too small, too low contrast, clipped,
in the caption band. What it cannot see is whether the type is a *system*: a film can pass every one of those checks
and still look assembled from six unrelated sizes, with a headline and a subhead that read as the same weight of
information, or a paragraph set so wide the eye loses the line.

This module adds that layer on the same lint payload (the renderer's per-frame text boxes, with their real pixel
size and tight box):
  type_sizes      more than six sizes in one film: a hierarchy is three to five
  type_close      two sizes within 12 % in the same scene: one of them is an accident, not a level
  type_flat       a scene whose largest text is under 1.2x its smallest: nothing is the headline
  type_line       a text run wider than 78 % of the frame: the measure is too long to track
  type_caps       all-caps over 26 characters: slower to read than sentence case, and it shouts
  type_small_long long text set at label size: a paragraph where a label belongs

The scale is modular (ratio 1.26) so a designer can add a level without inventing a size: 96 / 76 / 60 / 48 / 38 / 30 px
on a 1080-wide frame. The brief below is what the scene-plan designer and the reviewer read.
"""
from .layoutlint import SAFE

SCALE = {"display": 96, "h1": 76, "h2": 60, "lead": 48, "body": 38, "label": 30}   # px at 1080 wide
RATIO = 1.26
CLOSE = 0.12            # two sizes closer than this are the same level
FLAT = 1.20             # largest / smallest under this: no headline
WIDE = 0.78             # a text run wider than this share of the frame is too long a measure
CAPS = 26               # all-caps longer than this is hard to read
SMALL = 32              # a long text run set below this is a paragraph in a label's clothes
LONG = 40               # characters

BRIEF = f"""TYPOGRAPHY (binding: one scale, one hierarchy a scene)
- Sizes come from this scale on a 1080-wide frame: display {SCALE['display']} · h1 {SCALE['h1']} · h2 {SCALE['h2']} ·
  lead {SCALE['lead']} · body {SCALE['body']} · label {SCALE['label']} px. Scale it with the frame, never invent a size
  between two levels; three to five levels per film, not six.
- One scene has one headline. The second-largest text is at least 1.2x smaller than the largest, or the two read as
  the same level of information.
- A text run is at most about 40 characters wide (under 78 % of the frame). Longer than that wraps into a paragraph
  the eye cannot track; break it into lines that carry one idea each.
- All-caps only for short labels (under 26 characters). Long strings in sentence case.
- Never set a long line at label size: body text is {SCALE['body']} px or the reader squints.
"""


def _size(b):
    try:
        return round(float(b.get("size") or 0))
    except (TypeError, ValueError):
        return 0


def check(lint, aspect="9:16"):
    """Typography findings from a render.mjs --lint payload: the same shape as layoutlint's, so they travel together."""
    W = SAFE.get(aspect, SAFE["9:16"])["size"][0]
    out, film, per_scene = [], {}, {}
    for t, shot in sorted(lint.items(), key=lambda kv: float(kv[0])):
        for b in shot.get("boxes") or []:
            text = str(b.get("text") or "").strip()
            size = _size(b)
            if not text or size < 1:
                continue
            film[size] = film.get(size, 0) + 1
            per_scene.setdefault(b.get("scene"), {}).setdefault(size, []).append((float(t), b))
    if len(film) > 6:
        out.append({"t": 0.0, "scene": None, "kind": "type_sizes", "text": "",
                    "detail": f"{len(film)} type sizes in one film ({', '.join(str(s) for s in sorted(film))}): a "
                              f"hierarchy is three to five; use the scale"})
    for scene, sizes in per_scene.items():
        ordered = sorted(sizes)
        for small, big in zip(ordered, ordered[1:]):
            if big and (big - small) / big < CLOSE:
                t, b = sizes[small][0]
                out.append({"t": t, "scene": scene, "kind": "type_close", "text": b.get("text"),
                            "detail": f"{small} px and {big} px in one scene are the same level: pick one"})
                break
        if len(ordered) > 1 and ordered[-1] / max(1, ordered[0]) < FLAT:
            t, b = sizes[ordered[-1]][0]
            out.append({"t": t, "scene": scene, "kind": "type_flat", "text": b.get("text"),
                        "detail": f"the largest text is {ordered[-1] / max(1, ordered[0]):.2f}x the smallest: nothing "
                                  f"reads as the headline"})
        for size, runs in sizes.items():
            for t, b in runs:
                text = str(b.get("text") or "")
                if b.get("w") and b["w"] / W > WIDE and len(text) > 30:
                    out.append({"t": t, "scene": scene, "kind": "type_line", "text": text,
                                "detail": f"{len(text)} characters across {round(100 * b['w'] / W)} % of the frame: "
                                          f"too long a measure, break it"})
                    break
            for t, b in runs:
                text = str(b.get("text") or "").strip()
                if text.isupper() and len(text) > CAPS:
                    out.append({"t": t, "scene": scene, "kind": "type_caps", "text": text,
                                "detail": f"{len(text)} characters of all-caps: set it in sentence case or shorten it"})
                    break
            if size < SMALL:
                for t, b in runs:
                    text = str(b.get("text") or "").strip()
                    if len(text) > LONG:
                        out.append({"t": t, "scene": scene, "kind": "type_small_long", "text": text,
                                    "detail": f"{len(text)} characters at {size} px: body text is "
                                              f"{SCALE['body']} px, this is a label's size"})
                        break
    return out


def scale(aspect="9:16"):
    """The scale in pixels for a frame: the 1080-wide numbers scaled to the aspect's width."""
    W = SAFE.get(aspect, SAFE["9:16"])["size"][0]
    return {role: round(px * W / 1080) for role, px in SCALE.items()}


def brief(p=None):
    return BRIEF
