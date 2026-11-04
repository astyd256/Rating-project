"""add games, anime and manga tables

Revision ID: e5a7c1b9d3f4
Revises: b7e4d1c9a3f2
Create Date: 2026-11-03 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5a7c1b9d3f4"
down_revision: Union[str, Sequence[str], None] = "b7e4d1c9a3f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()

    if "games" not in tables:
        op.create_table(
            "games",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("external_id", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("poster_url", sa.String(), nullable=True),
            sa.Column("poster_path", sa.String(), nullable=True),
            sa.Column("rating", sa.Float(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("external_id"),
        )
        op.create_index("ix_games_external_id", "games", ["external_id"], unique=True)

    if "anime" not in tables:
        op.create_table(
            "anime",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("mal_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("title_type", sa.String(), nullable=True),
            sa.Column("episodes", sa.Integer(), nullable=True),
            sa.Column("poster_url", sa.String(), nullable=True),
            sa.Column("poster_path", sa.String(), nullable=True),
            sa.Column("rating", sa.Float(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("mal_id"),
        )
        op.create_index("ix_anime_mal_id", "anime", ["mal_id"], unique=True)

    if "manga" not in tables:
        op.create_table(
            "manga",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("mal_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("title_type", sa.String(), nullable=True),
            sa.Column("chapters", sa.Integer(), nullable=True),
            sa.Column("volumes", sa.Integer(), nullable=True),
            sa.Column("poster_url", sa.String(), nullable=True),
            sa.Column("poster_path", sa.String(), nullable=True),
            sa.Column("rating", sa.Float(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("mal_id"),
        )
        op.create_index("ix_manga_mal_id", "manga", ["mal_id"], unique=True)


def downgrade() -> None:
    tables = _tables()
    for table in ("manga", "anime", "games"):
        if table in tables:
            op.drop_table(table)
