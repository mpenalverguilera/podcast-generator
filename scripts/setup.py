"""One-shot environment bootstrap for this project.

Run after cloning, and again any time `backend/pyproject.toml` gains a new
dependency (see CLAUDE.md "Environment setup"). Idempotent: safe to re-run.

What it does:
1. Makes sure `uv` is on PATH (installs it with `pip install uv` if not).
2. Copies `.env.example` -> `.env` if `.env` doesn't exist yet (never overwrites it).
3. Runs `uv sync` in `backend/`, creating/updating `backend/.venv` from
   `pyproject.toml` + `uv.lock` -- this is the actual "requirements install" step.
4. Installs Exa's official `build-with-exa` skill into `.claude/skills/` if missing,
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


def ensure_env_file() -> None:
    env_path = ROOT / ".env"
    example_path = ROOT / ".env.example"
    if env_path.exists():
        print(".env already exists, leaving it alone.")
        return
    print(".env not found; copying .env.example -> .env.")
    shutil.copyfile(example_path, env_path)
    print("  Fill in real API keys in .env before running anything that hits a real provider.")


def ensure_backend_env(uv: str) -> None:
    if not BACKEND.exists():
        sys.exit(f"{BACKEND} does not exist; nothing to sync.")
    run([uv, "sync"], cwd=BACKEND)


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
    ensure_exa_skill()
    print("\nSetup complete.")
    print("- Backend deps installed/synced in backend/.venv from pyproject.toml + uv.lock")
    print("- Make sure .env has real API keys before running any real provider call")
    print("- Try: uv run --project backend python scripts/smoke/openai_check.py")
    print("  (uv run pytest -q works once a phase adds pytest as a dependency and tests exist)")


if __name__ == "__main__":
    main()
