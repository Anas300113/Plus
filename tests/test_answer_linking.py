from src.pipeline.link import is_answer_sheet, parse_answers
from src.core.database import SourceDocument


def test_parse_answers():
    text = "1. B\n2 - 42\nQ3: C"
    assert parse_answers(text) == {"1": "B", "2": "42", "3": "C"}


def test_is_answer_sheet_by_filename():
    doc = SourceDocument(id="x", repo_name="r", source_path="maths_answers.pdf",
                         file_sha256="s", file_size=1, file_type="pdf")
    assert is_answer_sheet(doc, []) is True
