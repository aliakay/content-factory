"""The v2 pages must read the same in TR and EN: identical key sets, and a key for every runtime status value."""
import re
from pathlib import Path

from factory.hat import agent, project

JS = (Path(__file__).resolve().parent.parent / "studio" / "hat.js").read_text(encoding="utf-8")


def _keys(lang):
    block = re.search(r"\n  %s: \{(.*?)\n  \},?" % lang, JS, re.S).group(1)
    return set(re.findall(r"\b([a-z_]+[a-z0-9_]*):\s*[\"']", block))


def test_tr_and_en_have_the_same_keys():
    tr, en = _keys("tr"), _keys("en")
    assert tr and tr == en, (sorted(tr ^ en))


def test_runtime_values_have_keys_in_both_languages():
    tr = _keys("tr")
    want = {"st_" + s for s in project.STATUSES} | {"sev_" + s for s in agent.SEVERITIES}
    want |= {"verdict_pass", "verdict_fix", "verdict_unknown"}
    want |= {"state_" + s for s in ("busy", "gate", "failed", "done", "run", "planned")}
    want |= {"status_" + s for s in ("ready", "partial", "planned")}
    assert not (want - tr), sorted(want - tr)


def test_shell_translation_map_covers_every_old_nav_label():
    app = (Path(__file__).resolve().parent.parent / "studio" / "app.js").read_text(encoding="utf-8")
    nav = re.search(r"const NAV = \[(.*?)\n\];", app, re.S).group(1)
    labels = set(re.findall(r'"#/[^"]*",\s*"[a-z]+",\s*"([^"]+)"', nav)) | {"Üretim", "Kütüphane", "Sistem"}
    mapped = set(re.findall(r'"([^"]+)":\s*"', re.search(r"const SHELL_EN = \{(.*?)\n\};", JS, re.S).group(1)))
    assert not (labels - mapped), sorted(labels - mapped)
