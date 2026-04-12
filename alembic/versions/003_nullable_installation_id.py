from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: str | None = "002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "review_runs",
        "installation_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE review_runs SET installation_id = 0 WHERE installation_id IS NULL")
    op.alter_column(
        "review_runs",
        "installation_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
