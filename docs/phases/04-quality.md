# Phase 04 — Quality: grounding check and classifier evaluation

## Context
Read `CLAUDE.md`, `docs/ARCHITECTURE.md` §5.3, §5.5, §11 (quality metrics), skills `podcast-script`
(grounding section) and `openai-llm`. Prosper runs AI agents where wrong facts are costly; this phase shows
we measure and control quality instead of hoping.

## Part A — Grounding check (must have)
1. Runtime prompt `grounding_check.v1.md`: input = story sections with their turns and the source texts;
   output = `GroundingReport {unsupported: [{section_index, turn_index, claim, reason, suggested_fix}]}`.
2. New sub-step at the end of `scripting`: run the check; if any unsupported claims, run one script revision
   with the report attached, re-validate, re-check once. Store `grounding_flags_initial` and
   `grounding_flags_final` on the episode (add columns via migration) and a `pipeline_steps` row.
3. CLI `grounding <episode_id>` prints the report.

Acceptance A: run on the phase 03 episode's script; show the report. Plant one false number in a copy of
the script and prove the check flags it (test with a fake LLM for CI, real run for the demo).

## Part B — Classifier evaluation (Luna vs Sol, and Jev if available)
Revised during planning; rationale in `docs/DECISIONS.md` D-29. The question: does Sol (~20x Luna's
price) or Jev earn its cost on the highest-volume LLM call in the pipeline? Two independent axes are
evaluated separately: `relevance` (does a candidate that Exa returned for a topic really match that topic's
description, include and exclude lists) and `newsworthy` (a real event, not PR, a listicle or an evergreen
explainer).

1. **Eval user and candidates.** Create a dedicated eval user (small extension to `seed-users`; do not
   touch the demo user's profile). Give it 5 deliberately different topics of varying ambiguity through
   the real path: `cli profile --user <eval> --answers <file>`. Run one episode with
   `--stop-after fetching` (real planner and Exa fetch, no classification yet).
2. **`eval/build_set.py`**: from that episode's `article_scores` rows, sample up to ~12 per topic (~60
   total, report the actual per-topic composition). Write `eval/articles.csv` with `encoding="utf-8-sig"`
   (Windows Excel needs the BOM). One row per `(article_id, fetched_topic)` pair, with columns `article_id,
   fetched_topic, title, outlet, published_at, highlights` plus empty `label_relevant` (y/n),
   `label_newsworthy` (y/n) and optional `label_actual_topic` (topic name or 0, informational only).
3. **Labeling, by hand in Excel** (replaces `label.py`). Fill in only the label columns; do not edit the
   other columns. Save as "CSV UTF-8". I label; you don't.
4. **`JevClassifier` adapter** (only if `TYPESAFE_API_KEY` is set): same `Classifier` protocol, questions for
   relevance to the given topic and newsworthiness, map probabilities to `ArticleScoreResult`. Follow phase
   00 findings.
5. **`eval/classifier_eval.ipynb`** (replaces `run_eval.py`). Add `jupyter`/`ipykernel` with `uv add --dev`
   in `backend/`. Run from the repo root with `uv run --project backend jupyter lab`.
   - Load the CSV and join labels on `(article_id, fetched_topic)`, never on row position. Build transient
     `Article` objects (no DB writes).
   - Score with the production classes: `LLMClassifier` for `gpt-6-luna` and for `gpt-6-sol`, plus
     `JevClassifier` if available. Pass `recent_headlines=[]`. Cache outputs to
     `eval/results/scores_<classifier>.jsonl` and reuse them on re-run (no repeat spend, stable numbers).
     Sum and print `Usage.cost_usd`: the runner's spend cap does not apply here.
   - Metrics, fixed before looking at results. Relevance: accuracy, precision and recall at a 0.5
     threshold, plus ROC-AUC. Newsworthy: precision and recall at 0.5, plus ROC-AUC. Also p50/p95
     latency, cost per 100 articles, and selection agreement: feed each classifier's scores through
     `rank.select_stories` (`target_minutes=10`, 8 stories) and compare the selected sets. Include one
     toy-example cell that checks the metric functions against hand-computed values.
   - Plots for `solution.md`: cost vs quality, where the classifiers disagree.
   - Final cells write `eval/results/<date>.json` (the file the dashboard metrics endpoint will read; no
     `classifier_eval_runs` table) and the markdown table `eval/results/latest.md`.
   - Trust and commit only after a clean "Restart & Run All". Outputs stay committed.
6. **Default choice rule**: Luna stays the default unless selection agreement with Sol is low **and** Sol's
   gain on the axis where they differ is material.

Acceptance B: `latest.md` shows the comparison table; a decision entry states which classifier is the
default and why, with the numbers. Expected spend is under $0.25 in total (eval user's fetch plus about
60 × 2–3 classifier calls).

## Out of scope
UI for labeling, large eval sets, query-planner quality (`label_actual_topic` only records it).

## Cut first
Jev (compare Luna vs Sol only), then selection agreement.

## Finish
Commit `phase 04: grounding check and classifier evaluation`.
