# Fix sheet for the 16 benchmark positions still open after the replacement loop (2026-11-22)

**What this is.** After three rounds of same-subtopic replacement and the difficulty decision, 16 positions had no candidate
that passed the Codex screen. For each, Claude picked the best candidate (on the dealt subtopic, preferably the right
difficulty) and checked in R whether its flagged problem is a number that can be recomputed. Claude writes no question text:
every edit is typed by Jaxson in `new_text`, then applied in one step with the rounding fixes
(`code/verification/rounding_fixes.py apply-owner-fixes`, all or nothing) and re-checked by R and the Codex screen and
alignment check.

**Groups** (column `group`):
- **A (6 positions, 8 rows):** Codex flagged exactly the number R recomputed (a p-value or a var.test interval). Type the
  suggested text. No key changes; no significance threshold is crossed.
- **B (5 positions, 9 rows):** the flagged number is a different one (an interval width, an adjusted R-squared, an exact
  binomial p-value and interval, ANOVA p-values); Claude computed it in R by hand (column `computation`). Type the suggested
  text. No key changes; no threshold crossed.
- **C (3 positions):** the printout needs a decision first (which residual df; drop the raw data or refit; new deviances).
  Write your decision in `owner_note`; Claude then computes consistent values in R and adds rows for you to type.
- **D (positions 218 and 499):** no usable candidate at all; handled by a new Qwen attempt (6 candidates each, loop D), so they are not on the sheet. They are added back only if no new candidate passes.

Rule for all computed values (owner's rule, 2026-11-21): inputs, estimates, test statistics and degrees of freedom stay as
printed; only final values (p-values, intervals, derived statistics such as adjusted R-squared) are recomputed.
