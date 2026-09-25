from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# app/config.py -> app/ -> backend/ -> repo root. Resolved as an absolute path so
# Settings() finds .env regardless of invocation cwd (uv run uvicorn ... from
# backend/, uv run --project backend python scripts/... from repo root, pytest
# from either) -- see docs/DECISIONS.md D-11 for the cwd footgun this avoids.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    # Providers -- optional so fake-only dev/test setups need no real keys; a
    # real adapter fails clearly at construction time if its key is missing.
    openai_api_key: SecretStr | None = None
    elevenlabs_api_key: SecretStr | None = None
    exa_api_key: SecretStr | None = None
    # Jev (TypeSafe) is only reachable through Vercel's AI Gateway, not TypeSafe's own API --
    # see docs/DECISIONS.md D-33 (D-32's direct-SDK integration used the wrong key/endpoint).
    ai_gateway_api_key: SecretStr | None = None
    search_provider: Literal["exa", "fake"] = "exa"
    llm_provider: Literal["openai", "fake"] = "openai"

    # Database -- plain str, not SecretStr: SQLAlchemy/Alembic need it unwrapped
    # constantly, and it's a local dev password, not worth the wrapping friction.
    database_url: str = "postgresql+psycopg://podcast:podcast@localhost:5432/podcast"

    # Auth
    jwt_secret: SecretStr = SecretStr("change-me")
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: SecretStr = SecretStr("admin")
    seed_user_email: str = "demo@example.com"
    seed_user_password: SecretStr = SecretStr("demo")
    seed_eval_user_email: str = "eval@example.com"
    seed_eval_user_password: SecretStr = SecretStr("eval")

    # Models
    model_profile: str = "gpt-6-sol"
    model_planner: str = "gpt-6-luna"
    model_classifier: str = "gpt-6-luna"
    model_script: str = "gpt-6-sol"
    model_script_reasoning: str = "medium"
    model_grounding: str = "gpt-6-luna"
    model_grounding_reasoning: str = "low"
    # Vercel AI Gateway model slug (provider/model), not a TypeSafe-native version string
    # (D-33). Pinned rather than an alias so classifier eval numbers stay reproducible.
    model_jev: str = "typesafe-ai/jev"
    # D-34: the real eval (eval/results/latest.md) found Jev non-inferior to Luna on the
    # production keep gate, ~2x cheaper and ~5x faster p50 -- now the default, with a per-article
    # fallback to Luna (FallbackClassifier, app/adapters/classifier/__init__.py) on Jev errors.
    classifier_provider: Literal["openai", "jev", "fake"] = "jev"
    jev_timeout_s: float = 30.0

    # TTS
    tts_provider: Literal["elevenlabs", "fake"] = "elevenlabs"
    elevenlabs_model: str = "eleven_v3"
    elevenlabs_output_format: str = "mp3_44100_128"
    default_voice_host_a: str = ""
    default_voice_host_b: str = ""
    elevenlabs_usd_per_1k_chars: float = 0.11

    # Guardrails
    max_tts_chars_per_episode: int = 12000
    daily_spend_cap_usd: float = 5.0

    # Paths
    data_dir: Path = Path("./data")


@lru_cache
def get_settings() -> Settings:
    return Settings()
