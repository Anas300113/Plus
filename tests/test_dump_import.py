from __future__ import annotations

import uuid

import pytest

from src.core.database import (
    CanonicalQuestion, QuestionOccurrence, QuestionReviewStatus,
    SourceDocument, SourcePage,
)
from src.pipeline.review import ApprovalContractError, set_status


def test_reference_only_source_cannot_enter_student_bank(session):
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="maths-arithmetic",
        question_type="mcq", question_text="What is 2 + 2?",
        correct_answer="B", explanation="Two plus two is four.",
        options_json=[{"letter": "A", "text": "3"},
                      {"letter": "B", "text": "4"}],
        answer_status="verified", explanation_status="verified",
        answer_evidence="dump page 1 answer key B",
        explanation_evidence="worked solution checked on dump page 1")
    session.add(q)
    session.flush()
    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="11-dump", source_path="paper.pdf",
        file_sha256="a" * 64, file_size=10, file_type="pdf",
        rights_status="reference_only")
    session.add(doc)
    session.flush()
    page = SourcePage(id=str(uuid.uuid4()), document_id=doc.id,
                      page_number=1, text_content=q.question_text)
    session.add(page)
    session.add(QuestionOccurrence(
        id=str(uuid.uuid4()), canonical_question_id=q.id,
        document_id=doc.id, page_id=page.id, question_number="1"))
    session.add(QuestionReviewStatus(question_id=q.id, status="validation_required"))
    session.commit()

    with pytest.raises(ApprovalContractError, match="reference_only"):
        set_status(session, q.id, "approved", reviewer="reviewer")
