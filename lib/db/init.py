"""Database bootstrap: run Alembic migrations and repair a half-initialized DB."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from lib.db.engine import get_engine, make_url
from lib.db.models import Base

REQUIRED_TABLES = {"movies", "music", "games", "anime", "manga"}


def ensure_db(path: str | Path) -> None:
    """Create (if needed) and migrate the database, then verify its tables exist."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    created = not db_path.exists()

    run_migrations(str(db_path))

    engine = get_engine(str(db_path))
    present = set(inspect(engine).get_table_names())
    missing = REQUIRED_TABLES - present
    if missing:
        # A DB can be stamped at head while being empty (e.g. an interrupted
        # alembic run). Recreate the missing tables from the models instead of
        # leaving a database that fails on the first query.
        Base.metadata.create_all(engine)
        print(f"Repaired schema, created tables: {', '.join(sorted(missing))}")

    status = "Created" if created else "Ready"
    print(f"{status} database: {db_path}")


def run_migrations(db_path: str) -> None:
    project_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    # ConfigParser treats '%' as interpolation, so escape it in the URL.
    alembic_cfg.set_main_option("sqlalchemy.url", make_url(db_path).replace("%", "%%"))
    command.upgrade(alembic_cfg, "head")
