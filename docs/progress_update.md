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
## 2026-10-01

### Student checkpoints pinned and downloaded (Phase 2)
- **Decision: all four students are the deduped Pythia variants at the final `step143000` checkpoint, pinned by commit SHA** (70M `9a7c847e...`, 160M `c54a0e0b...`, 410M `c66f7467...`, 1B `d1988145...`). Standard (non-deduped) variants are not used. Full versions, hashes and sources: `docs/model_versions.md`.
- Why: deduped models share the same training data and order across sizes, which keeps size comparisons clean. The `step143000` SHA is fixed, while `main` can move and its SHA differs from `step143000` for every size.
- Downloaded the four models with `curl` from the pinned commits to `C:\masters_project_large\models\pythia\` (about 4.6 GB, not committed). The `model.safetensors` SHA-256 and byte counts match the Hugging Face file listing for all four. `pytorch_model.bin` and the 12.2 GB 1B `optimizer.pt` were not downloaded. Rebuild steps: `recovery/pythia_base_models.md`.
- **Precision decisions:** original checkpoint files stay unchanged (no conversion or re-saving); all four students are loaded explicitly as `torch.float16` for baseline evaluation; the training precision recipe (AMP/mixed precision, gradient and optimizer-state precision, FP16 or BF16) is deliberately left for Phase 8, after the cluster GPU environment is known. `config.json` `torch_dtype` is not relied on. The three concepts (storage dtype, runtime load dtype, training precision) are kept separate.
- New README Section 12 rules: dated teacher/verifier outputs; current Pythia labels only (70M, 160M, 410M, 1B; the retired old names are listed only in the README rule table); the model precision rule.
- Open checks recorded in `docs/model_versions.md`: what changed between `step143000` and `main`; whether the 1B tokenizer files (which differ from the smaller models) change tokenization; direct tensor-dtype read and parameter-count check once Python is installed; the 512-value gap in the 1B parameter count reported by the Hugging Face API.
- Cluster notes added from public Redhawk and Talon documentation (Redhawk V100 16 GB GPUs, Talon H100 GPUs). Not public: internet access from cluster nodes, storage quotas, Python modules, Talon details. README Section 10 has the new open questions.
- README changes: Phase 2 checkbox ticked; students described as deduped `step143000`; Section 2 and Section 7.2 updated; Section 10 and Section 12 additions as above.

### Phase 3: compute cluster chosen and Redhawk access confirmed
- **Decision: use Redhawk now** for the Phase 3 pilot and baseline evaluation; request Talon (H100) in parallel as the fallback for the 1B student; OSC and local runs not recommended. Full analysis with sources: `docs/cluster_selection.md`.
- Why: Redhawk is the only option with confirmed access. A standard full-fine-tuning recipe for 1B is likely too tight for one 16 GB V100, but that is an estimate; the Phase 3 pilot must measure actual peak memory for all four sizes before choosing sharding, gradient checkpointing, an 8-bit optimizer, LoRA, or a larger GPU. Any change from the shared recipe is a logged deviation.
- Access: Jaxson logged in to `redhawk.hpc.muohio.edu` (user `buggjm`) with password + Duo on 2026-10-01 and confirmed it works. The command output was not captured.
- Created an SSH config entry (`Host redhawk`) and `C:\Users\Buggb\bin\redhawk.cmd` (on the user PATH) so typing `redhawk` logs in. Rebuild steps: `recovery/redhawk_ssh_access.md`. No SSH key yet; Duo is still required on every login, and any exemption is a question for Research Computing.
- Correction: Python 3.11.9 (pip 24.0) is installed on this PC. An earlier note (progress and `docs/model_versions.md`) said Python was not installed; the Windows Store alias had hidden it. PyTorch, Transformers, safetensors and huggingface_hub are not installed.
- README changes: Phase 3 "Confirm cluster access" ticked; Section 10 drops the resolved "which cluster" item and adds the Talon request and the pilot memory measurement.
- Still open: rest of the login probe (quota, partitions and GPU types, modules, outbound internet), Talon access.

### Redhawk probe, first partial result
- Login node `mualhplp02.hpc.miamioh.edu`; `/home` is an NFS share (63 TB total, 51 TB used, 12 TB free, 81% full). A `Stale file handle` NFS error appeared at the start of the probe; the login worked. Recorded in `docs/cluster_selection.md` section 7.

## 2026-10-06

### Workflow restructured around a 1k / 70M end-to-end pilot
- **Decision:** the next step is a small pilot of both the Claude API and the Miami cluster before committing to the full project. The pilot builds the full ~1k benchmark with the Claude API and freezes it, generates about 1k training examples with the Claude API (kept separate from the benchmark), fine-tunes Pythia 70M on Redhawk, then evaluates the untrained and fine-tuned 70M on the benchmark. The teacher is also run once on the benchmark. Plain-language walkthrough: `docs/pilot_plan.md`.
- **Why:** it finds problems and gives real token, cost, GPU-time and queue-time numbers for tens of dollars instead of thousands, and it replaces the desk estimates in `docs/cost_estimate.md`.
- **Phase renumbering:** old Phase 4 (benchmark) is now Phase 3 and runs first, because the pilot needs a frozen benchmark. The old Phase 3 (pilot) is now Phase 4 and is redefined as the end-to-end 1k / 70M run with a go/no-go review. Phases 5 to 13 keep their numbers. **Entries above this one use the old meaning of "Phase 3" (the pilot) and are left unchanged as history.** Updated pilot references in README Section 1, Section 8 and `docs/cost_estimate.md`, `docs/cluster_selection.md`, `docs/teacher_subscription_feasibility.md`.
- **Benchmark size in the pilot:** the full ~1k questions, so it is the real frozen benchmark and is not rebuilt later. Risk noted: a flawed benchmark would be frozen, so the answer-key checks below must be done before freezing.
- **Same-teacher risk and the independence ladder (README Section 9, Phase 3):** the benchmark and training data are both written by Claude, so teacher accuracy on its own benchmark is likely optimistic and answer keys may share its mistakes. A fresh API call has no memory of writing an item (removes anchoring) but is the same model with the same blind spots. Answer keys are checked in layers: run R code and recompute numbers; blind re-solve by a separate call with disagreements reviewed by hand; a different-family model (ChatGPT) on a sample; hand spot-check. Teacher accuracy is reported with the caveat.
- **Reuse rule:** if the pilot 1k training set passes verification it becomes the 1k subset of the nested sets in Phase 6, so it is not paid for twice.

### Rules and cost tracking
- Created `CLAUDE.md` (loaded automatically every session) with the **explain-everything** rule: any document or summary describing a process must explain it in plain language (what, why, how, terms, worked example, what could go wrong). Mirrored in README Section 12.
- Added the **record-every-cost** rule (README Section 12 and `CLAUDE.md`) and created `docs/cost_log.md`, the ledger of every API call with tokens, dollars and a running total, plus a pilot expected-versus-actual table. Expected pilot cost is about $13 to $57 (four runs of 1k items at $3 to $13, plus up to about $3 for replacements).
- **Cost to date: $0.00.** No API calls have been made and no subscription seats bought; teacher selection and the cost estimates were desk research.

### Other work logged for the record (2026-10-04 to 2026-10-06)
- Added `docs/teacher_subscription_feasibility.md`: desk analysis of running teacher generation on a Claude Team subscription (Standard $20 vs Premium $100 seats) instead of the API. Conclusion: feasible as a one-shot throttled run but depends on unpublished limits and a paused policy change, so the API stays the default and the pilot measures real numbers first.
- Looked up Miami funding. The Graduate Student Research Support Award is up to $300 for master's students (deadlines Nov 1 and Mar 1, one-time, advisor endorsement). Internal faculty programs and the new Miami Center for AI list no API or computing credits. Nothing applied for yet.

### Pythia base-model probe (Phase 2 addition)
- **Added** `code/evaluation/pythia_probe.py`: loads the four pinned Pythia checkpoints from `C:\masters_project_large\models\pythia`, checks parameter counts, dtypes and tokenizers, and gives each model 16 mixed questions (general, arithmetic, word problem, logic, definitions, statistics, R code, format) in 3 prompt formats (raw, `Question:/Answer:`, few-shot), greedy decoding, 128 new tokens. Output: `results/pythia_probe/2026-10-07_0015Z_probe.jsonl` (192 generations), `_summary.csv`, `_model_info.json`. Cost $0.00 (local CPU, no API). Write-up and recommendations: `docs/pythia_behavior_analysis.md`.
- **Why:** to learn how base models behave before designing the benchmark and training data. It sits in README Phase 2 (ticked) so the Phase 3 and 4 numbers are unchanged.
- **Environment:** venv `C:\masters_project_large\envs\probe` (Python 3.11.9, torch 2.14.1+cpu, transformers 5.19.0); pins in `environment/requirements.txt`; rebuild steps in `recovery/python_env.md`.
- **Findings:** (1) none of the 192 generations ended with the end-of-text token; all hit the 128-token limit and 183 of 192 repeated; (2) format changes the output style a lot, few-shot gives the shortest first lines but copies example content; (3) 410M and 1B recall simple facts, every size gets arithmetic wrong, statistics definitions are fluent but often wrong, R code is almost never correct; (4) **the 1B config says `eos_token_id: 2`, which is the token `!`, and its tokenizer has no end token** while 70M, 160M and 410M use id 0; (5) parameter counts match the official counts exactly for all four sizes (the 512-value API gap does not appear after loading); (6) stored dtypes: F32 for 70M, 160M, 410M and F16 for 1B, all loaded as `float16` on CPU without errors; (7) eight test strings tokenize identically across all four sizes.
- **Deviation / correction logged:** the first run of the probe stopped on the tokenizer's end token, which is `None` for 1B, so the 1B run was not checked for stops correctly. I fixed the script to look up `<|endoftext|>` by name (id 0) for all sizes, deleted that first run's uncommitted files, and reran everything. The reported data are from the second run. `float16` was kept (no `float32` fallback was needed).
- **Decisions proposed (README Section 10, to confirm in the pilot and with Dr. Lee):** one fixed `Question:/Answer:` template, short answers with a marked final answer, end-of-text id 0 explicitly on every training example, loss on the answer and end token only; a pre-declared evaluation protocol (format, stop rule, max new tokens, greedy); possibly a likelihood-scored multiple-choice slice in the benchmark; keep the benchmark answers short (about 20 tokens) and checkable.
- **Files updated:** README (Phase 2 item ticked, Phase 3 and Phase 4 checklist items, Section 7 results note, Section 10 open decisions), `docs/pilot_plan.md` (new Step 0 and adjustments to Steps 1, 3 and 5), `docs/model_versions.md` (dtype table, load check status, tokenizer result, environment versions, the 1B stop-token finding), `docs/cost_log.md` (a $0.00 row and a savings note), `docs/cost_estimate.md` (new section 7, sensitivity to answer length).
- **Cost to date: $0.00.**

### Phase 3: first Claude API run, the 20-question benchmark trial (2026-10-07)
- **Added** `data/prompts/benchmark_generation_v1.md` (the versioned prompt, reused unchanged for the 1,000-question run), `code/generation/generate_benchmark.py` (blueprint of question slots, one shared request builder, a `trial` command with a hard dollar cap, `submit`/`fetch` for the Batch API, a free `check` command) and `docs/api_console_guide.md` (beginner's walkthrough of the Claude Console, written from Anthropic's docs and not yet checked against the user's own screens). Installed `anthropic==1.11.0` in the probe venv and pinned it in `environment/requirements.txt`.
- **Run:** UTC 2026-10-07, `claude-sonnet-5-5`, effort `medium`, adaptive thinking (API default; it cannot be turned off on this model), sampling at API defaults (not settable on this model), standard (not Batch) calls, `max_tokens` 5000, structured JSON output, 20 separate calls. Dry run first (worst case $1.05, cap $3.00, expected about $0.35). Output: `C:\masters_project_large\data\teacher_outputs\2026-10-07_sonnet-5-5_benchmark-trial01\` with a review copy in `results/benchmark_trial/`. The API key was read from the user's environment variable and never printed or stored.
- **Cost: $0.1279** (28,850 input tokens, 7,017 output tokens). About $0.0064 per question, about a third of the estimate. Forecast for 1,000 questions on Batch: about $3.20. Cost to date: **$0.13**. Recorded in `docs/cost_log.md`.
- **Results:** 20 of 20 replies were valid JSON and passed the format checks (short answers, 4 choices for multiple choice, correct letters rotated A to D, nothing cut off). **Reading the questions found 3 of the 8 numerical answer keys wrong** (BM0005: key 0.8, correct 0.735; BM0013: key 12, code gives 25; BM0020: key 0.272, correct 0.314) and **one R check that did not test the student's answer** (BM0007). The other 17 keys were checked by hand and by recomputation and were correct. Details and explanation: `docs/pilot_plan.md` Step 1.
- **Decisions and next steps:** the same-teacher risk in README Section 9 is now a measured fact, not just a worry, so the independence ladder stays mandatory. Added automatic checks to the script (key versus the last number in its own explanation; an R check must use the variable `candidate`); re-running them on the trial items flagged 3 of the 4 problem items (BM0005, BM0007, BM0013) and missed BM0020, whose explanation itself contained the arithmetic error. Planned: prompt v2 (worked calculation before the key, an R recomputation for every number item), install R, rerun the 20-item trial (about $0.13), set up a dedicated Console workspace with a spend limit before the 1,000-question run. Trial items are discarded; they are not part of the frozen benchmark.
- **Open (to confirm with Dr. Lee):** the benchmark blueprint mix (README Section 10).
- Files updated: README (Phase 3 checklist and Section 10), `docs/pilot_plan.md`, `docs/cost_log.md`, `docs/api_console_guide.md`, `recovery/python_env.md`, new `recovery/benchmark_trial_outputs.md`.

### Phase 3: answer keys now come from running R (prompt v2, `verify`, trial 2, 2026-10-07)
- **Why:** the user asked how to make sure answer keys are correct, after BM0020's key was found wrong. The trial showed that the model's own written explanation can contain the arithmetic slip, so asking the same model to re-read it is not enough. R does not make the model's kind of arithmetic mistake, so the key should be what R computes.
- **R was already installed** (R 4.3.1 at `C:\R-4.3.1`, not on the PATH; the user uses RStudio). I had wrongly listed "install R" as a to-do. Added `rscript: C:\R-4.3.1\bin\Rscript.exe` to `configs/paths.yaml`.
- **Code:** `generate_benchmark.py` gained (1) a `verify` command (free): runs each number item's `r_solution` in R and compares the printed number with the key (tolerance 0.0006), runs each item's `r_check` with the key (must be TRUE) and with three wrong answers (must not be TRUE, otherwise the check is "vacuous"), and writes `*_verified.jsonl`; model-written R code runs in a throwaway folder with a 20 s limit, and code that uses files, the network, system commands or `library()` is refused; (2) two new schema fields placed before the key, `working` and `r_solution`; (3) a `--prompt v1|v2` option (default v2) shared by trial, submit and fetch.
- **Prompt:** `data/prompts/benchmark_generation_v2.md` (v1 untouched). Writes the calculation first, then R code that recomputes the number with R's own functions, then the key; `r_check` must use `candidate`.
- **Free test on the 20 old v1 items:** `verify` flagged BM0007 as vacuous (it accepts the wrong answer `NULL`). R reproduces the true values for the wrong keys: BM0005 = 0.7348 (key said 0.8), BM0020 = 0.3138 (key said 0.272); BM0013 = 25 from the earlier run.
- **Paid trial 2 (v2, same 20 slots):** cost **$0.1765** (35,767 input, 10,492 output tokens; expected $0.15 to $0.25, cap $1.50). Cost to date: **$0.30**, recorded in `docs/cost_log.md`. 20 of 20 parsed. `verify`: 12 ok, 1 flagged, 7 not machine-checkable (multiple choice and conceptual). I read all 20 questions: every numeric key R confirmed matches the question and the code.
- **The one flag, BM0001** (probability of 2 heads in 5 tosses): exact value 0.3125; the key says 0.313 and `r_solution` used `round(..., 3)`, which R rounds to 0.312. Not a wrong key, but it shows `r_solution` must not round. Planned for prompt v3. Another false alarm: the old automatic check flagged BM0020 because the last number in its explanation is the z value 0.553; R shows the key 0.29 is correct. This is why R is more reliable than text heuristics.
- **What this does not prove:** R confirms the key equals what the model's code computes, not that the code answers the question as asked; and 7 of 20 items (multiple choice, conceptual) have nothing to run. Next: prompt v3, a blind re-solve command, a different-family check on the multiple-choice items, and a hand-checked random sample.
- Files updated: README (Phase 3 checklist), `docs/cost_log.md`, `docs/pilot_plan.md`, `recovery/benchmark_trial_outputs.md`, `configs/paths.yaml`, new `data/prompts/benchmark_generation_v2.md`, `results/benchmark_trial/` (trial 2 items, log, verified file).

### Phase 3: prompt v3, rounding rules, and what R still cannot catch (trial 3, 2026-10-07)
- **Why:** trial 2's only flag (BM0001) was a rounding artifact, not a wrong key: the exact value is 0.3125, R's `round(x, 3)` gives 0.312, the key said 0.313. Also BM0005 asked for 3 decimals but its key was `0.74`.
- **Prompt v3** (`data/prompts/benchmark_generation_v3.md`; v1 and v2 untouched): `r_solution` prints the unrounded number; a number question must say how to round; the key is written with exactly that many decimals; `answer_tolerance` must be at least half of the last decimal place (so a tie rounded the other way is accepted).
- **Script (`generate_benchmark.py`):** default prompt is now v3 (`--prompt v1|v2|v3`); `check_item` flags a key whose decimals do not match the question and a tolerance below half the last decimal place (only when decimals are requested; whole-number answers from exact code may have tolerance 0); the "key equals last number in the explanation" text test now runs only for items without `r_solution` (it falsely flagged BM0020 in trial 2, whose key R confirmed); a new check flags question text that thinks aloud (`no:`, `wait`, `hmm`, `... no`); `verify` now also reports these free checks. (I first included `...` as a marker, saw it falsely flag legitimate text such as "X1, ..., Xn", and removed it.)
- **Run:** same 20 slots, `claude-sonnet-5-5`, effort medium, standard calls, cap $1.50 (worst case $1.07, expected $0.15 to $0.22). **Cost $0.1800** (37,675 in, 10,465 out). Cost to date: **$0.48**. Output: `...benchmark-trial03\`, review copy in `results/benchmark_trial/`.
- **Results:** 20 of 20 parsed; `verify`: 12 ok (every number and R-code item), 7 not machine-checkable, 1 flagged. No rounding flags. I re-solved the 7 multiple-choice and conceptual items by hand.
- **The flag, BM0015:** the question text contains a thinking-aloud fragment ("...at least 1 of the 3 economists must be... no: exactly 2 statisticians and 3 economists?"). R and the key are consistent (choose(6,2)*choose(8,3)/choose(14,5) = 0.420), so only the new text check catches it. It is a prompt problem (v4: forbid self-corrections in question text).
- **A wrong multiple-choice key nothing automatic caught, BM0017:** the printed Welch interval is -6.020 to 0.0203 (t = -2.10, df = 17.4, equal group sizes). The question asks about the interval after rerunning with `var.equal = TRUE`. The key (C) says it keeps the same center and standard error "but uses df = 18 so it is slightly wider". R shows the opposite: critical value 2.1061 at df 17.4 versus 2.1009 at df 18, half-widths 3.0088 versus 3.0013, so the pooled interval is slightly **narrower**. No choice is cleanly correct. The other six multiple-choice and conceptual items matched my own working. This is the evidence that the blind re-solve and other-family check are needed for the items R cannot run, and that v4 should require exactly one fully correct choice.
- **Decisions / next:** v4 prompt rules (no self-corrections; exactly one fully correct multiple-choice option); blind re-solve command; other-family check on multiple choice; hand-checked sample. Trial items remain discarded (not part of the frozen benchmark).
- Files updated: README (Phase 3 checklist), `docs/cost_log.md`, `docs/pilot_plan.md`, `recovery/benchmark_trial_outputs.md`, `code/generation/generate_benchmark.py`, new `data/prompts/benchmark_generation_v3.md`, `results/benchmark_trial/` (trial 3 items, log, verified file).
