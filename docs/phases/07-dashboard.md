# Phase 07 — Internal dashboard: metrics endpoint, seed data, charts

## Context
Read `CLAUDE.md`, `docs/ARCHITECTURE.md` §7 (events, `is_synthetic`), §11. The brief allows mocked data;
we mix real pipeline data with clearly flagged synthetic data.

## Build
1. **Seed script** `app/cli.py seed-metrics --days 60 --users 150`
   - Synthetic users (`is_synthetic=true`) with plausible topic mixes and a growth curve (acquisition rising,
     weekday/weekend pattern, some churn).
   - Synthetic episodes with realistic per-stage latencies and costs drawn around the medians of our real
     `pipeline_steps` (fall back to phase 03 numbers), a small failure rate concentrated in fetching/voicing.
   - Synthetic events: logins, generate clicks, focus requests (~30%), plays with a listen-through
     distribution, ratings. Deterministic with `--seed`. Idempotent (`--reset` removes synthetic rows only).
2. **Metrics** `GET /admin/metrics?from&to&include_synthetic=true`, one response with:
   - product: DAU, WAU, new users/day, episodes/day (manual vs scheduled), listen-through rate, avg % listened,
     7-day retention cohort table, top topics, 👍 ratio, focus-request usage rate;
   - operations: per-stage p50/p95 latency, failure rate per stage, cost per episode by provider (daily),
     cost per listened minute, total spend in range. ElevenLabs cost rows carry `cost_is_estimate=true`
     (D-12) — the cost chart/tile must visibly label the $ figure as an estimate wherever ElevenLabs
     contributes to it; characters (`units_in`) are the exact number if a chart wants an honest metric
     instead;
   - quality: latest classifier eval table (phase 04), grounding flags initial vs final (avg), rating by
     script prompt version.
   Compute in SQL where reasonable; keep each metric a small function with a test on a tiny fixture.
3. **Dashboard UI** (`/admin`): date-range picker (7/30/60 days), "include synthetic data" toggle (on by
   default, with a visible "includes mock data" badge), KPI tiles row (WAU, episodes, listen-through, cost per
   episode), then sections Product / Operations / Quality with Recharts line, bar and stacked-bar charts and
   two small tables (retention, classifier eval). Real vs synthetic: a note under each chart when the toggle is on.

## Acceptance
- `seed-metrics` runs in < 30 s; dashboard renders every chart with the toggle on and still renders (sparser)
  with it off, showing only real data from our actual runs.
- Metric functions have tests; numbers on the tiles match a manual SQL spot-check for one metric.

## Out of scope
Exporting, alerting, per-user drill-down.

## Cut first
Retention cohort table, cost per listened minute.

## Finish
Decision entry: which metrics define "success" for this product and why (activation = first episode
played ≥ 50%; retention = plays in week 2). Commit `phase 07: admin dashboard and seeded metrics`.
