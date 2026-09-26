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
scripts/setup.py    one-shot environment bootstrap (uv, .env, backend deps, build-with-exa skill)
scripts/smoke/      provider smoke tests (phase 00)
data/               runtime audio and chunks (gitignored)
docs/               ARCHITECTURE.md, DECISIONS.md, phases/
```

## Commands
```bash
python scripts/setup.py                        # one-shot bootstrap: installs uv if missing,
                                                 # creates .env from .env.example, uv sync's backend/
docker compose up -d db                        # Postgres only (dev)
cd backend && uv sync                          # install (also what scripts/setup.py runs)
uv run alembic upgrade head                    # migrate
uv run uvicorn app.main:app --reload           # API on :8000
uv run python -m app.cli --help                # pipeline CLI (plan, fetch, generate, ...)
LOG_LEVEL=DEBUG uv run python -m app.cli generate --user demo@example.com   # verbose terminal logs
uv run pytest -q                               # tests (never hit real APIs)
uv run ruff check . && uv run ruff format .    # lint/format
uv run --project backend python scripts/smoke/<name>.py   # provider smoke tests, run from repo root
uv run --project backend python eval/build_set.py --episode-id <id>       # phase 04 Part B, from repo root
uv run --project backend ruff check --config backend/pyproject.toml eval/ # lint eval/ (no root ruff config)
cd frontend && npm install && npm run dev      # web on :5173
docker compose up --build                      # everything
```

## Rules

**Secrets**
- Keys come only from environment via `app/config.py` (pydantic-settings reading `.env`): `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `EXA_API_KEY`, `AI_GATEWAY_API_KEY` (Jev, via Vercel AI Gateway — see D-40/D-42; free evaluation credits need a card on file with Vercel). Needed only when `CLASSIFIER_PROVIDER=jev`; Jev then retries transient errors and falls back per article to the OpenAI classifier, `MODEL_CLASSIFIER` (`FallbackClassifier`).
- `.env` is gitignored; `.env.example` lists every variable with a placeholder. Never print, log, or commit a key. Never put a key in frontend code.

**Environment setup**
- `scripts/setup.py` is the single source of truth for "how do I get a working environment." It installs `uv` if missing, creates `.env` if missing (from the main checkout's real `.env` when run inside a git worktree, else from `.env.example`), and runs `uv sync` in `backend/` — which installs from `backend/pyproject.toml` + `backend/uv.lock`, the actual dependency manifest.
- A new git worktree (`.claude/worktrees/<name>`) does not get `.env` — it's gitignored, so `git worktree add` never brings it along, and a bare `scripts/setup.py` there fills `.env` from `.env.example` placeholders instead. Any real-provider call (a smoke script, `cli generate`, the classifier eval notebook) will then fail or silently authenticate as nothing. Run `python scripts/setup.py` in the new worktree before any real call — it now copies the main checkout's `.env` automatically when it detects a worktree. If that copy is ever blocked (e.g. a sandbox deny rule on `.env` paths), stop and ask the user to run it themselves with `! cp <main-repo>/.env .env` from the worktree root, rather than working around the block or running real calls against placeholder keys.
- Never add a dependency by hand-editing `pyproject.toml` or running bare `pip install`. Add it with `uv add <package>` (or `uv add --dev <package>`) from `backend/`; this updates both `pyproject.toml` and `uv.lock` together, which is what makes `uv sync` reproducible for everyone else.
- After adding, removing, or upgrading a dependency, re-run `python scripts/setup.py` (or `uv sync`) yourself to confirm it installs clean, and commit the updated `pyproject.toml` + `uv.lock` in the same commit as the code that needs the new dependency.
- If a phase needs a new external tool the way phase 00 needed Exa's `build-with-exa` skill, add its bootstrap step to `scripts/setup.py` too (with a fallback if the usual installer — e.g. `npx` — isn't guaranteed to be on PATH) rather than leaving it as a one-off manual step in a phase report.
- There is deliberately only **one** Python environment in this repo: `backend/.venv`. Scripts that live outside `backend/` (e.g. `scripts/smoke/`) still run against it, via `uv run --project backend python scripts/<path>.py` from the repo root — never a bare `python scripts/...` or a bare `uv run python scripts/...` from outside `backend/`, both of which silently fall back to the system interpreter and look like "missing dependencies" when they're really just running the wrong Python.

**Providers and cost**
- All provider access goes through the adapters in `app/adapters/`. Pipeline code never imports an SDK directly.
- Every adapter call returns `(result, Usage)`; the runner writes a `pipeline_steps` row for each.
- Tests use fake adapters only. Real calls happen only through the CLI or the running app.
- Respect the guardrails `MAX_TTS_CHARS_PER_EPISODE` and `DAILY_SPEND_CAP_USD`. When iterating, use `--minutes 1`, `--tts fake` or `--stop-after scripting` before spending on full TTS runs.
- Model IDs, prices and voice IDs live in config / `pricing.py`, never inline.
- `pipeline_steps.units_in` is always the provider's exact count (OpenAI tokens, Exa's own `costDollars`, ElevenLabs' `character-cost` response header). `cost_usd` is exact for Exa/OpenAI but an estimate for ElevenLabs (`units_in × ELEVENLABS_USD_PER_1K_CHARS`, a config default since the real plan price isn't visible with this key) — flag it with `cost_is_estimate` on the row and label it as an estimate anywhere it's shown (dashboard, `solution.md`). See `docs/DECISIONS.md` D-12.

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
