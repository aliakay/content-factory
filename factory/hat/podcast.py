"""The podcast repurpose line: the clip factory's machinery on a podcast (audio or video, uploaded to raw/talk/),
plus quote cards. An audio-only episode becomes clips with a waveform on a dark ground. No credits.

  idea        transcribe, the model picks the strongest moments and the most quotable sentences -> proposal (gate)
  scene_plan  framing per clip (video) or the waveform look (audio), and the quote cards -> plates (gate)
  assets      every clip cut with captions and its hook -> assets (gate)
  edit, compose, publish as in the clip factory; publish lists the cards too
"""
import os

from PIL import Image, ImageDraw

from . import clips as C
from . import project as P
from .explainer import _rel
from .footage import _ui

QUOTES = 3


def idea(pid, s, note=None, d=None):
    out = C._idea(pid, note, d, quotes=QUOTES)
    art = out["artifact"]
    n = len(art.get("quotes") or [])
    art["summary"] = out["summary"] = out["summary"] + {"tr": f" {n} alıntı kartı.", "en": f" {n} quote cards."}[_ui(P.load(pid, d))]
    return out


def card(text, who, out, size=(1080, 1920), accent=(255, 217, 61)):
    """A quote card: the sentence large on a dark ground, an accent quote mark, the show's name under it."""
    from ..thumbs import FONT, _font, wrap_lines
    w, h = size
    img = Image.new("RGB", size, (16, 20, 24))
    d = ImageDraw.Draw(img)
    words = text.split()
    px = int(h * 0.05)
    while True:
        f = _font(FONT, px, 800)
        lines = wrap_lines(d, words, f, w * 0.84, 99)
        if len(lines) * px * 1.25 <= h * 0.5 or px <= int(h * 0.025):
            break
        px -= 4
    top = int((h - len(lines) * px * 1.25) / 2)
    d.text((int(w * 0.08), top - int(px * 1.9)), "“", font=_font(FONT, int(px * 2.4), 900), fill=accent)
    for i, ln in enumerate(lines):
        d.text((int(w * 0.08), top + int(i * px * 1.25)), ln, font=f, fill=(245, 245, 245))
    if who:
        d.text((int(w * 0.08), top + int(len(lines) * px * 1.25 + px)), "— " + who, font=_font(FONT, int(px * 0.55), 600),
               fill=accent)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out, quality=92)
    return out


def scene_plan(pid, s, note=None, d=None):
    from ..formats import ASPECTS
    out = C.scene_plan(pid, s, note, d)
    p = P.load(pid, d)
    size = ASPECTS.get(p.get("aspect", "9:16"), (1080, 1920))
    quotes = (P.read_artifact(pid, "proposal", d) or {}).get("quotes") or []
    cards = [_rel(card(q["text"], p["title"], P.path(pid, "plates", f"quote_{q['n']}.jpg", d=d), size)) for q in quotes]
    art = out["artifact"]
    art["cards"] = cards
    art["plates"] = art["plates"] + cards
    ui = _ui(p)
    art["summary"] = out["summary"] = art["summary"] + {"tr": f" {len(cards)} alıntı kartı da hazır.",
                                                        "en": f" {len(cards)} quote cards are ready too."}[ui]
    return out


assets, edit, compose = C.assets, C.edit, C.compose


def publish(pid, s, note=None, d=None):
    out = C.publish(pid, s, note, d)
    out["artifact"]["cards"] = (P.read_artifact(pid, "plates", d) or {}).get("cards") or []
    return out
