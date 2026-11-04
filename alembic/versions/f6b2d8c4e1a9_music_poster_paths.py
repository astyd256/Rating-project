"""music poster paths

Revision ID: f6b2d8c4e1a9
Revises: e5a7c1b9d3f4
Create Date: 2026-11-03 17:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6b2d8c4e1a9"
down_revision: Union[str, Sequence[str], None] = "e5a7c1b9d3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> dict[str, dict]:
    bind = op.get_bind()
    if "music" not in set(sa.inspect(bind).get_table_names()):
        return {}
    return {column["name"]: column for column in sa.inspect(bind).get_columns("music")}


def upgrade() -> None:
    columns = _columns()
    if not columns:
        return
    if "poster_path" not in columns:
        op.add_column("music", sa.Column("poster_path", sa.String(), nullable=True))


def downgrade() -> None:
    columns = _columns()
    if "poster_path" in columns:
        op.drop_column("music", "poster_path")
