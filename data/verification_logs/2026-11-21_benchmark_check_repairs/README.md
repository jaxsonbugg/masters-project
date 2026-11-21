# Repairs of broken R checks, benchmark and development set (2026-11-21)

**What this is.** After the benchmark and development set were generated (Talon jobs 299-309), `verify` ran every R-code question's grading check in the R sandbox: the check must accept the question's own answer key and reject deliberately wrong answers. 41 checks failed (33 benchmark, 8 development). Every failure was genuine: the check referred to objects it never created, handled randomness wrongly, compared with wrong hard-coded values, or used invalid R.

**Decision (Jaxson, 2026-11-21): repair or replace.** For each of the 41, Claude decided whether the question and its key are clearly right.
- **repair_check (32):** only the check was broken. The check was rewritten and verified again in the sandbox; it now accepts the key and rejects the wrong answers. The original check is kept in the item (`r_check_original`). The key is never changed.
- **replace (9):** the key or the question itself is wrong or doubtful; the position is filled by the next unused spare of the same category, difficulty and answer type.

**Files.**
- `decisions.json`: the 41 decisions, each with its reason and (for a repair) the new check. Applied with `python code/generation/generate_set.py apply-repairs`.
- `soft_flags_sheet.csv`: the 28 number questions in the final benchmark (23) and development set (5) whose typed key differed from R's value; R's rounded value is the key. **For Jaxson's look:** does R's code answer the question as written?
- `review_sheet.csv`: one row per decision, with the question, the key, the original and the new check, and the verify result after the repair. **For Jaxson's review:** fill `owner_ok` (yes or no) and a note; a "no" is handled before the freeze (the question is fixed or replaced, and the change is logged).

**Example.** BM0714: "A 3 x 3 matrix is defined as M <- matrix(1:9, nrow = 3). Write a one-line R expression that computes the sum of the diagonal elements of M." Key `sum(diag(M))`. The original check `isTRUE(all.equal(eval(parse(text = candidate)), 15))` never created `M`, so even the key failed. Repaired check: `M <- matrix(1:9, nrow = 3); isTRUE(all.equal(eval(parse(text = candidate)), 15))`.

**What it does not show.** That the questions are clear or that every key matches its question as written; the Codex screen and the 150-item audit check that.
