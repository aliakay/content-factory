"""factory doctor: required checks gate the exit code, optional ones only warn, and no secret is ever printed."""
import json

import pytest

from factory import doctor


def _run_ok(cmd, args=(), timeout=8, cwd=None):
    name = cmd.rsplit("/", 1)[-1]
    if name in ("ffmpeg", "ffprobe"):
        if "-filters" in args:
            return "".join(f" T.. {f} A->A x\n" for f in doctor.FILTERS)
        if "-encoders" in args:
            return " V....D libx264              H.264\n"
        return "ffmpeg version 7.1 Copyright\n"
    if name == "git":
        return "feat/factory-next\n"
    if name == "claude":
        return "2.1.322 (Claude Code)\n"
    return ""


def _browser_ok(root, run):
    return {"status": "ok", "detail": doctor._tr("Chromium 143.0", "Chromium 143.0"), "hint": None}


def _root(tmp_path):
    for name in ("fonts", "work", "out", "data", "motion/node_modules/playwright"):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    (tmp_path / "fonts" / "Anton-Regular.ttf").write_bytes(b"x")
    (tmp_path / "requirements.txt").write_text("numpy>=2\n")
    return tmp_path


def _ok(tr="ok", code="ok"):
    return {"status": "ok", "detail": doctor._tr(tr, tr), "hint": None}


def test_report_shape_and_ok(tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setattr(doctor, "_requirements", lambda r: _ok("packages"))
    monkeypatch.setattr(doctor, "_claude_cli", lambda run: _ok("claude"))
    monkeypatch.setattr(doctor, "_key_checks", lambda uid=None: [])
    monkeypatch.setattr(doctor, "_whisper", lambda: _ok("whisper"))
    monkeypatch.setattr(doctor, "_studio", lambda: _ok("studio"))
    rep = doctor.inspect(root=str(root), run=_run_ok, browser=_browser_ok)
    assert rep["version"] == 1 and rep["ok"] is True
    ids = [c["id"] for c in rep["checks"]]
    assert {"python", "venv", "requirements", "ffmpeg", "ffprobe", "ffmpeg.filters", "browser", "fonts",
            "data", "git"} <= set(ids)
    assert [c for c in rep["checks"] if c["id"] == "git"][0]["status"] == "info"
    assert "✓" in doctor.text(rep)


def test_a_missing_ffmpeg_blocks_the_exit_code(tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setattr(doctor, "_requirements", lambda r: _ok())
    monkeypatch.setattr(doctor, "_claude_cli", lambda run: _ok())
    monkeypatch.setattr(doctor, "_key_checks", lambda uid=None: [])
    monkeypatch.setattr(doctor, "_whisper", lambda: _ok())
    monkeypatch.setattr(doctor, "_studio", lambda: _ok())

    def no_tools(cmd, args=(), timeout=8, cwd=None):
        name = cmd.rsplit("/", 1)[-1]
        return _run_ok(cmd, args, timeout, cwd) if name == "git" else None

    rep = doctor.inspect(root=str(root), run=no_tools, browser=_browser_ok)
    assert rep["ok"] is False
    ff = next(c for c in rep["checks"] if c["id"] == "ffmpeg")
    assert ff["status"] == "fail" and ff["hint"]
    monkeypatch.setattr(doctor, "inspect", lambda **kw: rep)
    assert doctor.main(["--json"]) == 1


def test_optional_checks_never_block(tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setattr(doctor, "_requirements", lambda r: _ok())
    monkeypatch.setattr(doctor, "_claude_cli", lambda run: {"status": "warn", "detail": doctor._tr("not logged in", "giriş yok"),
                                                             "hint": doctor._tr("run claude", "claude çalıştır")})
    monkeypatch.setattr(doctor, "_key_checks", lambda uid=None: [])
    monkeypatch.setattr(doctor, "_whisper", lambda: _ok())
    monkeypatch.setattr(doctor, "_studio", lambda: {"status": "info", "detail": doctor._tr("not running", "çalışmıyor"),
                                                    "hint": None})
    rep = doctor.inspect(root=str(root), run=_run_ok, browser=_browser_ok)
    assert rep["ok"] is True                                  # a warning/info alone is not blocking
    assert any(c["status"] == "warn" for c in rep["checks"])


def test_filters_and_encoder_missing_is_a_failure(tmp_path):
    def run(cmd, args=(), timeout=8, cwd=None):
        name = cmd.rsplit("/", 1)[-1]
        if name == "ffmpeg" and "-filters" in args:
            return " T.. scale V->V\n"
        if name == "ffmpeg" and "-encoders" in args:
            return " V....D h264 H.264\n"
        return _run_ok(cmd, args, timeout, cwd)

    res = doctor._filters("ffmpeg", run)
    assert res["status"] == "fail"
    detail = res["detail"]["tr"]
    assert "loudnorm" in detail and "libx264" in detail


def test_keys_show_only_the_last_four(monkeypatch):
    monkeypatch.setattr(doctor.accounts, "usable_eleven", lambda uid=None: [{"id": "a", "type": "apikey"}])
    monkeypatch.setattr(doctor.accounts, "eleven", lambda aid: {"key": "sk-secret-1234567890abcd"})
    monkeypatch.setattr(doctor.accounts, "gemini_status", lambda uid=None: {"connected": True})
    monkeypatch.setattr(doctor.accounts, "gemini_key", lambda uid=None: "AIza-secret-wxyz")
    monkeypatch.setattr(doctor.accounts, "openrouter_status", lambda uid=None: {"connected": True})
    monkeypatch.setattr(doctor.accounts, "openrouter_key", lambda uid=None: "or-secret-9876")
    checks = doctor._key_checks("ali")
    text = json.dumps(checks, ensure_ascii=False)
    for secret in ("1234567890abcd", "AIza-secret-wxyz", "or-secret-9876"):
        assert secret not in text
    assert "…abcd" in text and "…wxyz" in text and "…9876" in text


def test_online_is_off_by_default(tmp_path, monkeypatch):
    root = _root(tmp_path)
    called = []
    monkeypatch.setattr(doctor, "_requirements", lambda r: _ok())
    monkeypatch.setattr(doctor, "_claude_cli", lambda run: _ok())
    monkeypatch.setattr(doctor, "_key_checks", lambda uid=None: [])
    monkeypatch.setattr(doctor, "_whisper", lambda: _ok())
    monkeypatch.setattr(doctor, "_studio", lambda: _ok())
    monkeypatch.setattr(doctor, "_online", lambda uid=None: called.append(1) or [])
    doctor.inspect(root=str(root), run=_run_ok, browser=_browser_ok)
    assert called == []
    doctor.inspect(root=str(root), run=_run_ok, browser=_browser_ok, online=True)
    assert called == [1]


def test_json_report_is_printed(monkeypatch, capsys):
    rep = {"version": 1, "ok": False,
           "checks": [{"id": "ffmpeg", "required": True, "status": "fail", "detail": "yok", "hint": "kur"}]}
    monkeypatch.setattr(doctor, "inspect", lambda **kw: rep)
    assert doctor.main(["--json", "--lang", "tr"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["checks"][0]["id"] == "ffmpeg"


def test_claude_login_is_read_from_the_config_dir(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / ".credentials.json").write_text('{"token": "x"}')
    res = doctor._claude_cli(_run_ok, env={"HOME": str(tmp_path)})
    assert res["status"] == "ok"
    res = doctor._claude_cli(_run_ok, env={"HOME": str(tmp_path / "empty")})
    assert res["status"] == "warn"
