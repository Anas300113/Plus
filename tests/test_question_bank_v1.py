"""Question Bank v1 regression tests.

These reproduce the concrete failures the trustworthy-question contract fixes:

* an unverified / unproven question could be approved (approval had no checks,
  ignored the ``reviewer`` argument and wrote no audit trail).
* a populated ``correct_answer`` was treated as if it implied approval.
* editing a verified answer/explanation silently kept a stale ``verified``.
* ``/api/questions`` leaked ``correct_answer`` to students.
* students could submit an arbitrary ``chosen_answer`` that was not one of the
  question's options and have it marked.

They assert against the real persistence + service path (no mocked services).
"""
from __future__ import annotations

import uuid

import pytest

from src.core.database import (
    CanonicalQuestion, CanonicalQuestionType, LearningStudent,
    QuestionOccurrence, QuestionReviewEvent, QuestionReviewStatus,
    SourceDocument, SourcePage,
)
from src.pipeline.review import (
    ApprovalContractError, approval_blockers, edit_question, has_provenance,
    option_labels, set_status, verify_answer, verify_explanation,
)


def _doc_page_occurrence(session, question_id):
    """Give a question real document+page provenance (the approval requires it)."""
    doc = SourceDocument(id=str(uuid.uuid4()), repo_name="r", repo_url="",
                         source_path="p.pdf", file_sha256="0" * 64,
                         file_size=1, file_type="pdf", commit_sha="",
                         ingestion_batch="b", ingestion_version="0.1.0")
    session.add(doc)
    page = SourcePage(id=str(uuid.uuid4()), document_id=doc.id,
                      page_number=1, text_content="stem")
    session.add(page)
    session.flush()
    session.add(QuestionOccurrence(
        id=str(uuid.uuid4()), canonical_question_id=question_id,
        document_id=doc.id, page_id=page.id, question_number="1"))
    session.commit()
    return doc.id, page.id


def _mcq(session, *, text="What is 2+2?", answer="B", explanation="2+2=4.",
         options=None, qtype="mcq", status="extracted", provenance=True):
    opts = options if options is not None else [
        {"letter": "A", "text": "3"}, {"letter": "B", "text": "4"}]
    if qtype and not session.query(CanonicalQuestionType).filter_by(
            id=qtype).first():
        session.add(CanonicalQuestionType(id=qtype, name=qtype,
                                          requires_options=(qtype == "mcq")))
    q = CanonicalQuestion(
        id=str(uuid.uuid4()), subject="maths", topic="maths-arithmetic",
        question_type=qtype or "", question_text=text,
        correct_answer=answer, explanation=explanation, options_json=opts)
    session.add(q)
    session.flush()
    session.add(QuestionReviewStatus(question_id=q.id, status=status))
    session.commit()
    if provenance:
        _doc_page_occurrence(session, q.id)
    return q.id


# ---- content integrity -----------------------------------------------------


def test_populated_answer_alone_is_not_enough_to_approve(session):
    """Regression: a correct_answer being set does NOT imply approval."""
    qid = _mcq(session, provenance=True)
    blockers = approval_blockers(session, qid)
    # answer/explanation are 'missing' by default -> still blocked.
    assert any("answer_status" in b for b in blockers)
    assert any("explanation_status" in b for b in blockers)
    with pytest.raises(ApprovalContractError):
        set_status(session, qid, "approved")


def test_approval_requires_document_and_page_provenance(session):
    """Regression: a question with no page-level provenance cannot be approved."""
    qid = _mcq(session, provenance=False)
    assert has_provenance(session, qid) is False
    assert any("provenance" in b for b in approval_blockers(session, qid))
    with pytest.raises(ApprovalContractError):
        set_status(session, qid, "approved")


def test_mcq_answer_must_map_to_a_real_option(session):
    """Regression: an answer that is not one of the options is invalid."""
    qid = _mcq(session, answer="Z", provenance=True)
    blockers = approval_blockers(session, qid)
    assert any("does not map to a valid option" in b for b in blockers)


def test_option_labels_use_letter_key_and_preserve_order(session):
    """Option order and labels survive; extraction stores the label in 'letter'."""
    qid = _mcq(session, options=[{"letter": "C", "text": "x"},
                                 {"letter": "A", "text": "y"}])
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert option_labels(q) == ["C", "A"]  # order preserved, not reordered


def test_missing_answer_distinct_from_unverified_and_verified(session):
    qid = _mcq(session, answer="", provenance=True)
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert q.answer_status == "missing"           # distinct: missing
    with pytest.raises(ValueError):
        verify_answer(session, qid, "rev")        # cannot verify empty answer
    q.correct_answer = "B"
    session.commit()
    verify_answer(session, qid, "rev", evidence="source p1")
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert q.answer_status == "verified" and q.answer_evidence == "source p1"
    q.correct_answer = "B"
    session.commit()
    verify_answer(session, qid, "rev", evidence="source p1")
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert q.answer_status == "verified" and q.answer_evidence == "source p1"


def _make_approvable(session, **kw):
    """A question that satisfies every approval requirement."""
    qid = _mcq(session, **kw)
    verify_answer(session, qid, "rev", evidence="answer key p1")
    verify_explanation(session, qid, "rev", note="derivation checked")
    return qid


def test_valid_question_can_be_approved_and_reviewer_recorded(session):
    qid = _make_approvable(session)
    set_status(session, qid, "approved", reviewer="alice")
    row = session.query(QuestionReviewStatus).filter_by(question_id=qid).one()
    assert row.status == "approved"
    assert row.reviewer == "alice"        # regression: reviewer was ignored
    assert row.decision == "approved"


def test_approval_and_rejection_are_audited(session):
    """Regression: review decisions must append an audit event, not be lost."""
    qid = _make_approvable(session)
    set_status(session, qid, "approved", reviewer="alice")
    set_status(session, qid, "rejected", reviewer="bob", reason="dupe")
    events = (session.query(QuestionReviewEvent)
              .filter_by(question_id=qid)
              .order_by(QuestionReviewEvent.created_at).all())
    actions = [e.action for e in events]
    assert "approve" in actions and "reject" in actions
    reject = next(e for e in events if e.action == "reject")
    assert reject.reviewer == "bob" and reject.reason == "dupe"


def test_editing_verified_answer_invalidates_verification(session):
    """Regression: editing a verified answer must not keep stale 'verified'."""
    qid = _make_approvable(session)
    edit_question(session, qid, "alice", correct_answer="A")
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert q.answer_status == "candidate"        # verification reset
    # ...and the question can no longer be approved until re-verified.
    with pytest.raises(ApprovalContractError):
        set_status(session, qid, "approved")


def test_editing_verified_explanation_invalidates_verification(session):
    qid = _make_approvable(session)
    edit_question(session, qid, "alice", explanation="new text")
    q = session.query(CanonicalQuestion).filter_by(id=qid).one()
    assert q.explanation_status == "candidate"
    with pytest.raises(ApprovalContractError):
        set_status(session, qid, "approved")


def test_edit_preserves_original_extraction_in_audit(session):
    """The original extracted answer is recorded, not silently destroyed."""
    qid = _make_approvable(session, answer="B")
    edit_question(session, qid, "alice", correct_answer="A")
    event = (session.query(QuestionReviewEvent)
             .filter_by(question_id=qid, action="edit").one())
    assert "'B'" in event.reason       # original value captured


def test_rejection_always_allowed_even_when_unproven(session):
    qid = _mcq(session, provenance=False)
    set_status(session, qid, "rejected", reviewer="bob", reason="bad OCR")
    row = session.query(QuestionReviewStatus).filter_by(question_id=qid).one()
    assert row.status == "rejected"
def test_rejection_always_allowed_even_when_unproven(session):
    qid = _mcq(session, provenance=False)
    set_status(session, qid, "rejected", reviewer="bob", reason="bad OCR")
    row = session.query(QuestionReviewStatus).filter_by(question_id=qid).one()
    assert row.status == "rejected"


# ---- student practice correctness ------------------------------------------


def _approved_for_practice(session):
    from src.learning.session import ensure_student, start_session
    qid = _make_approvable(session)
    set_status(session, qid, "approved", reviewer="alice")
    sid = str(uuid.uuid4())
    ensure_student(session, sid, name="S")
    sess = start_session(session, sid, subject="maths",
                         topic="maths-arithmetic", limit=5)
    return qid, sess.id


def test_pending_question_never_reaches_a_student_session(session):
    """Regression: a merely-extracted (pending) question is not practiceable.

    With no approved questions the session must be a truthful empty state
    (no fabricated or pending questions), never a session containing the
    pending question.
    """
    from src.learning.session import ensure_student, start_session
    _mcq(session, status="extracted", provenance=True)   # pending, not approved
    sid = str(uuid.uuid4())
    ensure_student(session, sid, name="S")
    sess = start_session(session, sid, subject="maths",
                         topic="maths-arithmetic", limit=5)
    assert sess.question_order_json == []   # empty, not the pending question


def test_out_of_options_answer_is_rejected_server_side(session):
    """Regression: a submitted answer must belong to the question's options."""
    from src.learning.session import submit_answer
    qid, sess_id = _approved_for_practice(session)
    with pytest.raises(ValueError):
        submit_answer(session, sess_id, qid, chosen_answer="Z")  # not an option


def test_correct_and_incorrect_marked_against_verified_answer(session):
    from src.core.database import LearningQuestionAttempt
    from src.learning.session import submit_answer
    qid, sess_id = _approved_for_practice(session)
    result = submit_answer(session, sess_id, qid, chosen_answer="B")
    assert result["is_correct"] is True          # verified answer is 'B'
    attempt = (session.query(LearningQuestionAttempt)
               .filter_by(session_id=sess_id, question_id=qid).one())
    assert attempt.is_correct is True


def test_only_one_attempt_recorded_per_submission(session):
    from src.core.database import LearningQuestionAttempt
    from src.learning.session import submit_answer
    qid, sess_id = _approved_for_practice(session)
    submit_answer(session, sess_id, qid, chosen_answer="B")
    n = (session.query(LearningQuestionAttempt)
         .filter_by(session_id=sess_id, question_id=qid).count())
    assert n == 1
def test_only_one_attempt_recorded_per_submission(session):
    from src.core.database import LearningQuestionAttempt
    from src.learning.session import submit_answer
    qid, sess_id = _approved_for_practice(session)
    submit_answer(session, sess_id, qid, chosen_answer="B")
    n = (session.query(LearningQuestionAttempt)
         .filter_by(session_id=sess_id, question_id=qid).count())
    assert n == 1


# ---- API boundary (student leak + reviewer authorisation) ------------------


def _api_client(tmp_path, monkeypatch):
    httpx = pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from src.core.database import get_engine, get_session_factory, init_db
    import src.api.main as api_main
    engine = get_engine(f"sqlite:///{tmp_path / 'api.db'}")
    init_db(engine)
    S = get_session_factory(engine)
    monkeypatch.setattr(api_main, "_Session", S)
    return TestClient(api_main.app)


def test_questions_endpoint_does_not_leak_correct_answer(tmp_path, monkeypatch):
    """Regression: students must never receive correct_answer from the list
    endpoint (marking is server-side)."""
    from src.core.database import CanonicalQuestion, QuestionReviewStatus
    import src.api.main as api_main
    c = _api_client(tmp_path, monkeypatch)
    S = api_main._Session
    db = S()
    q = CanonicalQuestion(id=str(uuid.uuid4()), subject="maths",
                          topic="maths-arithmetic", question_type="mcq",
                          question_text="2+2?", correct_answer="B",
                          options_json=[{"letter": "A", "text": "3"},
                                        {"letter": "B", "text": "4"}])
    db.add(q)
    db.add(QuestionReviewStatus(question_id=q.id, status="approved"))
    db.commit()
    db.close()
    rows = c.get("/api/questions").json()
    assert rows and "correct_answer" not in rows[0]


def test_reviewer_mutation_locked_without_token(tmp_path, monkeypatch):
    """Reviewer operations are gated server-side, not just hidden in a UI."""
    monkeypatch.delenv("PLUS_REVIEWER_TOKEN", raising=False)
    c = _api_client(tmp_path, monkeypatch)
    r = c.post(f"/api/review/{uuid.uuid4()}", json={"status": "approved"})
    assert r.status_code == 503          # fail-closed when not configured


def test_reviewer_mutation_rejects_wrong_token(tmp_path, monkeypatch):
    monkeypatch.setenv("PLUS_REVIEWER_TOKEN", "secret")
    c = _api_client(tmp_path, monkeypatch)
    r = c.post(f"/api/review/{uuid.uuid4()}", json={"status": "approved"},
               headers={"X-Reviewer-Token": "wrong"})
    assert r.status_code == 403


def test_reviewer_approve_with_token_enforces_contract(tmp_path, monkeypatch):
    """A reviewer with the right token still cannot approve an unverified
    question: the trustworthy contract is enforced server-side."""
    from src.core.database import CanonicalQuestion, QuestionReviewStatus
    import src.api.main as api_main
    monkeypatch.setenv("PLUS_REVIEWER_TOKEN", "secret")
    c = _api_client(tmp_path, monkeypatch)
    S = api_main._Session
    db = S()
    q = CanonicalQuestion(id=str(uuid.uuid4()), subject="maths",
                          topic="maths-arithmetic", question_type="mcq",
                          question_text="2+2?", correct_answer="B",
                          options_json=[{"letter": "A", "text": "3"},
                                        {"letter": "B", "text": "4"}])
    db.add(q)                             # no provenance, no verification
    db.add(QuestionReviewStatus(question_id=q.id, status="extracted"))
    db.commit()
    qid = q.id
    db.close()
    r = c.post(f"/api/review/{qid}", json={"status": "approved"},
               headers={"X-Reviewer-Token": "secret"})
    assert r.status_code == 400           # contract violation, not 200
    detail = c.get(f"/api/review/{qid}").json()
    assert detail["approval_blockers"]     # workbench shows what is missing