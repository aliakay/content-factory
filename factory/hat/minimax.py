"""MiniMax H3 clips through the ElevenLabs connector (t508): a cheap draft first, the final only for a draft the
creator approved.

No GPU on the server, so generated clips go through the connector. A clip is drafted at 480p (MiniMax H3 Max: about
30 s to make, the cheapest resolution). The creator watches it and approves it; only then is the final made with the
same prompt and inputs at the chosen quality (768p on H3 Max; 2K/4K, or any clip fed by reference images, on H3,
which upscales a 768p base). The final is a new take, not an upscale of the draft: composition and motion follow the
same prompt and start frame, details can differ.

Every clip spends from the project's approved budget (credits.guard refuses above it) and counts in the project's
spending. The clips of a project live in work/minimax/clips.json.
"""
import json, os, shutil, time, uuid

from . import explainer as X, project as P

DRAFT = "480p"
QUALITIES = ("768p", "2K", "4K")
SECONDS = (5, 15)                    # what both models accept, whole seconds
MAX, PLAIN = "minimax-h3-max", "minimax-h3"
STATES = ("draft", "approved", "final", "failed", "discarded")


class ClipError(P.GateError):
    pass


def model_for(res, refs=False):
    """H3 Max for text/start-frame clips at 480p/768p (faster, better adherence); H3 for references and 2K/4K."""
    return PLAIN if refs or res in ("2K", "4K") else MAX


def rate_key(model, res):
    return f"{model}@{res}"


def estimate(seconds, quality="768p", refs=False):
    """Credits of the draft and of the final, from the learned rates. -> {draft, final, total} (None = unknown)."""
    from .. import credits
    secs = clamp(seconds)
    out = {}
    for what, res in (("draft", DRAFT), ("final", quality)):
        m = model_for(res, refs)
        e = credits.estimate([{"kind": "video", "model": rate_key(m, res), "units": secs, "unit": "s"}])
        out[what] = {"model": m, "resolution": res, "seconds": secs, "credits": None if e["unknown"] else e["total"]}
    known = [x["credits"] for x in out.values()]
    out["total"] = None if None in known else sum(known)
    return out


def rates():
    """Credits per second of a draft and of each final quality (a start-frame or text clip; None = unknown)."""
    from .. import credits
    r = credits.rates()
    return {res: (r.get("video:" + rate_key(model_for(res), res)) or {}).get("rate") for res in (DRAFT,) + QUALITIES}


def clamp(seconds):
    return int(max(SECONDS[0], min(SECONDS[1], round(float(seconds)))))


# ---------------------------------------------------------------- the clip list

def _path(pid, d=None):
    return P.path(pid, "work", "minimax", "clips.json", d=d)


def clips(pid, d=None):
    try:
        return json.load(open(_path(pid, d)))
    except (OSError, ValueError):
        return []


def _save(pid, cs, d=None):
    path = _path(pid, d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    json.dump(cs, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def get(pid, cid, d=None):
    c = next((c for c in clips(pid, d) if c["id"] == cid), None)
    if not c:
        raise ClipError(f"no clip {cid}")
    return c


def _put(pid, clip, d=None):
    cs = [c for c in clips(pid, d) if c["id"] != clip["id"]] + [clip]
    _save(pid, sorted(cs, key=lambda c: c["created"]), d)
    return clip


def spent(pid, d=None):
    """Credits the project's clips have cost (drafts and finals)."""
    return sum((c.get(k) or {}).get("credits") or 0 for c in clips(pid, d) for k in ("draft", "final"))


# ---------------------------------------------------------------- draft, approve, final

def _project_file(pid, rel, d=None):
    base = os.path.realpath(P.path(pid, d=d))
    p = os.path.realpath(os.path.join(base, rel))
    if not p.startswith(base + os.sep) or not os.path.isfile(p):
        raise ClipError(f"{rel}: not a file in the project folder")
    return p


def new(pid, prompt, seconds, quality="768p", start=None, refs=(), d=None, user=None):
    """Register a clip (nothing is generated): its prompt, length, final quality and inputs (project files)."""
    prompt = str(prompt or "").strip()
    if len(prompt) < 12:
        raise ClipError("describe the shot in at least a sentence")
    if quality not in QUALITIES:
        raise ClipError(f"quality must be one of {', '.join(QUALITIES)}")
    if start and refs:
        raise ClipError("a start frame and reference images cannot be combined (MiniMax takes one or the other)")
    for f in [start, *refs] if start else list(refs):
        _project_file(pid, f, d)
    if len(refs) > 4:
        raise ClipError("at most 4 reference images")
    clip = {"id": "c" + uuid.uuid4().hex[:8], "prompt": prompt, "seconds": clamp(seconds), "quality": quality,
            "start": start, "refs": list(refs), "aspect": P.load(pid, d).get("aspect") or "9:16",
            "status": "new", "created": time.time(), "by": user, "flow_id": None}
    return _put(pid, clip, d)


def _inputs(pid, clip, account, d=None):
    """Upload the clip's input files onto its flow (free) -> {node_id: what it is}."""
    from .. import eleven
    if not (clip.get("start") or clip.get("refs")):
        return {}
    if not clip.get("flow_id"):
        clip["flow_id"] = eleven.new_flow(account, name=f"factory {pid} {clip['id']}")
    out = {}
    if clip.get("start"):
        out[eleven.upload(_project_file(pid, clip["start"], d), clip["flow_id"], account)] = "the clip's start frame"
    for i, f in enumerate(clip.get("refs") or []):
        out[eleven.upload(_project_file(pid, f, d), clip["flow_id"], account)] = \
            f"reference image {i + 1} (wire it to reference_images)"
    return out


def _generate(pid, clip, res, d=None, gen=None, con=None):
    from .. import eleven
    p = P.load(pid, d)
    account = p.get("eleven_account")
    refs = bool(clip.get("refs"))
    model = model_for(res, refs)
    inputs = _inputs(pid, clip, account, d)
    path, cost, flow, node = (gen or eleven.video)(
        con or X._con(), clip["prompt"], X.remaining_budget(pid, d), clip["seconds"], account, clip["aspect"],
        clip.get("flow_id"), model=model, inputs=inputs, resolution=res, rate_model=rate_key(model, res),
        frame_aspect=bool(clip.get("start")))
    clip["flow_id"] = clip.get("flow_id") or flow
    keep = P.path(pid, "work", "minimax", f"{clip['id']}_{res}_{int(time.time())}.mp4", d=d)
    os.makedirs(os.path.dirname(keep), exist_ok=True)
    shutil.copyfile(path, keep)                  # the clip lives with its project (the Studio serves it from there)
    return {"file": X._rel(keep), "credits": round(float(cost or 0), 1), "model": model, "resolution": res,
            "node_id": node, "at": time.time()}


def draft(pid, cid, d=None, gen=None, con=None):
    """Make (or remake) the 480p draft of a clip. Spends credits inside the approved budget."""
    clip = get(pid, cid, d)
    if clip["status"] in ("final", "discarded"):
        raise ClipError(f"clip {cid} is {clip['status']}")
    try:
        got = _generate(pid, clip, DRAFT, d, gen, con)
    except Exception as e:
        _put(pid, {**clip, "status": "failed", "busy": None, "error": f"{type(e).__name__}: {e}"[:300]}, d)
        raise
    prev = clip.get("draft")
    if prev:                                     # a remade draft: keep what the earlier one cost
        got["credits"] = round(got["credits"] + prev.get("credits", 0), 1)
    clip.update(status="draft", draft=got, error=None, approved_by=None, busy=None)
    P.event(pid, "clip_draft", d=d, clip=cid, credits=got["credits"])
    return _put(pid, clip, d)


def approve(pid, cid, user=None, d=None):
    """The creator approves a clip's draft: this is what allows its final to be made."""
    clip = get(pid, cid, d)
    if clip["status"] != "draft" or not clip.get("draft"):
        raise ClipError("only a finished draft can be approved")
    clip.update(status="approved", approved_by=user, approved_at=time.time())
    P.event(pid, "clip_approved", d=d, clip=cid, user=user)
    return _put(pid, clip, d)


def final(pid, cid, d=None, gen=None, con=None):
    """The final of an approved clip at its quality. Refused unless the creator approved the draft."""
    clip = get(pid, cid, d)
    if clip["status"] != "approved" or not clip.get("approved_by"):
        raise ClipError("the final is made only after the creator approves the draft")
    try:
        got = _generate(pid, clip, clip["quality"], d, gen, con)
    except Exception as e:
        _put(pid, {**clip, "busy": None, "error": f"{type(e).__name__}: {e}"[:300]}, d)   # stays approved: can be retried
        raise
    clip.update(status="final", final=got, error=None, busy=None)
    P.event(pid, "clip_final", d=d, clip=cid, credits=got["credits"])
    return _put(pid, clip, d)


def mark(pid, cid, busy, d=None):
    """A queued job is working on the clip ("draft" | "final"; None when done)."""
    clip = get(pid, cid, d)
    clip.update(busy=busy, error=None)
    return _put(pid, clip, d)


def discard(pid, cid, d=None):
    clip = get(pid, cid, d)
    if clip.get("busy"):
        raise ClipError("this clip is being made; wait for it to finish")
    clip["status"] = "discarded"
    return _put(pid, clip, d)


def offered(line):
    """A line whose stages make generated video gets the clip card."""
    return any(t in (s.get("tools") or []) for s in line["stages"] for t in ("video_gen", "minimax_draft"))


def card(pid, d=None):
    """What the Studio card shows: the clips (newest first) with their estimates."""
    out = []
    for c in reversed(clips(pid, d)):
        if c["status"] == "discarded":
            continue
        e = estimate(c["seconds"], c["quality"], bool(c.get("refs")))
        out.append({**{k: c.get(k) for k in ("id", "prompt", "seconds", "quality", "start", "refs", "status", "error",
                                             "draft", "final", "approved_by", "busy")}, "estimate": e})
    try:
        left = X.remaining_budget(pid, d)
    except P.GateError:
        left = None
    return {"clips": out, "spent": spent(pid, d), "left": left, "qualities": list(QUALITIES),
            "seconds": list(SECONDS), "rates": rates()}
