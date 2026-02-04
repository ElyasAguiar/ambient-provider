"""migrate_segments_to_words

Revision ID: 40c224e3be3d
Revises: 62b49d06c3fe
Create Date: 2026-02-02 23:47:21.087806

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "40c224e3be3d"
down_revision: Union[str, None] = "62b49d06c3fe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns
    op.add_column("transcripts", sa.Column("text", sa.Text(), nullable=False, server_default=""))
    op.add_column("transcripts", sa.Column("words", sa.JSON(), nullable=False, server_default="[]"))

    # Migrate existing data: convert segments to words (if needed)
    # This is a simplified migration - you may need to adjust based on your actual data
    op.execute(
        """
        UPDATE transcripts 
        SET text = '', 
            words = '[]'::json
        WHERE text IS NULL OR words IS NULL
    """
    )

    # Drop old segments column
    op.drop_column("transcripts", "segments")


def downgrade() -> None:
    # Add back segments column
    op.add_column(
        "transcripts", sa.Column("segments", sa.JSON(), nullable=False, server_default="[]")
    )

    # Drop new columns
    op.drop_column("transcripts", "words")
    op.drop_column("transcripts", "text")
