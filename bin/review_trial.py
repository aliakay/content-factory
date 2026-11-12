"""Is a Gemini reviewer as strict as the reviews a project already has?  Runs the single-shot reviewer on Gemini over
a COPY of a finished project and prints its verdict, score and findings per stage next to the recorded ones.

    cp -r projects/<id> /tmp/trial/projects/ && CF_PROJECTS=/tmp/trial/projects \\
        .venv/bin/python bin/review_trial.py <id> research proposal script publish

It never falls back to Claude (that would spend the limit this is meant to save and hide which model answered): a
busy or exhausted Gemini model is reported as an error. CHAIN=gemini-3.8-flash,gemini-3.7-flash picks the models.
Cost: about $0.05 per stage on a paid key. Decision rule: make Gemini the reviewer default (llm.AUTO_KEEPS_CLAUDE)
only when it finds the recorded findings, not when it merely agrees on "pass".
"""
import json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from factory import llm  # noqa: E402
from factory.hat import agent as A, manifest, project as P  # noqa: E402


def recorded(pid, sid):
    """The last recorded review of a stage in the project's own events."""
    last = None
    try:
        for line in open(P.path(pid, "events.jsonl"), encoding="utf-8"):
            e = json.loads(line)
            if e.get("kind") == "review" and e.get("stage") == sid and e.get("model_used") != "code" \
                    and e.get("provider") != "gemini":          # an earlier trial's own reviews are not the reference
                last = e
    except (OSError, ValueError):
        pass
    return last


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    if not os.environ.get("CF_PROJECTS"):
        raise SystemExit("set CF_PROJECTS to a copy: a review writes events and a ledger into the project")
    pid, stages = argv[0], argv[1:]
    if os.environ.get("CHAIN"):
        llm.GEMINI_CHAIN["agent.review_stage"] = tuple(os.environ["CHAIN"].split(","))
    # "Hafif işler: Gemini" for this process only: the reviewer goes to Gemini whatever the saved settings say, and
    # llm.ask_text falls back to Claude only in "otomatik"
    from factory import accounts
    accounts.light_mode = lambda uid=None: "gemini"
    m = manifest.get(P.load(pid)["line"])
    for sid in stages:
        t = time.time()
        r = A.review_stage(pid, manifest.stage(m, sid))
        old = recorded(pid, sid) or {}
        print(f"== {sid}: {r.get('verdict')} {r.get('score')} on {r.get('model_used')} (${r.get('cost_usd') or 0:.3f}, "
              f"{time.time() - t:.0f} s, {r.get('settled')} lines settled by code)"
              f" | recorded: {old.get('verdict')} {old.get('score')} on {old.get('model_used') or old.get('model')},"
              f" {old.get('findings')} findings" + (f" | ERROR {r['error']}" if r.get("error") else ""))
        for f in r.get("findings") or []:
            print(f"   {f['severity']:10} {f['item'][:50]:50} {f['problem'][:200]}")


if __name__ == "__main__":
    main(sys.argv[1:])
