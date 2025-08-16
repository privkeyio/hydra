"""Add TicketDependency and TicketArtifact tables

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ticket_dependencies table
    op.create_table('ticket_dependencies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('parent_ticket_id', sa.Integer(), nullable=False),
        sa.Column('depends_on_ticket_id', sa.Integer(), nullable=False),
        sa.Column('dependency_type', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['depends_on_ticket_id'], ['tickets.id'], ),
        sa.ForeignKeyConstraint(['parent_ticket_id'], ['tickets.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ticket_dependencies_depends_on_ticket_id'), 'ticket_dependencies', ['depends_on_ticket_id'], unique=False)
    op.create_index(op.f('ix_ticket_dependencies_id'), 'ticket_dependencies', ['id'], unique=False)
    op.create_index(op.f('ix_ticket_dependencies_parent_ticket_id'), 'ticket_dependencies', ['parent_ticket_id'], unique=False)
    
    # Add unique constraint for parent-depends_on combination
    op.create_unique_constraint('uq_ticket_dependency_pair', 'ticket_dependencies', 
                                ['parent_ticket_id', 'depends_on_ticket_id'])
    
    # Create ticket_artifacts table
    op.create_table('ticket_artifacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticket_id', sa.Integer(), nullable=False),
        sa.Column('artifact_type', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('path', sa.String(length=500), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ticket_artifacts_id'), 'ticket_artifacts', ['id'], unique=False)
    op.create_index(op.f('ix_ticket_artifacts_ticket_id'), 'ticket_artifacts', ['ticket_id'], unique=False)
    op.create_index('ix_ticket_artifacts_type', 'ticket_artifacts', ['artifact_type'], unique=False)
    op.create_index('ix_ticket_artifacts_name', 'ticket_artifacts', ['name'], unique=False)


def downgrade() -> None:
    # Drop ticket_artifacts table and indexes
    op.drop_index('ix_ticket_artifacts_name', table_name='ticket_artifacts')
    op.drop_index('ix_ticket_artifacts_type', table_name='ticket_artifacts')
    op.drop_index(op.f('ix_ticket_artifacts_ticket_id'), table_name='ticket_artifacts')
    op.drop_index(op.f('ix_ticket_artifacts_id'), table_name='ticket_artifacts')
    op.drop_table('ticket_artifacts')
    
    # Drop ticket_dependencies table and indexes
    op.drop_constraint('uq_ticket_dependency_pair', 'ticket_dependencies', type_='unique')
    op.drop_index(op.f('ix_ticket_dependencies_parent_ticket_id'), table_name='ticket_dependencies')
    op.drop_index(op.f('ix_ticket_dependencies_id'), table_name='ticket_dependencies')
    op.drop_index(op.f('ix_ticket_dependencies_depends_on_ticket_id'), table_name='ticket_dependencies')
    op.drop_table('ticket_dependencies')