"""Step: question candidate detection with MCQ option extraction.

Deterministic pattern-based splitter: splits page text on numbered markers
like '1.', 'Q1', '(1)'. Also extracts MCQ options from the body when present.

Option patterns detected:
  A. text    B. text    (letter + dot + space)
  A) text    B) text    (letter + paren + space)
  (A) text   (B) text   (paren + letter + paren)
  A - text   B - text   (letter + dash + space)

Extracted options are stored on the QuestionOccurrence. No answer is
inferred from options.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

from src.core.database import QuestionOccurrence, SourceDocument, SourcePage
from src.core.logging import get_logger

log = get_logger("pipeline.detect")

MARKER = re.compile(r"(?:^|\n)\s*(?:Q\s?)?(\d{1,3})\s*[.)\-:]\s+", re.IGNORECASE)

OPTION_PATTERNS = [
    re.compile(r"\b([A-Ea-e])\s*\.\s+(.+?)(?=\n\s*[A-Ea-e]\s*\.|\n\s*[A-Ea-e]\s*\)|$\n?)",
              re.IGNORECASE | re.DOTALL),
    re.compile(r"\b([A-Ea-e])\s*\)\s+(.+?)(?=\n\s*[A-Ea-e]\s*\)|\n\s*[A-Ea-e]\s*\)|$)",
              re.IGNORECASE | re.DOTALL),
    re.compile(r"\(([A-Ea-e])\)\s+(.+?)(?=\n\s*\([A-Ea-e]\)|\n\s*\([A-Ea-e]\)|$)",
              re.IGNORECASE | re.DOTALL),
    re.compile(r"\b([A-Ea-e])\s*-\s+(.+?)(?=\n\s*[A-Ea-e]\s*-|$)",
              re.IGNORECASE | re.DOTALL),
]


def split_candidates(text: str) -> list[tuple[str, str]]:
    """Return [(question_number, body)] in document order."""
    matches = list(MARKER.finditer("\n" + text))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.end() - 1
        end = matches[i + 1].start() + 1 if i + 1 < len(matches) else len(text) + 1
        body = text[start - 1:end - 1].strip()
        if len(body) >= 8:
            out.append((m.group(1), body))
    return out


def extract_options(text: str) -> list[dict[str, str]]:
    """Extract MCQ options from text body.

    Returns list of {letter, text} dicts. Empty list if no options found.
    Does NOT infer the correct answer.
    """
    for pattern in OPTION_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            options: list[dict[str, str]] = []
            for letter, opt_text in matches:
                options.append({
                    "letter": letter.upper(),
                    "text": opt_text.strip(),
                })
            if len(options) >= 2:
                return options
    return []


def run(session: Session, docs: list[SourceDocument],
        version: str = "0.1.0", batch: str = "") -> dict:
    created = 0
    for doc in docs:
        pages = session.query(SourcePage).filter_by(document_id=doc.id).all()
        for page in pages:
            if not page.text_content.strip():
                continue
            for number, body in split_candidates(page.text_content):
                exists = session.query(QuestionOccurrence).filter_by(
                    document_id=doc.id, page_id=page.id,
                    question_number=number).first()
                if exists:
                    continue
                options = extract_options(body)
                session.add(QuestionOccurrence(
                    id=str(uuid.uuid4()), document_id=doc.id, page_id=page.id,
                    question_number=number, extraction_run=batch,
                    extraction_version=version, extraction_confidence=0.5,
                    options_json=options if options else None))
                created += 1
    session.commit()
    log.info("detect: %d candidates", created)
    return {"candidates": created}
