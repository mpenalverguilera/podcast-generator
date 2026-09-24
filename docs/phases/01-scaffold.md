# Phase 01 — Scaffold: repo, database, config, adapters, CLI

## Context
Read `CLAUDE.md`, `docs/ARCHITECTURE.md` §4, §5 (status machine only), §6, §7, and `docs/DECISIONS.md`
D-09 (phase 00 findings). Use the verified call shapes from phase 00.

## Goal
A running skeleton: Postgres up, schema migrated, config loaded, all four adapter protocols with real
and fake implementations, a pipeline runner that moves a fake episode through every status, and a CLI.

## Build
1. **Repo and tooling**
   - `docker-compose.yml`: `db` (postgres:16, volume, healthcheck), `api` (backend Dockerfile, depends on db),
     `web` placeholder (built in phase 06). Include ffmpeg in the api image.
   - `backend/pyproject.toml` via uv: fastapi, uvicorn, sqlalchemy>=2, alembic, psycopg[binary],
     pydantic-settings, openai, exa-py, elevenlabs, pydub, apscheduler, python-jose or pyjwt, passlib[bcrypt],
     typer; dev: pytest, ruff.
   - `ruff` config in pyproject (line length 100).
2. **Config** `app/config.py`: pydantic-settings `Settings` with every variable in `.env.example`; secrets as
   `SecretStr`; `get_settings()` cached.
3. **Database** `app/db.py`, `app/models.py`: SQLAlchemy 2 typed models for every table in ARCHITECTURE §7.
   `EpisodeStatus` enum = pending, planning, fetching, ranking, extracting, scripting, voicing, assembling,
   ready, failed. First Alembic migration.
4. **Schemas** `app/schemas.py`: Pydantic models shared by pipeline and API: `InterestProfile`, `Topic`,
   `PlannedQuery`, `RawArticle`, `ContentResult`, `ArticleScore`, `Script`, `Section`, `Turn`, `Usage`.
   `Script` matches ARCHITECTURE §5.5 exactly.
5. **Pricing** `app/pricing.py`: per-model token prices; `ELEVENLABS_USD_PER_1K_CHARS` (config, `.env.example`,
   default 0.11 — an estimate, see D-12) for ElevenLabs; function `cost_for(provider, model, units_in, units_out)`
   returning `(cost_usd, cost_is_estimate)` — `cost_is_estimate=True` only for ElevenLabs, since its `units_in`
   is exact (the `character-cost` response header) but the $/character rate is not. `pipeline_steps` needs a
   `cost_is_estimate` boolean column (ARCHITECTURE §7).
6. **Adapters** `app/adapters/{search,llm,classifier,tts}/` each with `protocol.py`, real implementation,
   `fake.py`, and a `get_<kind>()` factory reading config. Real implementations follow the skills exactly.
   Fakes are deterministic (fixtures from phase 00 for search; canned JSON for LLM keyed by schema type;
   silence for TTS).
7. **Prompt loader** `app/prompts/__init__.py`: loads `<name>.v<N>.md`, parses the small front matter,
   renders placeholders, returns text + version. Latest version by default.
8. **Runner** `app/pipeline/runner.py`: `run_episode(episode_id, stop_after=None)` executes stages in order,
   skips stages already completed, wraps each stage to write a `pipeline_steps` row (stage-level) and to
   set `failed_stage`/`error` on exceptions, enforces `DAILY_SPEND_CAP_USD`. Stage functions are stubs that
   just advance status in this phase.
9. **CLI** `app/cli.py` (typer): `seed-users`, `new-episode --user <email> [--focus "..."] [--minutes N]`,
   `run <episode_id> [--stop-after STAGE] [--tts fake]`, `show <episode_id>` (status, steps, costs).
10. **Seed** `seed-users` creates the admin and demo users from env with a default profile and preferences.
11. **Health** minimal FastAPI `app/main.py` with `GET /health` (DB check).

## Acceptance
- `docker compose up -d db && uv run alembic upgrade head` works on a fresh volume.
- `uv run python -m app.cli seed-users` then `new-episode --user demo@example.com` then `run <id>` (all fakes)
  ends in status `ready` with one `pipeline_steps` row per stage; `show <id>` prints them.
- Tests: adapter factories return fakes when configured; runner resumes from `failed_stage` after a
  forced failure; prompt loader picks the latest version.
- `uv run pytest -q` and `uv run ruff check .` pass.

## Out of scope
Real stage logic, API routes beyond health, frontend.

## Cut first
Dockerfile for api (run it locally with uv instead; add Docker in phase 08).

## Finish
Decision entry for anything you chose that isn't in the docs (e.g. JWT library). Commit
`phase 01: scaffold, schema, adapters, runner and CLI`.
