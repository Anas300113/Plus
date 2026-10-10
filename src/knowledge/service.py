"""Build a KnowledgeIndex from already-ingested SourcePage rows.

This is the bridge between the (frozen) ingestion foundation and the retrieval
layer. It reads text directly from the database -- SourcePage.text_content,
which already includes OCR text merged in by the pipeline -- and never re-parses
source files. Streaming: pages are iterated with a bounded query; each page's
text is chunked and released before the next.

Incremental + idempotent:
  * ``build_index`` chunks only the requested pages; because chunk ids are
    content-stable and the index de-duplicates by chunk_id, re-running against
    unchanged pages yields an identical index and no duplicate chunks.
  * Pass ``only_document_ids`` to index a subset incrementally.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from src.core.database import SourceDocument, SourcePage
from src.knowledge.chunk import chunk_text
from src.knowledge.retriever import KnowledgeIndex


def iter_page_chunks(
    session: Session,
    *,
    only_document_ids: list[str] | None = None,
    chunk_size: int = 700,
    overlap: int = 80,
    batch_size: int = 200,
):
    """Yield Chunk objects page-by-page (bounded memory).

    Uses keyset pagination on SourcePage.id so memory stays bounded regardless
    of corpus size.
    """
    last_id = ""
    while True:
        q = session.query(SourcePage).order_by(SourcePage.id)
        if last_id:
            q = q.filter(SourcePage.id > last_id)
        if only_document_ids is not None:
            q = q.filter(SourcePage.document_id.in_(only_document_ids))
        rows = q.limit(batch_size).all()
        if not rows:
            break
        # cache doc filenames for this batch
        doc_ids = {r.document_id for r in rows}
        docs = {
            d.id: d for d in session.query(SourceDocument)
            .filter(SourceDocument.id.in_(doc_ids)).all()
        }
        for page in rows:
            doc = docs.get(page.document_id)
            filename = doc.source_path if doc else page.document_id
            text = (page.text_content or "").strip()
            if not text:
                # scanned pages carry their readable text in ocr_text
                text = (page.ocr_text or "").strip()
            if not text:
                continue  # never fabricate content for empty pages
            # human-facing filename (basename); keep full path in meta
            fname = filename.replace("\\", "/").rsplit("/", 1)[-1] or filename
            yield from chunk_text(
                text,
                filename=fname,
                page_number=page.page_number,
                page_id=page.id,
                document_id=page.document_id,
                chunk_size=chunk_size,
                overlap=overlap,
                meta={"ocr_used": bool(page.ocr_used), "source_path": filename},
            )
            last_id = page.id
        if len(rows) < batch_size:
            break


def build_index(
    session: Session,
    *,
    only_document_ids: list[str] | None = None,
    chunk_size: int = 700,
    overlap: int = 80,
) -> KnowledgeIndex:
    """Build and return a KnowledgeIndex from ingested pages."""
    chunks = list(iter_page_chunks(
        session,
        only_document_ids=only_document_ids,
        chunk_size=chunk_size,
        overlap=overlap,
    ))
    return KnowledgeIndex().build(chunks)


def index_to_path(path: str | Path, index: KnowledgeIndex) -> Path:
    p = Path(path)
    index.save(p)
    return p
