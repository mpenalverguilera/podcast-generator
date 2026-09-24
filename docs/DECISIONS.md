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

## D-12 — ElevenLabs per-call cost comes from the `character-cost` response header (2026-09-24, phase 00)
Context: `text_to_dialogue.convert()`'s response body is the audio itself, so the normal SDK return value has nowhere for a cost number to live, and D-09 already found this project's key can't read `user.subscription.get()` (no account-level quota either). Needed a real number for `Usage.units_in`/`pipeline_steps.cost_usd` in the future TTS adapter (phase 03) that isn't just re-deriving `len(text)`.
Decision: confirmed live via `client.text_to_dialogue.with_raw_response.convert(...)` (a `@contextlib.contextmanager`-decorated method on `elevenlabs` SDK 2.69.0, so `with ... as resp:` is required) — a 36-character 2-turn test call (`scripts/smoke/elevenlabs_headers.py`) returned response header `character-cost: 36`, exactly matching characters sent including tags, plus `request-id: OgDy9eSGGYSpJ3Lnmh9p` and a bonus `tts-latency-ms: 605`. The TTS adapter will read `Usage.units_in` from `character-cost` (tagged `usage_source="header"` on `pipeline_steps`) and store `request-id` on the row for debugging, with a character-count fallback (`usage_source="estimated"`) only if the header is ever absent. `.claude/skills/elevenlabs-dialogue/SKILL.md` updated: the documented adapter call now uses `with_raw_response`, not plain `.convert()`.
Alternatives: estimating `Usage.units_in` purely from `sum(len(t.text) for t in turns)` — rejected as the default (kept only as a defensive fallback) now that the provider's own billed number is directly readable and confirmed present on every phase 00 call.
Consequences: summing `character-cost` across `pipeline_steps` rows is this project's only available "characters used so far" figure (no account-level quota to check it against, per D-09) — `pricing.py`'s dollar-per-character rate stays an estimate, called out as such in `solution.md`, since the real plan pricing isn't visible with this scoped key. `history-item-id` came back `not_stored` on this call, so ElevenLabs-side history/playback isn't available as a fallback audit trail either — `pipeline_steps` is the only record. Dashboard shows characters as exact, dollars as estimated.

## D-13 — `backend/app` package layout replaces the `uv init` scaffold (2026-09-24, phase 01)
Context: phase 00's `uv init` created `backend/src/backend/__init__.py` (a src-layout package named `backend`), which doesn't match CLAUDE.md's documented layout (`backend/app/main.py`, `config.py`, etc. — a flat package named `app`). Phase 00 never needed real app code, so the mismatch went unnoticed until phase 01 had to actually build the package.
Decision: deleted `backend/src/`, created a flat `backend/app/` package, and added `[tool.uv.build-backend] module-name = "app"` / `module-root = ""` to `backend/pyproject.toml` so `uv sync` installs `app` as the importable module while the distribution name stays `backend`. Removed the now-dead `[project.scripts] backend = "backend:main"` entry point — the CLI is invoked via `uv run python -m app.cli`, per CLAUDE.md.
Alternatives: renaming the distribution itself to `app` — rejected, no reason to change `project.name`, only the importable module needed to match the docs.
Consequences: verified with `uv sync` + `uv run python -c "import app"` before building anything on top; any future confusion between "package `backend`" and "module `app`" should point back here.

## D-14 — pyjwt over python-jose (2026-09-24, phase 01)
Context: `docs/phases/01-scaffold.md` names both as acceptable JWT libraries and asks for the choice to be logged.
Decision: `pyjwt` — smaller surface, more actively maintained, and this project only ever needs HS256 sign/verify (no JWK sets, no JWE).
Alternatives: `python-jose` — broader JOSE-suite support (multiple crypto backends, JWE) that buys nothing here.
Consequences: none beyond the dependency choice; revisit only if a future phase needs JOSE features `pyjwt` doesn't have.

## D-15 — Every adapter factory takes a provider override; two config vars added beyond `.env.example` (2026-09-24, phase 01)
Context: `.env.example` only defined `CLASSIFIER_PROVIDER`/`TTS_PROVIDER`, but tests must be able to force *every* adapter to fake regardless of what a developer's local `.env` has configured (CLAUDE.md: tests never hit real APIs), and the CLI's `--tts fake` flag needed a per-call override mechanism anyway.
Decision: added `SEARCH_PROVIDER` (`exa|fake`, default `exa`) and `LLM_PROVIDER` (`openai|fake`, default `openai`) to `Settings` and `.env.example`. All four `get_<kind>()` factories share the shape `(settings=None, override=None)`; `backend/tests/conftest.py` sets all four provider env vars to `"fake"` for the whole test session before any `app.*` import.
Alternatives: monkeypatching adapter instances directly in tests instead of adding config knobs — rejected, less uniform across the four adapter kinds and doesn't help the CLI's `--tts fake` flag, which needs the same override path.
Consequences: `.env.example` now documents two variables beyond ARCHITECTURE §6's literal adapter list; low risk, but noted here since it's a tracked-file change beyond the phase doc's explicit ask.

## D-16 — `pipeline_steps.usage_source` / `provider_request_id` columns added beyond ARCHITECTURE §7 (2026-09-24, phase 01)
Context: D-12 committed to storing ElevenLabs' `character-cost` provenance and `request-id` "on the row" for debugging, but ARCHITECTURE §7's `pipeline_steps` column list has nowhere for either to live.
Decision: added `usage_source` (`exact|header|estimated|fake`) and `provider_request_id` (nullable string) columns to `pipeline_steps`.
Alternatives: leaving them out and only logging them — rejected, D-12 explicitly wants them on the persisted row, not just in application logs.
Consequences: minor schema drift from the literal §7 list, but a direct implementation of D-12's own stated requirement, not a new one.

## D-17 — Native enum columns store `.value`, not SQLAlchemy's default `.name` (2026-09-24, phase 01)
Context: SQLAlchemy's `Enum(SomePyEnum)` persists each member's `.name` (e.g. `"PENDING"`) by default, not `.value` (`"pending"`) — true even for an `enum.StrEnum` member that *is* a string. ARCHITECTURE §5/§7 specify lowercase enum values, and `pipeline_steps.stage` (a plain string column) already stores lowercase (`EpisodeStatus.PLANNING.value`), so the enum columns would otherwise be silently inconsistent with both the docs and the sibling column.
Decision: added a `_pg_enum(enum_cls, name)` helper in `app/models.py` that passes `values_callable=lambda members: [m.value for m in members]` to every native enum column (`episode_status`, `episode_trigger`, `content_source`, `step_status`).
Alternatives: SQLAlchemy's default `.name`-based storage — rejected as contradicting the documented lowercase values and surprising anyone querying the DB directly.
Consequences: caught before the first migration was ever applied, by inspecting the autogenerated migration's `sa.Enum(...)` calls (they showed uppercase names) rather than assuming the default was correct — the same check is worth repeating for any enum column added in a later phase.

## D-18 — Test DB isolation, and a SQLAlchemy URL-masking footgun (2026-09-24, phase 01)
Context: tests need a real Postgres (JSONB and native enums aren't SQLite-portable) but must never touch the developer's real dev database. While wiring this up, `backend/tests/conftest.py` derived the test DB's connection string with `str(url.set(database=f"{name}_test"))` — which compiled and looked correct when printed, but every test then failed with `password authentication failed for user "podcast"` even though the same credentials worked fine everywhere else.
Decision: the cause is that `str(sqlalchemy.engine.URL)` masks the password as the literal text `"***"` by default (it exists for safe logging) — so the "working" connection string actually had `***` baked in as the real password. Fixed by using `url.render_as_string(hide_password=False)` instead of `str(url)` when building a connection string that will actually be used to connect. `conftest.py` now creates a `<dbname>_test` database via a maintenance connection if missing, and calls `Base.metadata.create_all()` against it once per session — not `alembic upgrade head`, to keep tests fast and decoupled from migration authoring (whose own correctness is covered separately by the `docker compose up -d db && alembic upgrade head` acceptance check).
Alternatives: SQLite for tests — rejected, per CLAUDE.md's Postgres-only stack and this schema's use of JSONB/native enums. Debugging by re-checking credentials first — the confusing part was that the error pointed at Postgres auth, not at Python string handling, so this is written down for the next person who hits the same red herring.
Consequences: any future code that builds a Postgres connection string from a `sqlalchemy.engine.URL` object must use `render_as_string(hide_password=False)`, never `str()`, for anything other than logging.

## D-19 — `bcrypt` pinned below 4.1 for `passlib` compatibility (2026-09-24, phase 01)
Context: `passlib[bcrypt]` 1.7.4 probes `bcrypt.__about__.__version__` to detect its backend version; `bcrypt>=4.1` removed that attribute. The failure mode is misleading: every `CryptContext.hash()` call (i.e. every `seed-users` run) raised `ValueError: password cannot be longer than 72 bytes, truncate manually if necessary`, even for the 5-character seed passwords — a known passlib/bcrypt incompatibility, not a real length violation. This was flagged as a risk during planning and hit live on the first `seed-users` test run.
Decision: pinned `bcrypt<4.1` alongside `passlib[bcrypt]` via `uv add "bcrypt<4.1"` (resolved to 4.0.1).
Alternatives: switching to a different hashing library — rejected, this is a narrow, well-understood incompatibility with a one-line fix, not a reason to change libraries.
Consequences: revisit this pin if `passlib` ships a fix for the `bcrypt>=4.1` probe, or if `bcrypt`/`passlib` are ever upgraded independently of each other.

## D-20 — Docker Desktop is a manual prerequisite, not automated by `scripts/setup.py` (2026-09-24, phase 01)
Context: phase 01 needs Postgres via `docker compose up -d db`; this dev machine had no Docker, no WSL, and no native Postgres installed. Installed Docker Desktop via `winget install --id Docker.DockerDesktop`, which required a full system restart (WSL2 backend initialization) before the `docker` CLI worked.
Decision: left Docker Desktop as a manual, one-time, human-run prerequisite — already implied by `docs/phases/README.md`'s "Docker, uv, Node 20+, ffmpeg installed locally" prerequisite list — rather than teaching `scripts/setup.py` to install it.
Alternatives: scripting the Docker Desktop install into `scripts/setup.py` the way D-10 scripted `uv`/`build-with-exa` — rejected, a Docker Desktop install needs admin rights and typically a reboot, unlike `pip install uv` or a `git clone`; not something a bootstrap script can safely automate unattended.
Consequences: a fresh clone still needs a human to install Docker Desktop (or an equivalent local Postgres) once, by hand, before `docker compose up -d db` works — this was already true before phase 01, just not yet exercised.
