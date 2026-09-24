# Phase 02 — Ingestion: profile, query planning, Exa fetch

## Context
Read `CLAUDE.md`, `docs/ARCHITECTURE.md` §5.0–5.2, skills `exa-news-search` and `openai-llm`,
`docs/DECISIONS.md` D-07, D-08, D-09.

## Goal
From free-text interests to a stored profile, and from a profile (+ optional focus request) to a set of
deduplicated candidate articles in the database, all driven from the CLI.

## Build
1. **Profile extraction**
   - Runtime prompt `app/prompts/profile_extractor.v1.md`: given the user's answers to the guided questions,
     return an `InterestProfile` (2–8 topics; name, one-line description, include/exclude keywords, depth;
     plus global `avoid` list). Keep the user's own wording in names.
   - `app/pipeline/profile.py: extract_profile(answers: dict[str, str]) -> (InterestProfile, Usage)`.
   - CLI `profile --user <email> --answers answers.json [--save]` prints the profile; `--save` writes it.
   - Guided questions (store in `app/pipeline/profile.py` for reuse by the UI):
     "What do you follow for work?", "What do you follow for fun?", "Anything you never want to hear about?",
     "Headlines or deeper analysis — and for which topics?"
2. **Planning stage** (`planning`)
   - Runtime prompt `query_planner.v1.md`: inputs are profile, focus request, window description, recent
     headlines. Output: list of `PlannedQuery {topic, query, is_focus}`; ~2 per topic, 2–3 for the focus
     request; natural-language queries with recency phrasing; avoid repeating recent headlines' angles.
   - Window start = `ready_at` of the user's last ready episode, else now − 7 days; store on the episode.
   - Store `planned_queries` and prompt version on the episode.
3. **Fetch stage** (`fetching`)
   - For each planned query: `SearchSource.search(query, since=window_start)`; if < 3 results, retry once
     with `since=None` and keep results whose `published_date` is in the window or missing.
   - Normalize URLs (lowercase host, strip `utm_*`, fragments, trailing slash) → `url_hash` (sha256).
   - Upsert into `articles` (keep first-seen highlights; update missing fields). Link candidates to the
     episode through `article_scores` rows with `topic` set and scores null (ranking fills them).
   - Run queries concurrently with a small thread pool (4) to keep the stage fast.
   - Step cost = sum of Exa `cost_dollars`.
4. **CLI** `plan <episode_id>` and `fetch <episode_id>` (run the pipeline with `--stop-after`) and
   `candidates <episode_id>` printing a table: topic, outlet, date, title.

## Acceptance
- With real providers: write `answers.json` for a realistic user (work: health tech and AI voice agents;
  fun: Formula 1; avoid: celebrity gossip), run `profile --save`, create an episode with focus
  "the latest on prior authorization rules", run to `fetching`. `candidates` shows ≥ 30 unique articles,
  mostly inside the window, spread across topics, focus queries present.
- Show me the planned queries and 10 sample candidates; I judge whether they look right.
- Tests (fakes): URL normalization and dedupe; retry-without-date-filter logic; planner output validated;
  focus queries flagged.
- Cost of the real run reported (Exa + OpenAI).

## Out of scope
Ranking, full-text extraction, script.

## Cut first
Concurrency (run queries sequentially).

## Finish
Decision entry on anything learned about Exa result quality (e.g. how many results the date filter drops).
Commit `phase 02: profile extraction, query planning and Exa fetch`.
