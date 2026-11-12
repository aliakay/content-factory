"""Gemini as a text model: the fourth way to run an agent step (next to the Claude/Codex CLIs and OpenRouter).

factory/gemini.py makes media through the Interactions endpoint; this module talks to the same key's text models over
`models/<id>:streamGenerateContent?alt=sse` (REST, stdlib only). Why that endpoint and not the plain one or the
OpenAI-compatible one: tried live on 2026-11-12, a busy model (gemini-3.8-flash) made the plain `generateContent`
hang for the whole socket timeout, while the streaming call answers a 503 (in seconds, at worst ~70 s on a busy
afternoon), so the fallback to the next model happens sooner; a busy model then waits out BUSY_COOLDOWN. The native body also keeps the thought signatures that
Gemini 3 needs back on every function-call turn, and it carries images inline.

What a caller gets:
- `ask()`: one prompt -> text (JSON mode, optional inline images, optional Google Search grounding);
- `run()`: a stage agent over our MCP tools. The loop is openrouter.run (one loop for every API provider); this module
  is only its transport (`chat`), which turns the loop's OpenAI-shaped messages into Gemini contents and back;
- `WebSearch`/`WebFetch` are served as functions here, not as Google's built-in tool: on a free-tier key Search
  grounding exists only on gemini-2.5-flash, and no model mixes built-in search with function calling there, so a
  search is its own small grounded call and the agent can still use our tools in the same turn.

Money: every call is priced from its `usageMetadata` at the published paid-tier list prices below (a free-tier key is
billed $0, so this over-states, never hides, the spend), goes into llm_usage (source `live_gemini`) and into the
`gemini_ledger` under the same monthly ceiling as Gemini media (gemini.guard, CF_GEMINI_MONTHLY_USD).
"""
import base64, concurrent.futures, datetime, html, json, os, re, time, urllib.error, urllib.request

from . import gemini as G
from .config import ROOT

API = G.API
DEFAULT_MODEL = "gemini-3.8-flash"           # "our most intelligent Flash" at $0.75/$3.75 per 1M tokens (2026)
# When a model is busy (503), out of quota (429) or hangs, the next one answers instead. Only flash-class models:
# Pro and the Gemini 4 models have no free-tier quota on the owner's key (429 "limit: 0").
CHAIN = ("gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
SEARCH_MODELS = ("gemini-3.5-flash-lite", "gemini-2.5-flash")   # 3.x search needs a paid key; 2.5 has a free quota
MODELS_CACHE = os.path.join(ROOT, "data", "gemini_text_models.json")
MODELS_TTL = 24 * 3600
REQUEST_TIMEOUT = 240
MAX_IMAGES_BYTES = 15 * 1024 * 1024           # inline request cap is 20 MB; leave room for the text
FETCH_CHARS = 20_000
# Paid-tier list prices, USD per 1M tokens: (valid through, input, output incl. thinking, cached input). Read from
# ai.google.dev/gemini-api/docs/pricing on 2026-11-12; several are introductory prices with a dated step up.
PRICES = {
    "gemini-4-carbon": (("2026-11-30", 2.00, 10.00, 0.10), (None, 4.00, 20.00, 0.20)),
    "gemini-4-argon": (("2026-11-30", 2.00, 10.00, 0.10), (None, 4.00, 20.00, 0.20)),
    "gemini-3.8-flash": (("2026-12-31", 0.75, 3.75, 0.075), (None, 1.50, 7.50, 0.15)),
    "gemini-3.6-flash": (("2026-12-31", 0.75, 3.75, 0.075), (None, 1.50, 7.50, 0.15)),
    "gemini-3.5-flash-lite": ((None, 0.30, 2.50, 0.03),),
    "gemini-3.1-flash-lite": ((None, 0.25, 1.50, 0.025),),
    "gemini-3.1-pro-preview": ((None, 2.00, 12.00, 0.20),),        # prompts <= 200k tokens; above: LONG
    "gemini-3-flash-preview": ((None, 0.50, 3.00, 0.05),),
    "gemini-2.5-pro": ((None, 1.25, 10.00, 0.125),),
    "gemini-2.5-flash": ((None, 0.30, 2.50, 0.03),),
}
LONG = {"gemini-3.1-pro-preview": (4.00, 18.00, 0.40), "gemini-2.5-pro": (2.50, 15.00, 0.25)}
# Not on the pricing page: priced as the dearest model they can stand for, so the ledger never under-counts.
ALIAS = {"gemini-3.7-flash": "gemini-3.8-flash", "gemini-flash-latest": "gemini-3.8-flash",
         "gemini-flash-lite-latest": "gemini-3.5-flash-lite", "gemini-pro-latest": "gemini-3.1-pro-preview"}
SEARCH_USD = {"gemini-2.5": 0.035}            # per grounded prompt (2.5) / per search query (3.x: 0.014)
SEARCH_USD_3 = 0.014
FALLBACK_MODELS = tuple({"id": m, "name": m.replace("gemini-", "Gemini ").replace("-", " ").title()}
                        for m in CHAIN + ("gemini-3.1-pro-preview", "gemini-4-argon", "gemini-4-carbon"))
_DEAD = set()          # models this key cannot use at all (429 with a free-tier limit of 0): skipped from then on
_NO_SEARCH = set()     # models that refused Search grounding on this key
# A model that answered 503/429 is skipped for a while: measured 2026-11-12, gemini-3.8-flash took 70-240 s to say
# "high demand", so asking it first on every call of a busy afternoon doubles each review's wait.
BUSY_COOLDOWN = 600
_BUSY_UNTIL = {}
BUSY_FILE = os.path.join(ROOT, "data", "gemini_busy.json")   # shared by the worker, the MCP servers and cron runs


def _park(model, until):
    """Remember that `model` is out until `until` (epoch s), in this process and on disk. Never fatal."""
    _BUSY_UNTIL[model] = max(_BUSY_UNTIL.get(model, 0), until)
    try:
        data = {k: v for k, v in _load_busy().items() if v > time.time()}
        data[model] = max(data.get(model, 0), until)
        tmp = f"{BUSY_FILE}.{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, BUSY_FILE)
    except OSError:
        pass


def _load_busy():
    try:
        return {k: float(v) for k, v in json.load(open(BUSY_FILE)).items()}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


class GeminiTextError(RuntimeError):
    pass


class _Busy(GeminiTextError):
    """503 / 429 / a hung socket: the next model in the chain may still answer."""


# ---------------------------------------------------------------- prices, models
def _period(model, day=None):
    rows = PRICES.get(model) or PRICES.get(ALIAS.get(model, "")) or PRICES[DEFAULT_MODEL]
    day = day or datetime.date.today().isoformat()
    return next((r for r in rows if r[0] is None or day <= r[0]), rows[-1])


def price(model, prompt=0, cached=0, output=0, searches=0, day=None):
    """Dollars for one call from its token counts (output includes thinking tokens)."""
    _, pin, pout, pcache = _period(model, day)
    if model in LONG and prompt > 200_000:
        pin, pout, pcache = LONG[model]
    usd = (max(0, prompt - cached) * pin + cached * pcache + output * pout) / 1e6
    if searches:   # 2.5 bills a grounded PROMPT once however many queries it ran; 3.x bills each query
        usd += SEARCH_USD["gemini-2.5"] if model.startswith("gemini-2.5") else searches * SEARCH_USD_3
    return round(usd, 6)


def usage(meta):
    """usageMetadata -> ledger columns {input_tokens, cache_read_input_tokens, output_tokens} (+ prompt total)."""
    m = meta or {}
    cached = int(m.get("cachedContentTokenCount") or 0)
    prompt = int(m.get("promptTokenCount") or 0) + int(m.get("toolUsePromptTokenCount") or 0)
    out = int(m.get("candidatesTokenCount") or 0) + int(m.get("thoughtsTokenCount") or 0)
    return {"input_tokens": max(0, prompt - cached), "cache_read_input_tokens": cached,
            "cache_creation_input_tokens": 0, "output_tokens": out, "prompt": prompt}


def _text_model(m):
    mid = str(m.get("name") or "").split("/")[-1]
    skip = ("tts", "image", "lyria", "omni", "robotics", "computer-use", "transcribe", "deep-research",
            "antigravity", "embedding", "banana", "customtools", "gemma")
    return (mid if mid.startswith("gemini-") and "generateContent" in (m.get("supportedGenerationMethods") or ())
            and not any(s in mid for s in skip) else None)


def models(refresh=False):
    """The text models this key lists: [{id, name, context}] for Hesaplar. Cached for a day, never fatal."""
    if not refresh:
        try:
            cached = json.load(open(MODELS_CACHE))
            if time.time() - float(cached.get("at") or 0) < MODELS_TTL and cached.get("models"):
                return cached["models"]
        except (OSError, ValueError, TypeError):
            pass
    try:
        listed = G._req("/models?pageSize=200", timeout=20).get("models") or []
        out = [{"id": _text_model(m), "name": m.get("displayName") or _text_model(m),
                "context": (m.get("inputTokenLimit") or 0) // 1000 or None} for m in listed if _text_model(m)]
        rank = {m: i for i, m in enumerate(CHAIN)}
        out.sort(key=lambda m: (rank.get(m["id"], 99), m["id"]))
        if out:
            os.makedirs(os.path.dirname(MODELS_CACHE), exist_ok=True)
            with open(MODELS_CACHE, "w") as f:
                json.dump({"at": time.time(), "models": out}, f)
            return out
    except (G.GeminiError, OSError, ValueError):
        pass
    return [dict(m) for m in FALLBACK_MODELS]


# ---------------------------------------------------------------- one HTTP call
def _sse(model, body, key, timeout):
    """POST one streamGenerateContent call; -> the decoded `data:` chunks."""
    req = urllib.request.Request(f"{API}/models/{model}:streamGenerateContent?alt=sse", json.dumps(body).encode(),
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json",
                                          "Accept": "text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            chunks = []
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("data:"):
                    try:
                        chunks.append(json.loads(line[5:]))
                    except ValueError:
                        pass
            return chunks
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:6000]
        if (e.code == 429 and "limit: 0" in detail) or e.code == 404:
            _DEAD.add(model)              # this key cannot use it (no quota / retired): the chain moves on
            raise _Busy(f"Gemini {e.code} ({model}): " + _err_text(detail)) from None
        msg = f"Gemini {e.code} ({model}): " + _err_text(detail)
        wait = re.search(r'"retryDelay":\s*"(\d+)s"', detail)
        if e.code == 429 and wait:        # a free-tier day quota (20 requests/model/day): skip it until it resets
            _park(model, time.time() + int(wait.group(1)))
        if e.code in (429, 500, 502, 503, 504):
            raise _Busy(msg) from None
        raise GeminiTextError(msg) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise _Busy(f"Gemini ({model}) yanıt vermedi: {getattr(e, 'reason', e)}") from None


def _err_text(detail):
    try:
        return str(json.loads(detail).get("error", {}).get("message") or detail)[:300]
    except ValueError:
        return detail[:300]


def merge(chunks):
    """SSE chunks -> {parts, usage, finish, grounding}. Adjacent plain text parts are joined; a function call part
    and its thought signature stay exactly as sent (Gemini 3 refuses a replayed call without its signature)."""
    parts, meta, finish, grounding = [], {}, None, None
    for c in chunks:
        if c.get("error"):
            raise GeminiTextError(f"Gemini: {c['error'].get('message') or c['error']}"[:300])
        meta = c.get("usageMetadata") or meta
        for cand in (c.get("candidates") or [])[:1]:
            finish = cand.get("finishReason") or finish
            grounding = cand.get("groundingMetadata") or grounding
            for p in (cand.get("content") or {}).get("parts") or []:
                prev = parts[-1] if parts else None
                if ("text" in p and prev is not None and "text" in prev and bool(p.get("thought")) == bool(prev.get("thought"))
                        and "thoughtSignature" not in prev):
                    prev["text"] += p.get("text") or ""
                    if p.get("thoughtSignature"):
                        prev["thoughtSignature"] = p["thoughtSignature"]
                else:
                    parts.append(dict(p))
    return {"parts": parts, "usage": meta, "finish": finish, "grounding": grounding}


def _chain(model, fallback=True):
    first = model or DEFAULT_MODEL
    pool = fallback if isinstance(fallback, (tuple, list)) else CHAIN   # a caller may name its own quality floor
    rest = [m for m in pool if m != first] if fallback else []
    live = [m for m in [first] + rest if m not in _DEAD] or [first]
    now = time.time()
    if len(live) > 1:                  # a model in its busy cooldown goes last, not away: it may be the only one left
        busy = _load_busy()
        for k, v in _BUSY_UNTIL.items():
            busy[k] = max(busy.get(k, 0), v)
        live.sort(key=lambda m: busy.get(m, 0) > now)
    return live


def generate(body, model=None, key=None, timeout=REQUEST_TIMEOUT, fallback=True, step=None, searches=False):
    """One generation with model fallback. -> merged response + {model, cost_usd, counts}. Writes both ledgers."""
    key = key or G.key()
    started, last = time.time(), None
    _guard(body, model or DEFAULT_MODEL)
    for i, m in enumerate(_chain(model, fallback)):
        left = timeout - (time.time() - started)
        if left <= 5:
            break
        try:
            out = merge(_sse(m, _for_model(body, m), key, min(REQUEST_TIMEOUT, left)))
        except _Busy as e:
            last = e
            _park(m, time.time() + BUSY_COOLDOWN)
            time.sleep(min(2 * (i + 1), 6))
            continue
        counts = usage(out["usage"])
        n_search = len(((out.get("grounding") or {}).get("webSearchQueries")) or []) if searches else 0
        if searches and out.get("grounding") and not n_search:
            n_search = 1
        usd = price(m, counts["prompt"], counts["cache_read_input_tokens"], counts["output_tokens"], n_search)
        _ledger(m, counts, usd, step)
        return {**out, "model": m, "cost_usd": usd, "counts": counts}
    raise GeminiTextError(f"Gemini yanıt vermedi ({', '.join(_chain(model, fallback))}): {last}")


def _for_model(body, model):
    """Model-specific knobs: Gemini 3+ takes a thinking *level*; 2.5 only a budget, which we leave at its default."""
    gc = dict(body.get("generationConfig") or {})
    level = gc.pop("_thinking", None)
    if level and re.match(r"gemini-([3-9]|\d\d)|gemini-(flash|pro)", model):
        gc["thinkingConfig"] = {"thinkingLevel": level}
    return {**body, "generationConfig": gc} if gc else {k: v for k, v in body.items() if k != "generationConfig"}


def _guard(body, model):
    """The monthly ceiling (gemini.guard) before the call: the prompt's own size at the input price, plus a few
    thousand output tokens. It refuses only when the ledger is already at the cap."""
    from .store import connect
    try:
        con = connect()
    except Exception:
        return
    try:
        G.guard(con, price(model, len(json.dumps(body)) // 4, 0, 4000))
    except G.GeminiError as e:
        raise GeminiTextError(str(e)) from None
    finally:
        con.close()


def _ledger(model, counts, usd, step):
    """llm_usage (source live_gemini, the same table as every CLI call) and the dollar ledger. Never raises."""
    from . import llm
    llm._record({"usage": counts, "total_cost_usd": usd}, model, True, provider="gemini", step=step)
    try:
        from .store import connect
        con = connect()
        G.record(con, "text", model, counts["prompt"] + counts["output_tokens"], "tokens", usd, note=step or "")
        con.close()
    except Exception:
        pass


# ---------------------------------------------------------------- one-shot ask
IMAGE_RE = re.compile(r"(/[\w./@+-]+\.(?:png|jpe?g|webp))", re.I)


def prompt_images(prompt, limit=24):
    """Absolute image paths a prompt asks the model to Read: sent inline instead (Gemini has no file tool)."""
    seen = []
    for p in IMAGE_RE.findall(prompt or ""):
        if p not in seen and os.path.isfile(p):
            seen.append(p)
    return seen[:limit]


def image_parts(paths):
    out, total = [], 0
    for p in paths or ():
        try:
            blob = open(p, "rb").read()
        except OSError:
            continue
        if total + len(blob) > MAX_IMAGES_BYTES:
            break
        total += len(blob)
        out.append({"inlineData": {"mimeType": G.MIME.get(os.path.splitext(p)[1].lower(), "image/png"),
                                   "data": base64.b64encode(blob).decode()}})
    return out


def ask(prompt, model=None, images=(), json_out=False, search=False, effort=None, max_tokens=None,
        timeout=600, step=None, system=None, fallback=True):
    """One prompt -> (text, meta). `search` grounds it on Google Search (sources appended, resolved to real URLs).
    `fallback`: True = the whole CHAIN when the model is busy, False = this model only, a tuple = only those."""
    parts = [{"text": prompt}] + image_parts(images)
    if images:
        parts.insert(1, {"text": "Images (in this order): " + ", ".join(os.path.basename(x) for x in images)})
    gc = {}
    if json_out and not search:              # 2.5 refuses JSON mode next to a tool; the prompt asks for JSON anyway
        gc["responseMimeType"] = "application/json"
    if max_tokens:
        gc["maxOutputTokens"] = int(max_tokens)
    if effort in ("minimal", "low", "medium", "high"):
        gc["_thinking"] = effort
    body = {"contents": [{"role": "user", "parts": parts}]}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if gc:
        body["generationConfig"] = gc
    if search:
        out = _grounded(body, model, timeout, step)
    else:
        out = generate(body, model, timeout=timeout, step=step, fallback=fallback)
    text = "".join(p.get("text") or "" for p in out["parts"] if not p.get("thought"))
    srcs = sources(out.get("grounding")) if search else []
    if srcs:
        text += "\n\nSources:\n" + "\n".join(f"- {s['title']}: {s['url']}" for s in srcs)
    if not text.strip():
        raise GeminiTextError(f"Gemini boş yanıt döndü (finish={out.get('finish')}, {out['model']})")
    return text, {"cost_usd": out["cost_usd"], "turns": 1, "effort": effort, "model": out["model"], "sources": srcs}


def _grounded(body, model, timeout, step):
    """A Search-grounded call: the asked model first, then the models whose tier allows grounding on this key."""
    body = {**body, "tools": [{"googleSearch": {}}]}
    last = None
    for m in [model or SEARCH_MODELS[0]] + [x for x in SEARCH_MODELS if x != model]:
        if m in _NO_SEARCH or m in _DEAD:
            continue
        try:
            return generate(body, m, timeout=timeout, fallback=False, step=step, searches=True)
        except GeminiTextError as e:
            last = e
            if " 429 " in str(e) or " 400 " in str(e):
                _NO_SEARCH.add(m)
    raise GeminiTextError(f"Gemini web araması yapılamadı: {last}")


def _resolve(url, timeout=8):
    """Grounding links are vertexaisearch redirects; a source in an artifact must be the page itself."""
    if "grounding-api-redirect" not in url:
        return url
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.geturl()
    except urllib.error.HTTPError as e:            # the redirect itself already told us where it goes
        return e.geturl() if e.geturl() and "grounding-api-redirect" not in e.geturl() else url
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return url


def sources(grounding, limit=10):
    chunks = [(c.get("web") or {}) for c in ((grounding or {}).get("groundingChunks") or [])][:limit]
    chunks = [c for c in chunks if c.get("uri")]
    if not chunks:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        urls = list(ex.map(lambda c: _resolve(c["uri"]), chunks))
    return [{"title": c.get("title") or c.get("domain") or u, "url": u} for c, u in zip(chunks, urls)]


# ---------------------------------------------------------------- web tools for the agent loop
def web_search(query, step=None):
    """`WebSearch` for an agent on Gemini: a grounded answer with its resolved source URLs."""
    query = str(query or "").strip()[:400]
    if not query:
        return "ERROR: empty query"
    text, _ = ask("Search the web and answer precisely, with figures, dates and who said or published each fact. "
                  "Keep it under 250 words and note any disagreement between sources.\n\nQuestion: " + query,
                  search=True, step=step, max_tokens=2000)
    return text


def web_fetch(url, step=None):
    """`WebFetch`: the page as plain text, fetched here (free); a page we cannot read is said so plainly."""
    url = str(url or "").strip()
    if not re.match(r"https?://", url):
        return "ERROR: give a full http(s) URL"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Content Factory research)"})
        with urllib.request.urlopen(req, timeout=25) as r:
            ctype = r.headers.get("Content-Type", "")
            raw = r.read(3_000_000)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return f"ERROR: could not open {url}: {getattr(e, 'reason', e)}"
    if "html" not in ctype and "text" not in ctype and "json" not in ctype:
        return f"ERROR: {url} is {ctype or 'binary'}, not a text page"
    text = raw.decode("utf-8", "replace")
    text = re.sub(r"(?is)<(script|style|noscript|svg|nav|footer)\b.*?</\1>", " ", text)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:FETCH_CHARS] + (" …[truncated]" if len(text) > FETCH_CHARS else "")


LOCAL_TOOLS = {
    "WebSearch": ({"type": "object", "required": ["query"],
                   "properties": {"query": {"type": "string", "description": "What to find out"}}},
                  "Search the web (Google) and get a short sourced answer with the source URLs.",
                  lambda args, step: web_search(args.get("query"), step)),
    "WebFetch": ({"type": "object", "required": ["url"],
                  "properties": {"url": {"type": "string", "description": "A full http(s) URL"}}},
                 "Open one web page and read its text.",
                 lambda args, step: web_fetch(args.get("url"), step)),
}


# ---------------------------------------------------------------- the agent loop's transport
def _contents(messages):
    """The loop's OpenAI-shaped messages -> (systemInstruction, contents). A model turn that came from Gemini is
    replayed from its own parts (signatures included); tool results become functionResponse parts."""
    system, contents, names, real = [], [], {}, set()

    def add(role, parts):
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"] += parts
        else:
            contents.append({"role": role, "parts": parts})

    for msg in messages:
        role, content = msg.get("role"), msg.get("content")
        if role == "system":
            system.append(str(content or ""))
        elif role == "user":
            parts = []
            for c in (content if isinstance(content, list) else [{"type": "text", "text": str(content or "")}]):
                if c.get("type") == "text" and c.get("text"):
                    parts.append({"text": c["text"]})
                elif c.get("type") == "image_url":
                    m = re.match(r"data:([^;]+);base64,(.*)", (c.get("image_url") or {}).get("url") or "", re.S)
                    if m:
                        parts.append({"inlineData": {"mimeType": m.group(1), "data": m.group(2)}})
            if parts:
                add("user", parts)
        elif role == "assistant":
            for c in msg.get("tool_calls") or []:
                names[c.get("id")] = (c.get("function") or {}).get("name")
            if msg.get("_native"):
                real.update((p.get("functionCall") or {}).get("id") for p in msg["_native"])
                add("model", [dict(p) for p in msg["_native"]])
                continue
            parts = [{"text": str(content)}] if content else []
            for c in msg.get("tool_calls") or []:
                fn = c.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                parts.append({"functionCall": {"name": fn.get("name"), "args": args}})
            if parts:
                add("model", parts)
        elif role == "tool":
            cid = msg.get("tool_call_id")
            resp = {"name": names.get(cid) or cid or "tool", "response": {"result": str(content or "")}}
            if cid and cid in real:             # Gemini 3 numbers its calls; the answer must carry the same id
                resp["id"] = cid
            add("user", [{"functionResponse": resp}])
    return ("\n\n".join(system) or None), contents


def _declarations(schemas):
    decl = []
    for s in schemas or ():
        fn = s.get("function") if s.get("type") == "function" else None
        if fn:
            decl.append({"name": fn["name"], "description": (fn.get("description") or "")[:1000],
                         "parametersJsonSchema": fn.get("parameters") or {"type": "object", "properties": {}}})
    return [{"functionDeclarations": decl}] if decl else None


def chat(messages, model=None, tools=None, plugins=None, timeout=REQUEST_TIMEOUT, key=None, retries=2,
         max_tokens=None, reasoning=None, step=None):
    """One turn for openrouter.run's loop, answered in the OpenAI shape it reads. Once the conversation holds a
    Gemini turn the model is pinned (a thought signature is only valid for the model that wrote it)."""
    system, contents = _contents(messages)
    body = {"contents": contents}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    decl = _declarations(tools)
    if decl:
        body["tools"] = decl
    gc = {}
    if max_tokens:
        gc["maxOutputTokens"] = int(max_tokens)
    if reasoning in ("low", "medium", "high"):
        gc["_thinking"] = reasoning
    if gc:
        body["generationConfig"] = gc
    pinned = any(m.get("_native") for m in messages if m.get("role") == "assistant")
    out = generate(body, model, key=key, timeout=timeout, fallback=not pinned, step=step)
    text, calls = [], []
    for i, p in enumerate(out["parts"]):
        if p.get("functionCall"):
            fc = p["functionCall"]
            calls.append({"id": fc.get("id") or f"call_{i}_{fc.get('name')}", "type": "function",
                          "function": {"name": fc.get("name"), "arguments": json.dumps(fc.get("args") or {},
                                                                                     ensure_ascii=False)}})
        elif p.get("text") and not p.get("thought"):
            text.append(p["text"])
    c = out["counts"]
    return {"model": out["model"], "recorded": True,
            "choices": [{"finish_reason": out.get("finish"),
                         "message": {"role": "assistant", "content": "".join(text), "tool_calls": calls or None,
                                     "_native": out["parts"]}}],
            "usage": {"prompt_tokens": c["prompt"], "completion_tokens": c["output_tokens"],
                      "prompt_tokens_details": {"cached_tokens": c["cache_read_input_tokens"]},
                      "cost": out["cost_usd"]}}


BACKEND = {"label": "Gemini", "provider": "gemini", "chat": chat, "key": lambda: G.key(), "server_tools": {},
           "local": LOCAL_TOOLS, "error": GeminiTextError}


def run(prompt, tools=(), timeout=900, model=None, servers=None, budget_usd=None, effort=None, step=None,
        max_tokens=None):
    """A stage agent on Gemini: openrouter.run's loop over our MCP tools, with this module as its transport."""
    from . import openrouter
    return openrouter.run(prompt, tools=tools, timeout=timeout, model=model or DEFAULT_MODEL, servers=servers,
                          budget_usd=budget_usd, effort=effort, step=step, max_tokens=max_tokens, backend=BACKEND)
