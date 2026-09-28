"""preferences.target_minutes: lengths are now 6-20 minutes, default 10

D-65 moved episodes from ~1.2 minutes per story to 3 (deep) / 1.5
(headlines), which makes anything under 6 minutes a one-story episode. The
API now accepts 6-20; this lifts saved defaults below 6 up to 6 so the
settings slider never shows an out-of-range value. Existing episodes keep
the length they were made with.

Revision ID: e2b7a91c4d30
Revises: c4e81b7f02d5
Create Date: 2026-09-28 22:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2b7a91c4d30"
down_revision: str | Sequence[str] | None = "c4e81b7f02d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE preferences SET target_minutes = 6 WHERE target_minutes < 6")


def downgrade() -> None:
    # Data-only: the original sub-6 values are not recoverable, and 6 is valid either way.
    pass
