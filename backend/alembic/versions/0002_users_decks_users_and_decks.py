"""users and decks (SPEC §5)

Revision ID: 0002_users_decks
Revises: 0001_baseline
Create Date: 2026-08-21 00:41:15.401359

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_users_decks"
down_revision: str | None = "0001_baseline"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('telegram_id', sa.BigInteger(), nullable=False),
    sa.Column('username', sa.Text(), nullable=True),
    sa.Column('first_name', sa.Text(), nullable=True),
    sa.Column('native_lang', sa.String(length=8), server_default='uz', nullable=False),
    sa.Column('ui_lang', sa.String(length=8), server_default='uz', nullable=False),
    sa.Column('daily_new_limit', sa.Integer(), server_default=sa.text('20'), nullable=False),
    sa.Column('daily_review_limit', sa.Integer(), server_default=sa.text('200'), nullable=False),
    sa.Column('lookup_quota_per_day', sa.Integer(), server_default=sa.text('100'), nullable=False),
    sa.Column('timezone', sa.String(length=48), server_default='Asia/Tashkent', nullable=False),
    sa.Column('reminder_hour', sa.SmallInteger(), server_default=sa.text('20'), nullable=True),
    sa.Column('reminder_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('fsrs_params', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index(op.f('ix_users_telegram_id'), 'users', ['telegram_id'], unique=True)
    op.create_table('decks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('source_lang', sa.String(length=8), nullable=False),
    sa.Column('target_lang', sa.String(length=8), nullable=False),
    sa.Column('kind', sa.Enum('normal', 'daily', name='deck_kind'), server_default='normal', nullable=False),
    sa.Column('daily_date', sa.Date(), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_decks_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_decks'))
    )
    op.create_index('ix_decks_user_archived', 'decks', ['user_id', 'archived_at'], unique=False)
    op.create_index('uq_decks_user_daily_date', 'decks', ['user_id', 'daily_date'], unique=True, postgresql_where="kind = 'daily'")


def downgrade() -> None:
    op.drop_index('uq_decks_user_daily_date', table_name='decks', postgresql_where="kind = 'daily'")
    op.drop_index('ix_decks_user_archived', table_name='decks')
    op.drop_table('decks')
    op.drop_index(op.f('ix_users_telegram_id'), table_name='users')
    op.drop_table('users')
