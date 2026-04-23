from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "007"
down_revision: str | None = "006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("review_runs", sa.Column("run_logs", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("review_runs", "run_logs")
