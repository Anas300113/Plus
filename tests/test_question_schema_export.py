"""Tests for question schema and read-only export."""

import json
import tempfile
from pathlib import Path

from src.core.database import Base, get_engine, CanonicalQuestion
from src.question_schema import from_db_row, validate_record, canonical_digest
from src.export.export import export_bank, write_export


def _seed(session):
    q = CanonicalQuestion(
        id='q1', subject='maths', topic='maths-arithmetic',
        question_type='mcq', question_text='What is 2+2?',
        options_json=[{'letter': 'A', 'text': '3'}, {'letter': 'B', 'text': '4'}],
        correct_answer='B', answer_status='missing',
        exam_board='ks2', fingerprint='fp1')
    session.add(q)
    session.commit()


def test_export_readonly(engine):
    from sqlalchemy.orm import sessionmaker
    S = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = S()
    Base.metadata.create_all(bind=engine)
    _seed(s)
    recs = export_bank(s)
    assert len(recs) == 1
    assert recs[0].id == 'q1'
    ok, errs = validate_record(recs[0].to_dict())
    assert ok, errs
    s.close()


def test_export_deterministic_digest(engine):
    from sqlalchemy.orm import sessionmaker
    S = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = S()
    Base.metadata.create_all(bind=engine)
    _seed(s)
    r1 = export_bank(s)
    r2 = export_bank(s)
    assert canonical_digest(r1) == canonical_digest(r2)
    s.close()


def test_write_export_files(engine):
    from sqlalchemy.orm import sessionmaker
    S = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = S()
    Base.metadata.create_all(bind=engine)
    _seed(s)
    recs = export_bank(s)
    with tempfile.TemporaryDirectory() as d:
        m = write_export(recs, Path(d))
        assert (Path(d) / 'export.json').exists()
        assert (Path(d) / 'export.ndjson').exists()
        assert (Path(d) / 'manifest.json').exists()
        assert (Path(d) / 'dataset_digest.txt').exists()
        assert m['record_count'] == 1
    s.close()
"""Tests for validation and reconciliation."""

from src.export.validate import validate_records, reconcile_with_db


def test_validate_records_clean():
    recs = [{'id': 'q1', 'version': '1.0.0',
             'content': {'type': 'mcq', 'text': 'hi',
                         'options_json': [{'letter': 'A', 'text': '1'},
                                          {'letter': 'B', 'text': '2'}]},
             'answer': {'status': 'missing', 'representation': {'option': 'A'}},
             'explanation': {'status': 'missing'},
             'workflow': {'status': 'discovered'},
             'extraction': {}, 'curriculum': {}}]
    r = validate_records(recs)
    assert r['passed']
    assert r['errors'] == 0


def test_validate_records_duplicate_id():
    recs = [{'id': 'q1', 'version': '1.0.0', 'content': {'type': 'mcq', 'text': 'hi',
             'options_json': [{'letter': 'A', 'text': '1'}, {'letter': 'B', 'text': '2'}]},
             'answer': {'status': 'missing'}, 'explanation': {'status': 'missing'},
             'workflow': {'status': 'discovered'}, 'extraction': {}, 'curriculum': {}},
            {'id': 'q1', 'version': '1.0.0', 'content': {'type': 'mcq', 'text': 'hi',
             'options_json': [{'letter': 'A', 'text': '1'}, {'letter': 'B', 'text': '2'}]},
             'answer': {'status': 'missing'}, 'explanation': {'status': 'missing'},
             'workflow': {'status': 'discovered'}, 'extraction': {}, 'curriculum': {}}]
    r = validate_records(recs)
    assert not r['passed']
    assert r['errors'] >= 1


def test_reconcile_matches():
    recs = [{'id': 'q1', 'content': {'type': 'mcq'}}]
    db = {'total': 1, 'by_type': {'mcq': 1}}
    r = reconcile_with_db(recs, db)
    assert r['reconciled']


def test_reconcile_mismatch():
    recs = [{'id': 'q1', 'content': {'type': 'mcq'}}]
    db = {'total': 2, 'by_type': {'mcq': 2}}
    r = reconcile_with_db(recs, db)
    assert not r['reconciled']
    assert len(r['differences']) >= 1
