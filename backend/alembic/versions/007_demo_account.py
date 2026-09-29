"""Mark the shared read-only demo account.

A public demo lets anyone sign in to one account holding a few seeded
contracts. The flag is what makes that safe: the account cannot upload or
delete, and its questions are capped per day. Everyone else is unaffected.

Revision ID: 007
Revises: 006
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "is_demo")
