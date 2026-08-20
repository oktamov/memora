"""baseline — empty starting point so `alembic_version` exists from M0 onward

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-21

"""

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Intentionally empty. Tables arrive with their milestone's migration."""


def downgrade() -> None:
    """Intentionally empty."""
