# Factory v2: handoff (2026-11-02)

Next session: **Sonnet** does the work, **Opus** advises. Read this file first, then `docs/HAT_V2.md` (the design).
Progress tracker (keep it updated task by task): https://claude.ai/artifact/CM86JCjEpCnSVKH2sJNjqv
(db collections `tasks/<id>` with status todo|doing|done + steps, `meta/status` {now, updated}, `meta/log` {entries}).
Pin every write with `if_version`.

## Where things are
- Worktree `~/tiktok-v2`, branch `feat/hat-v2` (pushed). The live Studio (:8501) runs from `~/tiktok`: do not touch it.
- Test Studio: `http://100.98.58.82:8511` from the worktree (log `data/studio-v2.log`), with a copied DB. In the
  worktree's `users.json` the provider is **Claude**. Live Studio is still on Codex, whose limit is full until Nov 28.
- PR #19 (feat/codex-cli-model-settings → main) waits for the user to merge it on GitHub ("Create a merge commit").
  Main is protected, so the agent cannot merge it.
- Tests: `.venv/bin/python -m pytest -q tests/test_hat.py` (26 pass, ~40 s). The full suite is `pytest -q`.
- Playwright/Chromium needs `LD_LIBRARY_PATH=$(python -c 'import factory.config as c;print(c.CHROME_LIBS)')` and
  `NODE_PATH=/home/at-ali/tiktok/motion/node_modules`.

## Done (phase 1, explainer line)
| id | what | where |
|---|---|---|
| t101 | project folder, checkpoints, gate rules | `factory/hat/project.py` |
| t102 | line manager, `hat_stage` job | `factory/hat/runner.py`, `factory/jobs.py` |
| t103 | tool registry + artifact schemas | `factory/hat/tools.py`, `pipelines/_artifacts.yaml` |
| t104 | factory-tools MCP server (Claude + Codex) | `factory/hat/mcp_server.py`, `factory/llm.py` |
| t105 | stage agent (headless CLI, submit_artifact, budget caps) | `factory/hat/agent.py`, `skills/meta/stage-agent.md` |
| t106 | reviewer (other model, 2 fix rounds) | `skills/meta/reviewer.md` |
| t107/t109 | budget lock; assets/edit/compose code stages, real render | `factory/hat/explainer.py`, `bin/htmlmotion.py` |
| t108 | explainer briefs | `skills/pipelines/explainer/*.md` |
| t110–t113 (v1) | Studio: TR/EN switch, line cards, project list, flow board | `studio/hat.js`, `hat.css`, `hat_api.py` |

Real run with Claude: project `901-avrupa-gazinda-yuz-avro-esigi`, **research** stage finished in 436 s for $1.24
over 3 rounds. The Opus reviewer left one critical open: the Turkey/LNG misconception contradicts the insight, and
the LNG import share is missing. Research was run with a direct `execute`, so proposal is "run" and not queued: press
continue on the board, or call `runner.advance`.

## Next, in order
1. **t110–t113 finish** (small): look at the screenshots
   `/tmp/claude-1001/-home-at-ali-tiktok/dc7bd433-4dff-57e3-819d-bcfd5f23ad21/scratchpad/ui_{uret,list,board}.png`
   or retake them with `scratchpad/shot.js`. Fix visual and i18n gaps: every string must change with TR/EN, and
   phone width must not scroll sideways. Done when switching TR↔EN changes every label on all 3 pages.
2. **t115 end-to-end run** (the main goal): on the board, run project 901 (or a fresh news topic) through every
   gate: proposal → script → scene_plan → assets → edit → compose → publish. Rules:
   - **Stop at every gate and ask the user to approve or give feedback.** Never approve on their behalf.
   - Assets spends ElevenLabs credits only up to the budget locked when the proposal is approved.
   - Write down time and cost per stage in the tracker log.
   - Fix bugs as you find them, each with a test.
3. **t114 migrate the 11 old productions** into `projects/` (`factory/hat/migrate.py`): copy, never move.
   - Map the old states to checkpoints.
   - The old records stay readable.
   - Add a dry-run flag and a test.
4. **t116 tests:** gate edge cases (revision limit, reopen→stale), the hat_api endpoints, and migrate.
5. Phase 2+ (t2xx–t6xx in the tracker): the remaining 13 lines, the 10-repo capabilities (t501–t520), then
   go-live (t601–t603). Begin each line with a short plan reviewed by Opus.

## How Sonnet and Opus split the work
- Sonnet: implementation, tests, real runs, tracker updates, commits on `feat/hat-v2`.
- Ask Opus (Agent tool with `model: "opus"`, or a short consult) **before**:
  - changing gate, budget or checkpoint rules (`project.py`, `runner.py`, `lock_budget`);
  - writing a new line's manifest and briefs;
  - committing anything that touches the live repo or spends credits beyond the approved budget.
- Also ask Opus when a bug survives 2 fix attempts, and to review the diff before each push.
- Inside the factory the same split already exists: sonnet/opus authors with the other model as reviewer
  (`agent.OTHER_MODEL`).

## Binding user decisions
- TR interface means everything is Turkish; EN means everything is English. Video language is chosen per project.
- Stop at every gate. The process shows as a flow, with continue or a feedback loop (max 3 revisions).
- Migrate the 11 existing productions.
- OpenMontage and the noncommercial repos: ideas only, no code (AGPL/NC).
- No GPU: FreeVideo goes through minimax-h3 via ElevenLabs; ManimGX only after evaluation.
- Never spend credits without approval.

## Update 2026-11-02 (evening)
- Done: t110–t113 (board verified at 390px in TR and EN), t114 tooling, most of t116 (34 tests in `tests/test_hat.py`).
- Project 901: research done, proposal approved (2472 credits locked), **script waits at its gate for the user**. The
  reviewer's three points are still open: split line 10, align the closing question with the caption and the Turkey
  angle, write "sıvılaştırılmış doğal gaz" instead of "LNG" (TTS may spell it out). Do not approve for the user.
- Budget check: the connector account is capped by the app's monthly cap (100000, spent 0), so 2472 fits; the real
  ElevenLabs balance is not read for connector accounts.
- Migration (`python -m factory.hat.migrate`): 4 of 11 imported (103, 107, 108, 111); unfinished ones restart at research
  because later stages read the proposal. 7 rows are held for the user (QA failed ×4, 113 Avrupa = same topic as 901,
  113 Fiber numbering, 25 Kuyt DB says voice but out/116_kuyt exists). Import them with `--include-flagged` after the
  user decides. `--force` refuses a project that has events beyond created/imported.
- Next: t115 after the script decision; t114 held rows; phase 2 lines.
