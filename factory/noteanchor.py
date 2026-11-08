"""Review note anchors: keep absolute-time frame comments and animatic notes anchored to scenes across edits.

When a scene is trimmed, reordered, slipped or re-timed, notes stay anchored to their scene and offset,
and their absolute time `t` is re-derived. Notes whose scene disappeared or whose offset falls outside
the new duration are marked stale.
"""
import copy

TOL = 1e-4


def _scene_span(sc):
    start = float(sc.get("start", 0.0))
    if "end" in sc and sc["end"] is not None:
        end = float(sc["end"])
    else:
        end = start + float(sc.get("duration", 0.0))
    return start, end


def _scene_duration(sc):
    if "duration" in sc and sc.get("end") is None:
        return float(sc["duration"])
    start, end = _scene_span(sc)
    return end - start


def _distance(t, sc):
    start, end = _scene_span(sc)
    if start <= t < end:
        return 0.0
    if t < start:
        return start - t
    return t - end


def _fits(offset_s, duration):
    return -TOL <= offset_s <= duration + TOL


def _find_scene(t, scenes):
    for sc in scenes:
        start, end = _scene_span(sc)
        if start <= t < end:
            return sc
    return min(scenes, key=lambda sc: _distance(t, sc))


def anchor(note, scenes):
    """Anchor a note to the scene containing note["t"], or the nearest scene if none contains it.

    A note that already carries a valid anchor keeps it (idempotent).
    """
    out = copy.deepcopy(note)
    anc = out.get("anchor")
    if isinstance(anc, dict) and anc.get("scene_id") is not None and anc.get("offset_s") is not None:
        return out
    if not scenes:
        return out
    t = float(out.get("t", 0.0))
    sc = _find_scene(t, scenes)
    offset_s = round(t - float(sc.get("start", 0.0)), 6)
    out["anchor"] = {
        "scene_id": sc["id"],
        "offset_s": offset_s,
        "t": t,
    }
    return out


def follow(notes, scenes):
    """Re-derive every note's 't' from its anchor and the new scene starts.

    When the anchor's scene is gone or the offset no longer fits inside the new duration,
    marks stale=True and keeps the last known 't'. Notes without an anchor are unchanged.
    """
    out_notes = []
    by_id = {sc["id"]: sc for sc in (scenes or []) if "id" in sc}
    for n in (notes or []):
        item = copy.deepcopy(n)
        anc = item.get("anchor")
        if not isinstance(anc, dict) or anc.get("scene_id") is None or anc.get("offset_s") is None:
            out_notes.append(item)
            continue

        sid = anc["scene_id"]
        sc = by_id.get(sid)
        if sc is None:
            item["stale"] = True
            if "t" not in item and "t" in anc:
                item["t"] = anc["t"]
            out_notes.append(item)
            continue

        dur = _scene_duration(sc)
        offset = float(anc["offset_s"])
        if not _fits(offset, dur):
            item["stale"] = True
            if "t" not in item and "t" in anc:
                item["t"] = anc["t"]
        else:
            item["stale"] = False
            new_t = round(float(sc.get("start", 0.0)) + offset, 6)
            item["t"] = new_t
            item["anchor"]["t"] = new_t
        out_notes.append(item)
    return out_notes


def retime(note, old_scene, new_scene):
    """Update anchor when a scene changed start or duration.

    If note carries speed_scale=True, the offset scales with the speed change.
    """
    out = copy.deepcopy(note)
    anc = out.get("anchor")
    if not isinstance(anc, dict) or anc.get("offset_s") is None:
        return out

    old_dur = _scene_duration(old_scene)
    new_dur = _scene_duration(new_scene)
    offset = float(anc["offset_s"])
    if (out.get("speed_scale") is True or anc.get("speed_scale") is True) and old_dur > 0:
        offset = offset * (new_dur / old_dur)

    offset = round(offset, 6)
    out["anchor"]["offset_s"] = offset
    if "id" in new_scene:
        out["anchor"]["scene_id"] = new_scene["id"]

    if not _fits(offset, new_dur):
        out["stale"] = True
        if "t" not in out and "t" in anc:
            out["t"] = anc["t"]
    else:
        out["stale"] = False
        new_t = round(float(new_scene.get("start", 0.0)) + offset, 6)
        out["t"] = new_t
        out["anchor"]["t"] = new_t
    return out


def problems(notes, scenes):
    """List issues where anchored notes refer to missing scenes or exceed durations."""
    out = []
    by_id = {sc["id"]: sc for sc in (scenes or []) if "id" in sc}
    for i, n in enumerate(notes or []):
        nid = n.get("id") or str(i)
        anc = n.get("anchor")
        if not isinstance(anc, dict) or anc.get("scene_id") is None:
            if n.get("stale"):
                out.append(f"note {nid}: note is stale")
            continue

        sid = anc["scene_id"]
        if sid not in by_id:
            out.append(f"note {nid}: the scene it was written on is gone")
            continue

        sc = by_id[sid]
        dur = _scene_duration(sc)
        offset = float(anc.get("offset_s", 0.0))
        if not _fits(offset, dur):
            out.append(f"note {nid}: offset {offset:g} s no longer fits inside scene duration ({dur:g} s)")
    return out
