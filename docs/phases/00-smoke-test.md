# Phase 00 — Smoke test every provider

## Context
Read `CLAUDE.md`, `docs/ARCHITECTURE.md` §14, and the skills `exa-news-search`, `openai-llm`,
`elevenlabs-dialogue`. Nothing is built on an unverified API call shape. This phase confirms every
`[VERIFY]` item with one real, cheap call each.

## Goal
A `scripts/smoke/` folder of tiny standalone Python scripts that prove each provider works with our
keys, plus written findings that correct our docs where reality differs.

## Tasks
1. Install Exa's official skill into the project and confirm where it landed:
   `npx skills add exa-labs/agent-skills --skill build-with-exa` (expect `.claude/skills/build-with-exa/`).
2. Create `backend/` with `uv init` and add `openai`, `exa-py`, `elevenlabs`, `python-dotenv`. (Just
   enough for the scripts; phase 01 does the real scaffold.)
3. `scripts/smoke/openai_check.py`
   - List models available to the key; print which of `gpt-6-sol`, `gpt-6-luna`, `gpt-6-astra` exist.
   - One structured-output call with a tiny Pydantic model via `client.responses.parse(... text_format=...)`
     on the planner model with reasoning `none`. Print parsed result and usage fields.
4. `scripts/smoke/exa_check.py`
   - One `/search` exactly as in the `exa-news-search` skill (highlights + `start_published_date` = 7 days ago)
     for "latest news on AI voice agents this week". Print titles, dates, highlight length, `cost_dollars`,
     and the names of the response attributes.
   - Same query without the date filter: compare result counts.
   - One `/contents` with `text=True` for the top 2 URLs; print `statuses` and text length.
   - Save both raw responses (no keys) to `backend/tests/fixtures/exa_search.json` and `exa_contents.json`.
5. `scripts/smoke/elevenlabs_check.py`
   - Print the account's character quota and usage.
   - List voices (name, id, labels, preview URL). Print the 15 most suitable for an English news podcast.
   - Generate a 2-turn Text to Dialogue sample with `eleven_v3` (≤ 200 characters total, including one
     `[laughs]` tag) for 3 candidate voice pairs, saved to `data/smoke/pair_*.mp3`.
   - Try `output_format="pcm_44100"` once; report whether the plan allows it.
6. Optional `scripts/smoke/jev_check.py` if `TYPESAFE_API_KEY` is set: one classification call with a
   relevance question; print result, probabilities and latency.

## Acceptance
- All scripts run with `uv run python scripts/smoke/<name>.py` and exit 0.
- I have listened to the voice-pair samples and chosen two; their IDs are in `.env` as
  `DEFAULT_VOICE_HOST_A/B` (ask me which pair before writing them).
- `docs/DECISIONS.md` has entry D-09 "Phase 00 findings" listing: confirmed model IDs, confirmed SDK call
  shapes, Exa response attribute names and cost per search, date-filter result-count difference,
  ElevenLabs quota, PCM yes/no, chosen voices, Jev yes/no.
- Every skill file with a `[VERIFY]` that is now confirmed is updated (remove the tag or correct the code).
- Total spend reported (should be well under $1).

## Out of scope
FastAPI app, database, pipeline code.

## Cut first
Jev check.

## Finish
Commit `phase 00: provider smoke tests and verified API shapes`. Report findings in 10 lines max.
