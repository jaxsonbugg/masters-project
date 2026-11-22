# Difficulty review of 23 open benchmark positions (2026-11-22)

**What this is.** After the replacement loop (rounds 1-3), 39 benchmark positions were still open. At 23 of them, at least one
Qwen candidate passed R (keys and verify), the Codex screen and the subtopic part of the alignment check, and failed only the
difficulty part: Codex judged it easier (17) or harder (6) than the dealt level (intro, intermediate or graduate, as defined in
prompt v8). Jaxson decided (2026-11-22, option A) to judge each one himself; Codex's difficulty verdict is advice.

**The sheet** `difficulty_review_sheet.csv` has one row per position: the dealt subtopic and difficulty, the best candidate
(the first difficulty-only candidate in id order), Codex's difficulty verdict and reason, the question, choices and key, the
other difficulty-only candidates for the same position, and two columns for Jaxson:
- `owner_decision`: **accept** (the candidate fits the dealt level in his judgment; it fills the position, the override is
  logged), **hand-fix** (he edits the question to the dealt level; the edit is re-checked by R and the Codex screen and
  alignment), or **relabel** (the candidate fills the position with Codex's level; this changes the difficulty mix and is
  reported);
- `owner_note`: a one-line reason, especially for an accept that overrides Codex.

Every accepted or hand-fixed question is also part of the targeted review of owner-handled questions before the freeze.

| Category, dealt level, Codex verdict | Positions |
|---|---|
| output interpretation, graduate, easier | 10 |
| numerical, graduate, easier | 7 |
| numerical, intro, harder | 2 |
| R interpretation, intro, harder | 2 |
| output interpretation, intro, harder | 1 |
| R generation, intro, harder | 1 |
