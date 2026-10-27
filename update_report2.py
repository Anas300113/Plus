path = r"c:\Users\ADMIN\Downloads\Projects\Plus\QUALITY_GATE_REPORT.md"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Fix repo commit reference
old_repo = '**Repo:** `https://github.com/Anas300113/Plus.git` @ `b154e88` (main == origin/main, tree clean)'
new_repo = '**Repo:** `https://github.com/Anas300113/Plus.git` @ `25f41b9` (main is 2 commits ahead of origin/main `b154e88`; tree clean)'
if old_repo in c:
    c = c.replace(old_repo, new_repo)
    print("Repo line updated")
else:
    print("Repo line pattern not found, trying alternative")
    import re
    c = re.sub(r'@ `b154e88` \(main == origin/main, tree clean\)', '@ `25f41b9` (main is 2 commits ahead of origin/main `b154e88`; tree clean)', c)

# 2. Fix deployment readiness badge
old_dr = "| Deployment Readiness | ⏳ | 3/5 | 278 tests green; no manifest signing; identity default unsafe for prod; `utcnow` deprecation. |"
new_dr = "| Deployment Readiness | ⏳ | 3/5 | 301 tests green; identity P0 fail-closed guard; no manifest signing; `utcnow` deprecation. |"
if old_dr in c:
    c = c.replace(old_dr, new_dr)
    print("Deployment Readiness updated")
else:
    print("Deployment Readiness pattern not found")

# 3. Fix hard-gate decision: identity section
old_s5 = "- ❌ **Student identity:** unauthenticated, ownership enforcement off by default → **still release-blocking for real student data.**"
new_s5 = "- 🟡 **Student identity P0:** fail-closed real-data guard (`PLUS_REAL_STUDENT_DATA=1` → 503); ownership enforcement; design in `docs/ADR-002-student-identity.md`. Still release-blocking for production until Phase 2 (authenticated principal)."
if old_s5 in c:
    c = c.replace(old_s5, new_s5)
    print("Section 5 updated")
else:
    print("Section 5 pattern not found")

# 4. Fix evidence index baseline
old_ei = "- Baseline: `pytest -q` → 278 passed @ `b154e88`."
new_ei = "- Baseline: `pytest -q` → 278 passed @ `b154e88`. Current HEAD `25f41b9` (identity P0) and `985732c` (Gate 1) committed; 301 passed."
if old_ei in c:
    c = c.replace(old_ei, new_ei)
    print("Evidence index updated")
else:
    print("Evidence index pattern not found")

# 5. Fix scope/limitations
old_s8 = "- Assessment only. **No code changed, nothing committed or pushed** (tree clean @ `b154e88`)."
new_s8 = "- Assessment only. Gate 1 (`985732c`) and identity P0 (`25f41b9`) committed on top of `b154e88`; tree clean."
if old_s8 in c:
    c = c.replace(old_s8, new_s8)
    print("Scope updated")
else:
    print("Scope pattern not found")

with open(path, "w", encoding="utf-8") as f:
    f.write(c)
print("Done")
