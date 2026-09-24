# Decision log

One entry per non-trivial decision. Newest at the bottom. This file is the raw material for `solution.md`.

Format:
```
## D-NN — Title (YYYY-MM-DD, phase NN)
Context: what forced the decision.
Decision: what we chose.
Alternatives: what we didn't choose and why.
Consequences: what this costs us / what to watch.
```

---

## D-01 — Mirror Prosper's stack (2026-09-24, planning)
Context: Assignment for a team running FastAPI + PostgreSQL + React/TS.
Decision: FastAPI, PostgreSQL, React + TypeScript.
Alternatives: Django, Next.js full-stack. Rejected: less relevant to the role.
Consequences: React is new to the author; see `docs/react-for-angular-devs.md`.

## D-02 — Single process, in-process scheduler (2026-09-24, planning)
Context: 10–15 hours of build time; one user base, low volume.
Decision: API, APScheduler and pipeline in one FastAPI process; audio on local disk.
Alternatives: Celery/RQ + Redis workers; Exa Monitors for scheduled search (needs a public webhook).
Consequences: Jobs would double-run with two instances. Fix path: DB advisory lock or a queue + worker.

## D-03 — Two-host dialogue, English, tunable length (2026-09-24, planning)
Context: Episode quality is the main judged output.
Decision: Two hosts (Alex anchor, Sam co-host), English, 3–12 minutes (default 6), user-tunable.
Alternatives: Solo narrator (simpler, less engaging).
Consequences: More prompt and voice-tuning work; chunking must respect turn and story boundaries.

## D-04 — ElevenLabs Text to Dialogue on eleven_v3, chunked at story boundaries (2026-09-24, planning)
Context: ElevenLabs recommends ≤ 2,000 characters per dialogue request; v3 has no request stitching.
Decision: Pack whole script sections into ≤ ~1,800-char chunks; one request per chunk; fixed seed; concatenate with ffmpeg and loudness-normalize to −16 LUFS.
Alternatives: One call per episode (too large); one call per line (loses turn-taking prosody); GenFM Create Podcast API (black box over script, grounding and personalization).
Consequences: Chunk boundaries are the main audio risk; they land on topic changes where a pause is natural.

## D-05 — OpenAI GPT-6 family, split by task (2026-09-24, planning)
Context: Different steps need different cost/quality.
Decision: Luna (reasoning none) for query planning, classification and grounding checks; Sol (reasoning medium) for profile extraction and scripting; Astra only as a quality ceiling experiment for `sample.mp3`.
Alternatives: One model for everything.
Consequences: TTS (~$0.60/episode) dominates cost; LLM steps are ~$0.10. Savings come from shorter TTS input, not cheaper LLMs. Model IDs to be confirmed in phase 00.

## D-06 — Exa as the only v1 news source (2026-09-24, planning)
Context: Brief requires news via APIs or scraping; users can type any interest.
Decision: Exa `/search` driven by LLM-planned queries; curated RSS for a niche is a later step. Hacker News, Reddit and X dropped.
Alternatives: NewsAPI.org (dev-only free plan, no full text, ~24h delay), other aggregators (snippet-only free tiers), Reddit (2–4 week approval queue), X (pay per read, low signal).
Consequences: Coverage depends on Exa's index; very fresh or niche pages may be missed.

## D-07 — Exa request shape follows Exa's official guidance (2026-09-24, planning)
Context: Exa's `build-with-exa` skill documents over-specification as the most common mistake.
Decision: `/search` with `query`, `type: "auto"`, `contents.highlights: true` and `startPublishedDate` for the episode window (a stated window we must enforce). No `category`, `numResults`, domain filters or `maxAgeHours`. Retry once without the date filter if a query returns < 3 results. Full text only for selected URLs via `/contents` (`text: true`), checking per-URL `statuses`.
Alternatives: `category: "news"` (Exa advises against inferring categories); full text for every result (pays for text we never use).
Consequences: Classification runs on highlights, scripting on full text. Exa's `costDollars` gives exact search cost.

## D-08 — Interest profile via guided interview + per-episode focus request (2026-09-24, planning)
Context: Search needs concrete queries; users describe interests loosely.
Decision: LLM extracts an editable structured profile once; each episode an LLM plans queries from the profile, an optional focus request and recent headlines.
Alternatives: Plain topic tags (weak queries); full chat interview (time-expensive).
Consequences: Planned queries are stored on the episode, so every selection is traceable.

## D-09 — Phase 00 findings (2026-09-24, phase 00)
Context: Every `[VERIFY]` in `docs/ARCHITECTURE.md` and the provider skills had to be confirmed with one real, cheap call each before any pipeline code is written on top of them.
Decision / findings:
- **OpenAI** (`openai` SDK 3.19.2): `gpt-6-sol`, `gpt-6-luna`, `gpt-6-astra` all exist on this key. `client.responses.parse(model=..., input=[...], text_format=PydanticModel, reasoning={"effort": "none"})` works exactly as documented; `resp.output_parsed` is the parsed model, `resp.usage` is a `ResponseUsage` with `input_tokens`, `input_tokens_details` (`cache_write_tokens`, `cached_tokens`), `output_tokens`, `output_tokens_details` (`reasoning_tokens`), `total_tokens`.
- **Exa** (`exa-py` 2.22.2): `exa.search(query, type="auto", contents={"highlights": True}, start_published_date=...)` and `exa.get_contents(urls, text=True)` work as documented (snake_case kwargs only). The SDK response object uses **snake_case attributes**, not the raw HTTP's camelCase: `cost_dollars` (a `CostDollars` object with `.total`, `.search`, `.contents`, not a bare float), `results`, `statuses`, `output`, `resolved_search_type`, `auto_date`, `context`, `search_time`. There is **no `request_id`/`requestId` attribute on the SDK object** (only on the raw HTTP response), contradicting the original skill note — corrected. Search cost for one query: $0.007. Date-filter behavior: on a fast-moving topic ("AI voice agents this week"), the 7-day-windowed and unfiltered searches both returned the full 10-result default with no visible count difference — the documented retry-without-filter path is for slower-moving/narrower topics, not the common case. `/contents` correctly reported `statuses: success` (source: cached) for both test URLs.
- **ElevenLabs** (`elevenlabs` SDK 2.69.0): `client.text_to_dialogue.convert(inputs=[...], model_id="eleven_v3", seed=...)` works as documented, but **`ElevenLabs()` does not read `ELEVENLABS_API_KEY` from the environment** — `api_key=` must be passed explicitly, or every call 401s ("Neither authorization header nor xi-api-key received"). Separately, **this project's key is a take-home-test account key with no dashboard access and a restricted permission scope**: `client.user.subscription.get()` and `client.voices.get_all()` both 401 ("missing the permission user_read" / "voices_read"), so the account's real character quota and voice library are not readable through the API. `text_to_speech` / `text_to_dialogue` themselves are unrestricted. Worked around by verifying ElevenLabs' classic premade voice IDs (Rachel, Domi, Bella, Antoni, Elli, Josh, Arnold, Adam, Sam) live, one 1-word `text_to_speech` call each — all nine responded 200. `output_format="pcm_44100"` is confirmed available on this plan.
- **Voices chosen** (by ear, from 3 candidate `text_to_dialogue` pairs saved to `data/smoke/pair_*.mp3`): **Antoni** (`ErXwobaYiN019PkySvjV`) as host_a/Alex, **Rachel** (`21m00Tcm4TlvDq8ikWAM`) as host_b/Sam. Stored in `.env` as `DEFAULT_VOICE_HOST_A`/`DEFAULT_VOICE_HOST_B`.
- **Jev/Typesafe**: `TYPESAFE_API_KEY` is set, but no SDK or request shape for it exists anywhere in this repo or the installed skills, and phase 00 itself lists the Jev check as the first thing to cut. `jev_check.py` was not written; phase 04 (which is the first phase that actually needs `JevClassifier`) must research the Typesafe API before building that adapter.
Alternatives considered: widening the ElevenLabs key's permissions — not possible, the user has no dashboard access to this test-account key.
Consequences: `GET /voices` in the real API can only return the small hardcoded premade-voice list, not a real account library, until/unless a full-scope ElevenLabs key is available. No ElevenLabs quota check is possible for this project; only `MAX_TTS_CHARS_PER_EPISODE`/`DAILY_SPEND_CAP_USD` guard spend. Total phase 00 spend: OpenAI ~$0.0005 (1 structured call), Exa ~$0.014 (2 searches + 1 contents call), ElevenLabs ~440 characters across 13 small calls (exact $ cost unknown — quota endpoint unreadable, but well under $1 by the public ~$0.10/minute reference rate), Jev $0 (skipped). All well under the $1 budget.

## D-10 — `scripts/setup.py` as the single environment-bootstrap entry point (2026-09-24, phase 00)
Context: Phase 00 needed `uv` and Exa's `build-with-exa` skill, and neither `uv` nor `node`/`npx` were preinstalled on this machine; both had to be worked around by hand (`pip install uv`, `git clone` the skill repo instead of `npx skills add`). That workaround needs to be reproducible for anyone re-cloning the repo, not rediscovered by hand every time.
Decision: `scripts/setup.py`, a dependency-free Python script (Python is guaranteed present; `uv` and `node` are not), is the one command that gets a fresh clone to a working state: installs `uv` via `pip install uv` if missing, copies `.env.example` → `.env` if missing (never overwrites), runs `uv sync` in `backend/`, and installs the `build-with-exa` skill via `npx` if available or a `git clone` fallback (with a Windows-safe recursive delete, since `shutil.rmtree` chokes on git's read-only pack files) if not. `CLAUDE.md` now documents `uv add <package>` (never hand-editing `pyproject.toml` or bare `pip install`) as the only way to add a backend dependency, followed by re-running `scripts/setup.py`/`uv sync` and committing the updated `pyproject.toml` + `uv.lock` alongside the code that needs it.
Alternatives: A `setup.sh`/`setup.ps1` pair — rejected, this project's dev machine mixes Git Bash and PowerShell and a single Python script runs identically in both with no syntax duplication. A bare `README` instruction to run `uv sync` — rejected, it doesn't cover the "`uv`/`node` isn't installed yet" case this session actually hit.
Consequences: `scripts/setup.py` must be kept in sync by hand whenever a future phase needs a new external tool (the way `build-with-exa` was needed in phase 00) — there is no test enforcing that, only the `CLAUDE.md` rule.

## D-11 — One venv only (`backend/.venv`); fix the run command, not a second venv (2026-09-24, phase 00)
Context: Running a `scripts/smoke/*.py` script the "obvious" way — bare `python scripts/smoke/openai_check.py`, or even `uv run python scripts/smoke/openai_check.py` from the repo root — reproducibly hits `ModuleNotFoundError: No module named 'openai'`. Both silently fall back to the system Python (there's no `pyproject.toml` at the repo root for `uv run` to anchor on), not `backend/.venv`, even though `scripts/setup.py` had already `uv sync`'d `backend/.venv` correctly. The user asked whether `scripts/setup.py` should create a second `.venv` (root or `scripts/`) to fix this.
Decision: No second venv. `uv run --project backend python scripts/<path>.py`, run from the repo root, uses the existing `backend/.venv` correctly with no `cd` needed — verified live against `openai_check.py`. Fixed the documented invocation everywhere instead: `scripts/setup.py`'s printed hint, the `Run:` line in each `scripts/smoke/*.py` docstring, and added both a `CLAUDE.md` Commands entry and an Environment-setup rule spelling out that non-`backend/` scripts need `--project backend` or they'll silently use the wrong interpreter.
Alternatives: A second venv under `scripts/` (the user's suggestion) with its own dependency manifest — rejected: it would duplicate openai/exa-py/elevenlabs/python-dotenv across two lockfiles that drift the moment `backend/pyproject.toml` changes, directly contradicting D-10's "single dependency source of truth" rule from earlier this same phase.
Consequences: every future non-`backend/` script (e.g. `eval/` scripts in phase 04) must be invoked with `uv run --project backend ...` from the repo root, or documented with an equivalent explicit `cd backend &&` — bare `python`/bare `uv run` from outside `backend/` is a known foot-gun now written down in `CLAUDE.md`.
