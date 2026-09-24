# Phase 08 — Polish, sample.mp3, README and solution.md

## Context
Read everything in `docs/`, all skills, `eval/results/latest.md`, and `git log`. This phase produces what the
reviewers actually read and listen to.

## Part A — Episode quality loop (most of the time goes here)
1. Pick the demo profile (the realistic user from phase 02, or my own interests — ask me).
2. Generate 2 episodes at 6 minutes. I listen and give notes. Turn the notes into a `script_writer.v2.md` and,
   if needed, voice settings changes (stability, seed, pause length). Log each change in `docs/DECISIONS.md`
   with the note that caused it.
3. Optional quality ceiling: one run with `MODEL_SCRIPT=gpt-6-astra` to compare against Sol; record cost vs
   perceived quality.
4. Generate 2–3 final takes; I pick the best. Copy it to repo root as `sample.mp3`, plus
   `sample.transcript.md` (title, sources, transcript) and a `sample.meta.json` (episode id, models, prompt
   versions, costs, duration).

## Part B — Packaging
1. Docker: api Dockerfile (uv, ffmpeg), web Dockerfile (build + nginx), compose with `.env`; `docker compose up
   --build` then `seed-users` and `seed-metrics` via a one-line `make demo` or `scripts/demo.sh`.
2. `README.md`: what it is, 60-second quickstart, screenshots (login, settings, episode, dashboard), commands,
   env vars table, project layout.

## Part C — solution.md (write with me, don't finalize alone)
Draft from `docs/DECISIONS.md`, `docs/ARCHITECTURE.md` and real numbers. Sections:
1. Overview (one paragraph + architecture diagram).
2. How an episode is made (the pipeline in 8 short steps).
3. Key decisions and trade-offs (table: decision, alternatives, why) — ~10 rows.
4. Quality and reliability: grounding, validation, classifier eval results, resumable stages, guardrails.
5. Cost and latency per episode (real numbers, by provider) and where the money goes.
6. Metrics: what success means and what the dashboard shows (and what is synthetic).
7. What I'd do next with more time (queue + workers, episode memory, niche RSS, SSE, evals in CI, etc.).
8. How AI tools were used (Claude Code phases, where I intervened).
Keep it under ~4 pages. Every number must come from our data.

## Acceptance
- Fresh clone + `.env` + one command brings up the demo.
- `sample.mp3` is committed, 5–8 minutes, and I approved it.
- `solution.md` reviewed by me; no claim without a source in the repo.
- `git grep` for key-like strings finds nothing; `.env` not tracked.

## Finish
Commit `phase 08: sample episode, packaging, README and solution`.
