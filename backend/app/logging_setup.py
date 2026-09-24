"""Terminal logging setup shared by the CLI and the API.

Local/dev logging is deliberately architectural, not exhaustive: pipeline
stage transitions, user/episode creation, failures -- not per-request
provider chatter. See docs/DECISIONS.md for the entry that introduced this.
"""

import logging
import sys

_HANDLER_ATTR = "_podcast_generator_handler"

# Third-party libraries are noisy at INFO (every HTTP request, every SQL
# statement); keep them at WARNING so the architectural events above stand
# out on the terminal.
_NOISY_LOGGERS = ("httpx", "httpcore", "openai", "elevenlabs", "urllib3", "sqlalchemy.engine")


class _LiveStderrHandler(logging.StreamHandler):
    """A StreamHandler that always writes to the *current* sys.stderr.

    Typer's CliRunner (used in tests, invoked multiple times per process)
    temporarily swaps sys.stderr in and out around each CLI invocation and
    closes the old one afterwards. A plain StreamHandler(sys.stderr) binds to
    whichever stream was current when it was constructed, so a later
    invocation would try to write to an already-closed stream. Resolving
    sys.stderr dynamically on every emit avoids that.
    """

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _value):
        pass  # always resolved dynamically via the property getter above


def configure_logging(level: str = "INFO") -> None:
    """Attaches one stderr handler to the root logger, once.

    Safe to call multiple times (the CLI's Typer callback runs per-invocation
    in tests): a second call only updates the level, it never adds a second
    handler or clobbers a handler something else attached (e.g. pytest's
    caplog), unlike `logging.basicConfig(force=True)`.
    """
    root = logging.getLogger()
    root.setLevel(level)

    existing = next((h for h in root.handlers if getattr(h, _HANDLER_ATTR, False)), None)
    if existing is not None:
        existing.setLevel(level)
    else:
        handler = _LiveStderrHandler()
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s - %(levelname)s - %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        setattr(handler, _HANDLER_ATTR, True)
        root.addHandler(handler)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
