"""Index the columns lookups and cascades actually use.

Postgres indexes the key a foreign key points at, never the column holding it,
so a scoped retrieval and every cascading document delete read the whole
chunks table. The embedding_model index goes: it holds one or two values, so it
never narrows a scan, and every chunk insert paid for it. ix_users_email
duplicated the index the unique constraint already builds.

Revision ID: 008
Revises: 007
"""
from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_known_devices_user_device", "known_devices", ["user_id", "device_hash"])
    op.drop_index("ix_document_chunks_embedding_model", table_name="document_chunks")
    op.drop_index("ix_users_email", table_name="users")


def downgrade() -> None:
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_document_chunks_embedding_model", "document_chunks", ["embedding_model"])
    op.drop_index("ix_known_devices_user_device", table_name="known_devices")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
