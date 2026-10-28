# AxiomForge: an LLM-agent system that decides with statistics, not with the language model

Technical report. Status: engineering project with measured behaviour; not peer reviewed.

## 1. Problem

Language-model agents can read a paper, write code and write up a result, but they are unreliable judges of evidence. Three failure modes matter when an agent is asked whether a published claim about machine learning models holds:

1. **Fluent but unsupported conclusions.** The agent writes "model A clearly outperforms B" with no way for a reader to check a number.
2. **No notion of error rates.** Nobody knows how often the system says "yes" when there is no real difference.
3. **Adaptive analysis.** An agent that looks at results and then picks what to test next tests hypotheses selected by the same data, which inflates false discoveries.

AxiomForge addresses the first two with a **replication engine whose verdicts are computed, not written**, and the third with a **research protocol** that keeps confirmation data sealed from the agent that proposes hypotheses.

## 2. System

**Pipeline.** A question (or an arXiv identifier) goes through a LangGraph agent graph: literature retrieval, a planner that extracts testable claims and proposes three experiment plans, a human approval step, a campaign that runs every plan in an E2B sandbox, a deterministic analysis, a paper writer and a consistency check. FastAPI, Celery, Postgres (pgvector memory and graph checkpoints), MLflow and a Next.js console (Turkish and English, light and dark theme) complete the system.

**What the language model does.** It reads the literature, proposes plans, and writes the Introduction and Discussion of the paper. It never decides a verdict.

**What decides.** For each claim, per-dataset scores (mean over ten stratified splits) are compared over *datasets*, the unit of replication, with a two-sided Wilcoxon signed-rank test. Several metrics per claim are Holm-corrected; all tuning effects of a model form a Holm family; a stricter family over all effects is reported alongside. A claim is *replicated*, *contradicted*, *partially replicated*, *inconclusive* or *not testable*. Every number in the report is bound to an entry of an **evidence ledger** (dataset revision, library versions, scripts), and a report whose numbers are not traceable is flagged.

**What checks the language model.** The paper is composed from fixed sentences filled with ledger values; only the Introduction and Discussion are free text. Seventeen deterministic rules (digits, invented methods, certainty words, causal claims without hedging, generalisation beyond the datasets tested, missing deviations, and so on) reject a draft, which is rewritten at most twice with the issues as feedback.

## 3. How well do the verdicts hold up?

All numbers below come from tools in the repository and are reproducible with them.

| Question | Measurement | Result |
| --- | --- | --- |
| Does it get known claims right? | 10 well-established comparisons on 9 benchmark datasets | 10 of 10 verdicts as expected |
| Does it invent differences between near-equal models? | 7 near-equal model pairs, both directions, run with default and with tuned hyperparameters | no pair was judged better in both directions in either run; in the default run 10 of 14 directional claims were inconclusive and the decisive ones follow real differences (for example linear versus quadratic discriminant analysis) |
| False positive rate of the decision layer (simulation) | `tools/null_calibration.py`, 4000 replications, 9 datasets, no true effect | decisive verdict in 2.1% (Wilson 95%: 1.7–2.6%); any decisive claim 3.1% |
| False positive rate with real models | `tools/null_seed.py`, each model against a copy that differs only in its random seed, 3 seeds, 9 datasets | 0 of 45 testable effects significant (Wilson 95%: 0–7.9%) |
| Power | same simulation, true effect +0.005 / +0.01 / +0.03 in ROC-AUC | decisive in 4.5% / 18.7% / 98.5% |

The decision layer is conservative: it rarely says yes when there is no difference, and it has low power for small differences (below one ROC-AUC point) with only nine datasets. One consequence is arithmetic rather than statistical: the smallest two-sided Wilcoxon p-value for nine datasets is 2/2⁹ = 0.0039, so a strict correction over a single family can never be significant once there are 13 or more effects; the report therefore uses family-wise correction per model and says so.

**Paper checker.** On the default benchmark the first draft passed all rules in 4 of 10 samples; after removing one false-alarm class (a negated "was not supported") it passed in 7 of 10; every sample passed within three drafts. On the tuned benchmark, 7 of 15 first drafts passed and all 15 passed within three drafts. The remaining flags across 35 samples (55 drafts) were genuine overclaims (for example "demonstrated"); only 3 of the 17 rules fired in those drafts, so the false-alarm rate of the other 14 rules is not measured.

## 4. Comparison with a language model alone

`tools/llm_baseline.py` asks gpt-4o the same claims *without any data*, three times each, and compares its answers with the system's.

- **Known claims (10, ×3):** the model gave 21 of 30 correct answers, **0 wrong** and 9 abstentions ("unclear" for random forest versus nearest neighbours and for the reversed neural-network claim). The system decided all 10 from data.
- **Near-equal claims (14, ×3):** the model asserted a direction for 1 to 4 of 42 claims across two runs (the API is not fully deterministic at temperature 0) and never called both directions of a pair true.

So a strong language model is *not* reckless on famous claims: it abstains instead of guessing. What the system adds is **evidence** (per-dataset scores, effect sizes, an error rate) and **decisions where the model abstains**, not a higher hit rate on easy claims. Where the model's prior knowledge is wrong or out of date, only the data can say so.

## 5. From verification to a research agent: the protocol

A verification agent receives its hypotheses. A research agent proposes them from results, which makes the analysis adaptive. `RESEARCH_AGENT.md` gives the full design; the essentials:

- The dataset pool (16 numeric binary-classification datasets) is split once, by seeded hashing, into **exploration** (6) and **confirmation** (10) datasets.
- The hypothesis generator is *typed* to see only exploration results (`ExplorationView` copies exactly those datasets; the function signature has no confirmation argument).
- Each hypothesis is **registered** (frozen, SHA-256 digest, time) and saved to disk **before** any confirmation result is read; a saved session can be verified against tampering (`python -m app.research verify`).
- Each hypothesis is tested **once** on the confirmation datasets (Wilcoxon, one primary metric) and all hypotheses of the session share **one Holm correction**; Benjamini–Hochberg q-values are reported too. "Confirmed" requires the adjusted p-value below 0.05 and the registered direction.
- The number of registrations is capped by arithmetic: with *n* confirmation datasets at most ⌈0.05·2ⁿ⁻¹⌉−1 hypotheses can all be significant (25 for ten), so the protocol refuses to register more.
- Confirmation results never flow back into hypothesis generation; effect sizes are reported from the confirmation set only (the exploration estimate is inflated by selection and is labelled as such).
- Validity does not depend on how clever the generator is: any generator that only reads the exploration view, rule-based or a language model (`--generator llm`, which validates every proposal and falls back to the rules), keeps the guarantee. This is tested with an adversarial generator in a null world: the family-wise error stays under 10%.

### 5.1 Measuring the protocol on worlds with planted effects

`tools/planted_effects.py` simulates worlds where the true differences between models are known and compares four agents on 400 replications (8 models, 3 of them truly better by δ; 16 datasets; dataset × model interaction 0.01). *Family-wise error* is the probability of at least one false discovery; *power* is the share of real pairs found.

| δ | agent | family-wise error | power | reported |
| --- | --- | --- | --- | --- |
| 0 | all pairs, uncorrected | 0.55 | n/a | 1.2 |
| 0 | adaptive on the same data (Holm over proposed) | 0.10 | n/a | 0.15 |
| 0 | all pairs, Holm (not adaptive) | 0.055 | n/a | 0.06 |
| 0 | **protocol** | **0.022** | n/a | 0.02 |
| 0.02 | all pairs, uncorrected | 0.30 | 1.00 | 15.5 |
| 0.02 | adaptive on the same data | 0.00 | 0.53 | 8.0 |
| 0.02 | all pairs, Holm | 0.037 | 0.96 | 14.5 |
| 0.02 | **protocol** | **0.003** | **0.47** | 7.0 |

With 16 models (120 candidate pairs, 300 replications, δ = 0) the adaptive same-data agent's family-wise error rises to **0.24** (uncorrected: 0.89, Holm over all pairs: 0.043), while the protocol stays at **0.03**. Selection on the data that is then used for testing becomes more harmful as the candidate space grows; the protocol is immune to it.

**The honest cost.** The protocol keeps only 10 of 16 datasets for confirmation and registers at most 8 hypotheses per stage, so its power (0.47 at δ = 0.02) is lower than that of a non-adaptive all-pairs Holm test (0.96) when the hypotheses are known in advance. Its value is that it keeps the error rate under control when the hypotheses are chosen after looking at data, which is exactly what a research agent does.

## 6. A real session

The session `real-2` (`python -m app.research run --models RandomForest,ExtraTrees,GradientBoosting,HistGradientBoosting,MLP,LogisticRegression --tuning 12`) used the rule-based generator, 16 datasets (exploration: magic, heloc, eye, bioresponse, diabetes, jannis; the other ten for confirmation) and ran in the E2B sandbox: about 17 minutes for the default stage and about 29 minutes for the tuned stage, which the generator requested because the default-stage exploration effects were at least two ROC-AUC points.

**Result: 16 hypotheses registered (8 per stage), 15 confirmed, 0 reversed, 1 not confirmed** (budget: 25).

| claim (ROC-AUC) | stage | exploration estimate | confirmation effect | wins on 10 datasets |
| --- | --- | --- | --- | --- |
| tree ensembles (4 models) over logistic regression | default | +0.033 to +0.044 | +0.055 to +0.059 | 10/10 each |
| tree ensembles (4 models) over logistic regression | tuned | +0.032 to +0.036 | +0.045 to +0.053 | 10/10 each |
| tree ensembles (4 models, 3 confirmed) over the MLP | default | +0.024 to +0.031 | +0.005 to +0.013 | 7 to 10 of 10 |
| tree ensembles (4 models) over the MLP | tuned | +0.050 to +0.055 | +0.010 to +0.021 | 9 to 10 of 10 |

All confirmed claims have a Holm-adjusted p-value of 0.031. The one claim that was not confirmed is ExtraTrees over the MLP at default settings (7 of 10 datasets, adjusted p = 0.084).

What the numbers say, and what they do not:

- Tree ensembles beat logistic regression by about five ROC-AUC points on every one of the ten confirmation datasets, with default and with tuned settings. The lead over the MLP is real but small, one to two points.
- **The winner's curse is visible.** Against the MLP the exploration datasets suggested leads of +0.028 (default) and +0.052 (tuned); on the confirmation datasets they were +0.009 and +0.016. Against logistic regression the exploration estimate was too small instead (+0.038 against +0.056). An agent that reported the exploration numbers would have overstated the lead over neural networks by a factor of about three. This is exactly why the report labels the two effects apart.
- The result agrees with Grinsztajn et al. (2022); it is not new. No tuning-effect hypothesis (a model against its own default control) passed the exploration thresholds.

**Hypothesis generators on identical data.** The stage results are saved, so another generator can be run on exactly the same experiments (`--reuse`, `--no-history`). On the default-stage results of `real-2`, over eight different splits, the rule generator registered 61 hypotheses and 19 were confirmed (31%, none reversed); the language-model generator (gpt-4o, asked for the model it expects to score higher and the one it expects to score lower) registered 55, 14 were confirmed (25%) and one was reversed by the confirmation datasets. The eight splits reuse the same experiments, so they are not independent. The first version of the prompt asked for a "subject" and an "other" model; in a first run three of the eight answers contradicted their own rationale (the model named the pair in the wrong order). Such answers would have become false discoveries in an unguarded agent; here they were counted as reversed or not confirmed, and the prompt was changed to ask for the "higher" and the "lower" model.

**A failure the session found.** The first attempt of this session died in the tuned stage, after the default stage had finished, because a sandbox connection dropped (`RemoteProtocolError`) and the campaign runner did not count that exception as a dataset failure. Fixed at the root: any exception of a dataset attempt now counts as a failed attempt (retry, then one failed dataset). The session also keeps the earlier stages when a later stage fails, saves the results of every stage, and can reuse them.

## 7. Engineering

- 3600+ backend tests, 150+ frontend unit tests and 38 browser tests (Playwright, with axe accessibility scans in both themes and keyboard tests); most behaviour changes were checked with mutation tests that change the code and require a test to fail.
- CI (GitHub Actions): backend, frontend and browser jobs; Docker images for the API, worker, MLflow and console; `docker compose up` runs the whole system.
- Operations: API key and daily start limit, campaign cancel and retry, stale-run detection, task redelivery after a worker dies (verified by killing a worker in Docker), a heartbeat that stops duplicate runs.
- Provenance: dataset revision pinning, library versions and the scripts that produced every number are stored with each campaign.

## 8. Limitations

- Binary classification on tabular data from one benchmark family; 16 datasets at most. Nothing is claimed about regression, multi-class, text or images.
- The decision layer has low power for differences under one ROC-AUC point at nine datasets.
- Hypotheses of the research agent are limited to model comparisons and tuning effects; with six exploration datasets the exploration picture is noisy. One real session was run; the generator comparison reuses its experiments and used one language model.
- The paper text is written by one language model (gpt-4o); the rules are tuned to its habits. Only 3 of 17 rules fired in the audited drafts.
- The language-model baseline is one model with one prompt, and its API is not fully deterministic.
- No external users or reviewers yet. This is not a new scientific result; the benchmark finding it reproduces (tree-based models lead neural networks on medium-sized tabular data) is from Grinsztajn et al., NeurIPS 2022.

## 9. Reproduce

```text
python -m pytest -q                                        # backend tests
python -m tools.null_calibration                           # decision layer, simulated null
python -m tools.null_seed --seed 1                         # real-model null (needs E2B)
python -m tools.planted_effects --reps 400                 # protocol against naive agents
python -m tools.llm_baseline --repeats 3                   # language model without data (needs OpenAI)
python -m app.research run --models RandomForest,ExtraTrees,GradientBoosting,HistGradientBoosting,MLP,LogisticRegression --id demo --tuning 12
python -m app.research show demo
python -m app.research run ... --id again --reuse demo --generator llm --no-history   # another generator, same experiments
```
