"""Tests for review note anchors: anchoring to scenes, following edits, and detecting stale notes."""
import pytest
from factory import noteanchor


def test_anchor_and_follow_scene_move():
    # 1. a note at t=4.5 inside a scene [3.0, 6.0] anchors with offset_s=1.5;
    #    after the scene starts at 2.0, follow() moves the note to t=3.5 and stale is False
    scenes = [{"id": "s1", "start": 3.0, "end": 6.0}]
    note = {"id": "n1", "t": 4.5, "text": "review comment"}
    anchored = noteanchor.anchor(note, scenes)
    assert anchored["anchor"]["scene_id"] == "s1"
    assert abs(anchored["anchor"]["offset_s"] - 1.5) < 1e-4
    assert abs(anchored["anchor"]["t"] - 4.5) < 1e-4

    moved_scenes = [{"id": "s1", "start": 2.0, "end": 5.0}]
    followed = noteanchor.follow([anchored], moved_scenes)[0]
    assert abs(followed["t"] - 3.5) < 1e-4
    assert followed["stale"] is False


def test_follow_marks_stale_when_scene_trimmed():
    # 2. the scene is trimmed to 1.0 s duration -> follow() marks stale=True and keeps t
    scenes = [{"id": "s1", "start": 3.0, "end": 6.0}]
    note = {"id": "n1", "t": 4.5}
    anchored = noteanchor.anchor(note, scenes)

    trimmed_scenes = [{"id": "s1", "start": 3.0, "end": 4.0}]
    followed = noteanchor.follow([anchored], trimmed_scenes)[0]
    assert followed["stale"] is True
    assert abs(followed["t"] - 4.5) < 1e-4


def test_follow_leaves_unanchored_note_unchanged():
    # 3. a note with no anchor is returned unchanged by follow()
    note = {"id": "n_unanchored", "t": 2.5, "text": "fresh note"}
    scenes = [{"id": "s1", "start": 1.0, "end": 4.0}]
    followed = noteanchor.follow([note], scenes)[0]
    assert followed == note
    assert "anchor" not in followed
    assert "stale" not in followed


def test_anchor_is_idempotent():
    # 4. anchor() is idempotent
    scenes = [{"id": "s1", "start": 0.0, "end": 5.0}]
    note = {"id": "n1", "t": 2.0}
    anchored = noteanchor.anchor(note, scenes)
    reanchored = noteanchor.anchor(anchored, scenes)
    assert anchored == reanchored

    other_scenes = [{"id": "s2", "start": 10.0, "end": 20.0}]
    assert noteanchor.anchor(anchored, other_scenes) == anchored


def test_problems_reports_disappeared_scene():
    # 5. problems() reports a note whose scene disappeared
    scenes = [{"id": "s1", "start": 0.0, "end": 3.0}]
    note = {"id": "n3", "t": 1.5}
    anchored = noteanchor.anchor(note, scenes)

    probs = noteanchor.problems([anchored], [])
    assert any("the scene it was written on is gone" in p for p in probs)
    assert any("n3" in p for p in probs)


def test_retime_with_speed_scale():
    old_scene = {"id": "s1", "start": 0.0, "end": 4.0}
    new_scene = {"id": "s1", "start": 0.0, "end": 2.0}
    note = {
        "id": "n1",
        "t": 2.0,
        "speed_scale": True,
        "anchor": {"scene_id": "s1", "offset_s": 2.0, "t": 2.0},
    }
    retimed = noteanchor.retime(note, old_scene, new_scene)
    assert abs(retimed["anchor"]["offset_s"] - 1.0) < 1e-4
    assert abs(retimed["t"] - 1.0) < 1e-4
    assert retimed["stale"] is False


def test_retime_without_speed_scale():
    old_scene = {"id": "s1", "start": 0.0, "end": 4.0}
    new_scene = {"id": "s1", "start": 1.0, "end": 5.0}
    note = {
        "id": "n1",
        "t": 2.0,
        "anchor": {"scene_id": "s1", "offset_s": 2.0, "t": 2.0},
    }
    retimed = noteanchor.retime(note, old_scene, new_scene)
    assert abs(retimed["anchor"]["offset_s"] - 2.0) < 1e-4
    assert abs(retimed["t"] - 3.0) < 1e-4
    assert retimed["stale"] is False


def test_anchor_picks_nearest_scene_when_outside():
    scenes = [
        {"id": "s1", "start": 1.0, "end": 3.0},
        {"id": "s2", "start": 4.0, "end": 6.0},
    ]
    # Before all scenes -> picks s1
    before = noteanchor.anchor({"t": 0.5}, scenes)
    assert before["anchor"]["scene_id"] == "s1"
    # Gap between scenes: t=3.2 is closer to s1 (dist 0.2) than s2 (dist 0.8)
    gap = noteanchor.anchor({"t": 3.2}, scenes)
    assert gap["anchor"]["scene_id"] == "s1"
    # After all scenes -> picks s2
    after = noteanchor.anchor({"t": 8.0}, scenes)
    assert after["anchor"]["scene_id"] == "s2"


def test_input_immutability():
    note = {"id": "n1", "t": 2.0, "anchor": {"scene_id": "s1", "offset_s": 1.0, "t": 2.0}}
    scenes = [{"id": "s1", "start": 1.0, "end": 4.0}]
    note_copy = {"id": "n1", "t": 2.0, "anchor": {"scene_id": "s1", "offset_s": 1.0, "t": 2.0}}
    scenes_copy = [{"id": "s1", "start": 1.0, "end": 4.0}]

    noteanchor.follow([note], scenes)
    assert note == note_copy
    assert scenes == scenes_copy

    noteanchor.anchor(note, scenes)
    assert note == note_copy

    noteanchor.retime(note, scenes[0], {"id": "s1", "start": 2.0, "end": 6.0})
    assert note == note_copy

    noteanchor.problems([note], scenes)
    assert note == note_copy
