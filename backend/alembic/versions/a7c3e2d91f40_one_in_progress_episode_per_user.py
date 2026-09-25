"""one in-progress episode per user

Partial unique index: a user can have at most one episode whose status is
not 'ready' or 'failed'. docs/DECISIONS.md D-37.

Revision ID: a7c3e2d91f40
Revises: 1df08563f23c
Create Date: 2026-09-25 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e2d91f40"
down_revision: str | Sequence[str] | None = "1df08563f23c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_episodes_one_in_progress_per_user",
        "episodes",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('ready', 'failed')"),
    )


def downgrade() -> None:
    op.drop_index("uq_episodes_one_in_progress_per_user", table_name="episodes")
