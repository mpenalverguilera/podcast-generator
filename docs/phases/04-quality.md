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
1. `eval/build_set.py`: take ~60 candidates from real episodes (mixed topics), write
   `eval/articles.jsonl` (title, outlet, highlights, topic list).
2. `eval/label.py`: a tiny terminal labeler — shows each article and asks me: relevant to which topic
   (number or 0 = none), newsworthy (y/n). Writes `eval/labels.jsonl`. I label; you don't.
3. `JevClassifier` adapter (only if `TYPESAFE_API_KEY` is set): same `Classifier` protocol, questions for
   relevance per topic and newsworthiness, map probabilities to `ArticleScore`. Follow phase 00 findings.
4. `eval/run_eval.py --classifiers openai:gpt-6-luna openai:gpt-6-sol jev`: scores every labeled article,
   computes accuracy (topic), precision/recall (newsworthy), p50/p95 latency, cost per 100 articles, and
   selection agreement (would the top-8 be the same?). Writes `eval/results/<date>.json` and a markdown table
   `eval/results/latest.md`. Also stores rows so the dashboard can show them (table `classifier_eval_runs`
   or a JSON file the metrics endpoint reads — pick the simpler one and log the decision).

Acceptance B: `latest.md` shows the comparison table; a decision entry states which classifier is the
default and why, with the numbers.

## Out of scope
UI for labeling, large eval sets.

## Cut first
Jev (compare Luna vs Sol only), then selection agreement.

## Finish
Commit `phase 04: grounding check and classifier evaluation`.
