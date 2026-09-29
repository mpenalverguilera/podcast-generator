# Personal Podcast Generator

A user sets their interests; on a schedule (or on demand) the backend finds news with
[Exa](https://exa.ai), writes a grounded two-host script with OpenAI, voices it with
ElevenLabs, and publishes an MP3. An admin dashboard shows usage and pipeline metrics.

Backend: FastAPI, Python 3.12, PostgreSQL. Frontend: Vite + React + TypeScript.
See `solution.md` for the decisions, trade-offs and next steps, `docs/ARCHITECTURE.md` for the full design (with diagrams) and `docs/DECISIONS.md` for the decision log.

## Requirements

- **Git**
- **Python 3.12+** (with `pip`) — `scripts/setup.py` uses it to bootstrap `uv`
- **Node.js 20+** (`npm`/`npx`) — frontend, and used by `scripts/setup.py` to install the Exa skill
- **Docker** (Desktop on Windows/macOS, Engine + Compose plugin on Linux) — runs Postgres

You do **not** need to install `uv` yourself — `scripts/setup.py` installs it automatically.

<details>
<summary>Windows (PowerShell, <code>winget</code>)</summary>

```powershell
winget install Git.Git Python.Python.3.12 OpenJS.NodeJS.LTS Docker.DockerDesktop
```

Then start Docker Desktop before continuing.
</details>

<details>
<summary>Linux (Debian/Ubuntu, <code>apt</code>)</summary>

```bash
sudo apt update && sudo apt install -y git python3.12 python3-pip nodejs npm
```

Docker install varies by distro/version — follow
[Docker's own Engine + Compose plugin install docs](https://docs.docker.com/engine/install/)
for yours, then make sure the daemon is running (`sudo systemctl start docker`).
</details>

## Quickstart

1. **Bootstrap everything** — installs `uv`, creates `.env` from `.env.example`, installs
   backend deps, starts Postgres via Docker Compose, runs migrations, and seeds the db
   (admin/demo/eval users, plus synthetic dashboard data):

   ```bash
   python scripts/setup.py
   ```
   *Note:* It's recommended to run it in a plain PS terminal (when running it from VSCode fails due to a keyboard interrupt when creating the virtual environment)

2. **Add real API keys** — open `.env` and fill in `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`,
   `EXA_API_KEY`. Not needed for steps 3-5 below, but required for anything that generates a
   real episode.

3. **Start the API** (from `backend/`):

   ```bash
   cd backend
   uv run uvicorn app.main:app --reload --reload-dir app
   ```

   Serves on `http://localhost:8000`.

4. **Start the frontend** (from `frontend/`, in another terminal):

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   Serves on `http://localhost:5173`.

5. **Log in** at `http://localhost:5173` with the seeded demo user
   (`SEED_USER_EMAIL` / `SEED_USER_PASSWORD` in `.env`, default `demo@example.com` / `demo`),
   or the admin user (`SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`, default
   `admin@example.com` / `admin`) to see the dashboard.

Re-running `python scripts/setup.py` any time is safe — every step is idempotent.

## Pipeline CLI

The backend also ships a CLI for driving the pipeline directly, without the API. From `backend/`:

```bash
uv run python -m app.cli --help
```

A couple of commonly used commands:

```bash
uv run python -m app.cli generate --user demo@example.com   # create + run a full episode
uv run python -m app.cli show <episode_id>                  # status, cost and pipeline steps
```

Run `--help` on any subcommand for its options.

## More

Full command list, provider/cost rules, and coding conventions live in `CLAUDE.md`.
Design and decisions live in `docs/ARCHITECTURE.md` and `docs/DECISIONS.md`.
