"""lookup cache — global, not per-user (SPEC §5, §13)

Revision ID: 0003_lookup_cache
Revises: 0002_users_decks
Create Date: 2026-08-21 01:04:40.784700

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_lookup_cache"
down_revision: str | None = "0002_users_decks"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table('lookup_cache',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('term', sa.Text(), nullable=False),
    sa.Column('source_lang', sa.String(length=8), nullable=False),
    sa.Column('target_lang', sa.String(length=8), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('hit_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lookup_cache'))
    )
    op.create_index('uq_lookup_cache_term_langs', 'lookup_cache', ['term', 'source_lang', 'target_lang'], unique=True)


def downgrade() -> None:
    op.drop_index('uq_lookup_cache_term_langs', table_name='lookup_cache')
    op.drop_table('lookup_cache')
