"""Add tenant isolation

Revision ID: 2875b1ab6f13
Revises: 0f3adaa73cfb
Create Date: 2025-08-05 00:38:29.604830

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2875b1ab6f13'
down_revision: Union[str, Sequence[str], None] = '0f3adaa73cfb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('tenants',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('max_requests_per_minute', sa.Integer(), nullable=False),
        sa.Column('max_tokens_per_month', sa.Integer(), nullable=False),
        sa.Column('max_concurrent_tasks', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tenants_is_active'), 'tenants', ['is_active'], unique=False)
    
    op.add_column('tasks', sa.Column('tenant_id', sa.String(), nullable=True))
    op.create_index('ix_tasks_tenant_status', 'tasks', ['tenant_id', 'status'], unique=False)
    op.create_foreign_key(None, 'tasks', 'tenants', ['tenant_id'], ['id'])
    
    op.add_column('api_keys', sa.Column('tenant_id', sa.String(), nullable=True))
    op.create_index('ix_api_keys_tenant', 'api_keys', ['tenant_id'], unique=False)
    op.create_foreign_key(None, 'api_keys', 'tenants', ['tenant_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(None, 'api_keys', type_='foreignkey')
    op.drop_index('ix_api_keys_tenant', table_name='api_keys')
    op.drop_column('api_keys', 'tenant_id')
    
    op.drop_constraint(None, 'tasks', type_='foreignkey')
    op.drop_index('ix_tasks_tenant_status', table_name='tasks')
    op.drop_column('tasks', 'tenant_id')
    
    op.drop_index(op.f('ix_tenants_is_active'), table_name='tenants')
    op.drop_table('tenants')
