# Fix sheet 2 (2026-11-24)

**Why.** The Codex rescreen of the 42 questions edited on 2026-11-22 flagged 14. Ten still had other numbers that did not fit
(confidence intervals, test statistics against their counts or correlation), and some text or answer choices still quoted an
old value (BM1265's question and choices quoted 0.0447 / 4.47 percent; BM0597's choice D quoted 0.02565). BM1401 (position
490) reverts to option b: R gives no "fitted probabilities 0 or 1" warning for the question's own data, so the code and data
lines are removed and the original table is kept (its intercept z corrected to estimate / standard error).

**What to do.** Copy `suggested_text` into `new_text` for every row, as before. `field` says where the edit goes: the
question, or one answer choice (`choice_A` .. `choice_D`). `(delete line)` removes that whole line. Every value was computed
in R (column `computation`); the owner's rule holds: inputs and degrees of freedom stay; a test statistic that does not fit its
own inputs (BM0897's t against r, BM0364's and BM0810's chi-squared against the counts) is recomputed first, then the
p-value and interval. No key changes; no significance threshold is crossed. All other numbers in these printouts were
cross-checked against each other in R.

Positions 190, 224, 617, 817 and 997 are being replaced by loop E and are not on this sheet.
