# CLAUDE.md — Personal Podcast Generator

Interview assignment for a Forward Deployed Engineer role at Prosper AI (FastAPI + PostgreSQL + React/TypeScript shop, voice AI agents). The product: a user sets their interests; on a schedule (or on demand) the backend finds news with Exa, writes a grounded two-host script with OpenAI, voices it with ElevenLabs, and publishes an MP3. An admin dashboard shows usage and pipeline metrics.

**What gets judged:** `sample.mp3` (episode quality), `solution.md` (decisions and trade-offs), and whether the author understands every decision. Prefer simple, explainable code over clever code.

## Read first
- `docs/ARCHITECTURE.md` — the design. Follow it; if you need to deviate, say so and log it.
- `docs/DECISIONS.md` — decision log. Append an entry for every non-trivial decision you make.
- `docs/phases/` — the build is done phase by phase. Only do the phase you are asked to do.
- `.claude/skills/` — provider notes: `exa-news-search`, `openai-llm`, `elevenlabs-dialogue`, `podcast-script`. Exa's official `build-with-exa` skill is the canonical source for Exa request shapes.

## Stack and layout
```
backend/            FastAPI, Python 3.12, uv, SQLAlchemy 2 + Alembic, Pydantic v2
  app/
    main.py config.py db.py models.py schemas.py pricing.py cli.py scheduler.py
    adapters/{search,llm,classifier,tts}/   protocol.py, <provider>.py, fake.py
    pipeline/       planner fetch rank extract script voice assemble runner
    prompts/        runtime prompts, versioned: <name>.v<N>.md
    api/            routers
  alembic/  tests/
frontend/           Vite + React + TS, React Router, TanStack Query, Tailwind, Recharts
eval/               classifier eval set and results
scripts/smoke/      provider smoke tests (phase 00)
data/               runtime audio and chunks (gitignored)
docs/               ARCHITECTURE.md, DECISIONS.md, phases/
```

## Commands
```bash
docker compose up -d db                        # Postgres only (dev)
cd backend && uv sync                          # install
uv run alembic upgrade head                    # migrate
uv run uvicorn app.main:app --reload           # API on :8000
uv run python -m app.cli --help                # pipeline CLI (plan, fetch, generate, ...)
uv run pytest -q                               # tests (never hit real APIs)
uv run ruff check . && uv run ruff format .    # lint/format
cd frontend && npm install && npm run dev      # web on :5173
docker compose up --build                      # everything
```

## Rules

**Secrets**
- Keys come only from environment via `app/config.py` (pydantic-settings reading `.env`): `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `EXA_API_KEY`, optional `TYPESAFE_API_KEY` (Jev).
- `.env` is gitignored; `.env.example` lists every variable with a placeholder. Never print, log, or commit a key. Never put a key in frontend code.

**Providers and cost**
- All provider access goes through the adapters in `app/adapters/`. Pipeline code never imports an SDK directly.
- Every adapter call returns `(result, Usage)`; the runner writes a `pipeline_steps` row for each.
- Tests use fake adapters only. Real calls happen only through the CLI or the running app.
- Respect the guardrails `MAX_TTS_CHARS_PER_EPISODE` and `DAILY_SPEND_CAP_USD`. When iterating, use `--minutes 1`, `--tts fake` or `--stop-after scripting` before spending on full TTS runs.
- Model IDs, prices and voice IDs live in config / `pricing.py`, never inline.

**Exa (from Exa's official guidance — see the skill)**
- `/search`: `query`, `type: "auto"`, `contents: {"highlights": true}`, plus `startPublishedDate` for the episode window. Do not add `category`, `numResults`, domain filters or `maxAgeHours`.
- `/contents`: top-level `text: true` for selected URLs only; always check `statuses`.
- Python SDK uses snake_case keyword arguments; always pass `contents` explicitly.

**Pipeline**
- Each stage persists its output and updates `episodes.status`; failures set `failed_stage` and `error`; retry resumes from `failed_stage`.
- Runtime prompts live in `app/prompts/*.vN.md`. Changing a prompt means a new version file; the version used is stored on the episode.
- Scripts are structured output validated with Pydantic; no fact that is not in the provided articles.

**Code style**
- Type hints everywhere; small modules; no premature abstractions beyond the four adapter protocols.
- Log with the standard `logging` module, one line per stage with episode id, duration and cost.
- Frontend: function components and hooks, TanStack Query for server state, no global state library.

**Working style**
- Before coding a phase, restate the plan in a few bullets and list files you will touch.
- Keep changes inside the current phase's scope. If something outside scope is broken, note it in the phase report instead of fixing it silently.
- Finish every phase with: tests passing, lint clean, the phase's acceptance checks run and shown, a `docs/DECISIONS.md` entry, and one commit (`phase NN: <summary>`).
- End with a short report: what was built, how it was verified, what is left, and any `[VERIFY]` items still open.
