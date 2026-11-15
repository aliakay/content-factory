# Limit savings: where one film's Claude subscription goes, and what was changed

The stage agents run on a Claude subscription through the headless CLI. One explainer used about 27% of the 5-hour
limit. Measured on project 121 (ledger table `llm_usage`, list-price equivalents): **$2.96** = authors $1.59 +
reviewers $0.56 + scene design $0.57 + score $0.24, plus discovery cards in the background at ~$0.10 a run, five
runs a day.

## What changed

| What | Before | Now |
|---|---|---|
| Reviewer (`agent.review_stage`) | a second CLI session with MCP tools on the *other* model (opus reviewing a sonnet caption) | **one call, no tools**: the artifact, the earlier artifacts, the open findings and the render sheet are in the prompt; never a dearer model than the author |
| Rubric lines a program can measure | read by the model | **scored by code** (`factory/hat/rubriccheck.py`: source and angle counts, word budget, hook rule, cold-test evidence, scene coverage, caption and hashtag counts, credits). When nothing is left for a model, no model is called (publish usually) |
| Author turns | `project_info` + `read_artifact` turns, each re-reading the whole context; the script was refused three times at the gate | earlier artifacts and project facts are **embedded in the task**; the gate's hard numbers (hook word limit, word budget, "cold_test after the last edit") are stated before the work; recurring refusals come from `skills/meta/lessons.md` |
| Cold test | ran again on the same text | cached per title + lines |
| Light steps (`coldtest._ask`, `discover.make_cards`, `router.suggest`, image tagging, `lab.*`) | Claude | **Gemini API** when a key exists (Hesaplar → "Hafif işler": otomatik / Gemini / Claude), the cheapest Claude model otherwise |
| Discovery | 5 runs a day | at most 3 per rolling 24 h (`CF_DISCOVER_MAX_PER_DAY`; the Studio button is not capped) |
| Seeing it | per step only | `python -m factory.usage [--project ID] [--days N]`: per project, the Claude-limit dollars split from Gemini and the rest |

Gemini is also a full provider now (`factory/gemini_text.py`): any agent can be pointed at it in Hesaplar, like
OpenRouter. Its agent loop with MCP tools has only been tested with fakes.

## What it saves (an estimate, not yet measured on a whole film)

Reviewers $0.56 → about $0.21 on single-shot sonnet (publish needs none). Authors $1.59 → about $1.08 if the three
script refusals do not recur. Scene design and score are unchanged ($0.81). **About $2.10 instead of $2.96 (-29%)**;
with the reviewer on Gemini about $1.89 (-36%). Discovery drops from ~$0.50 a day to about nothing.

More than half needs the two creative steps that were left alone on purpose: scene design (`shortplan._ask`, sonnet,
$0.57) and the score (`compose.write_score`, opus, $0.24), or a cheaper model for script and proposal. Those are the
owner's call, in Hesaplar.

## The reviewer stays on Claude in "otomatik", and why

The trial (2026-11-12, a copy of project 121) could not get one answer from `gemini-3.8-flash`: the key is on the
**free tier, 20 requests per model per day**, and the quota was gone. The flash models that did answer (3.6-flash,
flash-lite) gave 100 to every stage, where the recorded opus/sonnet reviews had found real gaps (88-97). The
single-shot sonnet reviewer found what the recorded reviews found. So `llm.AUTO_KEEPS_CLAUDE` keeps
`agent.review_stage` and `qa.review` on Claude unless the creator picks "Hafif işler: Gemini".

To decide: enable billing on the Gemini key (or wait for the daily reset), then

    mkdir -p /tmp/trial/projects && cp -r projects/<id> /tmp/trial/projects/
    CF_PROJECTS=/tmp/trial/projects .venv/bin/python bin/review_trial.py <id> research proposal script publish

It never falls back to Claude and prints the recorded review next to Gemini's. Make Gemini the default only if it
finds the recorded findings.

On the free tier the other light steps also run out of quota quickly; in "otomatik" they then fall back to the
cheapest Claude model (haiku), so nothing stalls, but the saving is smaller. A busy model is parked for a while
(`data/gemini_busy.json`) instead of being asked again on every call.

## Cron (not changed by code)

The five discovery lines run five times a day; with the cap of three, two are skipped. Suggested:

    40 5  * * * … factory.discover --region tr
    30 7  * * * … factory.discover --region global
    30 20 * * * … factory.discover --region tr --only tr_spor

The Lab's weekly run, if wanted: `0 4 * * 1 … -m factory.lab run --build 2` (see docs/LAB.md).
