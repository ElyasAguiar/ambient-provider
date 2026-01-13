"""rename_audio_url_to_audio_key

Revision ID: 62b49d06c3fe
Revises: 8c0bc5ecc175
Create Date: 2026-01-08 15:46:39.151942

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "62b49d06c3fe"
down_revision: Union[str, None] = "8c0bc5ecc175"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename column from audio_url to audio_key
    op.alter_column("transcripts", "audio_url", new_column_name="audio_key")


def downgrade() -> None:
    # Rename column back from audio_key to audio_url
    op.alter_column("transcripts", "audio_key", new_column_name="audio_url")
