"""drop legacy image blob columns

Revision ID: a7c3e1f9b2d4
Revises: f6b2d8c4e1a9
Create Date: 2026-11-04 16:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e1f9b2d4"
down_revision: Union[str, Sequence[str], None] = "f6b2d8c4e1a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    if table not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    if "poster_blob" in _columns("movies"):
        with op.batch_alter_table("movies") as batch:
            batch.drop_column("poster_blob")

    if "album_art" in _columns("music"):
        with op.batch_alter_table("music") as batch:
            batch.drop_column("album_art")


def downgrade() -> None:
    if "poster_blob" not in _columns("movies"):
        with op.batch_alter_table("movies") as batch:
            batch.add_column(sa.Column("poster_blob", sa.LargeBinary(), nullable=True))

    if "album_art" not in _columns("music"):
        with op.batch_alter_table("music") as batch:
            batch.add_column(sa.Column("album_art", sa.LargeBinary(), nullable=True))
