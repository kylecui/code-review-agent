from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    _ = op.create_table(
        "review_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("repo", sa.String(), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("head_sha", sa.String(length=40), nullable=False),
        sa.Column("base_sha", sa.String(length=40), nullable=False),
        sa.Column("installation_id", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "PENDING",
                "CLASSIFYING",
                "COLLECTING",
                "NORMALIZING",
                "REASONING",
                "DECIDING",
                "PUBLISHING",
                "COMPLETED",
                "FAILED",
                "SUPERSEDED",
                name="reviewstate",
            ),
            nullable=False,
        ),
        sa.Column("superseded_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "trigger_event",
            sa.Enum("OPENED", "SYNCHRONIZE", "READY_FOR_REVIEW", name="triggerevent"),
            nullable=False,
        ),
        sa.Column("delivery_id", sa.String(), nullable=False),
        sa.Column("classification", sa.JSON(), nullable=True),
        sa.Column("decision", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["superseded_by"], ["review_runs.id"]),
        sa.UniqueConstraint("delivery_id"),
    )
    op.create_index("ix_review_runs_head_sha", "review_runs", ["head_sha"], unique=False)
    op.create_index("ix_review_runs_repo", "review_runs", ["repo"], unique=False)
    op.create_index(
        "ix_review_runs_repo_pr_number", "review_runs", ["repo", "pr_number"], unique=False
    )
    op.create_index("ix_review_runs_state", "review_runs", ["state"], unique=False)

    _ = op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("review_run_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("finding_id", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column(
            "severity",
            sa.Enum("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", name="findingseverity"),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Enum("HIGH", "MEDIUM", "LOW", name="findingconfidence"),
            nullable=False,
        ),
        sa.Column("blocking", sa.Boolean(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("source_tools", sa.JSON(), nullable=False),
        sa.Column("rule_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("impact", sa.String(), nullable=False),
        sa.Column("fix_recommendation", sa.String(), nullable=False),
        sa.Column("test_recommendation", sa.String(), nullable=True),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column(
            "disposition",
            sa.Enum("NEW", "EXISTING", "FIXED", name="findingdisposition"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["review_run_id"], ["review_runs.id"]),
    )
    op.create_index("ix_findings_fingerprint", "findings", ["fingerprint"], unique=False)
    op.create_index("ix_findings_review_run_id", "findings", ["review_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_findings_review_run_id", table_name="findings")
    op.drop_index("ix_findings_fingerprint", table_name="findings")
    op.drop_table("findings")

    op.drop_index("ix_review_runs_state", table_name="review_runs")
    op.drop_index("ix_review_runs_repo_pr_number", table_name="review_runs")
    op.drop_index("ix_review_runs_repo", table_name="review_runs")
    op.drop_index("ix_review_runs_head_sha", table_name="review_runs")
    op.drop_table("review_runs")
