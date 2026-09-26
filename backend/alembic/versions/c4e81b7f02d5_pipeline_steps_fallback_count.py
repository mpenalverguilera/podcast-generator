"""pipeline_steps.fallback_count

How many classifier calls in a stage fell back from Jev to Luna
(FallbackClassifier). docs/DECISIONS.md D-44/D-45. A new revision rather than
amending the initial schema: a database already at head would silently skip
an amended file (D-44's migration gotcha). `IF NOT EXISTS` because the dev DB
already got this column by hand during the phase 04 eval.

Revision ID: c4e81b7f02d5
Revises: a7c3e2d91f40
Create Date: 2026-09-25 23:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e81b7f02d5"
down_revision: str | Sequence[str] | None = "a7c3e2d91f40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE pipeline_steps ADD COLUMN IF NOT EXISTS fallback_count INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE pipeline_steps DROP COLUMN IF EXISTS fallback_count")
