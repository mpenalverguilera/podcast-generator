import os
from datetime import UTC, datetime

from sqlalchemy.engine import make_url

# Must happen before any `app.*` import: app.db builds its engine from
# get_settings().database_url at module-import time, so DATABASE_URL has to
# point at the test database before that first import, not after.
_default_url = "postgresql+psycopg://podcast:podcast@localhost:5432/podcast"
_url = make_url(os.environ.get("DATABASE_URL", _default_url))
_test_db_name = f"{_url.database}_test"
# str(URL) masks the password as "***" -- render_as_string(hide_password=False)
# is required to get a URL that actually authenticates.
os.environ["DATABASE_URL"] = _url.set(database=_test_db_name).render_as_string(hide_password=False)

# CLAUDE.md: tests use fake adapters only, never hit real APIs -- force this
# regardless of what a developer's local .env has configured.
os.environ["SEARCH_PROVIDER"] = "fake"
os.environ["LLM_PROVIDER"] = "fake"
os.environ["CLASSIFIER_PROVIDER"] = "fake"
os.environ["TTS_PROVIDER"] = "fake"

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Episode, EpisodeStatus, EpisodeTrigger, Preferences, User  # noqa: E402


def _create_test_database() -> None:
    maintenance_engine = create_engine(_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with maintenance_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": _test_db_name}
        ).first()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{_test_db_name}"'))
    maintenance_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Creates a separate <dbname>_test database (never the real dev DB) and
    the schema in it once per test session, via Base.metadata.create_all --
    not `alembic upgrade head`, to keep tests fast and decoupled from
    migration authoring (whose own correctness is covered separately by the
    phase's `alembic upgrade head` acceptance check)."""
    _create_test_database()
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()


@pytest.fixture
def db():
    """A Session for the test body. Cleans up by deleting every row from
    every table afterwards (FK-safe order), so tests don't leak state into
    each other regardless of how many separate Sessions (get_db,
    session_scope, the pipeline runner) touched the DB during the test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())


def make_user_with_episode(db, *, status: EpisodeStatus = EpisodeStatus.PENDING) -> Episode:
    """Shared helper for pipeline-runner tests: a user + preferences + one
    episode ready to run."""
    user = User(email="test@example.com", password_hash="x", is_admin=False, is_synthetic=True)
    db.add(user)
    db.flush()
    db.add(Preferences(user_id=user.id, host_a={"name": "Alex"}, host_b={"name": "Sam"}))
    episode = Episode(
        user_id=user.id,
        status=status,
        trigger=EpisodeTrigger.MANUAL,
        window_start=datetime.now(UTC),
        target_minutes=6,
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)
    return episode
