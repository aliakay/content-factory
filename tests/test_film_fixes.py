"""Fixes found by the first real 3D film (projects/122, the juice-box straw): board-colour shades are not new colours,
Turkish "bir" / "yüz" are not always figures, a scene note naming a "headline" is not a design note, and a scene
whose JavaScript throws becomes a finding the repair round can act on."""
from factory import words
from factory.hat import direction, shortplan as SP


def test_a_shade_of_a_board_colour_is_the_same_colour():
    for c, base in [("#2c3152", "#20243a"), ("#b23a3e", "#ff5a5f"), ("#b9782a", "#ffb347"), ("#c9c2b4", "#f4efe6")]:
        assert direction._shade_of(c, base), (c, base)
    for c in ("#00ff88", "#3a7cff", "#ff5a9f", "#111111", "#7a1f22"):
        assert not any(direction._shade_of(c, b) for b in ("#20243a", "#f4efe6", "#959499", "#ffb347", "#ff5a5f", "#7c5cff")), c


def test_bir_and_yuz_are_figures_only_when_they_count():
    for t in ("dokuz yüz", "Fiyat yüz avroyu geçti", "üç yüz kişi", "yüzde 72", "1989"):
        assert words.has_number(t), t
    for t in ("Delik geniş yüzün köşesine yakın, pipet o yüz kadar uzun.",
              "Delik de kullanana kadar soyulan bir katmanla kapalı kalıyor."):
        assert not words.has_number(t), t


def test_design_words_match_word_starts_only():
    assert not SP.needs_design("the cta headline is cropped, keep it in the top third")
    assert SP.needs_design("satırları yeniden böl")
    assert not SP.needs_design("")


def test_scene_js_errors_become_findings():
    errs = ["scene cta js: Cannot read properties of undefined (reading 'split') | at split (fxlib.js:10)",
            "scene other js: boom", "unrelated console line"]
    out = SP.js_findings(errs, {"cta", "hook"})
    assert len(out) == 1 and out[0].startswith("scene cta: its JavaScript throws") and "split" in out[0]


def test_new_action_verbs_count():
    for t in ("the straw slams into the corner", "a foil layer peels away", "the box tilts and the straw rolls"):
        assert words.has_action(t, "en"), t
