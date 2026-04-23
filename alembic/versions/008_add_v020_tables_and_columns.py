from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "008"
down_revision: str | None = "007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("findings", sa.Column("fingerprint_v2", sa.String(), nullable=True))
    op.add_column("findings", sa.Column("engine_tier", sa.String(), nullable=True))
    op.add_column("review_runs", sa.Column("detected_languages", sa.JSON(), nullable=True))
    op.add_column("review_runs", sa.Column("engine_selection", sa.JSON(), nullable=True))

    op.create_table(
        "user_settings",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "key", name="uq_user_settings_user_key"),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"])

    op.create_table(
        "user_repositories",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("repo_url", sa.String(), nullable=False),
        sa.Column("repo_name", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default="github"),
        sa.Column("auth_token", sa.Text(), nullable=True),
        sa.Column("default_branch", sa.String(), nullable=False, server_default="main"),
        sa.Column("scan_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "repo_url", name="uq_user_repo_url"),
    )
    op.create_index("ix_user_repositories_user_id", "user_repositories", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_repositories_user_id", table_name="user_repositories")
    op.drop_table("user_repositories")
    op.drop_index("ix_user_settings_user_id", table_name="user_settings")
    op.drop_table("user_settings")
    op.drop_column("review_runs", "engine_selection")
    op.drop_column("review_runs", "detected_languages")
    op.drop_column("findings", "engine_tier")
    op.drop_column("findings", "fingerprint_v2")
