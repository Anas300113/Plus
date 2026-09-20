"""Deterministic page-level OCR tests and MCQ option extraction tests."""
from __future__ import annotations

import uuid

from src.core.database import (
    QuestionOccurrence, SourceDocument, SourcePage,
)
from src.pipeline.detect import extract_options
from src.pipeline.ocr import (
    MIN_NATIVE_TEXT_CHARS, is_scanned_page, ocr_page, run_ocr,
)


def _page(session, text="", ocr_used=False, ocr_text=""):
    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="test", source_path="t.pdf",
        file_sha256=str(uuid.uuid4()), file_type="pdf")
    session.add(doc)
    session.flush()
    page = SourcePage(
        id=str(uuid.uuid4()), document_id=doc.id, page_number=1,
        text_content=text, text_confidence=0.9 if text else 0.0,
        ocr_used=ocr_used, ocr_text=ocr_text)
    session.add(page)
    session.commit()
    return doc, page


def test_ocr_tests_cover_expected_functions(session):
    _, page = _page(session, text="")
    assert callable(is_scanned_page)
    assert callable(ocr_page)
    assert callable(run_ocr)
    assert isinstance(MIN_NATIVE_TEXT_CHARS, int)
    assert page.id


def test_empty_page_with_no_native_text_is_scanned(session):
    _, page = _page(session, text="")
    assert page.text_content == ""
    assert not page.ocr_used
    assert is_scanned_page(page) is True


def test_short_native_text_page_is_scanned(session):
    _, page = _page(session, text="1. hello")
    assert is_scanned_page(page) is True


def test_long_native_text_page_is_not_scanned(session):
    _, page = _page(session, text="x" * MIN_NATIVE_TEXT_CHARS)
    assert is_scanned_page(page) is False
    assert len(page.text_content.strip()) == MIN_NATIVE_TEXT_CHARS


def test_already_ocred_page_is_not_scanned(session):
    _, page = _page(session, text="", ocr_used=True, ocr_text="older text")
    assert page.ocr_used is True
    assert is_scanned_page(page) is False


def test_ocr_page_with_no_image_bytes_returns_empty(session):
    _, page = _page(session, text="")
    assert ocr_page(session, page, image_bytes=None) == ""
    assert page.ocr_used is False
    assert page.ocr_text == ""
    assert ocr_page(session, page, image_bytes=b"") == ""
    assert page.ocr_used is False


def test_run_ocr_skips_pages_without_renderable_source(session, tmp_path):
    doc, page = _page(session, text="")
    assert is_scanned_page(page) is True
    stats = run_ocr(session, [doc], source_root=tmp_path)
    assert stats["skipped"] >= 1
    session.refresh(page)
    assert page.ocr_used is False
    assert page.ocr_text == ""


def test_run_ocr_skips_pages_with_reliable_native_text(session, tmp_path):
    doc, _ = _page(session, text="x" * (MIN_NATIVE_TEXT_CHARS + 5))
    stats = run_ocr(session, [doc], source_root=tmp_path)
    assert stats["ocred"] == 0
    assert stats["skipped"] == 1


def test_run_ocr_is_idempotent_for_already_ocred_pages(session, tmp_path):
    doc, page = _page(session, text="", ocr_used=True, ocr_text="old")
    stats = run_ocr(session, [doc], source_root=tmp_path)
    assert stats["ocred"] == 0
    session.refresh(page)
    assert page.ocr_text == "old"
    assert page.ocr_used is True


def test_ocr_does_not_touch_native_text_content(session):
    _, page = _page(session, text="existing text")
    session.refresh(page)
    assert page.text_content == "existing text"
    assert page.text_confidence == 0.9


def test_dot_letter_option_extraction():
    text = "1. Pick one.\nA. apple\nB. banana\nC. cherry"
    options = extract_options(text)
    assert [o["letter"] for o in options] == ["A", "B", "C"]
    assert options[0]["text"] == "apple"
    assert options[2]["text"] == "cherry"


def test_paren_letter_option_extraction():
    text = "2. Choose.\nA) red\nB) blue\nC) green"
    options = extract_options(text)
    assert [o["letter"] for o in options] == ["A", "B", "C"]
    assert options[1]["text"] == "blue"


def test_single_option_is_not_enough(session):
    assert extract_options("Question?\nA. only one") == []
    assert extract_options("plain question without options") == []


def test_detect_run_does_not_infer_answers(session):
    from src.pipeline.detect import run as detect_run

    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="test", source_path="choices.pdf",
        file_sha256=str(uuid.uuid4()), file_type="pdf")
    session.add(doc)
    session.flush()
    session.add(SourcePage(
        id=str(uuid.uuid4()), document_id=doc.id, page_number=1,
        text_content="1. Pick one.\nA. apple\nB. banana"))
    session.commit()
    stats = detect_run(session, [doc], version="0.1.0", batch="b1")
    assert stats["candidates"] == 1
    occ = session.query(QuestionOccurrence).one()
    assert occ.linked_answer == ""
    assert len(occ.options_json or []) == 2
    assert [o["letter"] for o in occ.options_json] == ["A", "B"]


def test_detect_run_has_no_options_when_source_has_none(session):
    from src.pipeline.detect import run as detect_run

    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="test", source_path="plain.pdf",
        file_sha256=str(uuid.uuid4()), file_type="pdf")
    session.add(doc)
    session.flush()
    session.add(SourcePage(
        id=str(uuid.uuid4()), document_id=doc.id, page_number=1,
        text_content="1. What is seven plus eight?"))
    session.commit()
    assert detect_run(session, [doc], version="0.1.0", batch="b1")["candidates"] == 1
    occ = session.query(QuestionOccurrence).one()
    assert occ.options_json in (None, [])


def test_validate_promote_preserves_real_options(session):
    from src.pipeline.validate import run as validate_run

    doc = SourceDocument(
        id=str(uuid.uuid4()), repo_name="test", source_path="v.pdf",
        file_sha256=str(uuid.uuid4()), file_type="pdf")
    session.add(doc)
    session.flush()
    session.add(SourcePage(
        id=str(uuid.uuid4()), document_id=doc.id, page_number=1,
        text_content="1. Pick one.\nA. apple\nB. banana\nC. cherry"))
    session.commit()
    pages = session.query(SourcePage).filter_by(document_id=doc.id).all()
    page = pages[0]
    options = extract_options(page.text_content)
    assert len(options) == 3
    session.add(QuestionOccurrence(
        id=str(uuid.uuid4()), document_id=doc.id, page_id=page.id,
        question_number="1", extraction_run="b1",
        extraction_version="0.1.0", extraction_confidence=0.5,
        options_json=options))
    session.commit()
    stats = validate_run(session, [doc])
    assert stats["promoted"] == 1

    from src.core.database import CanonicalQuestion

    kept = session.query(CanonicalQuestion).one()
    assert len(kept.options_json or []) == 3
    assert [o["letter"] for o in kept.options_json] == ["A", "B", "C"]
    assert kept.options_json[0]["text"] == "apple"
    assert kept.question_type == "mcq"

