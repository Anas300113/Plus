"""Quality gates for the GL-style foundation bank and curriculum seed."""
from __future__ import annotations

from pathlib import Path

from src.core.database import (
    CanonicalQuestion, CanonicalSubject, CanonicalTopic,
    CurriculumLesson, QuestionOccurrence, QuestionReviewStatus,
    SourceDocument, get_engine, get_session_factory,
)
from scripts.seed_gl_curriculum import build


ROOT = Path(__file__).resolve().parents[1]


def test_gl_seed_builds_a_balanced_reviewable_bank(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'elevenplus.db'}"
    result = build(db_url, str(ROOT / "config/taxonomy.yaml"),
                   str(ROOT / "config/exams.yaml"))
    assert result["questions"]["created"] == 40
    assert result["approved_total"] == 40
    assert result["topic_total"] == 48

    engine = get_engine(db_url)
    session = get_session_factory(engine)()
    try:
        questions = session.query(CanonicalQuestion).all()
        assert {q.subject for q in questions} == {
            "maths", "english", "verbal_reasoning", "non_verbal_reasoning"
        }
        assert all(q.exam_board == "GL" for q in questions)
        assert all(q.answer_status == "verified" for q in questions)
        assert all(q.explanation_status == "verified" for q in questions)
        assert all(q.answer_evidence and q.explanation_evidence for q in questions)
        assert all(len(q.options_json or []) == 4 for q in questions)
        assert all(
            session.query(QuestionOccurrence)
            .filter_by(canonical_question_id=q.id).count() == 1
            for q in questions
        )
        assert session.query(SourceDocument).filter_by(
            repo_name="plus-original-gl-foundation-v1").count() == 1
        assert session.query(CurriculumLesson).count() == 48
        assert session.query(CanonicalSubject).count() == 4
        assert session.query(CanonicalTopic).count() == 48
    finally:
        session.close()
        engine.dispose()


def test_gl_seed_is_idempotent(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'elevenplus.db'}"
    first = build(db_url, str(ROOT / "config/taxonomy.yaml"),
                  str(ROOT / "config/exams.yaml"))
    second = build(db_url, str(ROOT / "config/taxonomy.yaml"),
                   str(ROOT / "config/exams.yaml"))
    assert first["questions"]["created"] == 40
    assert second["questions"]["created"] == 0
    assert second["questions"]["approved"] == 0
    assert second["question_total"] == 40
