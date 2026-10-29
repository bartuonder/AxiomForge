# API reference

[Türkçe](API.tr.md) · [Back to the README](../README.md)

The backend is a FastAPI application (`app/main.py`). With the stack running, interactive OpenAPI documentation is served at `http://127.0.0.1:8000/docs`. This page explains what each endpoint does and the behaviour that the schema alone does not tell you.

**Conventions**

- Endpoints that start paid work (OpenAI, E2B) check an optional API key and a daily start limit; see [Access control](#access-control).
- Errors are JSON `{"detail": "..."}`. Typical codes: `401` missing or wrong key, `404` unknown id, `409` action not allowed in the current state, `422` invalid input, `429` daily limit reached, `503` a dependency (queue, OpenAI key) is unavailable.
- Long work runs in a Celery worker. Start endpoints return at once with an id; you poll the matching `GET`.

## Overview

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Redis and Celery status |
| `POST /start_research` | Start the agent graph (single experiment or campaign mode) |
| `GET /research/{thread_id}` | Status, plan, verification and result of a graph run |
| `POST /approve_plan` | Approve (with the chosen plan) or reject the proposed plans |
| `POST /research/{thread_id}/retry` | Resume a failed or stale graph run from its last checkpoint |
| `GET /reports/{thread_id}` | The paper written for a graph run |
| `POST /experiments` | One experiment without the graph |
| `POST /start_campaign` | Run a replication campaign directly |
| `GET /campaigns` | List campaigns |
| `GET /campaign/{id}` | Campaign state |
| `GET /campaign/{id}/summary` | Plain-language summary (`lang=tr\|en`) |
| `GET /campaign/{id}/report` | Markdown report and evidence ledger |
| `POST /campaign/{id}/cancel`, `/retry` | Cancel or restart a campaign |
| `POST /start_research_session` | Start a research agent session |
| `GET /research_sessions`, `/research_sessions/{id}`, `/research_sessions/{id}/report` | Read sessions |
| `POST /research_sessions/{id}/cancel`, `/retry` | Cancel or restart a session |
| `GET /glossary`, `GET /vocabulary` | Terms and plain names for the console |
| `GET /usage` | Today's start count and the remaining allowance |

## Health

`GET /health` returns `{"redis": "ok", "celery": "ok"}` with `200` when both are up and `503` when either is down.

## Research graph

### `POST /start_research`

```json
{"query": "Compare SVM and Random Forest on tabular data classification", "mode": "experiment"}
```

- `mode` is `experiment` (default, one dataset) or `campaign` (many datasets). Any other value is `422`; there is no automatic mode, because a language model is not allowed to spend sandbox money on its own.
- The query must name **at least two models** (every hypothesis is a comparison). Otherwise `422 query names fewer than two models` and nothing runs.
- In campaign mode an arXiv identifier or link in the query makes that paper the source: its claim and abstract go to the planner.
- The reply is `{"thread_id": "...", "status": "running", "mode": "..."}`. The graph runs literature retrieval and planning, then pauses before any experiment (`paused`). Nothing runs without approval.

### `GET /research/{thread_id}?lang=tr|en`

Returns the run state. `status` is `starting`, `running`, `paused`, `rejected`, `completed`, `needs_review` or `failed`.

Fields worth knowing:

- `hypotheses`, `experiment_specs`, `selected_hypothesis`: the three proposed plans and the chosen one.
- `verification_status`, `verifier_feedback`, `instability`: whether verification passed, why not, and any model whose standard deviation across splits exceeds 0.05.
- `research_status`: `Completed`, or `NeedsReview` when the paper failed the consistency check; `consistency_feedback` says why. `referee_notes` are advisory comments.
- `error` and `error_info` (title, reason, advice, technical detail) when `failed`; `can_retry` says whether `/retry` applies.
- Campaign mode adds `campaign_specs` (three candidate campaigns with estimates and evidence), `campaign_id` and `campaign_status`.

### `POST /approve_plan`

```json
{"thread_id": "...", "decision": "Y", "selected": 1}
```

`Y` requires `selected` (zero-based plan index); a missing or out-of-range value is `422` and nothing changes. `N` rejects the plans and ends the run. The reply is `{"status": "running"}`; a second decision on the same run is rejected. If the queue is down the approval is rolled back and `503` is returned.

### `POST /research/{thread_id}/retry`

Restarts a failed run, or one that wrote no checkpoint for 30 minutes, from its last checkpoint; finished steps are kept. In campaign mode a stopped campaign is re-queued and tied back to the run. `409` for a run that is waiting for approval, finished, rejected or has nothing left to run. Counts as one start.

### `GET /reports/{thread_id}`

`{"markdown": "..."}` with the paper, or `404 report not ready`.

## Single experiment

`POST /experiments` takes `{"prompt": "...", "csv_schema": "..."}` and runs one experiment outside the graph: the agent writes a scikit-learn script for the models named in the prompt on a real Hugging Face dataset, runs it in an E2B sandbox, and fixes it from the traceback up to three times. The reply carries the code, `status` (`Finished` or `Failed`), `attempts` and the MLflow run id.

## Replication campaigns

A campaign tests a published claim on many datasets with **no language model**: the verdict is computed (per-dataset scores compared over datasets with a Wilcoxon signed-rank test, Holm correction, Friedman test) and every number is tied to an entry of an evidence ledger.

### `POST /start_campaign`

Exactly one of `demo` (a built-in campaign name, for example `grinsztajn-2022`) or `spec` (a campaign specification); `datasets` replaces the specification's datasets.

```json
{"demo": "grinsztajn-2022", "datasets": ["tb_credit", "tb_pol"]}
```

The specification is validated synchronously (`422` if invalid, nothing is stored). Then the state is written as `queued`, the task is queued and `{"campaign_id": "...", "status": "queued"}` is returned. If the queue is down: `503`, and the campaign is marked `failed`.

### Reading a campaign

- `GET /campaigns`: `items`, newest first: `id`, `title`, `statement`, `origin` (`api`, `console`, `cli`), `status`, `datasets`, `finished`, `failed`, `verdicts`.
- `GET /campaign/{id}`: `status`, per-dataset `status`, `attempts`, `seconds`, `error`, and when done `verdicts` (replicated, partially replicated, contradicted, inconclusive, not testable), `issues`.
- `GET /campaign/{id}/summary?lang=tr|en`: the plain-language view used by the console: one-sentence headline, verdict label and tone, confidence, "datasets where it came out ahead", chart points per dataset, overall ranking, method notes and cautions, progress, and `error_info` when something failed.
- `GET /campaign/{id}/report`: `{"markdown": "...", "ledger": [...]}`, or `404 report not ready`.

An invalid id is `400`, an unknown campaign `404`. A `queued` or `running` campaign that has made no progress for 20 minutes is shown as `failed` with `stale: true` (not written to disk).

### Cancel and retry

- `POST /campaign/{id}/cancel`: a queued campaign becomes `cancelled` at once; for a running one a cancel request is stored, the datasets already running finish, the rest never start, and no analysis is produced. `409` when already finished.
- `POST /campaign/{id}/retry`: only for `failed` or `cancelled` (including stale) campaigns; re-queues the saved specification, increments `recoveries`, counts as one start; `503` if the queue is down.

The campaign task uses late acknowledgement: if a worker dies, the message is redelivered (after at most the visibility timeout), a live campaign writes a heartbeat every 15 seconds so duplicates wait, and a finished campaign is never run again.

## Research agent sessions

A session splits the 16-dataset pool once into exploration (6) and confirmation (10) datasets, lets a generator propose hypotheses from the exploration results only, registers them, then tests each exactly once on the sealed confirmation datasets with one Holm correction. Full design: [`RESEARCH_AGENT.md`](../RESEARCH_AGENT.md).

### `POST /start_research_session`

```json
{"models": ["RandomForest", "ExtraTrees", "MLP", "LogisticRegression"], "tuning": 12, "seed": 0, "generator": "rules"}
```

- `models`: at least two distinct model keys; invalid input is `422` with the reason. `tuning` (optional, 4–40 trials per model) adds a tuned stage. `generator` is `rules` or `llm` (the latter checks OpenAI access first and answers `503` if unavailable). Unknown fields are rejected.
- Counts as one start. Returns `{"session_id": "r-xxxxxxxx", "status": "queued"}`.

### Reading and controlling sessions

- `GET /research_sessions`: summaries, newest first, with `status` (`queued`, `running`, `completed`, `aborted`, `failed`, `cancelled`), `phase`, per-dataset `progress` (`stage`, `total`, `finished`, `failed`, `running`), counts of `confirmed`, `reversed`, `not_confirmed`, `not_testable`.
- `GET /research_sessions/{id}`: the summary, the full session (hypotheses with their SHA-256 digests, confirmations, skipped proposals) and `intact`, which is `false` if a registered hypothesis no longer matches its digest.
- `GET /research_sessions/{id}/report`: the Markdown report.
- `POST /research_sessions/{id}/cancel`: a queued session is cancelled at once; a running one stops when the running datasets finish and registers nothing.
- `POST /research_sessions/{id}/retry`: for `failed`, `cancelled` or `aborted` sessions; results of finished stages are reused, hypotheses are proposed again from the exploration view only. A running worker that stops writing its heartbeat for 90 seconds makes the session show as `failed` (stale), which can be retried.

## Console helpers

- `GET /glossary?lang=` returns the term glossary; `GET /vocabulary?lang=` returns plain names for models, datasets and metrics. Unknown language is `422`. These only present data; they never change a verdict.

## Access control

- If `API_KEY` is set, every endpoint that starts work (`/experiments`, `/start_research`, `/approve_plan`, `/start_campaign`, retries, cancels, `/start_research_session`) needs an `X-API-Key` header (`401`, `[unauthorized]` otherwise). Reads stay open. The console sends the key from `NEXT_PUBLIC_API_KEY`.
- `DAILY_START_LIMIT` (default 100, `0` is unlimited) caps starts per day: `429` with `[daily_limit]` once reached. `GET /usage` returns `{"date", "used", "limit", "remaining"}`; the counter lives in `reports/usage.json`.
- `CELERY_VISIBILITY_TIMEOUT` (seconds, default 7200) is how long a campaign message waits before redelivery after a worker dies.
