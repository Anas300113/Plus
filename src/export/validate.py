"""Validation and reconciliation for the question-bank export."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from src.question_schema import validate_record


def validate_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate a list of portable records. Returns a report dict."""
    issues: List[Dict[str, Any]] = []
    seen_ids = set()
    for r in records:
        rid = r.get('id')
        if rid in seen_ids:
            issues.append({'id': rid, 'severity': 'error',
                           'code': 'duplicate_id', 'detail': 'duplicate id'})
        seen_ids.add(rid)
        ok, errs = validate_record(r)
        if not ok:
            for e in errs:
                issues.append({'id': rid, 'severity': 'error',
                               'code': 'schema_validation', 'detail': e})
    errors = [i for i in issues if i['severity'] == 'error']
    warnings = [i for i in issues if i['severity'] == 'warning']
    return {
        'total': len(records),
        'errors': len(errors),
        'warnings': len(warnings),
        'issues': issues,
        'passed': len(errors) == 0,
    }


def reconcile_with_db(exported: List[Dict[str, Any]],
                      db_counts: Dict[str, int]) -> Dict[str, Any]:
    """Reconcile exported counts with DB counts.

    db_counts should be a dict like:
        {'total': 1057, 'by_type': {'mcq': 1057}, 'by_status': {...}}
    """
    result: Dict[str, Any] = {'differences': []}
    exported_total = len(exported)
    db_total = db_counts.get('total', 0)
    if exported_total != db_total:
        result['differences'].append({
            'field': 'total',
            'exported': exported_total,
            'db': db_total,
            'status': 'unresolved',
        })
    # by type
    exported_types = Counter(r.get('content', {}).get('type') for r in exported)
    db_types = db_counts.get('by_type', {})
    for t in set(exported_types) | set(db_types):
        e = exported_types.get(t, 0)
        d = db_types.get(t, 0)
        if e != d:
            result['differences'].append({
                'field': 'by_type.' + str(t),
                'exported': e, 'db': d, 'status': 'unresolved',
            })
    result['reconciled'] = len(result['differences']) == 0
    return result


def write_validation_report(report: Dict[str, Any], out_path: Path) -> None:
    """Write a human-readable + JSON validation report."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    (out_path.with_suffix('.json')).write_text(
        json.dumps(report, sort_keys=True, indent=2) + chr(10), encoding='utf-8')
    lines = ['# Validation Report', '',
             'Total: {0}'.format(report.get('total', 0)),
             'Errors: {0}'.format(report.get('errors', 0)),
             'Warnings: {0}'.format(report.get('warnings', 0)),
             'Passed: {0}'.format(report.get('passed', False)), '']
    for i in report.get('issues', []):
        lines.append('- [{0}] {1}: {2}'.format(
            i.get('severity', '?').upper(), i.get('id', '?'), i.get('detail', '')))
    out_path.write_text(chr(10).join(lines) + chr(10), encoding='utf-8')
