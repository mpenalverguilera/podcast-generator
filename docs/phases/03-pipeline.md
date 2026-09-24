# Phase 03 — Pipeline: rank → extract → script → voice → assemble (first MP3)

## Context
Read `CLAUDE.md`, `docs/ARCHITECTURE.md` §5.3–5.9, skills `openai-llm`, `podcast-script`,
`elevenlabs-dialogue`, `exa-news-search` (contents part). This phase produces the first listenable episode.

## Goal
`uv run python -m app.cli generate --user demo@example.com --focus "..." --minutes 6` runs the whole
pipeline and writes `data/audio/<id>.mp3`, with every step's cost and latency recorded.

## Build
1. **Ranking stage** (`ranking`)
   - Runtime prompt `classifier.v1.md`. `LLMClassifier.score()` sends title + outlet + date + highlights +
     the profile's topic list + recent headlines, and returns `ArticleScore {topic, relevance 0–1,
     newsworthy 0–1, already_covered bool, is_same_event_as: optional url}`.
   - Score all candidates concurrently (thread pool of 8). Store in `article_scores`.
   - Selection: final = relevance × newsworthy × recency decay (half-life 3 days); drop already_covered and
     final < 0.3; collapse same-event duplicates (keep highest score, keep others as extra sources);
     story count = round(target_minutes / 1.2) (min 3); per-topic cap = ceil(count / 2); focus items reserved
     first. Write `episode_items` with position and story_id.
   - Keep selection logic in a pure function with unit tests.
2. **Extract stage** (`extracting`): `get_contents` for selected URLs (+ their extra sources, max 2 per story);
   check statuses; store `content`, `content_source`, `content_fetched_at`; truncate to 6,000 chars in the prompt
   builder, not in the DB.
3. **Script stage** (`scripting`)
   - Runtime prompt `script_writer.v1.md` built from the `podcast-script` skill: personas, structure, ear-writing
     rules, v3 tag rules, grounding rules, word budget, focus request, listener's interests.
   - Input articles as a numbered block: `[a12] Outlet — Date — Title\n<text>`.
   - Validate (schema, ±15% words, source ids ⊆ selected, speakers, turn length); one retry with errors.
   - Store `script`, `title`, `summary`, prompt version.
4. **Voice stage** (`voicing`)
   - Chunker as described in the `elevenlabs-dialogue` skill (pure function, unit-tested).
   - Check `MAX_TTS_CHARS_PER_EPISODE` before the first request.
   - Synthesize missing chunks only (resume-safe), fixed seed per episode (store it).
5. **Assemble stage** (`assembling`): ffmpeg concat with 600 ms silence between chunks, `loudnorm` to
   −16 LUFS, MP3 128 kbps; store duration and path. Transcript for the UI = turns with tags stripped.
6. **CLI** `generate --user --focus --minutes [--tts fake] [--stop-after STAGE]` and
   `transcript <episode_id>` (prints the script readably).

## Acceptance
- First run with `--minutes 1 --tts fake`: completes, transcript readable, costs recorded.
- Then `--minutes 1` with real TTS: I listen to it. Then one full `--minutes 6` run.
- `show <id>` prints per-stage latency and cost; total cost per episode reported, split by provider.
- Forced failure test: kill the process during `voicing`, rerun `run <id>`, it resumes and does not re-request
  existing chunks.
- Unit tests: selection function, chunker (never exceeds limit, never splits a turn, prefers section boundaries),
  script validator, tag stripping.

## Out of scope
API, UI, grounding check, Jev (phase 04).

## Cut first
Same-event collapsing (keep simple top-N with per-topic cap).

## Finish
Decision entries: selection formula and thresholds, chunk size, anything surprising in the audio. Commit
`phase 03: end-to-end pipeline, first episode`. Report the episode title, duration, cost, and 3 things
you'd improve in the script after listening.
