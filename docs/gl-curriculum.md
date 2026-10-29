# GL-style 11+ curriculum and question bank

This repository now includes a reproducible GL-style foundation curriculum. It is aligned to the four areas that GL Assessment identifies in its familiarisation materials: English, maths, verbal reasoning, and non-verbal reasoning. The official GL guidance also says that local authorities and schools decide which subjects, timings, and question balance they use, so this bank is a flexible foundation rather than a guarantee that one local test will have the same format.

The seed bank in `src/curriculum/gl_bank.py` contains 40 original questions: ten each for maths, English, verbal reasoning, and non-verbal reasoning. They are not copied from GL Assessment. Every seeded question has:

- a subject, topic, skill, and difficulty;
- four explicit multiple-choice options;
- a verified answer and written explanation;
- answer and explanation evidence fields;
- source provenance and a review event;
- `approved` status so it can flow into practice sessions.

The curriculum builder creates a structured lesson, strategy, worked-example, and common-mistake record for every taxonomy topic. The lesson contract is retrieval warm-up, explicit method, worked example, guided practice, independent practice, exit check, and spaced review. The GL plan is staged as diagnostic baseline, foundation skill building, consolidation, exam conditioning, and readiness maintenance.

## Build the local database

From the repository root:

```bash
PYTHONPATH=. .venv/bin/python scripts/seed_gl_curriculum.py \
  --db sqlite:///./elevenplus.db
```

The command is idempotent. It creates or updates the schema, seeds the taxonomy, adds curriculum records, and loads the original approved foundation bank. The generated `elevenplus.db` is intentionally ignored by Git; deployments should run the builder against their configured `DATABASE_URL` as a controlled data-preparation step rather than commit learner data.

## Quality gates

The bank is deliberately review-gated. Student-facing selection uses approved questions only. The regression suite checks that the seed is balanced across all four subjects, has verified answers and explanations, has provenance, has one lesson for every taxonomy topic, and can be run twice without duplicating questions.

Before adding more questions, run the schema validator and keep new records pending until their answer, explanation, provenance, and licensing status have been checked. For non-verbal reasoning, the current seed uses compact symbolic prompts as a functional foundation. A production bank should add reviewed visual assets and image-specific validation before treating those items as a complete visual analogue of a local paper.

## Intended pupil flow

The learner dashboard follows a fixed weekly cadence: Monday maths, Tuesday English, Wednesday non-verbal reasoning, and Thursday verbal reasoning. Each weekday opens with the selected topic's mini-lesson and then a ten-question subject test. Friday starts a 40-question balanced test (ten per subject); if measured performance identifies a weak topic, the Friday plan switches to a focused repair test instead. When a topic has fewer than ten approved items, the lesson remains topic-specific but the test temporarily draws ten unique approved questions from that subject, avoiding repeats while the reviewed bank grows.

Start with a short diagnostic across the four subjects. Use the result to choose two focus topics. Teach one method, practise untimed questions, and immediately review mistakes. Permit mixed or timed practice only after a topic has at least eight answered questions and 75% accuracy. Use repeated-mistake and review-queue data to create catch-up work, then introduce mixed timed sessions. Near the test, prioritise pacing, accuracy, and retrieval of known methods rather than continuously adding new topics.

This supports high-quality preparation, but no question bank can guarantee that every pupil will achieve a particular score. Scores also depend on the local test, starting point, time available, attendance, wellbeing, and the quality of ongoing human review.
