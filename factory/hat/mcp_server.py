"""factory-tools: the tool registry as a stdio MCP server, so a stage agent (Claude Code or Codex CLI) calls our tools.

One server process serves one stage run. Its environment says which project and stage it works for and which tools
the manifest allows; nothing else is listed or callable:
  HAT_PROJECT=<id>  HAT_STAGE=<stage>  HAT_TOOLS=<comma list>  [HAT_DIR=<projects dir>]  [HAT_USER=<user>]

Transport: newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio). Methods: initialize, tools/list, tools/call,
ping; notifications are accepted silently. Logs go to stderr only (stdout is the protocol).
Run: python -m factory.hat.mcp_server
"""
import json, os, sys

PROTOCOL = "2025-06-18"
NAME = "factory"


def _ctx_and_allowed():
    from . import tools as T
    ctx = T.Ctx(os.environ["HAT_PROJECT"], os.environ.get("HAT_STAGE") or None, os.environ.get("HAT_DIR") or None,
                os.environ.get("HAT_USER") or None)
    allowed = [n for n in os.environ.get("HAT_TOOLS", "").split(",") if n]
    return ctx, allowed


def _listing(allowed):
    from . import tools as T
    return [{"name": t["name"], "description": t["summary"] + ("" if t["available"] else f" [unavailable: {t['why']}]"),
             "inputSchema": t["schema"]} for t in T.describe(allowed, agent_only=True)]


def handle(msg, ctx, allowed):
    """One request -> one response dict (None for notifications)."""
    from . import tools as T
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:                      # a notification (initialized, cancelled, ...)
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": NAME, "version": "1"},
            "instructions": "Content Factory production tools for one project stage. Hand in the stage output with "
                            "submit_artifact; it must be accepted."}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": _listing(allowed)}}
    if method == "tools/call":
        name = params.get("name")
        if name not in allowed:
            return _text(mid, f"tool '{name}' is not allowed in this stage", True)
        try:
            out = T.call(name, ctx, params.get("arguments") or {})
        except T.ToolError as e:
            return _text(mid, str(e), True)
        return _text(mid, json.dumps(out, ensure_ascii=False, default=str), False)
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}}


def _text(mid, text, error):
    return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text[:200000]}], "isError": error}}


def serve(stdin=sys.stdin, stdout=sys.stdout):
    ctx, allowed = _ctx_and_allowed()
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}) + "\n")
            stdout.flush()
            continue
        try:
            resp = handle(msg, ctx, allowed)
        except Exception as e:           # never die on one bad call: the agent gets the error and can go on
            print(f"factory-tools: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            resp = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}
        if resp is not None:
            stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            stdout.flush()


def config(pid, stage, allowed, d=None, user=None):
    """The server entry for a CLI: {command, args, env}."""
    from ..config import ROOT
    env = {"HAT_PROJECT": pid, "HAT_STAGE": stage or "", "HAT_TOOLS": ",".join(allowed), "PYTHONPATH": ROOT}
    if d:
        env["HAT_DIR"] = d
    if user:
        env["HAT_USER"] = user
    return {"command": os.path.join(ROOT, ".venv", "bin", "python"), "args": ["-m", "factory.hat.mcp_server"], "env": env}


if __name__ == "__main__":
    serve()
