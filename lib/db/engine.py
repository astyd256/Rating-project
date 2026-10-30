from pathlib import Path
from typing import Dict

from sqlalchemy import create_engine, event

_engine_cache: Dict[str, object] = {}


def make_url(db_path: str | Path) -> str:
    """Build a SQLAlchemy URL from a filesystem path (or pass a URL through)."""
    text = str(db_path).strip()
    if "://" in text:
        return text
    if text == ":memory:":
        return "sqlite://"
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    return f"sqlite:///{path.as_posix()}"


def get_engine(db_path: str | Path):
    url = make_url(db_path)
    if url not in _engine_cache:
        is_sqlite = url.startswith("sqlite:")
        connect_args = {"check_same_thread": False} if is_sqlite else {}
        engine = create_engine(url, connect_args=connect_args, future=True)

        if is_sqlite:
            @event.listens_for(engine, "connect")
            def _set_sqlite_pragmas(dbapi_connection, _connection_record):
                # Keep sorting of rows with poster/cover blobs in RAM: temp
                # files may be unavailable in restricted environments.
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA temp_store = MEMORY")
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.close()

        _engine_cache[url] = engine
    return _engine_cache[url]
