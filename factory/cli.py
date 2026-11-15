"""`factory` — one command for the whole studio (Türkçe yardım, İngilizce komut adları).

This is a thin dispatcher over functions that already exist; it never re-implements a pipeline:

  factory doctor                     factory/doctor.py  (free readiness report)
  factory make <konu>                factory/hat/project.py + runner.py (creates and advances a line)
  factory show <id>                  the project's flow and last events
  factory run <id>                   advance the next runnable stage
  factory approve <id> <kapı>        open a gate (runner.approve keeps every binding rule)
  factory list                       every project with its state
  factory styles                     the film style library
  factory recipes [check]            recipe cards (check renders their demos, free)
  factory lab ...                    python -m factory.lab
  factory usage [--project ID]       python -m factory.usage
  factory plan [--family image]      factory/hat/media.py ranking, nothing is spent

Python usage: `python -m factory.cli <komut>`. The executable wrapper is `bin/factory`.
"""
import argparse
import os
import sys

from . import accounts
from .config import ROOT
from .hat import manifest, project as P, runner

try:                                                 # the CLI prints Turkish; Windows consoles need this
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def _sync_queue():
    """Run a queued stage here and now, so `factory make/run/approve` go as far as the next gate or the end."""
    def queue(kind, arg):
        return runner.run_job(arg, queue)
    return queue


def _lang(lang):
    return lang if lang in ("tr", "en") else "tr"


def _say(tr, en, lang):
    print(tr if _lang(lang) == "tr" else en)


# ---------------------------------------------------------------- commands

def cmd_doctor(rest, **_):
    from . import doctor
    return doctor.main(rest)


def cmd_make(a, queue=None):
    queue = queue or _sync_queue()
    title = (a.topic or "").strip()
    if not title:
        print("konu boş olamaz", file=sys.stderr)
        return 2
    manifest.get(a.line)                                  # unknown line fails before a folder is made
    extra = {"target_seconds": a.seconds} if a.seconds else {}
    p = P.create(a.line, title, brief=title, video_lang=_lang(a.lang), user=accounts.current(), extra=extra)
    print(f"proje: {p['id']}  ({a.line}, {p['video_lang']})")
    if a.manual:
        print("sonraki adım: factory run " + p["id"])
        return 0
    state, stage = runner.advance(p["id"], queue, by=accounts.current())
    print(_state_line(p["id"], state, stage, a.lang))
    return 0


def cmd_show(a):
    p = P.load(a.id)
    m = manifest.localize(manifest.get(p["line"]), _lang(a.lang))
    state, cur = P.next_stage(a.id)
    print(f"{p['id']}  {p['title']}")
    print(f"hat: {m['name']} · dil: {p.get('video_lang')} · oran: {p.get('aspect')} · durum: {state}"
          + (f" ({cur})" if cur else ""))
    for s, cp in P.stages(a.id):
        mark = {"approved": "✓", "done": "✓", "awaiting_approval": "⏸", "running": "…", "failed": "✗",
                "stale": "↻"}.get(cp["status"], "·")
        print(f"  {mark} {s['id']:<14} {cp['status']:<18}" + (f" {cp.get('summary') or ''}"[:90]))
    try:
        arts = sorted(os.path.splitext(f)[0] for f in os.listdir(P.path(a.id, "artifacts")) if f.endswith(".json"))
    except OSError:
        arts = []
    if arts:
        print("artifacts: " + ", ".join(arts))
    ev = P.tail(a.id, n=5)
    if ev:
        print("son olaylar:")
        for e in ev:
            print(f"  {e.get('at', '')} {e.get('kind', '')} {e.get('stage') or ''}".rstrip())
    return 0


def cmd_run(a, queue=None):
    queue = queue or _sync_queue()
    P.load(a.id)                                          # a clear error before any job is queued
    state, stage = runner.advance(a.id, queue, by=accounts.current())
    print(_state_line(a.id, state, stage, a.lang))
    return 0


def cmd_approve(a, queue=None):
    queue = queue or _sync_queue()
    state, stage = runner.approve(a.id, a.gate, queue, by=accounts.current())
    print(_state_line(a.id, state, stage, a.lang))
    return 0


def cmd_list(a):
    ids = P.list_ids()
    if not ids:
        print("henüz proje yok")
        return 0
    print(f"{'id':<28} {'durum':<20} {'aşama':<16} başlık")
    for pid in ids:
        try:
            p, (state, cur) = P.load(pid), P.next_stage(pid)
        except Exception as e:
            print(f"{pid:<28} okunamadı: {str(e)[:50]}")
            continue
        print(f"{pid:<28} {state:<20} {(cur or '-'):<16} {p.get('title', '')[:60]}")
    return 0


def cmd_styles(a):
    from . import filmstyles
    for c in filmstyles.cards(_lang(a.lang)):
        print(f"{c['id']:<18} {c['name'][:26]:<26} {c['look'][:70]}")
        if a.verbose and c.get("preview"):
            print(f"    {c['preview']}")
    return 0


def cmd_recipes(a):
    from . import recipes
    if a.check is not None:
        ids = a.ids or [c["id"] for c in recipes.cards()]
        bad = 0
        for cid in ids:
            try:
                _, errs = recipes.check(cid)
            except Exception as e:
                errs = [f"{type(e).__name__}: {e}"]
            bad += bool(errs)
            print(f"{cid}: " + ("OK" if not errs else "; ".join(map(str, errs))[:300]))
        return 1 if bad else 0
    for c in recipes.cards():
        print(f"{c['family']:<12} {c['id']:<26} {c['name'][_lang(a.lang)][:34]:<34} {c['call'][:70]}")
    return 0


def cmd_lab(rest, **_):
    from . import lab
    return lab.main(rest)


def cmd_usage(rest, **_):
    from . import usage
    return usage.main(rest)


def cmd_plan(a):
    from .hat import media
    families = [a.family] if a.family else media.FAMILIES
    have = tuple(x.strip() for x in (a.have or "prompt").split(",") if x.strip())
    for fam in families:
        picks = media.pick(fam, have=have, need=tuple(a.need or ()), seconds=a.seconds, aspect=a.aspect, cheap=a.cheap)
        print(f"\n{fam}:")
        if not picks:
            print("  (bu girdilerle aday model yok)")
            continue
        for i, m in enumerate(picks[:7], 1):
            why = ", ".join(m["why"][:4])
            print(f"  {i}. {m['name']:<24} skor {m['score']:>5}  {why}")
    return 0


def _state_line(pid, state, stage, lang):
    labels = {"run": ("sıradaki aşama", "next stage"), "gate": ("onay bekliyor", "waiting for approval"),
              "busy": ("çalışıyor", "running"), "failed": ("başarısız", "failed"), "done": ("bitti", "done"),
              "planned": ("henüz yapılmadı", "not built yet")}
    lab = labels.get(state, (state, state))
    text = (lab[0] if _lang(lang) == "tr" else lab[1]) + (f": {stage}" if stage else "")
    return f"{pid}: {text}" + (f"  → factory approve {pid} {stage}" if state == "gate" else "")


# ---------------------------------------------------------------- parser

def build_parser():
    ap = argparse.ArgumentParser(prog="factory", description="Content Factory: tek komut, mevcut üretim hatları.",
                                 epilog="Örnek: factory make \"Roma'nın su kemerleri\" --line explainer --lang tr\n"
                                        "        factory show 012-roma-nin-su-kemerleri\n"
                                        "        factory approve 012-roma-nin-su-kemerleri proposal")
    sub = ap.add_subparsers(dest="command", metavar="komut")

    def add(name, help_tr, fn, **kw):
        p = sub.add_parser(name, help=help_tr, **kw)
        p.set_defaults(fn=fn)
        return p

    p = add("doctor", "hazırlık denetimi (ücretsiz)", cmd_doctor)
    p.add_argument("--json", action="store_true", help="makine okunur rapor")
    p.add_argument("--online", action="store_true", help="ücretsiz kimlik doğrulamalı GET denetimleri de yap")
    p.add_argument("--lang", choices=("tr", "en"), default="tr")

    p = add("make", "yeni proje oluştur ve ilk kapıya kadar ilerlet", cmd_make)
    p.add_argument("topic", help="konu / brief")
    p.add_argument("--line", default="explainer", help="üretim hattı (varsayılan: explainer)")
    p.add_argument("--lang", choices=("tr", "en"), default="tr", help="videonun dili")
    p.add_argument("--seconds", type=int, help="hedef süre (saniye)")
    p.add_argument("--manual", action="store_true", help="projeyi oluştur, ilk aşamayı başlatma")

    p = add("show", "projenin akışını ve son olaylarını göster", cmd_show)
    p.add_argument("id")
    p.add_argument("--lang", choices=("tr", "en"), default="tr")

    p = add("run", "sıradaki çalıştırılabilir aşamayı ilerlet", cmd_run)
    p.add_argument("id")
    p.add_argument("--lang", choices=("tr", "en"), default="tr")

    p = add("approve", "bir kapıyı onayla (bütün bağlayıcı kurallar çalışır)", cmd_approve)
    p.add_argument("id")
    p.add_argument("gate")
    p.add_argument("--lang", choices=("tr", "en"), default="tr")

    add("list", "bütün projeleri durumuyla listele", cmd_list)

    p = add("styles", "film stil kütüphanesi", cmd_styles)
    p.add_argument("--lang", choices=("tr", "en"), default="tr")
    p.add_argument("--verbose", action="store_true", help="önizleme yolunu da yaz")

    p = add("recipes", "tarif kartları; `recipes check` demolarını render eder", cmd_recipes)
    p.add_argument("check", nargs="?", default=None, help="`check` yaz: demoları render edip hataları göster")
    p.add_argument("ids", nargs="*", help="denetlenecek kart id'leri (boş: hepsi)")
    p.add_argument("--lang", choices=("tr", "en"), default="tr")

    p = add("lab", "Lab: scan/distill/build/approve/reject/list/lessons/run", cmd_lab)
    p.add_argument("args", nargs=argparse.REMAINDER)

    p = add("usage", "model harcaması (proje/adım, sağlayıcıya göre)", cmd_usage)
    p.add_argument("args", nargs=argparse.REMAINDER)

    p = add("plan", "medya modeli sıralaması (para harcamaz)", cmd_plan)
    p.add_argument("--family", choices=("image", "video", "avatar", "lipsync", "performance"),
                   help="tek bir aile (varsayılan: hepsi)")
    p.add_argument("--have", default="prompt", help="eldeki girdiler, virgülle (varsayılan: prompt)")
    p.add_argument("--need", action="append", help="istenen etiket (tekrarlanabilir)")
    p.add_argument("--seconds", type=int)
    p.add_argument("--aspect")
    p.add_argument("--cheap", action="store_true")
    return ap


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if not getattr(a, "fn", None):
        ap.print_help()
        return 0
    try:
        if a.command in ("lab", "usage"):
            return a.fn(a.args) or 0
        if a.command == "doctor":
            rest = (["--json"] if a.json else []) + (["--online"] if a.online else []) + ["--lang", a.lang]
            return a.fn(rest) or 0
        return a.fn(a) or 0
    except (P.GateError, manifest.ManifestError, ValueError, FileNotFoundError) as e:
        print(f"factory {a.command}: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("iptal", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
