"""Thin, strict CRUD helpers built on top of SQLAlchemy sessions."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, class_mapper

T = TypeVar("T")


def _model_column_names(model: type[T]) -> set[str]:
    """Return the set of mapped column names for a model class."""
    return {column.key for column in class_mapper(model).columns}


def _validate_kwargs(
    model: type[T],
    data: Mapping[str, Any],
    *,
    allow_id: bool = False,
) -> dict[str, Any]:
    """Validate that every key in ``data`` is a mapped column of ``model``."""
    payload = dict(data)
    valid_fields = _model_column_names(model)
    unknown_fields = sorted(set(payload.keys()) - valid_fields)
    if unknown_fields:
        raise ValueError(f"Invalid fields for {model.__name__}: {', '.join(unknown_fields)}")
    if not allow_id and "id" in payload:
        raise ValueError(f"'id' must not be provided for {model.__name__}")
    return payload


def create_record(session: Session, model: type[T], **kwargs: Any) -> T:
    """Create and flush a new record."""
    payload = _validate_kwargs(model, kwargs)
    record = model(**payload)
    session.add(record)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise
    return record


def find_one(session: Session, model: type[T], **filters: Any) -> T | None:
    """Return the first record matching all ``filters`` (``None`` matches SQL NULL)."""
    if not filters:
        raise ValueError("At least one filter is required")
    payload = _validate_kwargs(model, filters)
    query = session.query(model)
    for key, value in payload.items():
        column = getattr(model, key)
        query = query.filter(column.is_(None) if value is None else column == value)
    return query.order_by(model.id).first()


def upsert_by(
    session: Session,
    model: type[T],
    filters: Mapping[str, Any],
    **values: Any,
) -> tuple[T, bool]:
    """Update the record matching ``filters`` or create it with ``filters`` + ``values``.

    Returns:
        ``(record, created)`` where ``created`` is True for a new row.
    """
    filter_payload = _validate_kwargs(model, filters)
    values_payload = _validate_kwargs(model, values)
    record = find_one(session, model, **filter_payload)
    if record is not None:
        changed = {
            key: value
            for key, value in values_payload.items()
            if getattr(record, key) != value
        }
        if changed:
            update_record(session, record, **changed)
        return record, False

    record = create_record(session, model, **{**filter_payload, **values_payload})
    return record, True


def upsert_record(
    session: Session,
    model: type[T],
    match_by_title: str,
    **kwargs: Any,
) -> tuple[T, bool]:
    """Upsert a record by ``title`` (kept for backwards compatibility)."""
    return upsert_by(session, model, {"title": match_by_title}, **kwargs)


def batch_insert(
    session: Session,
    model: type[T],
    records: Sequence[Mapping[str, Any]],
) -> list[T]:
    """Insert multiple records in one batched flush."""
    payloads: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        try:
            payloads.append(_validate_kwargs(model, record))
        except ValueError as exc:
            raise ValueError(f"Invalid record at index {index}: {exc}") from exc

    if not payloads:
        return []

    objs = [model(**payload) for payload in payloads]
    session.add_all(objs)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise
    return objs


def retrieve_record_by_title(session: Session, model: type[T], title: str) -> T | None:
    """Return the first record with a matching ``title``."""
    if "title" not in _model_column_names(model):
        raise ValueError(f"Model {model.__name__} has no 'title' column")
    return find_one(session, model, title=title)


def retrieve_records_by_column(
    session: Session,
    model: type[T],
    column: str,
    limit: int | None = None,
    *,
    descending: bool = True,
) -> list[T]:
    """Return records ordered by a mapped column, best values first by default."""
    if column not in _model_column_names(model):
        raise ValueError(f"Model {model.__name__} has no column '{column}'")
    attribute = getattr(model, column)
    ordering = attribute.desc() if descending else attribute.asc()
    query = session.query(model).order_by(ordering, model.id.asc())
    if limit and limit > 0:
        query = query.limit(limit)
    return query.all()


def update_record(session: Session, record: T, **kwargs: Any) -> T:
    """Update mapped fields on an existing record."""
    payload = _validate_kwargs(type(record), kwargs)
    for key, value in payload.items():
        setattr(record, key, value)
    session.add(record)
    return record


def delete_record(session: Session, record: T) -> bool:
    """Delete the given record and flush the operation."""
    session.delete(record)
    session.flush()
    return True
