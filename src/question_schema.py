import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = '1.0.0'

VALID_WORKFLOW_STATUSES = {
    'discovered', 'extracted', 'ai_reviewed',
    'validation_required', 'approved', 'rejected',
}

VALID_ANSWER_STATUSES = {'missing', 'candidate', 'verified'}
VALID_EXPLANATION_STATUSES = {'missing', 'candidate', 'verified'}

VALID_SUBJECTS = {'maths', 'english', 'verbal_reasoning', 'non_verbal_reasoning'}

VALID_QUESTION_TYPES = {
    'mcq', 'numeric', 'free_text', 'multi_select', 'matching',
    'ordering', 'cloze', 'image_choice', 'creative_writing', 'unknown_custom',
}

VALID_DIFFICULTIES = {1, 2, 3, 4, 5}

_ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,127}$')


@dataclass
class Curriculum:
    subject: Optional[str] = None
    topic: Optional[str] = None
    subtopic: Optional[str] = None
    skill_ids: List[str] = field(default_factory=list)
    exam_board: Optional[str] = None
    region: Optional[str] = None
    difficulty: Optional[int] = None


@dataclass
class Content:
    type: str = 'unknown_custom'
    text: str = ''
    instructions: Optional[str] = None
    context: Optional[str] = None
    options_json: Optional[List[Dict[str, Any]]] = None
    media_json: Optional[List[Dict[str, Any]]] = None


@dataclass
class Answer:
    representation: Optional[Dict[str, Any]] = None
    status: str = 'missing'
    evidence: Optional[str] = None


@dataclass
class Explanation:
    text: Optional[str] = None
    status: str = 'missing'
    evidence: Optional[str] = None


@dataclass
class Workflow:
    status: str = 'discovered'
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Extraction:
    source_filename: Optional[str] = None
    page: Optional[int] = None
    question_number: Optional[str] = None
    fingerprint: Optional[str] = None
    method: Optional[str] = None
    extraction_run: Optional[str] = None


@dataclass
class CanonicalQuestion:
    id: str
    version: str = SCHEMA_VERSION
    db_id: Optional[str] = None
    source_id: Optional[str] = None
    original_id: Optional[str] = None
    extraction: Extraction = field(default_factory=Extraction)
    curriculum: Curriculum = field(default_factory=Curriculum)
    content: Content = field(default_factory=Content)
    answer: Answer = field(default_factory=Answer)
    explanation: Explanation = field(default_factory=Explanation)
    workflow: Workflow = field(default_factory=Workflow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'CanonicalQuestion':
        return CanonicalQuestion(
            id=data['id'],
            version=data.get('version', SCHEMA_VERSION),
            db_id=data.get('db_id'),
            source_id=data.get('source_id'),
            original_id=data.get('original_id'),
            extraction=Extraction(**data.get('extraction', {})),
            curriculum=Curriculum(**data.get('curriculum', {})),
            content=Content(**data.get('content', {})),
            answer=Answer(**data.get('answer', {})),
            explanation=Explanation(**data.get('explanation', {})),
            workflow=Workflow(**data.get('workflow', {})),
        )


def _iso(dt: Any) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt)


def from_db_row(row: Any, *, source_id: Optional[str] = None,
                original_id: Optional[str] = None) -> CanonicalQuestion:
    q = CanonicalQuestion(
        id=row.id,
        db_id=row.id,
        source_id=source_id,
        original_id=original_id,
        extraction=Extraction(
            source_filename=getattr(row, 'exam_board', None) or None,
            fingerprint=getattr(row, 'fingerprint', None) or None,
        ),
        curriculum=Curriculum(
            subject=getattr(row, 'subject', None) or None,
            topic=getattr(row, 'topic', None) or None,
            subtopic=getattr(row, 'subtopic', None) or None,
            skill_ids=list(getattr(row, 'skill_ids', None) or []),
            exam_board=getattr(row, 'exam_board', None) or None,
            region=getattr(row, 'region', None) or None,
            difficulty=getattr(row, 'difficulty', None),
        ),
        content=Content(
            type=getattr(row, 'question_type', None) or 'unknown_custom',
            text=getattr(row, 'question_text', None) or '',
            instructions=getattr(row, 'instructions', None) or None,
            context=getattr(row, 'context', None) or None,
            options_json=getattr(row, 'options_json', None),
        ),
        answer=Answer(
            representation={'option': getattr(row, 'correct_answer', None)}
            if getattr(row, 'correct_answer', None) else None,
            status=getattr(row, 'answer_status', None) or 'missing',
            evidence=getattr(row, 'answer_evidence', None) or None,
        ),
        explanation=Explanation(
            text=getattr(row, 'explanation', None) or None,
            status=getattr(row, 'explanation_status', None) or 'missing',
            evidence=getattr(row, 'explanation_evidence', None) or None,
        ),
        workflow=Workflow(
            status=getattr(row, 'status', None) or 'validation_required',
            created_at=_iso(getattr(row, 'created_at', None)),
            updated_at=_iso(getattr(row, 'updated_at', None)),
        ),
    )
    if (q.explanation.text is None or not q.explanation.text) and getattr(row, 'worked_solution', None):
        q.explanation.text = row.worked_solution
    return q

def validate_record(record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    if not isinstance(record, dict):
        return False, ['record must be an object']
    rid = record.get('id')
    if not rid or not isinstance(rid, str) or not _ID_RE.match(rid):
        errors.append('id: missing or invalid (lowercase slug/uuid)')
    ver = record.get('version')
    if ver is not None and ver != SCHEMA_VERSION:
        errors.append('version: unsupported ({0}); expected {1}'.format(ver, SCHEMA_VERSION))
    if 'db_id' in record and record['db_id'] is not None and not isinstance(record['db_id'], str):
        errors.append('db_id: must be string or null')

    cur = record.get('curriculum') or {}
    if not isinstance(cur, dict):
        errors.append('curriculum: must be object')
    else:
        subj = cur.get('subject')
        if subj is not None and subj not in VALID_SUBJECTS:
            errors.append('curriculum.subject: unknown ({0})'.format(subj))
        diff = cur.get('difficulty')
        if diff is not None and (not isinstance(diff, int) or diff not in VALID_DIFFICULTIES):
            errors.append('curriculum.difficulty: must be 1-5')
        skills = cur.get('skill_ids', [])
        if skills is not None and not isinstance(skills, list):
            errors.append('curriculum.skill_ids: must be array')

    content = record.get('content') or {}
    if not isinstance(content, dict):
        errors.append('content: must be object')
    else:
        ctype = content.get('type')
        if ctype is not None and ctype not in VALID_QUESTION_TYPES:
            errors.append('content.type: unknown ({0})'.format(ctype))
        text = content.get('text')
        if text is not None and not isinstance(text, str):
            errors.append('content.text: must be string')
        options = content.get('options_json')
        if options is not None and not isinstance(options, list):
            errors.append('content.options_json: must be array')
        if ctype in ('mcq', 'multi_select', 'image_choice'):
            opts = options or []
            if len(opts) < 2:
                errors.append('content.options_json: choice question needs >= 2 options')
            ids = []
            for o in opts:
                if not isinstance(o, dict):
                    errors.append('content.options_json: option must be object')
                    continue
                oid = o.get('letter') or o.get('id')
                if not oid:
                    errors.append('content.options_json: option missing id/letter')
                else:
                    ids.append(str(oid).upper())
            if len(ids) != len(set(ids)):
                errors.append('content.options_json: duplicate option ids')
            ans = (record.get('answer') or {}).get('representation')
            if isinstance(ans, dict):
                opt = ans.get('option')
                if opt is not None and ids and str(opt).upper() not in ids:
                    errors.append('answer.representation.option: not among options')

    ans = record.get('answer') or {}
    if not isinstance(ans, dict):
        errors.append('answer: must be object')
    else:
        st = ans.get('status', 'missing')
        if st not in VALID_ANSWER_STATUSES:
            errors.append('answer.status: invalid ({0})'.format(st))
        ev = ans.get('evidence')
        if st == 'verified' and (not ev or not isinstance(ev, str) or len(ev.strip()) < 16):
            errors.append('answer.evidence: verified requires evidence >= 16 chars')
        rep = ans.get('representation')
        if rep is not None and not isinstance(rep, dict):
            errors.append('answer.representation: must be object or null')

    expl = record.get('explanation') or {}
    if not isinstance(expl, dict):
        errors.append('explanation: must be object')
    else:
        st = expl.get('status', 'missing')
        if st not in VALID_EXPLANATION_STATUSES:
            errors.append('explanation.status: invalid ({0})'.format(st))
        ev = expl.get('evidence')
        if st == 'verified' and (not ev or not isinstance(ev, str) or len(ev.strip()) < 16):
            errors.append('explanation.evidence: verified requires evidence >= 16 chars')

    wf = record.get('workflow') or {}
    if not isinstance(wf, dict):
        errors.append('workflow: must be object')
    else:
        st = wf.get('status', 'discovered')
        if st not in VALID_WORKFLOW_STATUSES:
            errors.append('workflow.status: invalid ({0})'.format(st))

    ext = record.get('extraction') or {}
    if not isinstance(ext, dict):
        errors.append('extraction: must be object')

    return (len(errors) == 0), errors


def to_jsonl(records: List[CanonicalQuestion]) -> str:
    lines = []
    for r in sorted(records, key=lambda x: x.id):
        lines.append(json.dumps(r.to_dict(), sort_keys=True, ensure_ascii=True,
                                separators=(',', ':')))
    return chr(10).join(lines) + (chr(10) if lines else '')


def canonical_digest(records: List[CanonicalQuestion]) -> str:
    payload = json.dumps([r.to_dict() for r in sorted(records, key=lambda x: x.id)],
                         sort_keys=True, ensure_ascii=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()
