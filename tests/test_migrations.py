"""Schema migration tests: the additive column migrator.

Guarantees:
  * a database created before the learning layer still opens and gains the
    new columns (no wipe, no data loss);
  * running twice is a no-op;
  * a fresh database needs no migration at all;
  * applied migrations are recorded for auditability.
"""
from __future__ import annotations

import sqlite3

from sqlalchemy import inspect

from src.core.database import (
    Base, get_engine, get_session_factory,
    LearningReviewItem, LearningSkillMastery, LearningStudySession,
)
from src.core.migrations import (
    SCHEMA_VERSION, applied_migrations, ensure_schema,
)

# Shape of learning_study_sessions before the learning layer existed.
LEGACY_SESSION_SQL = """
CREATE TABLE learning_study_sessions (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL,
    session_type TEXT,
    started_at DATETIME,
    ended_at DATETIME
)
"""

NEW_SESSION_COLUMNS = {"state", "planned_duration_seconds",
                       "actual_duration_seconds", "goals_json",
                       "recommended_activities_json", "question_order_json",
                       "current_index", "skipped_ids_json", "accuracy"}


def _legacy_engine(db_file):
    con = sqlite3.connect(db_file)
    con.execute(LEGACY_SESSION_SQL)
    con.commit()
    con.close()
    return get_engine(f"sqlite:///{db_file}")


def test_legacy_database_gains_new_columns(tmp_path):
    engine = _legacy_engine(str(tmp_path / "legacy.db"))
    applied = ensure_schema(engine)
    cols = {c["name"] for c in
            inspect(engine).get_columns("learning_study_sessions")}
    assert NEW_SESSION_COLUMNS <= cols
    assert any(m.startswith(SCHEMA_VERSION) for m in applied)
    assert all(
        any(m.endswith(f"learning_study_sessions.{c}") for m in applied)
        for c in sorted(NEW_SESSION_COLUMNS))


def test_ensure_schema_is_idempotent(tmp_path):
    engine = _legacy_engine(str(tmp_path / "idem.db"))
    first = ensure_schema(engine)
    second = ensure_schema(engine)
    assert second == []
    assert len(first) > 0
    assert ensure_schema(engine) == []


def test_migrations_are_recorded_for_audit(tmp_path):
    engine = _legacy_engine(str(tmp_path / "audit.db"))
    ensure_schema(engine)
    recorded = applied_migrations(engine)
    assert any("learning_study_sessions.accuracy" in m for m in recorded)
    assert all(m.startswith(SCHEMA_VERSION) for m in recorded)


def test_fresh_database_needs_no_migration(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    assert ensure_schema(engine) == []
    assert ensure_schema(engine) == []


def test_new_learning_tables_exist_after_migration(tmp_path):
    engine = _legacy_engine(str(tmp_path / "tables.db"))
    ensure_schema(engine)
    insp = inspect(engine)
    for table in ("learning_review_items", "learning_skill_mastery",
                  "schema_migrations"):
        assert insp.has_table(table), table
    review_cols = {c["name"] for c in insp.get_columns("learning_review_items")}
    assert {"source_type", "source_id", "state", "due_at", "interval_days",
            "consecutive_correct", "review_history_json"} <= review_cols


def test_legacy_rows_survive_the_migration(tmp_path):
    """Existing sessions must keep their identity and student link."""
    db_file = str(tmp_path / "rows.db")
    con = sqlite3.connect(db_file)
    con.execute(LEGACY_SESSION_SQL)
    con.execute("INSERT INTO learning_study_sessions VALUES "
                "('sess-1', 'student-1', 'practice', NULL, NULL)")
    con.commit()
    con.close()
    engine = get_engine(f"sqlite:///{db_file}")
    ensure_schema(engine)
    S = get_session_factory(engine)
    s = S()
    row = s.query(LearningStudySession).filter_by(id="sess-1").one()
    assert row.student_id == "student-1"
    # New columns fall back to their server defaults for old rows.
    assert row.state == "started"
    assert row.current_index == 0
    assert row.accuracy == 0.0
    assert row.question_order == []
    s.close()


def test_review_item_unique_constraint_prevents_duplicates(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'unique.db'}")
    ensure_schema(engine)
    S = get_session_factory(engine)
    s = S()
    s.add(LearningReviewItem(id="ri-1", student_id="stu-1",
                             source_type="question", source_id="q-1"))
    s.commit()
    s.add(LearningReviewItem(id="ri-2", student_id="stu-1",
                             source_type="question", source_id="q-1"))
    try:
        s.commit()
    except Exception:
        s.rollback()
    else:
        raise AssertionError("duplicate review item should be rejected")
    assert s.query(LearningReviewItem).count() == 1
    s.close()


def test_base_metadata_still_creates_everything(tmp_path):
    """The create_all path used by tests stays valid alongside ensure_schema."""
    engine = get_engine(f"sqlite:///{tmp_path / 'all.db'}")
    Base.metadata.create_all(bind=engine)
    assert ensure_schema(engine) == []