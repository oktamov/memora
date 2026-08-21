"""review_logs — append-only, written on every review from day one (SPEC §5, §13)

Revision ID: 0005_review_logs
Revises: 0004_cards
Create Date: 2026-08-21 09:20:53.008954

"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0005_review_logs"
down_revision: str | None = "0004_cards"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table('review_logs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('card_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('rating', sa.SmallInteger(), nullable=False),
    sa.Column('state', sa.SmallInteger(), nullable=False),
    sa.Column('due', sa.DateTime(timezone=True), nullable=False),
    sa.Column('stability', sa.Float(), nullable=True),
    sa.Column('difficulty', sa.Float(), nullable=True),
    sa.Column('elapsed_days', sa.Integer(), nullable=False),
    sa.Column('last_elapsed_days', sa.Integer(), nullable=False),
    sa.Column('scheduled_days', sa.Integer(), nullable=False),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['card_id'], ['cards.id'], name=op.f('fk_review_logs_card_id_cards'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_review_logs_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_review_logs'))
    )
    op.create_index('ix_review_logs_card_reviewed', 'review_logs', ['card_id', 'reviewed_at'], unique=False)
    op.create_index('ix_review_logs_user_reviewed', 'review_logs', ['user_id', 'reviewed_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_review_logs_user_reviewed', table_name='review_logs')
    op.drop_index('ix_review_logs_card_reviewed', table_name='review_logs')
    op.drop_table('review_logs')
