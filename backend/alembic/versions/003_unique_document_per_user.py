from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.execute(
        """
        DELETE FROM documents d
        USING documents keep
        WHERE d.user_id = keep.user_id
          AND d.filename = keep.filename
          AND d.id < keep.id
        """
    )
    op.create_unique_constraint(
        "uq_documents_user_filename", "documents", ["user_id", "filename"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_documents_user_filename", "documents", type_="unique")
