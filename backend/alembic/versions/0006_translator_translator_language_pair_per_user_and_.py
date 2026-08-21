"""translator: a language pair per user, and a daily deck per pair

The product became a translator: the user picks source and target, types a word, and it
is filed automatically. Two consequences for the schema:

  * `users.source_lang` remembers the pair the user last chose.
  * The daily-deck uniqueness moves from `(user_id, daily_date)` to
    `(user_id, daily_date, source_lang, target_lang)`, so switching from EN→UZ to RU→UZ
    mid-day produces two decks instead of colliding on one.

The old cards held English definitions rather than translations, and the deck index
cannot be widened while duplicates exist, so this migration clears them. That was a
deliberate choice — the only rows were test data (DECISIONS.md D28).

Revision ID: 0006_translator
Revises: 0005_review_logs
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0006_translator"
down_revision: str | None = "0005_review_logs"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("source_lang", sa.String(length=8), server_default="en", nullable=False),
    )

    # Content shaped for the old flow. `card_states` and `review_logs` cascade from
    # `cards`, and the daily decks they hang off cannot be re-keyed while they exist.
    op.execute("DELETE FROM cards")
    op.execute("DELETE FROM decks WHERE kind = 'daily'")

    op.drop_index(
        "uq_decks_user_daily_date", table_name="decks", postgresql_where=sa.text("kind = 'daily'")
    )
    op.create_index(
        "uq_decks_user_daily_date",
        "decks",
        ["user_id", "daily_date", "source_lang", "target_lang"],
        unique=True,
        postgresql_where=sa.text("kind = 'daily'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_decks_user_daily_date", table_name="decks", postgresql_where=sa.text("kind = 'daily'")
    )
    op.create_index(
        "uq_decks_user_daily_date",
        "decks",
        ["user_id", "daily_date"],
        unique=True,
        postgresql_where=sa.text("kind = 'daily'"),
    )
    op.drop_column("users", "source_lang")
