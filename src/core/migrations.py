"""Lightweight additive schema migration for the 11+ platform.

Scope (deliberately small):
  * create any missing tables from the SQLAlchemy metadata
  * append any missing *columns* to existing tables (additive only)
  * record what was applied in ``schema_migrations`` so re-runs are no-ops

This is not a replacement for a real migration tool. Alembic is the intended
long-term answer for destructive/renaming changes; it is deferred until the
schema stabilises. Every new learning-layer column declares a ``server_default``
so ``ALTER TABLE ... ADD COLUMN`` satisfies SQLite's NOT NULL rule and an
existing database keeps working without a wipe.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn, CreateIndex

from src.core.database import Base, utcnow

SCHEMA_VERSION = "0.2.0-learning"
_MIGRATION_TABLE = "schema_migrations"


def _ensure_migration_table(conn) -> None:
    conn.exec_driver_sql(
        f"CREATE TABLE IF NOT EXISTS {_MIGRATION_TABLE} ("
        "id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")


def _acquire_migration_lock(conn) -> None:
    """Serialize schema preparation for concurrent PostgreSQL replicas."""
    if conn.dialect.name == "postgresql":
        conn.exec_driver_sql(
            "SELECT pg_advisory_xact_lock(1848375211, 20261029)")


def _record_migration(conn, migration_id: str) -> bool:
    """Record one migration using portable named parameters.

    Migrations are intentionally run as a single-writer deployment step, so
    checking before inserting avoids dialect-specific ignore/upsert syntax.
    """
    exists = conn.execute(
        text(f"SELECT 1 FROM {_MIGRATION_TABLE} WHERE id = :id"),
        {"id": migration_id},
    ).first()
    if exists:
        return False
    conn.execute(
        text(f"INSERT INTO {_MIGRATION_TABLE} (id, applied_at) "
             "VALUES (:id, :applied_at)"),
        {"id": migration_id, "applied_at": utcnow().isoformat()},
    )
    return True


def applied_migrations(engine) -> set[str]:
    """Ids of migrations already applied (empty if the table is absent)."""
    insp = inspect(engine)
    if not insp.has_table(_MIGRATION_TABLE):
        return set()
    with engine.connect() as conn:
        return {row[0] for row in conn.exec_driver_sql(
            f"SELECT id FROM {_MIGRATION_TABLE}")}


def _pending_columns(engine) -> list[tuple[str, str]]:
    """[(table, column)] that exist in the metadata but not in the database."""
    insp = inspect(engine)
    pending: list[tuple[str, str]] = []
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for column in table.columns:
            if column.name not in existing:
                pending.append((table.name, column.name))
    return pending


def ensure_schema(engine) -> list[str]:
    """Create tables, add missing columns, reconcile data; return applied ids.

    Idempotent: calling repeatedly applies nothing and returns ``[]``.
    """
    # PostgreSQL deployments may start more than one replica at once. Keep
    # table creation and the additive migration pass behind a transaction-
    # scoped advisory lock; SQLite/MySQL retain the documented single-writer
    # deployment contract.
    with engine.begin() as conn:
        _acquire_migration_lock(conn)
        Base.metadata.create_all(bind=conn)
    applied: list[str] = []
    pending = _pending_columns(engine)
    if pending:
        tables = {t.name: t for t in Base.metadata.sorted_tables}
        touched = {t for t, _ in pending}
        with engine.begin() as conn:
            _ensure_migration_table(conn)
            for table_name, column_name in pending:
                column = tables[table_name].columns[column_name]
                ddl = str(CreateColumn(column).compile(dialect=engine.dialect))
                conn.exec_driver_sql(
                    f'ALTER TABLE "{table_name}" ADD COLUMN {ddl}')
                migration_id = f"{SCHEMA_VERSION}:{table_name}.{column_name}"
                if _record_migration(conn, migration_id):
                    applied.append(migration_id)
        _create_missing_indexes(engine, touched, applied)
    else:
        _ensure_migration_table_exists(engine)
    applied.extend(_reconcile_fabricated_page_ids(engine))
    applied.extend(_record_new_tables(engine))
    _backfill_canonical_contract(engine)
    return applied


def _backfill_canonical_contract(engine) -> None:
    """Populate normalized question fields from the legacy representation."""
    insp = inspect(engine)
    if not insp.has_table("canonical_questions"):
        return
    from src.core.database import (
        CanonicalQuestion, CanonicalSkill, CanonicalSubject, CanonicalTopic,
        QuestionOccurrence, QuestionReviewStatus, SourceAsset,
        get_session_factory,
    )
    session = get_session_factory(engine)()
    try:
        subjects = {s.id for s in session.query(CanonicalSubject).all()}
        topics = {t.id for t in session.query(CanonicalTopic).all()}
        skills = {s.id for s in session.query(CanonicalSkill).all()}
        changed = False
        for q in session.query(CanonicalQuestion).yield_per(200):
            if not q.schema_version:
                q.schema_version = "1.1.0"
                changed = True
            if not q.subject_id and q.subject in subjects:
                q.subject_id = q.subject
                changed = True
            if not q.topic_id and q.topic in topics:
                q.topic_id = q.topic
                changed = True
            if not q.skill_id:
                first = next((sid for sid in (q.skill_ids or []) if sid in skills), None)
                if first:
                    q.skill_id = first
                    changed = True
            if q.prompt_json is None:
                q.prompt_json = {"text": q.question_text or "",
                                 "instructions": q.instructions or "",
                                 "context": q.context or ""}
                changed = True
            if q.answer_json is None:
                answer_type = "single_choice" if q.question_type in {
                    "mcq", "multi_select", "image_choice"} else "text"
                q.answer_json = {"type": answer_type,
                                 "value": q.correct_answer or ""}
                changed = True
            if q.assets_json is None:
                occ = (session.query(QuestionOccurrence)
                       .filter_by(canonical_question_id=q.id)
                       .order_by(QuestionOccurrence.id).first())
                assets = []
                if occ:
                    for asset in (session.query(SourceAsset)
                                  .filter_by(document_id=occ.document_id,
                                             page_id=occ.page_id).all()):
                        assets.append({"asset_id": asset.id,
                                       "storage_path": asset.storage_path,
                                       "mime_type": asset.mime_type})
                q.assets_json = assets
                changed = True
            if not q.source_id:
                occ = (session.query(QuestionOccurrence)
                       .filter_by(canonical_question_id=q.id)
                       .order_by(QuestionOccurrence.id).first())
                if occ:
                    q.source_id = occ.document_id
                    changed = True
            review = session.get(QuestionReviewStatus, q.id)
            desired = review.status if review else "validation_required"
            if q.validation_status != desired:
                q.validation_status = desired
                changed = True
        if changed:
            session.commit()
    finally:
        session.close()


def _record_new_tables(engine) -> list[str]:
    """Record creation of additive tables (question_region_board,
    corpus_snapshots) in schema_migrations for audit/idempotency.

    The tables themselves are created by Base.metadata.create_all in
    ensure_schema; this function only records that they exist so a
    re-run is a no-op.
    """
    insp = inspect(engine)
    if not insp.has_table("schema_migrations"):
        return []
    applied: list[str] = []
    for table_name, migration_id in (
        ("question_region_board", _QUESTION_REGION_BOARD_ID),
        ("corpus_snapshots", _CORPUS_SNAPSHOT_ID),
    ):
        if not insp.has_table(table_name):
            continue
        with engine.begin() as conn:
            already = {row[0] for row in conn.exec_driver_sql(
                f"SELECT id FROM {_MIGRATION_TABLE}").fetchall()}
            if migration_id in already:
                continue
            if _record_migration(conn, migration_id):
                applied.append(migration_id)
    return applied


_DATA_PAGE_PROVENANCE_ID = (
    f"{SCHEMA_VERSION}:data:page_provenance_reconciliation")
_QUESTION_REGION_BOARD_ID = (
    f"{SCHEMA_VERSION}:create_table:question_region_board")
_CORPUS_SNAPSHOT_ID = (
    f"{SCHEMA_VERSION}:create_table:corpus_snapshots")


def _reconcile_fabricated_page_ids(engine) -> list[str]:
    """Clear fabricated page provenance (Gate 1).

    Legacy reference-import rows stored the *document* id in
    ``question_occurrences.page_id`` -- a dangling pointer into the
    ``source_pages`` foreign key that falsely claimed page granularity. Provenance
    must reference a real page row, so those values are cleared to ``""`` (the
    file-level sentinel). The honest file+record provenance lives in
    ``document_id`` + ``question_number`` and is left untouched, so imported
    questions keep verifiable file-level provenance rather than losing it.

    Only rows whose ``page_id`` equals their ``document_id`` AND does not match
    any real ``source_pages.id`` are touched. Idempotent, recorded for audit,
    and a no-op (``[]``) on a database with no fabricated rows.
    """
    insp = inspect(engine)
    if not insp.has_table("question_occurrences"):
        return []
    with engine.begin() as conn:
        _ensure_migration_table(conn)
        already = {row[0] for row in conn.exec_driver_sql(
            f"SELECT id FROM {_MIGRATION_TABLE}").fetchall()}
        if _DATA_PAGE_PROVENANCE_ID in already:
            return []
        result = conn.exec_driver_sql(
            "UPDATE question_occurrences SET page_id = '' "
            "WHERE page_id <> '' AND page_id = document_id "
            "AND page_id NOT IN (SELECT id FROM source_pages)")
        changed = result.rowcount
        if not changed:
            return []  # nothing to fix; do not record a no-op migration
        _record_migration(conn, _DATA_PAGE_PROVENANCE_ID)
    return [_DATA_PAGE_PROVENANCE_ID]


def _create_missing_indexes(engine, table_names: set[str],
                            applied: list[str]) -> None:
    """Backfill indexes for columns added by ALTER (index=True only)."""
    insp = inspect(engine)
    for table_name in sorted(table_names):
        table = Base.metadata.tables[table_name]
        existing = {ix["name"] for ix in insp.get_indexes(table_name)}
        for index in table.indexes:
            if index.name in existing:
                continue
            with engine.begin() as conn:
                conn.exec_driver_sql(str(CreateIndex(index).compile(
                    dialect=engine.dialect)))
            applied.append(f"{SCHEMA_VERSION}:{table_name}.index:{index.name}")


def _ensure_migration_table_exists(engine) -> None:
    with engine.begin() as conn:
        _ensure_migration_table(conn)
