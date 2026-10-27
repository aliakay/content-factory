"""Claude via the local Claude Code CLI in headless mode (no separate API key needed)."""
import json, os, re, subprocess

from .config import CLAUDE, WORK as WORKDIR
MODEL = "opus"  # creative steps (script, motion design, art direction, revise, style); checks/tools pass "sonnet"


class LLMError(RuntimeError):
    pass


def _caller():
    """'module.function' of the factory code that asked Claude (the step name in the usage ledger)."""
    import inspect
    for fr in inspect.stack()[2:]:
        mod = os.path.splitext(os.path.basename(fr.filename))[0]
        if mod != "llm":
            return f"{mod}.{fr.function}"
    return "?"


def _record(out, model, ok):
    """One row per headless call in factory.db llm_usage (Studio > Pano > Claude kullanımı). Never raises."""
    try:
        from .store import connect, now
        u = (out or {}).get("usage") or {}
        used = list(((out or {}).get("modelUsage") or {}).keys())
        con = connect()
        con.execute("INSERT INTO llm_usage (at, step, model, job_id, job_kind, prod_id, user, input, cache_write, cache_read,"
                    " output, cost_usd, ok, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (now(), _caller(), ",".join(used) or model, os.environ.get("FACTORY_JOB_ID"),
                     os.environ.get("FACTORY_JOB_KIND"), os.environ.get("FACTORY_PROD_ID"), os.environ.get("FACTORY_USER"),
                     u.get("input_tokens", 0), u.get("cache_creation_input_tokens", 0), u.get("cache_read_input_tokens", 0),
                     u.get("output_tokens", 0), (out or {}).get("total_cost_usd") or 0, int(ok), "live"))
        con.commit()
        con.close()
    except Exception:
        pass


def extract_json(text):
    """First JSON object/array in `text` (handles ```json fences and surrounding prose)."""
    m = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if m:
        text = m.group(1)
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise LLMError("no JSON in model output: " + text.strip()[:300].replace("\n", " "))
    s = min(starts)
    opener = text[s]
    closer = "}" if opener == "{" else "]"
    depth, in_str, esc = 0, False, False
    for i in range(s, len(text)):
        ch = text[i]
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return json.loads(text[s:i + 1])
    raise LLMError("unterminated JSON in model output")


def ask(prompt, tools=("Read",), timeout=900, model=None, retries=2, mcp=False):
    text, meta = ask_text(prompt, tools, timeout, model, retries, mcp)
    return extract_json(text), meta


def ask_text(prompt, tools=("Read",), timeout=900, model=None, retries=2, mcp=False):
    """Run one headless Claude turn; ask() returns (parsed_json, meta), ask_text() the raw reply text.

    Slim mode: no skills/slash commands and no MCP connectors are loaded (the craft rules travel in the prompt),
    which cuts the per-call context ~8x. Built-in tools (Read, WebSearch, WebFetch) still work.
    Transient failures (rate limits, concurrent sessions) are retried with backoff.
    """
    import time
    cmd = [CLAUDE, "-p", prompt, "--output-format", "json", "--allowedTools", ",".join(tools),
           "--disable-slash-commands"]
    if not mcp:  # connectors (e.g. ElevenLabs) are only loaded when a step needs them
        cmd.append("--strict-mcp-config")
    cmd += ["--model", model or MODEL]
    os.makedirs(WORKDIR, exist_ok=True)
    from . import accounts
    try:
        env = {**os.environ, **accounts.claude_env()}   # the member's own Claude subscription, if a member started it
    except accounts.NoClaude as e:
        raise LLMError(str(e)) from None
    if mcp and env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        raise LLMError("claude.ai connectors only work on the owner's login; use an ElevenLabs API-key account")
    last = ""
    for attempt in range(retries + 1):
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=WORKDIR,
                           stdin=subprocess.DEVNULL, env=env)
        out = None
        try:
            out = json.loads(p.stdout) if p.stdout.strip() else None
        except ValueError:
            pass
        if out:
            _record(out, model or MODEL, p.returncode == 0 and not out.get("is_error"))
        if p.returncode == 0 and out and not out.get("is_error"):
            return out.get("result", ""), {"cost_usd": out.get("total_cost_usd"), "turns": out.get("num_turns")}
        last = (f"exit {p.returncode}: " + ((out or {}).get("result") or p.stderr[-300:] or p.stdout[-300:])).strip()
        if "limit" in last.lower() and "usage" in last.lower():
            break  # subscription usage limit: retrying won't help
        if attempt < retries:
            time.sleep(10 * (attempt + 1))
    raise LLMError(f"claude failed: {last}")
