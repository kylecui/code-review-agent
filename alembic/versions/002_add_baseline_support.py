from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: str | None = "001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_RUN_KIND_ENUM = sa.Enum("PR", "BASELINE", name="runkind")


def upgrade() -> None:
    _RUN_KIND_ENUM.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "review_runs",
        sa.Column("run_kind", _RUN_KIND_ENUM, nullable=False, server_default="PR"),
    )

    op.alter_column("review_runs", "pr_number", existing_type=sa.Integer(), nullable=True)
    op.alter_column("review_runs", "base_sha", existing_type=sa.String(40), nullable=True)
    op.alter_column(
        "review_runs",
        "trigger_event",
        existing_type=sa.Enum("OPENED", "SYNCHRONIZE", "READY_FOR_REVIEW", name="triggerevent"),
        nullable=True,
    )
    op.alter_column("review_runs", "delivery_id", existing_type=sa.String(), nullable=True)

    op.drop_constraint("review_runs_delivery_id_key", "review_runs", type_="unique")
    op.create_index(
        "ix_review_runs_delivery_id",
        "review_runs",
        ["delivery_id"],
        unique=True,
        postgresql_where=sa.text("delivery_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_review_runs_delivery_id", table_name="review_runs")
    op.create_unique_constraint("review_runs_delivery_id_key", "review_runs", ["delivery_id"])

    op.alter_column("review_runs", "delivery_id", existing_type=sa.String(), nullable=False)
    op.alter_column(
        "review_runs",
        "trigger_event",
        existing_type=sa.Enum("OPENED", "SYNCHRONIZE", "READY_FOR_REVIEW", name="triggerevent"),
        nullable=False,
    )
    op.alter_column("review_runs", "base_sha", existing_type=sa.String(40), nullable=False)
    op.alter_column("review_runs", "pr_number", existing_type=sa.Integer(), nullable=False)

    op.drop_column("review_runs", "run_kind")
    _RUN_KIND_ENUM.drop(op.get_bind(), checkfirst=True)
