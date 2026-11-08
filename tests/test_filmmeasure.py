"""Measuring a reference picture (factory/filmmeasure.py): the board's palette and light come from a real still."""
from PIL import Image

from factory import filmmeasure as FM

GROUND = "#101418"
ACCENT = "#FFD93D"


def _still(path, ground, block, size=(96, 96)):
    """A synthetic picture: a ground with one accent block in the middle."""
    im = Image.new("RGB", size, ground)
    w, h = size
    im.paste(block, (w // 4, h // 4, w // 4 + w // 3, h // 4 + h // 3))
    im.save(path)
    return path


def _near(hex_a, hex_b, tol=30):
    """Are two hex colours close enough channel by channel?"""
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_measure_reads_the_palette_the_accent_and_the_light(tmp_path):
    p = _still(str(tmp_path / "still.png"), GROUND, ACCENT)
    m = FM.measure(p)
    assert len(m["palette"]) == 5
    assert all(c.startswith("#") and len(c) == 7 for c in m["palette"])
    assert _near(m["accent"], ACCENT), m["accent"]          # the yellow block is the accent of the picture
    assert m["l_p50"] < m["l_p95"]                          # a dark ground with a bright block in it
    assert m["contrast"] == m["l_p95"] - m["l_p5"]
    assert 0 <= m["dark_share"] <= 1 and 0 <= m["bright_share"] <= 1
    assert abs(sum(m["shares"]) - 1) < 0.01
    assert 90 <= m["key"]["azimuth_deg"] <= 270
    assert 10 <= m["key"]["elevation_deg"] <= 70


def test_the_same_picture_measures_the_same_every_time(tmp_path):
    p = _still(str(tmp_path / "still.png"), GROUND, ACCENT)
    assert FM.measure(p) == FM.measure(p)


def test_a_big_picture_is_read_small_and_still_measures_the_same(tmp_path):
    p = _still(str(tmp_path / "big.png"), GROUND, ACCENT, size=(480, 270))
    m = FM.measure(p)
    assert len(m["palette"]) == 5
    assert m == FM.measure(p)                      # the picture is decoded small, and that stays deterministic


def test_a_bright_picture_reads_brighter_and_shadows_less(tmp_path):
    dark = FM.measure(_still(str(tmp_path / "dark.png"), GROUND, ACCENT))
    bright = FM.measure(_still(str(tmp_path / "bright.png"), "#FFFFFF", ACCENT))
    assert bright["l_p50"] > dark["l_p50"]
    assert bright["dark_share"] < dark["dark_share"]
    assert bright["bright_share"] > dark["bright_share"]


def test_the_look_patch_keeps_the_light_inside_its_range(tmp_path):
    p = _still(str(tmp_path / "still.png"), GROUND, ACCENT)
    patch = FM.look_patch(FM.measure(p))
    assert 10 <= patch["elevationDeg"] <= 70
    assert 90 <= patch["azimuthDeg"] <= 270
    assert patch["post"]["contrast"] > 0 and patch["post"]["saturation"] > 0
    assert 0 <= patch["vignette"]["darkness"] <= 1
    assert 0 < patch["ambient"] <= 1 and 0 < patch["exposure"] <= 2


def test_compare_passes_a_picture_against_itself_and_fails_a_dark_against_a_bright(tmp_path):
    a = FM.measure(_still(str(tmp_path / "a.png"), GROUND, ACCENT))
    b = FM.measure(_still(str(tmp_path / "b.png"), GROUND, ACCENT))
    rows = FM.compare(a, b)
    assert rows and all(r["ok"] for r in rows)

    c = FM.measure(_still(str(tmp_path / "c.png"), "#FFFFFF", ACCENT))
    rows = FM.compare(a, c)
    lp50 = next(r for r in rows if r["metric"] == "l_p50")
    assert lp50["ok"] is False
    assert abs(lp50["a"] - lp50["b"]) > lp50["tolerance"]
