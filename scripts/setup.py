"""One-shot environment bootstrap for this project.

Run after cloning, and again any time `backend/pyproject.toml` gains a new
dependency (see CLAUDE.md "Environment setup"). Idempotent: safe to re-run.

What it does:
1. Makes sure `uv` is on PATH (installs it with `pip install uv` if not).
2. Creates `.env` if it doesn't exist yet (never overwrites it): if this checkout is a git worktree
   (`.claude/worktrees/<name>`), copies the real `.env` from the main checkout, since `.env` is
   gitignored and a new worktree doesn't get it; otherwise copies `.env.example` -> `.env`.
3. Runs `uv sync` in `backend/`, creating/updating `backend/.venv` from
   `pyproject.toml` + `uv.lock` -- this is the actual "requirements install" step.
4. Starts the `db` service from `docker-compose.yml` (`docker compose up -d --wait db`) and
   waits for its healthcheck -- requires Docker to be installed and running.
5. Runs Alembic migrations (`alembic upgrade head`) against that db.
6. Seeds the db: `seed-users` (idempotent admin/demo/classifier-eval users from `.env`) and
   `seed-metrics` (synthetic usage data for the admin dashboard; safe to re-run -- it replaces
   its own previously seeded rows and never touches real ones).
7. Installs Exa's official `build-with-exa` skill into `.claude/skills/` if missing,
   via `npx skills add ...` when Node is available, else by cloning
   `exa-labs/agent-skills` and copying just that skill folder (this repo's fallback,
   used in phase 00 where neither `node` nor `npx` were on PATH).

Usage: `python scripts/setup.py` (plain Python 3, no dependencies of its own --
this has to run *before* the backend venv exists).
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def rmtree_force(path: Path) -> None:
    """shutil.rmtree that also removes read-only files (git objects on Windows)."""

    def on_error(func, target_path, _exc):
        os.chmod(target_path, stat.S_IWRITE)
        func(target_path)

    shutil.rmtree(path, onexc=on_error)


def ensure_uv() -> str:
    uv = shutil.which("uv")
    if uv:
        return uv
    print("uv not found on PATH; installing with `pip install uv`...")
    run([sys.executable, "-m", "pip", "install", "uv"])
    uv = shutil.which("uv")
    if not uv:
        sys.exit(
            "uv installed but still not on PATH in this shell. "
            "Open a new terminal (so PATH picks it up) and re-run this script."
        )
    return uv


def find_main_worktree_env() -> Path | None:
    """If ROOT is a linked git worktree, return the main checkout's `.env` path, if it has one.

    A linked worktree's `--git-dir` (its own `<main>/.git/worktrees/<name>`) differs from its
    `--git-common-dir` (the main repo's shared `<main>/.git`); a plain checkout's are the same
    path. `.env` is gitignored, so `git worktree add` never brings it along -- copy it from the
    main checkout instead of leaving the new worktree on `.env.example` placeholders.
    """
    git = shutil.which("git")
    if not git:
        return None
    try:
        common_dir = subprocess.run(
            [git, "rev-parse", "--git-common-dir"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout.strip()
        git_dir = subprocess.run(
            [git, "rev-parse", "--git-dir"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return None
    common_dir_path = (ROOT / common_dir).resolve()
    git_dir_path = (ROOT / git_dir).resolve()
    if common_dir_path == git_dir_path or common_dir_path.name != ".git":
        return None  # not a linked worktree
    main_env = common_dir_path.parent / ".env"
    return main_env if main_env.exists() else None


def ensure_env_file() -> None:
    env_path = ROOT / ".env"
    example_path = ROOT / ".env.example"
    if env_path.exists():
        print(".env already exists, leaving it alone.")
        return

    main_env = find_main_worktree_env()
    if main_env is not None:
        print("This is a git worktree; .env is gitignored so it wasn't checked out here.")
        print(f"Copying the real .env from the main checkout ({main_env}) -- values not printed.")
        shutil.copyfile(main_env, env_path)
        print("  Copied. Confirm it has the keys you expect before running real provider calls.")
        return

    print(".env not found; copying .env.example -> .env.")
    shutil.copyfile(example_path, env_path)
    print("  Fill in real API keys in .env before running anything that hits a real provider.")


def ensure_backend_env(uv: str) -> None:
    if not BACKEND.exists():
        sys.exit(f"{BACKEND} does not exist; nothing to sync.")
    # --link-mode=copy: uv's default (hardlink) fails on Windows when the repo lives inside a
    # cloud-synced folder (OneDrive, etc.) -- "cloud operation cannot be performed on a file with
    # incompatible hardlinks" (os error 396). Copying is a little slower but works everywhere.
    run([uv, "sync", "--link-mode=copy"], cwd=BACKEND)


def ensure_db() -> None:
    """Brings up the `db` compose service and waits for it to be healthy."""
    docker = shutil.which("docker")
    if not docker:
        sys.exit(
            "docker not found on PATH. Install Docker Desktop (Windows/macOS) or Docker "
            "Engine + the compose plugin (Linux), make sure it's running, and re-run this script."
        )
    run([docker, "compose", "up", "-d", "--wait", "db"], cwd=ROOT)


def run_migrations(uv: str) -> None:
    run([uv, "run", "alembic", "upgrade", "head"], cwd=BACKEND)


def seed_database(uv: str) -> None:
    run([uv, "run", "python", "-m", "app.cli", "seed-users"], cwd=BACKEND)
    run([uv, "run", "python", "-m", "app.cli", "seed-metrics"], cwd=BACKEND)


def ensure_exa_skill() -> None:
    skill_dir = ROOT / ".claude" / "skills" / "build-with-exa"
    if skill_dir.exists():
        print("build-with-exa skill already installed, skipping.")
        return

    npx = shutil.which("npx")
    if npx:
        print("Installing Exa's official skill via npx...")
        run([npx, "skills", "add", "exa-labs/agent-skills", "--skill", "build-with-exa"], cwd=ROOT)
        return

    print("npx not found on PATH; falling back to cloning exa-labs/agent-skills...")
    git = shutil.which("git")
    if not git:
        print("git not found either; skipping build-with-exa skill install (do it manually later).")
        return

    tmp = ROOT / ".setup-tmp-agent-skills"
    if tmp.exists():
        rmtree_force(tmp)
    run([git, "clone", "--depth", "1", "https://github.com/exa-labs/agent-skills.git", str(tmp)])
    shutil.copytree(tmp / "skills" / "build-with-exa", skill_dir)
    rmtree_force(tmp)
    print(f"Installed build-with-exa skill to {skill_dir}")


def main() -> None:
    uv = ensure_uv()
    ensure_env_file()
    ensure_backend_env(uv)
    ensure_db()
    run_migrations(uv)
    seed_database(uv)
    ensure_exa_skill()
    print("\nSetup complete.")
    print("- Backend deps installed/synced in backend/.venv from pyproject.toml + uv.lock")
    print("- Postgres is up (docker compose, db service), migrated to head, and seeded")
    print("  Log in with SEED_USER_EMAIL/SEED_USER_PASSWORD from .env (demo@example.com/demo by")
    print("  default), or SEED_ADMIN_EMAIL/SEED_ADMIN_PASSWORD for the admin dashboard")
    print("- Make sure .env has real API keys before running any real provider call")
    print("- Try: uv run --project backend python scripts/smoke/openai_check.py")
    print("  (cd backend && uv run pytest -q to run the test suite)")


if __name__ == "__main__":
    main()
