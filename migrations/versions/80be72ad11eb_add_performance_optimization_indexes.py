"""Add performance optimization indexes

Revision ID: 80be72ad11eb
Revises: 2875b1ab6f13
Create Date: 2025-08-05 00:52:12.018370

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '80be72ad11eb'
down_revision: Union[str, Sequence[str], None] = '2875b1ab6f13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create performance optimization indexes
    op.create_index("ix_usage_task_id", "usage", ["task_id"])
    op.create_index("ix_usage_model_provider", "usage", ["model", "provider"])
    op.create_index("ix_tasks_tenant_created", "tasks", ["tenant_id", sa.text("created_at DESC")])
    op.create_index(
        "ix_usage_cost_timestamp", 
        "usage", 
        ["cost", "timestamp"],
        postgresql_where=sa.text("cost IS NOT NULL")
    )
    op.create_index("ix_api_keys_active", "api_keys", ["is_active", "key"])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop performance optimization indexes
    op.drop_index("ix_api_keys_active", "api_keys")
    op.drop_index("ix_usage_cost_timestamp", "usage")
    op.drop_index("ix_tasks_tenant_created", "tasks")
    op.drop_index("ix_usage_model_provider", "usage")
    op.drop_index("ix_usage_task_id", "usage")
