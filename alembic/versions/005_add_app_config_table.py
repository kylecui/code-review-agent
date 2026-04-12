from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: str | None = "004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    _ = op.create_table(
        "app_config",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_app_config_key", "app_config", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_app_config_key", table_name="app_config")
    op.drop_table("app_config")
