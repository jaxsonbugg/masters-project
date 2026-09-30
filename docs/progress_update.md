# Progress Updates

Running, dated record of every change made to the Masters Project. Entries are in chronological order, newest at the bottom. Each entry says what changed, why, and where. The README stays the source of truth for scope and the current plan; this file is the history.

---

## 2026-09-17

### Project setup decisions
| Decision | Rationale |
|---|---|
| Domain = statistics and R programming | Project scope |
| Students = Pythia 70M / 160M / 410M / 1B | Same training data, designed for controlled experiments |
| Benchmark ~1k questions, frozen before training | Prevents leakage and tuning to the test set |

## 2026-09-29

### README created
- Living guide for the project created with the research question, experimental design, phase checklists, benchmark design, metrics, statistical analysis plan, storage layout, timeline, risks, open decisions, and working notes for Claude.

### Storage layout and recovery docs
| Decision | Rationale |
|---|---|
| Fallback distillation size = 50k | Feasible single-size option if compute-limited |
| Two-location storage: small/important items in OneDrive, large items in `C:\masters_project_large\` | Keeps OneDrive small while protecting important work |
| Every off-OneDrive item gets a recovery md in `recovery/` | Anything not backed up must be reproducible |

### Project folder moved
- The OneDrive project folder now lives at `C:\Users\Buggb\OneDrive\Desktop\Masters Project\` (under Desktop, with a space between "Masters" and "Project"). It was previously `C:\Users\Buggb\OneDrive\masters_project\`.
- Updated README Section 7.1 (heading and folder tree root). No other file referenced the old path. `C:\masters_project_large\` (outside OneDrive) is unchanged.

### Phase 1: domain finalized
- Domain confirmed as statistics and R programming. Phase 1 checklist item marked done in the README.

### Phase 1: success metrics defined and pre-registered
Success is defined by four criteria, all of which must be met by a student (model size, data size). Full text is in README Section 1.

1. **Retained accuracy.** Student/teacher accuracy ratio on the frozen benchmark, judged by the lower bound of its bootstrap 95% CI. Tiers: Useful >= 70%, Strong >= 85%, Near-parity >= 95%. Accuracy is macro-averaged across categories; R code graded by execution.
2. **Real gain over own baseline.** Significant improvement over the same student untrained (McNemar's test, Holm correction).
3. **Usable output.** Minimum share of well-formed responses and of R code that runs (starting value 90% each; confirm in the Phase 3 pilot).
4. **At least 10x cheaper than the teacher.** Measured on inference cost per query and latency; protocol to be set in the pilot.

| Decision | Rationale |
|---|---|
| Success = four criteria: retained accuracy tiers, significant gain over baseline, usable output, >=10x cheaper than teacher | Makes "successful specialization" testable before results exist |
| Retained-accuracy tiers: Useful 70%, Strong 85%, Near-parity 95% (lower bound of bootstrap 95% CI of student/teacher ratio) | Reports the tradeoff at several levels instead of one cutoff |
| Absolute accuracy floor of 60% for any tier; teacher below 80% is a red flag; always report absolute accuracies | Ratios alone mislead when the teacher is weak (a 58% student vs. a 60% teacher would otherwise count as near-parity) |
| No general-purpose small-model comparator unless a matching open-weight model (same size and purpose as Pythia) is found | Likely no fair match exists |
| Efficiency requirement: at least 10x cheaper than the teacher | Guard that the student is meaningfully smaller and cheaper; at these sizes the accuracy tiers carry the analysis |

Thresholds are fixed before any student results exist. Any later change must be logged in this file with a reason.

README changes: Phase 1 checklist items checked; Section 1 "Definition of success" rewritten; Section 5 metrics updated; Section 10 Open Decisions updated (removed the old "useful capability" threshold; added validity thresholds and the efficiency measurement protocol, both for the pilot).

## 2026-09-29

### Progress log created
- Created this file (`docs/progress_update.md`) to hold the dated change history so the README does not get crowded.
- Moved the README Decision Log (all rows above) into this file. README Section 11 is now a pointer to this file.
- Added a README rule (Section 12) requiring every project change to be recorded here with the date and what was done.

## 2026-09-30

### Teacher model selected (desk research, no API spend)
- Compared Claude Opus 5.5, Sonnet 5.5, Fable 5.1, and Haiku 4.5 using public pricing, model specs, and published benchmarks, plus cost projections for 1k to 200k examples. Full write-up: `docs/teacher_selection.md`.
- **Decision: Claude Sonnet 5.5 is the teacher**, run at medium or high effort (not max). Opus 5.5 is the fallback.
- Why: on the Artificial Analysis Intelligence Index Opus 5.5 scores 58 and Sonnet 5.5 scores 56, within the pre-set 3-point equivalence band, and Sonnet costs about half as much (about $665 vs. $1,330 for 50k examples via Batch API under the base-plus-thinking assumptions). Fable 5.1 (53) is dominated at 2.5x Opus's price. Haiku 4.5 was dropped for lack of evidence it is strong enough.
- Revisit trigger: switch to Opus 5.5 if teacher accuracy on the frozen benchmark in Phase 5 is below 80%, or the Phase 7 verifier pass rate is poor.
- Still open: total API budget for teacher generation.
- README changes: Phase 2 teacher item checked; Section 2 teacher row updated; removed the teacher item from Open Decisions.

### Git and GitHub set up
- Installed Git 2.55.0 and GitHub CLI 2.102.0; Git identity set to Jaxson Bugg (buggjm@miamioh.edu); logged in to GitHub as `jaxsonbugg`.
- Created `C:\dev\masters-project` as the main working copy (copied from the OneDrive folder, which is left in place and no longer updated), added a `.gitignore` for model files, environments, caches, logs, and secrets, and `.gitkeep` files so empty folders are kept.
- First commit "Initial project setup" pushed to the new **private** repository `jaxsonbugg/masters-project`. Verified the files appear on GitHub.
- Practiced the status, diff, add, commit, push loop on the README changes. Needed `gh auth setup-git` once so `git push` could use the GitHub login.
- README changes: Section 7 notes the new working copy; Section 12 has a Git rule. Added `docs/github_notes.md` as a personal command cheat sheet.

### README header spacing (Git practice change)
- Added blank lines between the Author, Advisor, Institution, Duration, and Status lines at the top of the README so each shows on its own line when rendered. Used as a second practice run of the status, diff, add, commit, push loop.

### Old OneDrive folder verified and removed
- Compared every file in `C:\Users\Buggb\OneDrive\Desktop\Masters Project` against `C:\dev\masters-project` by SHA-256 hash. `configs/paths.yaml`, `docs/teacher_selection.md`, and `recovery/_TEMPLATE.md` were identical. The old `README.md` differed only in one outdated heading line, and the old `docs/progress_update.md` had no lines missing from the repo. All 11 empty folders exist in the repo, each kept by a `.gitkeep` file. Nothing in the old folder was missing from the repo.
- Committed and pushed everything to GitHub first, then moved the old OneDrive folder to the Windows Recycle Bin.
- README Section 7 and Section 12 and the comment in `configs/paths.yaml` now describe only the current layout: the project repository at `C:\dev\masters-project` (backed up on GitHub) and large items outside the repository in `C:\masters_project_large\`.