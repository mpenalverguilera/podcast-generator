import logging

from app.logging_setup import configure_logging


def _podcast_generator_handlers() -> list[logging.Handler]:
    root = logging.getLogger()
    return [h for h in root.handlers if getattr(h, "_podcast_generator_handler", False)]


def test_configure_logging_is_idempotent() -> None:
    configure_logging("INFO")
    configure_logging("INFO")
    configure_logging("DEBUG")

    handlers = _podcast_generator_handlers()
    assert len(handlers) == 1
    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_quiets_noisy_third_party_loggers() -> None:
    configure_logging("DEBUG")

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("openai").level == logging.WARNING
