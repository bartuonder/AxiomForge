# Demo: explore real results without any API key

This folder holds **real output of AxiomForge**, so you can open the console and look around without OpenAI or E2B keys, without a database and without spending anything.

[Türkçe](README.tr.md)

| What | Where | What you will see |
| --- | --- | --- |
| Research agent session `real-2` | `data/research/real-2/` | 16 hypotheses proposed from six exploration datasets, tested once on ten sealed datasets: 15 confirmed, 0 reversed, 1 not confirmed, with the exploration estimate next to the confirmation effect |
| Replication campaign "Tree-based vs Neural Networks" | `data/campaigns/g-21bf5f449bb26c00fc824d40ed83aaf5/` | One claim tested on 9 datasets: verdict, confidence, per-dataset chart, evidence ledger, report |
| Replication campaign from a paper (Grinsztajn et al., 2022) | `data/campaigns/demo-grinsztajn-1/` | Two claims from arXiv 2207.08815 with the comparison to the source |

Every number in these files was produced by the system in a sandbox run. The sessions are not edited; `python -m app.research verify real-2` confirms that the registered hypotheses were not changed.

## Run it locally (no keys needed)

You need Python 3.12 and Node 24 (the versions CI uses).

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
bash demo/load.sh                                # Windows: powershell -File demo/load.ps1
.venv/bin/uvicorn app.main:app --port 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` (use `localhost`, not `127.0.0.1`) and go to:

- **Past runs** for the campaigns: summary, detailed report and the evidence ledger tab. The paper campaign is listed as a benchmark run; tick "Show test and benchmark runs too" to see it.
- **Research agent** for session `real-2`: the protocol in plain words, the hypothesis table, the integrity check and the report download.

The page that starts new work (the question box and the "Start the session" form) needs the full stack and your own keys; see the main [README](../README.md).

## Run it with Docker

```bash
docker compose up -d --build
docker compose cp demo/data/research/. api:/srv/reports/research/
docker compose cp demo/data/campaigns/. api:/srv/reports/campaigns/
```

Then open `http://localhost:3000`.

## Read the files directly

```bash
python -m app.research verify real-2          # needs the data copied by load.sh
python -m app.research show real-2            # the session report
```

The campaign reports are plain Markdown: `data/campaigns/*/report.md`. Every figure in them carries an `[E#]` reference to an entry of `ledger.json` (dataset revision, row count, library versions, script digest). The scripts that ran in the sandbox are in `scripts/`.

## Good to know

- The data was produced on 28 October 2026 with the datasets and library versions recorded in the ledgers. New runs can differ slightly.
- Copying the demo into `reports/` also makes the research agent skip claims that session `real-2` already confirmed (tree ensembles over logistic regression and the MLP). Use `--no-history` to turn that off.
- `reports/` is not tracked by git; the demo never touches your own results unless an id clashes.
