"""ElevenLabs generation through the claude.ai ElevenLabs connector (headless Claude + MCP).

No API key needed: a headless Claude turn calls the connector's generate tool, polls the flow run and returns the
signed audio/image/video URL plus its `credit_cost`; we download the file and write the spend to the ledger.
Callers must have shown the user a credit estimate and received approval first (see credits.estimate).
"""
import hashlib, json, os, subprocess, urllib.request

from . import accounts, credits, eleven_api, llm

from .config import FFPROBE, ROOT
OUT = os.path.join(ROOT, "assets", "eleven")
CLAUDE_MODEL = "sonnet"  # Claude only drives the connector tools here; no creative judgement
T = "mcp__claude_ai_ElevenLabs__"
POLL_TOOLS = (T + "creative_get_flow_run_status", T + "creative_get_flow_node", T + "creative_get_flow")


class ElevenError(RuntimeError):
    pass


def _download(url, ext, key):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{key}.{ext}")
    urllib.request.urlretrieve(url, path + ".part")
    os.replace(path + ".part", path)
    return path


def recover(model):
    """The generation may have run even if the reply was malformed: fetch the newest one for `model`
    (URL + credit cost) instead of generating again and paying twice."""
    prompt = f"""Use ElevenLabs tools to READ only (never generate). Call creative_get_generations, take the most recent
generation made with model "{model}" (it was started in the last few minutes), then call
creative_get_flow_run_status on its flow/node to read price.credits and the signed file URL.
Reply ONLY JSON: {{"url": "<signed url>", "credit_cost": <number>, "created": "<time>"}}"""
    data, meta = llm.ask(prompt, tools=(T + "creative_get_generations",) + POLL_TOOLS, timeout=600, mcp=True, model=CLAUDE_MODEL)
    if not isinstance(data, dict) or not data.get("url"):
        raise ElevenError(f"could not recover the generation for {model}")
    return data, meta


def _run(prompt, tools, timeout=900, model=None):
    try:
        data, meta = llm.ask(prompt, tools=tools, timeout=timeout, mcp=True, model=CLAUDE_MODEL)
    except llm.LLMError:
        if not model:
            raise
        return recover(model)
    if not isinstance(data, dict) or not data.get("url"):
        if model:
            return recover(model)
        raise ElevenError(f"no file URL returned: {json.dumps(data)[:300]}")
    return data, meta


def _account(account):
    account = account or accounts.default_eleven()
    acc = accounts.eleven(account)
    if not acc or not accounts.can_use(account):
        raise ElevenError(f"ElevenLabs hesabı kullanılamıyor: {account}")
    return account, acc


def _write(data, ext, key):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{key}.{ext}")
    with open(path + ".part", "wb") as f:
        f.write(data)
    os.replace(path + ".part", path)
    return path


def tts(con, text, voice_id, model="eleven_v4", idea_id=None, approved=None, account=None):
    """Speech for `text` (one take) from the given ElevenLabs account (connector or API key). Returns (mp3_path,
    credit_cost). Cached by (text, voice, model). `approved`: the credit amount the user approved; guard refuses without it."""
    key = "tts_" + hashlib.sha1(f"{model}|{voice_id}|{text}".encode()).hexdigest()[:16]
    cached = os.path.join(OUT, f"{key}.mp3")
    if os.path.exists(cached):
        return cached, 0.0
    account, acc = _account(account)
    credits.guard(con, "tts", model, len(text), approved, account)
    if acc["type"] == "apikey":
        data, cost = eleven_api.tts(acc["key"], text, voice_id, model)
        path = _write(data, "mp3", key)
        credits.record(con, "tts", model, len(text), "char", cost, idea_id, text[:60], account)
        return path, cost
    prompt = f"""Use the ElevenLabs tools. Generate speech with creative_generate_speech using voice_id "{voice_id}"
and model "{model}" with generations_count 1 (exactly one take) for EXACTLY this text (do not change a word):
<<<{text}>>>
Then poll creative_get_flow_run_status (wait between tries) until the generation is finished, and find the signed
mp3 URL of the generated audio. Generate only once. Reply ONLY JSON:
{{"url": "<signed audio url>", "credit_cost": <number from the generate result>, "duration_s": <number or null>}}"""
    with accounts.as_user(acc["owner"]):   # the connector lives on its owner's Claude login
        data, _ = _run(prompt, (T + "creative_generate_speech",) + POLL_TOOLS, model=model)
    path = _download(data["url"], "mp3", key)
    cost = float(data.get("credit_cost") or 0)
    credits.record(con, "tts", model, len(text), "char", cost, idea_id, text[:60], account)
    return path, cost


def generate(con, kind, model, prompt_text, params, units, unit, idea_id=None, ext="mp3", approved=None, account=None):
    """Generic flow generation (sfx / music / image / video) with the given model and params.
    `approved`: credits the user approved for this call; credits.guard refuses without it."""
    key = f"{kind}_" + hashlib.sha1(f"{model}|{prompt_text}|{json.dumps(params, sort_keys=True)}".encode()).hexdigest()[:16]
    cached = os.path.join(OUT, f"{key}.{ext}")
    if os.path.exists(cached):
        return cached, 0.0
    account, acc = _account(account)
    credits.guard(con, kind, model, units, approved, account)
    if acc["type"] == "apikey":
        if kind not in ("music", "sfx"):
            raise ElevenError(f"{kind} yalnızca connector hesabıyla üretilebiliyor")
        before = eleven_api.subscription(acc["key"])["used"]
        secs = float(params.get("duration_seconds") or units)
        data = (eleven_api.music if kind == "music" else eleven_api.sound)(acc["key"], prompt_text, secs)
        path = _write(data, ext, key)
        cost = float(max(0, eleven_api.subscription(acc["key"])["used"] - before))   # measured from the balance
        credits.record(con, kind, model, units, unit, cost, idea_id, prompt_text[:60], account)
        return path, cost
    tool = {"image": "creative_generate_image", "video": "creative_generate_video"}.get(kind, "creative_generate_in_flow")
    prompt = f"""Use the ElevenLabs tools. Run ONE {kind} generation with model "{model}" and these parameters:
{json.dumps(params)}
Prompt: <<<{prompt_text}>>>
Use {tool} (if it needs a flow, create the node with the given model and run only that node). Poll
creative_get_flow_run_status until finished and find the signed URL of the generated file. Generate only once.
The credit cost is in the run status as price.credits (or credit_cost). Reply ONLY JSON, nothing else:
{{"url": "<signed file url>", "credit_cost": <number>}}"""
    tools = (T + tool, T + "creative_create_flow", T + "creative_add_flow_node", T + "creative_run_flow_nodes",
             T + "creative_update_node", T + "creative_get_model_schema") + POLL_TOOLS
    with accounts.as_user(acc["owner"]):
        data, _ = _run(prompt, tools, timeout=1500, model=model)
    path = _download(data["url"], ext, key)
    cost = float(data.get("credit_cost") or 0)
    credits.record(con, kind, model, units, unit, cost, idea_id, prompt_text[:60], account)
    return path, cost


IMAGE_MODEL = "gpt-image-2"


def image(con, prompt_text, approved, account=None, aspect="9:16", flow_id=None, refs=(), idea_id=None, model=IMAGE_MODEL):
    """One illustration (png) through the connector, on flow `flow_id` (a series keeps all its images on one flow).
    `refs` = node ids of earlier images on that flow (character sheets, the previous plate): the new image is made
    from them with creative_edit_image so characters and style stay the same. Returns (path, cost, flow_id, node_id).
    Cached by (prompt, refs, aspect)."""
    key = "img_" + hashlib.sha1(f"{model}|{aspect}|{','.join(refs)}|{prompt_text}".encode()).hexdigest()[:16]
    cached = os.path.join(OUT, f"{key}.png")
    meta_path = cached + ".json"
    if os.path.exists(cached) and os.path.exists(meta_path):
        m = json.load(open(meta_path))
        return cached, 0.0, m.get("flow_id"), m.get("node_id")
    account, acc = _account(account)
    if acc["type"] == "apikey":
        raise ElevenError("görsel üretimi yalnızca connector hesabıyla yapılabiliyor")
    credits.guard(con, "image", model, 1, approved, account)
    ratio = "2:3" if aspect == "9:16" else "3:2"
    if refs:
        how = (f"Use creative_edit_image on flow_id \"{flow_id}\" with connect_from {json.dumps(list(refs))} (these nodes "
               f"are the reference images: keep their characters, faces, outfits, colours and drawing style exactly) and "
               f"this prompt.")
    else:
        where = f' on flow_id "{flow_id}"' if flow_id else " (it creates a flow)"
        how = f'Use creative_generate_image{where} with model "{model}" and this prompt.'
    prompt = f"""Use the ElevenLabs tools. {how} Aspect ratio {ratio} (portrait for a 9:16 video, landscape for 16:9);
exactly ONE image (generations_count 1). Prompt: <<<{prompt_text}>>>
Poll creative_get_flow_run_status until finished, then read the signed image URL. Generate only once.
Reply ONLY JSON: {{"url": "<signed image url>", "credit_cost": <number>, "flow_id": "<flow id>", "node_id": "<the
generated image node id>"}}"""
    tools = (T + "creative_generate_image", T + "creative_edit_image", T + "creative_get_model_schema") + POLL_TOOLS
    with accounts.as_user(acc["owner"]):
        data, _ = _run(prompt, tools, timeout=1200, model=model)
    path = _download(data["url"], "png", key)
    cost = float(data.get("credit_cost") or 0)
    json.dump({"flow_id": data.get("flow_id") or flow_id, "node_id": data.get("node_id"), "prompt": prompt_text,
               "refs": list(refs)}, open(meta_path, "w"))
    credits.record(con, "image", model, 1, "img", cost, idea_id, prompt_text[:60], account)
    return path, cost, data.get("flow_id") or flow_id, data.get("node_id")


def media_duration(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                          "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return float(out.strip() or 0)


def avatar_node(flow_id):
    """Find the avatar node the creator placed (Avatar Picker) on their avatar flow. Read-only, no credits."""
    prompt = f"""Use the ElevenLabs tools to READ only (never generate, never add or change nodes). Call
creative_get_flow for flow_id "{flow_id}" and find nodes whose type or node_type is "avatar".
Reply ONLY JSON: {{"avatar_nodes": [{{"node_id": "...", "label": "...", "status": "..."}}], "node_count": <int>}}"""
    data, _ = llm.ask(prompt, tools=(T + "creative_get_flow",), timeout=300, mcp=True, model=CLAUDE_MODEL)
    return data


def list_voices():
    """Voices of the ElevenLabs account behind the current user's claude.ai connector (read-only, no credits)."""
    prompt = """Use the ElevenLabs tools to READ only. Call creative_list_voices (all pages) and list the account's own
voices first (cloned / professional / generated), then at most 15 library voices.
Reply ONLY JSON: {"voices": [{"voice_id": "...", "name": "...", "category": "...", "language": "<2-letter code>",
"note": "accent/age/gender if known", "preview_url": "... or null"}]}"""
    data, _ = llm.ask(prompt, tools=(T + "creative_list_voices",), timeout=600, mcp=True, model=CLAUDE_MODEL)
    out = data.get("voices") if isinstance(data, dict) else data
    if not isinstance(out, list):
        raise ElevenError("ses listesi okunamadı")
    return [v for v in out if isinstance(v, dict) and v.get("voice_id")]
