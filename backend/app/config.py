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
    # see docs/DECISIONS.md D-43 (D-42's direct-SDK integration used the wrong key/endpoint).
    ai_gateway_api_key: SecretStr | None = None
    search_provider: Literal["exa", "fake"] = "exa"
    llm_provider: Literal["openai", "fake"] = "openai"

    # Database -- plain str, not SecretStr: SQLAlchemy/Alembic need it unwrapped
    # constantly, and it's a local dev password, not worth the wrapping friction.
    database_url: str = "postgresql+psycopg://podcast:podcast@localhost:5432/podcast"

    # Auth
    jwt_secret: SecretStr = SecretStr("change-me")
    # Comma-separated allowed origins for CORS (the Vite dev server by default).
    cors_origins: str = "http://localhost:5173"
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: SecretStr = SecretStr("admin")
    seed_user_email: str = "demo@example.com"
    seed_user_password: SecretStr = SecretStr("demo")
    seed_eval_user_email: str = "eval@example.com"
    seed_eval_user_password: SecretStr = SecretStr("eval")

    # Models
    model_profile: str = "gpt-6-sol"
    model_planner: str = "gpt-6-luna"
    # D-45: Sol, the classifier eval's verdict (eval/results/latest.md). Luna (gpt-6-luna) and Jev
    # (CLASSIFIER_PROVIDER=jev) stay one .env change away.
    model_classifier: str = "gpt-6-sol"
    model_script: str = "gpt-6-sol"
    model_script_reasoning: str = "medium"
    model_grounding: str = "gpt-6-luna"
    model_grounding_reasoning: str = "low"
    # Vercel AI Gateway model slug (provider/model), not a TypeSafe-native version string
    # (D-43). Pinned rather than an alias so classifier eval numbers stay reproducible.
    model_jev: str = "typesafe-ai/jev"
    # The default follows the classifier eval verdict (eval/results/latest.md, D-45). "jev" is
    # always wrapped in a per-article fallback to the OpenAI classifier (FallbackClassifier) on
    # Jev errors.
    classifier_provider: Literal["openai", "jev", "fake"] = "openai"
    # Per attempt. JevClassifier retries 502/503/504 and transport errors up to jev_max_attempts
    # times; a 429 pauses every Jev call for jev_rate_limit_cooldown_s instead (D-45). Whatever
    # still fails is scored by the OpenAI classifier (FallbackClassifier).
    jev_timeout_s: float = 30.0
    jev_max_attempts: int = 3
    jev_rate_limit_cooldown_s: float = 300.0

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

    # Logging -- terminal-only, architectural (stage transitions, not
    # per-request provider chatter); see app/logging_setup.py.
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
