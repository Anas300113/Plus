# 11-dump corpus import

`https://github.com/Anas300113/11-dump` contains a large mixed corpus: KS2 worksheets, school sample papers, verbal and non-verbal practice, answer sheets, PDFs, PPTX files, and ZIP archives. The repository has no licence or permission manifest, and several documents explicitly identify third-party publishers such as CGP and KSOL. It must therefore be treated as a **reference-only corpus** until an authorised reviewer confirms rights for a specific source.

## What the importer does

Run:

```bash
PYTHONPATH=. .venv/bin/python scripts/import_11_dump.py \
  --dump /path/to/11-dump \
  --db sqlite:///./elevenplus.db
```

The importer:

1. inventories all non-Git files with SHA-256 hashes and the source commit;
2. records every source as `reference_only` with an explicit rights note;
3. extracts PDF pages and native text with page-level provenance;
4. detects numbered question occurrences and multiple-choice options where the extraction is structurally reliable;
5. links answers only from an answer key belonging to the same source document;
6. assigns subject suggestions from the source path;
7. promotes schema-valid records only to `validation_required`.

It does **not** approve, publish, rewrite, or copy content into the student-facing bank. Questions from `reference_only` sources are blocked by the approval contract even if a reviewer verifies the answer and explanation. The source rights status must first be changed by an authorised person after permission or an acceptable licence is documented.

The initial import of this repository produced 500 source-file records, 2,828 extracted pages, 5,315 numbered question occurrences, and 219 same-document answer-key links. Sixty-three records passed structural validation and entered the review queue; the remaining occurrences stay queued because their options, OCR, or answer relationship was incomplete or ambiguous. The database contains 40 approved original foundation questions for student practice; dump-derived records remain review-gated.

## Normalized bulk dataset

The canonical database model now includes explicit `schema_version`, `subject_id`, `topic_id`, `skill_id`, `prompt_json`, `answer_json`, `assets_json`, `source_id`, and `validation_status` fields. Legacy fields remain for compatibility, but new import/export code uses the normalized contract in [`schemas/question.schema.json`](../schemas/question.schema.json).

Generate a large JSONL interchange file with:

```bash
PYTHONPATH=. .venv/bin/python scripts/export_question_bank.py \
  --db sqlite:///./elevenplus.db \
  --out data/exports/question-bank.jsonl
```

The current export contains 5,355 records: 40 approved original questions and 5,315 dump-derived occurrence records. All but one extractable occurrence is now represented in the canonical model. The latter records are explicitly marked pending/discovered and `reference_only`; they are available for review, deduplication, rights clearance, answer verification, and curriculum classification, but cannot enter pupil practice automatically.

The enhanced linker recovered **262 answer values** from answer keys: 219 same-document matches plus 43 additional matches from unambiguous question/answer filename pairs. The remaining records have an explicit missing answer rather than a guessed answer. This distinction is intentional: a question with no trustworthy key must be solved and independently checked before it becomes an approved teaching item.

## Curriculum sorting

The existing taxonomy remains the learner-facing structure: Maths, English, Verbal Reasoning, and Non-Verbal Reasoning, with 48 topics and a staged lesson sequence. Dump candidates receive subject suggestions from filenames and folders, but a reviewer must confirm the exact topic and skill. This prevents a filename such as `maths` or `verbal` from silently determining the teaching sequence.

Use the resulting review queue to curate a smaller, high-quality bank. Prefer complete question-and-answer pairs with clear page provenance, readable options, an answer explanation, appropriate age/difficulty, and an acceptable rights status. Reject duplicates, incomplete OCR, ambiguous answer keys, and copyrighted content that cannot be licensed. For Non-Verbal Reasoning, retain the page/image asset as part of the review record; text extraction alone is not sufficient evidence for visual questions.

The imported material remains useful for source discovery, curriculum coverage analysis, and human-led selection. It is not treated as an automatic promise of correctness or as an official GL Assessment bank.
