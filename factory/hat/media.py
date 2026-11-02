"""Image, video, avatar and lip-sync models the factory can drive through the ElevenLabs connector, and a scored picker.

What is known about each model comes from the schema and guide checks stored in data/elevenlabs_models.json and
data/elevenlabs_avatar_models.json; nothing here is a guess about price (the connector exposes none): `tier` is the
cost-relevant knob as the guide describes it (1 cheap/fast .. 3 heavy), used only to rank. A stage agent asks the
picker with what it has (inputs) and what it needs (tags, seconds, aspect); the picker filters by inputs, then ranks
and says why.
"""

MODELS = [
    # ---------------------------------------------------------------- images
    {"id": "gpt-image-2", "family": "image", "name": "GPT Image 2", "inputs": ["prompt"], "optional": ["images"],
     "aspects": ["9:16", "16:9", "1:1", "4:3", "3:4"], "tier": 2, "default": True,
     "good": ["illustration", "text_free", "general", "photoreal"], "note": "14 aspect ratios; quality low/medium/high."},
    {"id": "gpt-image-2.5-sunburst", "family": "image", "name": "GPT Image 2.5 Sunburst", "inputs": ["prompt", "images"],
     "aspects": ["9:16", "16:9", "1:1"], "tier": 2,
     "good": ["refs", "consistent_character", "edit", "illustration"],
     "note": "The connector's model for an image made from reference images (character sheets, an earlier plate)."},
    {"id": "gemini-3-pro-image", "family": "image", "name": "Nano Banana Pro", "inputs": ["prompt"], "optional": ["images"],
     "aspects": ["9:16", "16:9", "1:1", "4:3", "3:4"], "tier": 2, "good": ["photoreal", "refs", "general"],
     "note": "10 aspect ratios; resolution 1K/2K/4K is the cost knob."},
    # ---------------------------------------------------------------- video
    {"id": "bytedance-seedance-v2.5", "family": "video", "name": "Seedance 2.5", "inputs": ["prompt"],
     "optional": ["start_frame", "end_frame", "reference_images", "reference_videos", "reference_audios"],
     "aspects": ["9:16", "16:9", "1:1", "4:3", "3:4", "21:9"], "seconds": [4, 30], "tier": 2, "default": True,
     "good": ["general", "long", "start_frame", "refs", "sound"],
     "note": "4-30 s; resolution 480p/720p/1080p, duration and generate_audio set the cost."},
    {"id": "veo-3.1-generate-001", "family": "video", "name": "Veo 3.1", "inputs": ["prompt"],
     "optional": ["start_frame", "end_frame", "reference_images"], "aspects": ["9:16", "16:9"], "seconds": [4, 8],
     "steps": [4, 6, 8], "tier": 3, "good": ["cinematic", "sound", "photoreal", "start_frame"],
     "note": "4, 6 or 8 s; negative_prompt; 720p/1080p/4K."},
    {"id": "ltx-audio-to-video", "family": "video", "name": "LTX audio-to-video", "inputs": ["audio"],
     "optional": ["image", "prompt"], "aspects": ["9:16", "16:9"], "tier": 2, "good": ["music_reactive"],
     "note": "Video that moves with the audio; not a talking-head model."},
    # ---------------------------------------------------------------- avatars: a still image + audio -> talking video
    {"id": "creatify-aurora", "family": "avatar", "name": "Creatify Aurora", "inputs": ["image", "audio"],
     "optional": ["prompt"], "aspects": ["9:16", "16:9", "1:1"], "tier": 2, "default": True,
     "good": ["talking_head", "long", "presenter"], "note": "Built for talking heads; long continuous speech."},
    {"id": "heygen-avatar4", "family": "avatar", "name": "HeyGen Avatar 4", "inputs": ["image", "audio"],
     "aspects": ["9:16", "16:9", "1:1"], "tier": 3, "good": ["talking_head", "presenter", "expressive"],
     "note": "1080p only; talking_style stable|expressive; length follows the audio."},
    {"id": "bytedance-omnihuman-v1.5", "family": "avatar", "name": "OmniHuman 1.5", "inputs": ["image", "audio"],
     "aspects": ["9:16", "16:9"], "tier": 3, "good": ["talking_head", "full_body"],
     "note": "Needs a well-lit, front-facing image and clear audio."},
    {"id": "veed-fabric-1-fast", "family": "avatar", "name": "Veed Fabric 1 Fast", "inputs": ["image", "audio"],
     "aspects": ["9:16", "16:9"], "tier": 1, "good": ["talking_head", "cheap", "fast"],
     "note": "Cheap and fast image-plus-audio talking head."},
    {"id": "minimax-h3-max-lipsync", "family": "avatar", "name": "MiniMax H3 lip-sync", "inputs": ["image", "audio"],
     "aspects": ["9:16", "16:9", "1:1"], "seconds": [5, 14.8], "tier": 1,
     "good": ["illustration", "animal", "character", "short", "cheap"],
     "note": "Audio 5-14.8 s; works on illustrations and animals; one speaker per image (the no-GPU path for FreeVideo-style clips)."},
    # ---------------------------------------------------------------- lip-sync on an existing video
    {"id": "sync-lipsync-v3", "family": "lipsync", "name": "Sync Lipsync 3", "inputs": ["video", "audio"],
     "aspects": ["any"], "tier": 2, "default": True, "good": ["dubbing", "relipsync"],
     "note": "Re-lip-syncs an existing video to new audio (dubbing)."},
    {"id": "veed-lipsync-v2", "family": "lipsync", "name": "Veed Lipsync 2", "inputs": ["video", "audio"],
     "aspects": ["any"], "tier": 1, "good": ["dubbing", "cheap"], "note": "Video-to-video lip-sync."},
    {"id": "runway-act-two", "family": "performance", "name": "Runway Act-Two", "inputs": ["image", "video"],
     "aspects": ["9:16", "16:9"], "tier": 3, "good": ["performance", "character"],
     "note": "Moves the image's subject with a driving performance video; not audio-driven."},
]
FAMILIES = sorted({m["family"] for m in MODELS})


def get(model_id):
    return next((m for m in MODELS if m["id"] == model_id), None)


def pick(family, have=(), need=(), seconds=None, aspect=None, cheap=False):
    """Models of `family` the inputs in `have` can feed, best first: [{id, name, score, why[], note}].
    `need`: tags wanted (see each model's `good`); `seconds`: the clip length; `cheap`: prefer low tiers."""
    have, need = set(have) | {"prompt"}, list(need)
    out = []
    for m in MODELS:
        if m["family"] != family:
            continue
        missing = [i for i in m["inputs"] if i not in have]
        if missing:
            continue
        score, why = 0.0, []
        for tag in need:
            if tag in m["good"]:
                score += 2
                why.append(f"good for {tag}")
        if seconds and m.get("seconds"):
            lo, hi = m["seconds"]
            if lo <= seconds <= hi:
                score += 1
                why.append(f"{seconds} s fits {lo}-{hi} s")
            else:
                score -= 3
                why.append(f"{seconds} s is outside {lo}-{hi} s")
        if aspect and "any" not in m["aspects"] and aspect not in m["aspects"]:
            score -= 3
            why.append(f"no {aspect}")
        score += (1.5 if cheap else 0.3) * (3 - m["tier"])
        if m.get("default"):
            score += 0.5
            why.append("the connector's default")
        out.append({"id": m["id"], "name": m["name"], "score": round(score, 2), "why": why, "note": m["note"]})
    return sorted(out, key=lambda x: -x["score"])
