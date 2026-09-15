"""Let the embedding column hold any width.
Revision ID: 005
Revises: 004
"""
from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("document_chunks", "embedding", type_=Vector(), existing_type=Vector(768))


def downgrade() -> None:
    # Fails if any row holds a vector that is not 768 wide, which is correct:
    # narrowing the column would silently drop those rows' searchability.
    op.alter_column("document_chunks", "embedding", type_=Vector(768), existing_type=Vector())
