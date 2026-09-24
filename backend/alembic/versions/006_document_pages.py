"""Keep each document's extracted page text.

Whole-document chat context needs the pages as extracted. Rebuilding them from
chunks would lose the line breaks, which chunking collapses, and the overlap
between chunks would have to be undone. Nullable: documents indexed before
this have no pages and fall back to retrieval until they are re-indexed.

Revision ID: 006
Revises: 005
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("pages", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "pages")
