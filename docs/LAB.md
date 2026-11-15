# The Lab — the factory grows its own technique catalogue

Our pictures are HTML/CSS/JS scenes written against `FX` (`motion/templates/fxlib.js`, `motion/templates/lineart.js`,
`motion/templates/fx3d.js`) and described by **recipe cards** (`motion/recipes/*.yaml`, `factory/recipes.py`). The Lab
adds to that catalogue by itself: it watches public collections of example videos, turns what it sees into technique
candidates, writes each candidate as a real card and **proves it with code before a human sees it**. Approve is the
only human step, and it decides whether the designer may use the new move.

Everything lives in `factory/lab.py`; fetching is `factory/labscan.py` (its own module, `data/lab/sources.json` names
the collections). A candidate's state lives in the `lab_candidates` table of `data/factory.db`; the card itself is
`motion/recipes/lab/<id>.yaml` and its optional helper module `motion/templates/lab/<id>.js`.

```
scan     collect new cases from the collections            (no model call)
distill  new cases -> technique candidates                 (one cheap model call per 20 cases)
build    candidate -> recipe card + helper, proven by code (one model call, up to 2 repairs)
approve  a human yes: the card becomes active
reject   a human no, with a reason; distill never proposes that id again
list     candidates with status
lessons  regenerate skills/meta/lessons.md from the review evidence
run      scan -> distill -> build K newest ideas -> lessons (the weekly cron entry point)
```

Interface: `python -m factory.lab <cmd>` from the repo root (`.venv/bin/python` here). Every command prints JSON;
`list` prints a table. `--limit N` (distill), `--why "…"` (reject), `--build K` (run, default 2), `--projects DIR`
(lessons, read-only source of the project folders).

## What a technique must pass (no human in the loop)

`build` writes the card on disk and then runs these checks; anything red goes back to the model with the exact
findings (two repair rounds), then the candidate is stored `rejected` with the reason and never proposed again:

| check | rule |
| --- | --- |
| `problems` | `recipes.problems([card])` is clean: every field in `recipes.FIELDS`, `name/use/timing/pitfalls` in **tr and en**, the id's family matches |
| `static` | the demo and the helper JS contain none of `fetch(`, `XMLHttpRequest`, `WebSocket`, `import(`, `http://`, `https://`, `Math.random`, `Date.now`, `performance.now`, `eval(`, `new Function` |
| `render` | the demo renders through the same path `recipes.render` uses (`bin/htmlmotion.py` → `motion/render.mjs`), `--opaque --scale=0.5`, 24 fps |
| `budget` | one render finished inside `lab.BUDGET_S` = 180 s |
| `deterministic` | two renders in two fresh Chromium processes, sampled at 15/50/85 % of the length, are pixel-identical (SHA of the grey stills) |
| `not_blank` | the stills' brightness spread is at least `lab.BLANK_STD` = 4 (out of 255) |
| `moves` | the largest mean pixel change between stills is at least `lab.MOVE_MIN` = 0.6 (out of 255) |

Each result is stored in `lab_candidates.checks` (JSON) and shown on the Studio page. Every event is one line in
`work/lab/lab.log`.

## The Studio page

`#/atolye` — "Atölye" (TR) / "Lab" (EN): sources and case counts, the newest cases, every candidate with its status,
its check results and its demo clip, Approve / Reject (with a reason), `skills/meta/lessons.md`, and the novelty brief
(`factory.memory.novelty_brief()`) when that helper exists. API: `GET /api/hat/lab`, `POST /api/hat/lab`
`{action: approve|reject, id, why}`.

## Cron

Suggested crontab line (not installed by this repo, the VM's crontab is the operator's):

```
30 4 * * 1 cd /home/at-ali/tiktok && .venv/bin/python -m factory.lab run --build 2 >> work/lab/cron.log 2>&1
```

`run` records a failing step and continues: a network error in `scan` cannot stop `lessons`, and one bad card cannot
stop the next. The real model trial is the lead's job; all unit tests inject fake model functions.

## Safety rules

- **Third-party text is data.** Case titles and descriptions come from public collections. They are put inside a
  `<case>` block, the prompt says they are untrusted and must never be followed as instructions, and nothing from them
  is executed or fetched. A case that is only instructions is ignored.
- **Generated JS is scanned, then rendered headless.** No `eval`/`new Function`/network/clock/random in a card's code;
  the only place a card's JS runs is the headless Chromium page of `motion/render.mjs`, on loopback, which serves the
  repo and nothing else.
- **Search and replace of the catalogue is gated by a human.** A card is invisible to the designer (`recipes.index`,
  `card_text`, `listing` skip every lab card whose `status` is not `active`) until `approve`/Approve on the page sets
  both the DB row and the card file to `active`. Cards without a `status` (all hand-written ones) stay active.
- **No paid call is hidden**: `distill` is `lab.distill`, `build` is `lab.build` in the usage ledger, one row per call.

## Wiring left for the lead

A lab card's helper module is inlined into its **demo** bundle (`recipes.bundle` → `recipes.helper(cid)`), so demos
never touch `explainer_shell.html`. A real film gets it the same way: `bin/htmlmotion.py` `make_bundle` puts
`recipes.lab_helpers(js)` ahead of each scene's JS, i.e. the helper of every **approved** card whose `FX.lab.<name>`
the scene calls. The scene names nothing and loads nothing; a candidate's or a rejected card's code never reaches a
film. `FX.lab` itself is created by that prefix (fxlib.js does not know the Lab).

**The page is sandboxed** (`motion/render.mjs`, `tests/test_render_sandbox.py`): the loopback server answers 403 for
dot files (`.env`, `.git`) and for `data/` (accounts, ledgers), and every request that does not go to that server is
aborted. Generated code can therefore neither read a key nor send anything out, whatever the static scan misses.
