"""Step: OCR for scanned/image-only pages.

Deterministic detection: a page is considered scanned when native text
extraction produced nothing usable. OCR output is stored in page.ocr_text,
separate from page.text_content (native extraction).

OCR remains extraction data, not canonical content.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from src.core.database import SourcePage, SourceAsset
from src.core.logging import get_logger

if TYPE_CHECKING:
    from src.core.database import SourceDocument

log = get_logger("pipeline.ocr")

MIN_NATIVE_TEXT_CHARS = 40


def is_scanned_page(page: SourcePage) -> bool:
    """Page likely needs OCR when no reliable native text exists."""
    if page.ocr_used:
        return False
    if len(page.text_content.strip()) >= MIN_NATIVE_TEXT_CHARS:
        return False
    return True


def ocr_page(session: Session, page: SourcePage,
             image_bytes: bytes | None = None,
             engine: str = "tesseract",
             version: str = "unknown") -> str:
    """OCR a single page from image bytes. Stores result on SourcePage."""
    if image_bytes is None or len(image_bytes) == 0:
        log.warning("ocr: no image bytes for page %s.%s",
                    page.document_id[:8], page.page_number)
        return ""
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(io.BytesIO(image_bytes))
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
        text = pytesseract.image_to_string(img).strip()
    except Exception as exc:
        log.warning("ocr: failed page %s.%s: %s",
                    page.document_id[:8], page.page_number, exc)
        text = ""
    page.ocr_text = text
    page.ocr_used = True
    page.ocr_engine = engine
    page.ocr_version = version
    session.commit()
    log.info("ocr: page %s.%s -> %d chars (%s)",
             page.document_id[:8], page.page_number, len(text), engine)
    return text


def run_ocr(session: Session, docs: list["SourceDocument"],
            source_root: str | Path = "",
            assets_dir: str | Path = "data/assets",
            engine: str = "tesseract",
            version: str = "unknown") -> dict:
    """OCR scanned pages. Only pages without reliable native text."""
    root = Path(source_root) if source_root else Path.cwd()
    assets_dir = Path(assets_dir)
    ocred = 0
    skipped = 0
    for doc in docs:
        pages = session.query(SourcePage).filter_by(document_id=doc.id).all()
        asset_by_page: dict[str, int] = {}
        for a in session.query(SourceAsset).filter_by(document_id=doc.id).all():
            asset_by_page[a.page_id] = asset_by_page.get(a.page_id, 0) + 1
        for page in pages:
            if not is_scanned_page(page):
                skipped += 1
                continue
            img = _render_page(session, doc, page, root, assets_dir)
            if img is None or len(img) == 0:
                skipped += 1
                continue
            text = ocr_page(session, page, img, engine, version)
            if text:
                ocred += 1
    session.commit()
    log.info("ocr: %d ocred, %d skipped", ocred, skipped)
    return {"ocred": ocred, "skipped": skipped}


def _render_page(session: Session, doc: "SourceDocument", page: SourcePage,
                 source_root: Path, assets_dir: Path) -> bytes | None:
    """Render page to PNG bytes for OCR."""
    pdf_path = source_root / doc.source_path
    if not pdf_path.exists():
        return None
    try:
        import fitz
        with fitz.open(str(pdf_path)) as pdf:
            if page.page_number > len(pdf):
                return None
            pix = pdf[page.page_number - 1].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            return pix.tobytes("png")
    except Exception as exc:
        log.warning("ocr render: fitz failed for %s p%s: %s",
                    doc.source_path, page.page_number, exc)
    for a in session.query(SourceAsset).filter_by(page_id=page.id).all():
        try:
            full = assets_dir / a.storage_path
            if full.exists():
                return full.read_bytes()
        except Exception:
            continue
    return None
