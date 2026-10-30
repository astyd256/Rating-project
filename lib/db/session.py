from contextlib import contextmanager

from sqlalchemy.orm import sessionmaker

from .engine import get_engine


@contextmanager
def get_session(db_path: str):
    """Yield a session, commit on success and roll back on any exception."""
    engine = get_engine(db_path)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
