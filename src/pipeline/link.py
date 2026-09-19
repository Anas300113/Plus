"""Step: answer linking. Matches answer-sheet lines ('1. B', '1 - 42',
'Q1: C') to occurrences in the same batch by question number.
Multiple occurrences of the same question are preserved."""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from src.core.database import QuestionOccurrence, SourceDocument, SourcePage
from src.core.logging import get_logger

log = get_logger("pipeline.link")

ANSWER_LINE = re.compile(
    r"(?:^|\n)\s*(?:Q\s?)?(\d{1,3})\s*[.).:\-]\s*([A-Ea-e]|\d[\d,./]*)\b")
ANSWER_HINTS = ("answer", "marking", "mark scheme", "mark-scheme", "answers", "key")


def is_answer_sheet(doc: SourceDocument, pages: list[SourcePage]) -> bool:
    hay = (doc.source_path + " " + " ".join(p.text_content[:500] for p in pages)).lower()
    return any(h in hay for h in ANSWER_HINTS)


def parse_answers(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in ANSWER_LINE.finditer("\n" + text)}


def run(session: Session, docs: list[SourceDocument]) -> dict:
    linked = 0
    answer_maps: dict[str, str] = {}
    for doc in docs:
        pages = session.query(SourcePage).filter_by(document_id=doc.id).all()
        if is_answer_sheet(doc, pages):
            for p in pages:
                answer_maps.update(parse_answers(p.text_content))
    if not answer_maps:
        return {"linked": 0}
    for occ in session.query(QuestionOccurrence).all():
        ans = answer_maps.get(str(occ.question_number))
        if ans:
            occ.linked_answer = ans
            linked += 1
    session.commit()
    log.info("link: %d occurrences matched to answers", linked)
    return {"linked": linked, "answer_keys": len(answer_maps)}
