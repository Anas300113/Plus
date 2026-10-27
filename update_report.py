path = r"c:\Users\ADMIN\Downloads\Projects\Plus\QUALITY_GATE_REPORT.md"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# Section 3: Student Identity
old_s3 = "- `X-Student-Id` is a **supplied identifier, not authenticated**; the app has no identity provider (`review.py:18-26` documents this for reviewers and it applies to students)."
new_s3 = old_s3 + "\n- Identity P0 adds fail-closed ownership checks and a real-data guard (PLUS_REAL_STUDENT_DATA=1 returns 503 on student-scoped routes)."
if old_s3 in c:
    c = c.replace(old_s3, new_s3)

# Section 4: Deployment Readiness badge
old_s4 = "| Deployment Readiness | ⏳ | 3/5 | 278 tests green; no manifest signing; identity default unsafe for prod; `utcnow` deprecation. |"
new_s4 = "| Deployment Readiness | ⏳ | 3/5 | 301 tests green; identity P0 fix; no manifest signing; `utcnow` deprecation. |"
if old_s4 in c:
    c = c.replace(old_s4, new_s4)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)
print("Sections 3 & 4 updated")
