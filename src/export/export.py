"""Read-only question-bank exporter."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from src.core.database import CanonicalQuestion
from src.question_schema import CanonicalQuestion as PortableQuestion, from_db_row, canonical_digest


def export_bank(session: Session, *, batch_size: int = 500) -> List[PortableQuestion]:
    """Read-only export of all canonical questions. No writes performed."""
    out: List[PortableQuestion] = []
    last_id = None
    while True:
        q = session.query(CanonicalQuestion)
        if last_id is not None:
            q = q.filter(CanonicalQuestion.id > last_id)
        q = q.order_by(CanonicalQuestion.id).limit(batch_size).all()
        if not q:
            break
        for row in q:
            out.append(from_db_row(row))
        last_id = q[-1].id
    return out


def write_export(records: List[PortableQuestion], out_dir: Path) -> dict:
    """Write export files. Returns manifest dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # export.json
    payload = [r.to_dict() for r in sorted(records, key=lambda x: x.id)]
    (out_dir / 'export.json').write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=True, indent=2) + chr(10),
        encoding='utf-8')
    # export.ndjson
    (out_dir / 'export.ndjson').write_text(
        chr(10).join(json.dumps(r.to_dict(), sort_keys=True, ensure_ascii=True)
                     for r in sorted(records, key=lambda x: x.id)) + chr(10),
        encoding='utf-8')
    # manifest
    manifest = {
        'schema_version': '1.0.0',
        'record_count': len(records),
        'digest': canonical_digest(records),
    }
    (out_dir / 'manifest.json').write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + chr(10),
        encoding='utf-8')
    (out_dir / 'dataset_digest.txt').write_text(
        canonical_digest(records) + chr(10), encoding='utf-8')
    return manifest
