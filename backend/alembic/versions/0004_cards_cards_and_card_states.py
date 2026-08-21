"""cards and card_states — content and scheduling kept apart (SPEC §5, §13)

Revision ID: 0004_cards
Revises: 0003_lookup_cache
Create Date: 2026-08-21 06:43:24.920818

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_cards"
down_revision: str | None = "0003_lookup_cache"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table('cards',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('deck_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('term', sa.Text(), nullable=False),
    sa.Column('display_term', sa.Text(), nullable=False),
    sa.Column('ipa', sa.Text(), nullable=True),
    sa.Column('pos', sa.String(length=32), nullable=True),
    sa.Column('meanings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('examples', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('source_lang', sa.String(length=8), nullable=False),
    sa.Column('target_lang', sa.String(length=8), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['deck_id'], ['decks.id'], name=op.f('fk_cards_deck_id_decks'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_cards_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cards'))
    )
    op.create_index('ix_cards_user_created', 'cards', ['user_id', 'created_at'], unique=False)
    op.create_index('uq_cards_deck_term', 'cards', ['deck_id', 'term'], unique=True)
    op.create_table('card_states',
    sa.Column('card_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('due', sa.DateTime(timezone=True), nullable=False),
    sa.Column('stability', sa.Float(), nullable=True),
    sa.Column('difficulty', sa.Float(), nullable=True),
    sa.Column('elapsed_days', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('scheduled_days', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('reps', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('lapses', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('state', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_review', sa.DateTime(timezone=True), nullable=True),
    sa.Column('suspended', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.ForeignKeyConstraint(['card_id'], ['cards.id'], name=op.f('fk_card_states_card_id_cards'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_card_states_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('card_id', name=op.f('pk_card_states'))
    )
    op.create_index(op.f('ix_card_states_due'), 'card_states', ['due'], unique=False)
    op.create_index('ix_card_states_user_due', 'card_states', ['user_id', 'due'], unique=False, postgresql_where=sa.text('suspended = false'))


def downgrade() -> None:
    op.drop_index('ix_card_states_user_due', table_name='card_states', postgresql_where=sa.text('suspended = false'))
    op.drop_index(op.f('ix_card_states_due'), table_name='card_states')
    op.drop_table('card_states')
    op.drop_index('uq_cards_deck_term', table_name='cards')
    op.drop_index('ix_cards_user_created', table_name='cards')
    op.drop_table('cards')
