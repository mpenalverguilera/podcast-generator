from pydantic import SecretStr

from app.config import Settings, get_settings


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_secrets_are_secret_str() -> None:
    s = Settings(
        openai_api_key="k1",
        elevenlabs_api_key="k2",
        exa_api_key="k3",
        jwt_secret="k4",
        seed_admin_password="k5",
        seed_user_password="k6",
    )
    for field in (
        s.openai_api_key,
        s.elevenlabs_api_key,
        s.exa_api_key,
        s.jwt_secret,
        s.seed_admin_password,
        s.seed_user_password,
    ):
        assert isinstance(field, SecretStr)


def test_defaults_match_dot_env_example() -> None:
    # Field defaults, not an instantiated Settings() -- conftest.py forces the
    # provider env vars to "fake" for the whole test session (tests must never
    # hit real APIs), which would otherwise shadow the true field defaults.
    defaults = {name: field.default for name, field in Settings.model_fields.items()}
    assert defaults["search_provider"] == "exa"
    assert defaults["llm_provider"] == "openai"
    assert defaults["classifier_provider"] == "openai"
    assert defaults["tts_provider"] == "elevenlabs"
    assert defaults["max_tts_chars_per_episode"] == 18000
    assert defaults["daily_spend_cap_usd"] == 5.0
