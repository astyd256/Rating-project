"""align movie column types

Revision ID: b7e4d1c9a3f2
Revises: 400f5eef0bd2
Create Date: 2026-10-26 23:40:00.000000

The first revision created ``movies.imdb_const`` and ``movies.imdb_rating`` as
INTEGER, but IMDb ids are strings (``tt0133093``) and ratings are fractional
(``8.6``). This revision aligns the existing databases with the models and is
safe to run on databases that are already at the previous revision.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e4d1c9a3f2"
down_revision: Union[str, Sequence[str], None] = "400f5eef0bd2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> dict[str, dict]:
    bind = op.get_bind()
    if table not in set(sa.inspect(bind).get_table_names()):
        return {}
    return {column["name"]: column for column in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    columns = _columns("movies")
    if not columns:
        return

    with op.batch_alter_table("movies") as batch:
        if "poster_path" not in columns:
            batch.add_column(sa.Column("poster_path", sa.String(), nullable=True))
        if "tomatoes_rating" not in columns:
            batch.add_column(sa.Column("tomatoes_rating", sa.Integer(), nullable=True))

        if "imdb_const" not in columns:
            batch.add_column(sa.Column("imdb_const", sa.String(length=32), nullable=True))
        elif not isinstance(columns["imdb_const"]["type"], sa.String):
            batch.alter_column(
                "imdb_const",
                type_=sa.String(length=32),
                existing_type=columns["imdb_const"]["type"],
                existing_nullable=True,
            )

        if "imdb_rating" not in columns:
            batch.add_column(sa.Column("imdb_rating", sa.Float(), nullable=True))
        elif not isinstance(columns["imdb_rating"]["type"], sa.Float):
            batch.alter_column(
                "imdb_rating",
                type_=sa.Float(),
                existing_type=columns["imdb_rating"]["type"],
                existing_nullable=True,
            )

    music_columns = _columns("music")
    if music_columns:
        with op.batch_alter_table("music") as batch:
            if "album" not in music_columns:
                batch.add_column(sa.Column("album", sa.String(), nullable=True))
            if "artist" not in music_columns:
                batch.add_column(sa.Column("artist", sa.String(), nullable=True))
            if "album_art" not in music_columns:
                batch.add_column(sa.Column("album_art", sa.LargeBinary(), nullable=True))
            if "rating" not in music_columns:
                batch.add_column(sa.Column("rating", sa.REAL(), nullable=True))


def downgrade() -> None:
    columns = _columns("movies")
    if not columns:
        return
    with op.batch_alter_table("movies") as batch:
        if "imdb_const" in columns:
            batch.alter_column(
                "imdb_const",
                type_=sa.Integer(),
                existing_type=sa.String(length=32),
                existing_nullable=True,
            )
        if "imdb_rating" in columns:
            batch.alter_column(
                "imdb_rating",
                type_=sa.Integer(),
                existing_type=sa.Float(),
                existing_nullable=True,
            )
