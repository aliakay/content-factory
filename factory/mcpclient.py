"""A minimal MCP stdio client: the other half of factory/hat/mcp_server.py.

The Claude and Codex CLIs are MCP clients themselves, so our tools reach the stage agents through them. An
OpenRouter model (factory/openrouter.py) is a plain HTTP chat completion and brings no client of its own: this module
starts the same stdio server, lists its tools as function schemas and runs the calls the model asks for.

Transport: newline-delimited JSON-RPC 2.0 on the server's stdin/stdout (MCP stdio). Nothing else is spoken.
"""
import json, os, selectors, subprocess

from .config import ROOT

PROTOCOL = "2025-06-18"
CLIENT = {"name": "content-factory", "version": "1"}


class MCPError(RuntimeError):
    pass


class StdioServer:
    """One stdio MCP server process ({name, command, args, env} as factory/hat/mcp_server.py:config writes it)."""

    def __init__(self, name, command, args=(), env=None, cwd=None):
        self.name = name
        self.command = command
        self.args = list(args or ())
        self.env = {k: str(v) for k, v in (env or {}).items()}
        self.cwd = cwd or ROOT
        self.proc = None
        self._id = 0

    # ---- lifecycle ----
    def start(self):
        if self.proc:
            return self
        env = {**os.environ, **self.env}
        try:
            self.proc = subprocess.Popen([self.command, *self.args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
                                         cwd=self.cwd, env=env)
        except (OSError, ValueError) as e:
            raise MCPError(f"MCP server '{self.name}' could not start: {e}") from None
        self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                    "clientInfo": CLIENT}, timeout=60)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def close(self):
        p, self.proc = self.proc, None
        if not p:
            return
        try:
            if p.stdin:
                p.stdin.close()
        except OSError:
            pass
        try:
            p.terminate()
            p.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            try:
                p.kill()
            except OSError:
                pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()

    # ---- protocol ----
    def _send(self, msg):
        if not self.proc or not self.proc.stdin:
            raise MCPError(f"MCP server '{self.name}' is not running")
        try:
            self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError) as e:
            raise MCPError(f"MCP server '{self.name}' closed its input: {e}") from None

    def _read(self, timeout):
        """One JSON message from the server, or None when the wait ran out."""
        if not self.proc or not self.proc.stdout:
            raise MCPError(f"MCP server '{self.name}' is not running")
        sel = selectors.DefaultSelector()
        sel.register(self.proc.stdout, selectors.EVENT_READ)
        try:
            if not sel.select(timeout):
                return None
        finally:
            sel.close()
        line = self.proc.stdout.readline()
        if not line:
            raise MCPError(f"MCP server '{self.name}' ended the session")
        try:
            return json.loads(line)
        except ValueError:
            return {}                      # a stray log line: ignore it and keep reading

    def request(self, method, params=None, timeout=600):
        self._id += 1
        mid = self._id
        self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
        while True:
            msg = self._read(timeout)
            if msg is None:
                raise MCPError(f"MCP server '{self.name}' did not answer {method} in {timeout} s")
            if not isinstance(msg, dict) or msg.get("id") != mid:
                continue                   # a notification or another request's reply
            if msg.get("error"):
                raise MCPError(str(msg["error"].get("message") or msg["error"])[:400])
            return msg.get("result") or {}

    # ---- tools ----
    def tools(self, allowed=()):
        """The server's tool schemas (optionally only `allowed` names)."""
        listed = self.request("tools/list").get("tools") or []
        keep = set(allowed or ())
        return [t for t in listed if isinstance(t, dict) and t.get("name") and (not keep or t["name"] in keep)]

    def call(self, name, arguments=None, timeout=600):
        """One tool call -> (text, is_error). The server's text content joined with newlines."""
        out = self.request("tools/call", {"name": name, "arguments": arguments or {}}, timeout=timeout)
        parts = [c.get("text", "") for c in out.get("content") or [] if isinstance(c, dict) and c.get("type") == "text"]
        return "\n".join(p for p in parts if p), bool(out.get("isError"))


def open_servers(servers):
    """Start every {name: {command, args, env}} entry; returns {name: StdioServer} (caller closes them)."""
    started = {}
    try:
        for name, spec in (servers or {}).items():
            started[name] = StdioServer(name, spec.get("command"), spec.get("args"), spec.get("env")).start()
    except Exception:
        for s in started.values():
            s.close()
        raise
    return started


def close_servers(started):
    for s in (started or {}).values():
        s.close()
