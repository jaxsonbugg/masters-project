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

### Phase 3: trial 4 refused by the API, prompt v5 without a `working` field, trial 7 (2026-10-07)
- **What happened:** all 20 calls of trial 4 (prompt v4) came back with `stop_reason: "refusal"` and no content. A refusal is a normal HTTP 200 reply, not an error, so the script treated the empty reply as bad JSON and still sent all 20 calls ($0.0867 billed). Anthropic's documentation (Refusals and fallback; Handle streaming refusals) says its safety checks decline prompts that ask the model to put its reasoning in the reply, for example "a `reasoning`, `thinking`, or `trace` field in JSON output". v4 made `working` the first output field and told the model to design the question and judge every answer choice inside it. That is the most likely cause, but the first script did not save `stop_details`, so the refusal category was never recorded and the cause is **not proven**. (An earlier cost-log row stated the category as `reasoning_extraction` as if known; it has been corrected.)
- **Script changes** (`code/generation/generate_benchmark.py`): every call now stores the whole `stop_details` object and the request id; a refusal is reported as a refusal, not parsed as JSON; the run stops at the first refusal, but only after that call's entry and raw reply are saved and the run log is written (the batch `fetch` path records refusals the same way); new prompt version `v5` (default) whose schema has no `working` field; `check_item` accepts v5 items. Also `verify` now allows a key to differ from R's value by half of the key's own last decimal place (it had assumed 3 decimals and falsely flagged BM0008's correct key 0.94 for R's 0.940869; re-running trials 2 and 3 with the fix did not change their results).
- **Prompt v5** (`data/prompts/benchmark_generation_v5.md`; v1 to v4 untouched): started from v3, removed the `working` field and every instruction to write out working, kept `r_solution`, the rounding rules, and v4's content rules (no self-corrections in the question; exactly one fully true choice; consistent printed output), and ended with one plain sentence: "Return only the requested JSON fields. Do not include scratch work, chain-of-thought, design notes, or intermediate reasoning." It deliberately gives no instruction about hidden thinking.
- **A new, unexplained error (trial 5):** the first probe attempt got HTTP 403, `model_access_suspended` ("claude-sonnet-5-5 is suspended for this organization until 2026-10-07T20:42:04Z"), request `req_011CfoViqobCFianU9t3QyB4`. Nothing was billed. Anthropic's error documentation does not describe it. It began after the 20 refused calls and ended at the stated time; whether those are linked is a guess. One probe at 20:48 UTC worked.
- **Results** (same 20 slots in trials 2, 3 and 7; effort medium; one trial per prompt, so differences of one or two items are within noise):

| | v2 (trial 2) | v3 (trial 3) | v5 (trial 7) |
|---|---|---|---|
| Parsed | 20 of 20 | 20 of 20 | 20 of 20 |
| `verify`: ok / flagged / not machine-checkable | 9 / 4 / 7 | 12 / 1 / 7 | 10 / 3 / 7 |
| Wrong number key found by R | 1 (rounding) | 0 | 1 (BM0013) |
| Rounding-rule problems | 3 | 0 | 0 |
| Question text that thinks aloud or is unfinished | 0 | 1 (BM0015) | 2 (BM0015, BM0020) |
| Output tokens per question | 525 | 523 | 398 |
| Cost per question (standard) | $0.0088 | $0.0090 | $0.0081 |

- **What the flags are in trial 7:** BM0013 (an R-output question) has the key 4.867 while R computes 4.25, and the item's own explanation also says 4.25, so the key is simply wrong (the arithmetic slip is in the key field). BM0015 (the same combinations slot as in trial 3) again starts thinking aloud inside the question ("...at least 1 of the 3 biologists must be...") and then gives up, leaving the answer, R code and explanation empty. BM0020 (a graduate normal-probability slot) ends "... no", has `r_solution` `cat(0)`, key 0.000 and explanation "invalid". These two are the kind of failure v4 was meant to prevent by letting the model settle the design first in a written field.
- **What this tells us and what it does not:** without a `working` field the model is accepted by the API and about as accurate on keys as v2, but not clearly better than v3 (v3 had 12 verified keys and one thinking-aloud question, v5 has 10 and two). The two thinking-aloud items are both hard slots that need a conditional or constructed question, which suggests the model needs room to design such questions; that room could come from higher effort (more thinking) instead of a written field. This trial is too small to say whether v5 is worse than v3 or the same. The 7 multiple-choice and conceptual items per trial still need the blind re-solve and other-family checks; I have not re-solved trial 7's by hand.
- **Decisions / next:** (1) decide with the project owner whether to try effort `high` with v5 on the same 20 slots (cost about $0.25 to $0.40), or to rewrite the two hard slot types; (2) write the blind re-solve command; (3) hand-check trial 7's multiple-choice items. Trial items remain discarded.
- Files updated: `code/generation/generate_benchmark.py`, `docs/cost_log.md`, new `data/prompts/benchmark_generation_v4.md` and `v5.md`, `results/benchmark_trial/` (trials 4 to 7 logs and items).

### Phase 3: prompt v6, answer keys from R, automatic regeneration, trial 8 (2026-10-14/15)
- **Why:** trial 7 (v5, no `working` field) showed that without a place to calculate, the model typed a wrong number key (BM0013: typed 4.867, its own code and explanation give 4.25) and twice trailed off in the question text. v3 had been the best prompt but still had a thinking-aloud question (BM0015) and a multiple-choice question with no correct option (BM0017). The decision was to return to v3 (the `working` field stays AFTER the question; v3 already had that order and was never refused), add three content rules, take number keys from R, and regenerate failed items.
- **Prompt v6** (`data/prompts/benchmark_generation_v6.md`; v1 to v5 untouched): v3 plus (2a) the question field is final text only, with no self-corrections or trailing "..."; (8) multiple choice has exactly one fully true choice, every clause of it true, no wrong choice partly right; (8a) software output printed in a question must be internally consistent. v4's sentence telling the model to judge every choice true or false inside `working` was NOT carried over, because reasoning written into the reply is the likely cause of the v4 refusal.
- **R writes the number key** (`apply_r_key` in `code/generation/generate_benchmark.py`): the script runs the model's `r_solution`, rounds R's number the way the question says (halves rounded up, on R's printed digits, so 0.3125 to 3 places is 0.313), and uses that as `canonical_answer`. The model's typed key is kept as `model_canonical_answer` and R's unrounded number as `r_value`. If the typed key differs from R's value the item gets a **soft flag** (keep it, but look at it). A disagreement does not trigger regeneration on purpose: regenerating on it would quietly remove questions whose arithmetic is hard to do in one's head and make the benchmark easier than intended, and the key is R's anyway. R fixes slips of arithmetic and typing; it cannot notice code that answers a different question than the one written.
- **Regeneration** (`run_attempts`): a question with a **hard problem** (invalid JSON, cut off, any failed format check, no usable R number, no stated rounding rule, a question that trails off with "...", an empty or placeholder explanation) is asked for again with the same prompt, up to 3 attempts in all. The retry does not tell the model what was wrong, so the first-attempt pass rate stays an honest measure of the prompt. Every attempt's reply is saved and failed attempts are written to `rejected_attempts.jsonl`. A refusal is not retried: the run stops after saving that call's log entry (with the whole `stop_details`), because refusals repeat.
- **Other script changes:** `process_reply` is the one path for checking a reply (used by trial, fetch and the new free `replay` command, which re-runs the checks on saved API replies); `fetch --retry-failed` regenerates failed or missing questions from a Batch run with standard calls; `--effort` option so a high-effort trial needs no code edit; each call logs `content_blocks` (whether the model produced a thinking block); the script finds R before spending any money; `verify` prints the soft flags; the cost cap still covers retries because it is checked before every call.
- **Tests before spending (free):** `replay` on trial 7: BM0013 becomes key 4.250 with a soft flag, BM0008 stays 0.94, BM0015 and BM0020 fail as expected. `replay` on trial 3: only BM0015 fails, no keys change. A fake-client test of the retry loop covered a retry that succeeds, three failed attempts, a refusal (stops, writes the log entry first, no retry), the cost cap and attempt numbering (19 checks, all passed), plus the rounding function on ties, negative zero and exponent notation. The real retry path was **not** exercised live because nothing failed.
- **Run:** same 20 slots, `claude-sonnet-5-5`, effort medium, standard calls. Probe $0.0070 then trial **$0.1885** (41,575 in, 10,531 out). Cost to date: **$0.94**. Output: `...2026-10-15_sonnet-5-5_benchmark-trial02\`, review copies in `results/benchmark_trial/`.
- **Results** (one trial per prompt, so one or two items is within noise; this trial changed the prompt and the script together, so it cannot say which change helped):

| | v2 (trial 2) | v3 (trial 3) | v5 (trial 7) | v6 + R key + regeneration (trial 8) |
|---|---|---|---|---|
| Usable after checks | 16 of 20 | 19 of 20 | 17 of 20 | 20 of 20 (all on the first attempt) |
| `verify`: ok / flagged / not machine-checkable | 9 / 4 / 7 | 12 / 1 / 7 | 10 / 3 / 7 | 13 / 0 / 7 |
| Number key disagreed with R | 1 (rounding) | 0 | 1 (BM0013) | 0 of 8 |
| Question thinks aloud or trails off | 0 | 1 | 2 | 0 |
| Output tokens per question | 525 | 523 | 398 | 527 |
| Cost per question (standard) | $0.0088 | $0.0090 | $0.0081 | $0.0094 |

- **Hand check of the 7 multiple-choice and conceptual items** (the ones R cannot test): all 7 keys are correct. BM0002 (p-value), BM0006 (lowering alpha raises Type II error), BM0010 (summary shows right skew), BM0011 (R-squared equals the squared correlation), BM0016 (S2 unbiased, V biased down with smaller variance for normal data) and BM0017 (reversing a paired t-test negates and swaps the interval, p unchanged) match my own working. BM0004's key B is right, but the printed output is not fully consistent: with t = 2.50, df = 15 and mean 44 the 95% interval is 40.59 to 47.41, not the printed 40.8 to 47.2 (R). BM0017's printed p-value and interval are also slightly off the exact values (0.02951 and 0.287 to 4.513 against the printed 0.02955 and 0.3000 to 4.5000), which does not change its key. Rule 8a asks for consistency and the model only partly follows it; no automatic check exists for this. **Limit of this check:** I am a Claude model too, so a hand check by me shares some blind spots with the generator; the blind re-solve with another model family is the independent check.
- **The 8 number questions:** I re-derived BM0001 (15/64 = 0.234375, written 0.234), BM0013 (6.5), BM0019 (24) and BM0020 (0.746) by hand, and each R program answers the question as written. All 8 typed keys already matched R after rounding, so R-as-key changed nothing this time, but it would have fixed trial 7's BM0013.
- **What this tells us and what it does not:** this is the cleanest trial so far (20 of 20 usable, no flags), which matches the aim of the changes, but it is one 20-question run. The regeneration and soft-flag paths never fired live. Items were also easier in places: BM0015 (the slot that failed in trials 3 and 7) became "at least 2 statisticians" instead of a conditional question. Two things are still unknown: whether the failure rate stays this low over 100 or 1,000 questions, and whether R's code answers the intended question in the cases a human did not re-derive.
- **Decisions / next:** (1) a 100-question run (Batch, about $0.50) to measure the failure and soft-flag rates and exercise `fetch --retry-failed` before the full 1,000; (2) blind re-solve with a model from another family for multiple-choice and conceptual items; (3) add an automatic consistency check for printed software output if hand review keeps finding it. Trial items remain discarded (not part of the frozen benchmark).
- Files updated: `code/generation/generate_benchmark.py`, `docs/cost_log.md`, `recovery/benchmark_trial_outputs.md`, README, new `data/prompts/benchmark_generation_v6.md`, `results/benchmark_trial/` (the 2026-10-15 trial 1 and 2 items, logs, verified file, and rejected attempts if any).

### Phase 3: the 100-question batch (BM0021 to BM0120), how often problems arise (2026-10-15)
- **What it is and why:** the 20-question pilot (trial 8) was clean but small, so 100 more questions were generated with exactly the same settings (`claude-sonnet-5-5`, effort medium, prompt v6, number keys from R, up to 3 attempts) through the **Batch API** (half price; requests are queued and answered within minutes to hours). The aim was to measure how often each kind of problem appears, not to build the benchmark: these 100 are treated as trial items, not as frozen benchmark questions.
- **Which questions:** the slot list repeats a 20-slot pattern, so slots BM0021 to BM0120 have exactly the pilot's mix: 30% numerical, 20% conceptual, 20% R generation, 15% R interpretation, 15% output interpretation; 40/35/25% intro/intermediate/graduate; 35 multiple choice, 40 number, 20 R expression, 5 short text. None of the pilot's slots (BM0001 to BM0020) were reused. (Slots, not question text, were separated; see the duplicate finding below.)
- **New in the script:** `--start N` (so `--start 21 --n 100` means BM0021 to BM0120), a free `dupcheck` command that compares a new question with earlier ones using text similarity (difflib; a score near 1 means near-identical text), and `fetch` now copies its results into `results/benchmark_trial/` and prints the first-attempt pass rate.
- **Run:** a 2-question test batch first ($0.0083; proved the Batch request format and `fetch` work), then the 100: 100 of 100 requests succeeded, no refusals, no API errors, every reply ended normally. Batch cost **$0.4681** plus **$0.0268** for 3 standard-price regeneration calls (the regeneration path ran live for the first time and worked). Total **$0.4949**, about $0.0049 per usable question; cumulative spend **$1.44**. 5 of 100 first replies contained a thinking block.
- **Results, by kind of problem** (counts out of 100 unless stated; with 100 items, 0 events means the true rate is probably under about 3%, and 2 events means roughly 0.2% to 7%):

| Kind of problem | Count | What it was |
|---|---|---|
| Question rejected by the automatic checks on the first attempt | 2 | BM0056 and BM0063. **Both were false alarms**: BM0056 was rejected because the word "wait" appears in "customers wait at a clinic"; BM0063 because an R-template question ends with `cv <- function(x) ...`, where the ellipsis means "write the body". Regenerating cost $0.0268. |
| Flawed question that **passed** the automatic checks | 2 | BM0047: the question text changes its mind midway ("Actually, to keep it simple, consider this version instead...") and shows two versions of the code. BM0078: the question spells out its own answer (`rep(c(1,2,3,4,3,2,1), times = c(3,2,1,4,2,2,3))`), breaking the rule that the answer must not be in the question. |
| Number key typed by the model differs from R (soft flag) | 1 of 40 number items | BM0028: the model typed 207.01 for Var(Y); R gives 207.0202, so the key is 207.02. I recomputed it by hand (Y takes the values 5, 6, 13, 26, 45; the weights are 1, 4, 9, 16, 25 over 55) and R is right. With the typed key, a student answering 207.02 would have been marked wrong (the tolerance is 0.005). This is the problem R-written keys exist to prevent, and it happened once in 40. |
| Number question where R's code answers a different question than written | 0 of 40 | I checked every one of the 40 number items (30 numerical, 10 R-interpretation) by reading the question against the code, and recomputed several by hand (for example BM0053 = 19, BM0060 = P(Binomial(5, 0.4) = 2) = 0.346, BM0120 = P(Binomial(7, 1/3) = 2) = 0.307). |
| Wrong multiple-choice key | 0 of 35 | All 20 conceptual and 15 output-interpretation items checked by hand. (0 of 35 here plus 0 of 7 in the pilot.) |
| R-expression and short-text items | 0 of 25 wrong keys | The automatic test (the key passes its own check, nonsense answers fail it) passed for 23; the other 2 (BM0039, BM0079) I checked by hand. The two flawed items above (BM0047, BM0078) are among these 25: their keys are fine but the question text is not. |
| Printed software output that is not quite consistent (output-interpretation items) | 4 of 15, plus 1 deliberate | By R recomputation: BM0050's interval is printed 1.2417 to 7.0916 where t and the mean difference give 1.2666 to 7.0668; BM0090's is 40.60 to 47.40 where 40.56 to 47.44 is right; BM0070 prints p = 0.0215 where F = 4 on 3 and 20 df gives 0.0221; BM0110 prints a slope p-value of 1.2e-07 where t = 7 on 23 df gives 3.9e-07. BM0057 shows a correlation matrix that cannot exist (determinant -1.42), but that is the point of the question. **None of these changes a key**, because each conclusion rests on the 5% level or on the structure of the output, not on the last digits. With the pilot's BM0004 and BM0017, that is 6 of 18 output-interpretation items with small inconsistencies. Rule 8a asks for consistency; the model follows it only partly, and nothing checks it automatically. |
| Duplicates (see below) | 1 pilot duplicate, 7 pilot-template matches, 2 identical pairs inside the batch | |

- **The duplicate finding, which is the most important result.** The text-similarity check compared each question with the pilot (and with all earlier trial drafts of slots 1 to 20). Findings: **BM0107 is a true duplicate of pilot question BM0007** (identical code `mean(scores, na.omit = TRUE)` and identical answer). **7 more questions use the same template as a pilot question with different numbers** (for example BM0072 is the pilot's standard-error question with n = 36 instead of 25, and BM0119 reuses the pilot's famous `x <- c(4, 8, 15, 16, 23, 42)` vector); four conceptual questions repeat the concept of a pilot question (BM0091 p-value, BM0096 Type I and Type II errors, BM0102 R-squared, BM0106 bias and variance). **Inside the batch itself, BM0032 and BM0092 are the same question and BM0035 and BM0095 are the same question** (identical wording and numbers), and 6 more pairs share a template (BM0028/0088, BM0041/0101, BM0048/0108, BM0052/0112, BM0060/0120, BM0087/0099). Every repeated pair is exactly 60 slots apart (or 90 or 100). **Why:** the model, given the same category, subtopic and difficulty, writes nearly the same question again (calibration on trials 1 to 8: the same slot written by different trials scored 0.80 or higher on template similarity in about half the cases, and BM0012 scored 1.00). And the slot design repeats those combinations: in the first 120 slots 24 slots (20%) reuse an earlier slot's combination of category, subtopic and difficulty; in the full 1,000 there are **only 138 distinct combinations for 1,000 slots, so 86% of slots would repeat one, up to 17 times** (77 subtopic pairs, about 13 questions per subtopic). At that rate a 1,000-question benchmark made with the current slot design and prompt would contain large numbers of near-copies. **This has to be solved before the 1,000-question run** (options: build slots so that no combination repeats, add a variety instruction or per-slot scenario/number seed to the prompt, run `dupcheck` on the whole set and regenerate duplicates, or all three).
- **Checks changed after seeing the data (so a clean replay is not independent evidence):** the word "wait" now counts as thinking aloud only as an interjection ("Wait, ..."); phrases such as "Actually," at the start of a sentence, "to keep it simple", "on second thought" and "scratch that" now count; a trailing "..." is allowed after code (`)`, `(`, `{`, `,`, `=`, `<-`); and a new check fails an R-expression or short-text question that contains its own answer key verbatim. Replaying the 103 saved replies of this batch through the new checks gives exactly BM0047 and BM0078 as hard failures and no false alarms; replays of trials 8, 3 and 7 are unchanged. BM0047 and BM0078 are still in this batch's `items.jsonl`, marked as passing, because they were not regenerated; treat them as flawed.
- **What this tells us:** the pipeline (Batch submit, fetch, R keys, regeneration, `dupcheck`) works end to end for about $5 per 1,000 questions; keys were correct in every item I could check (0 of 100 wrong keys found, 1 typed-key slip caught by R); genuine text flaws are rare (2 of 100) but were not all caught by the automatic checks, and the checks also raised 2 false alarms, so they needed tuning in both directions; printed-output inconsistencies are common in output-interpretation items (about a third) but do not change keys; duplication is the real threat to scaling. **What it does not tell us:** my hand check was done by a Claude model, so it shares some blind spots with the generator (the blind re-solve by another model family is still the independent check); 100 questions give wide error bars; BM0021 to BM0120 are all written by one prompt in one run.
- **Decisions / next:** (1) fix the slot design and add variety before any 1,000 run, then re-run `dupcheck` (the most important step); (2) decide whether to build the per-test consistency checker or the "R generates the printout" design for output-interpretation items (about a third show small inconsistencies; keys unaffected so far); (3) blind re-solve by another model family for multiple-choice and conceptual items; (4) regenerate BM0047, BM0078, BM0107 and the duplicate pairs if any of these 100 are kept.
- Files updated: `code/generation/generate_benchmark.py`, `docs/cost_log.md`, `recovery/benchmark_trial_outputs.md`, README, `results/benchmark_trial/` (batch01 and batch02 items, logs, rejected attempts, verified file).

## 2026-11-03

### Open-weight teacher alternatives evaluated (desk research, no spend)
- **Why:** Jaxson has asked Anthropic support whether Claude outputs may be used to train the Pythia students (the Commercial Terms bar using the service "to train competing AI models"; see `docs/teacher_subscription_feasibility.md` Section 1.4). A "no" looks increasingly likely, so a replacement **open-weight** teacher (a model whose weights are published and can be run anywhere) was researched in advance. No teacher switch is decided yet; that waits for Anthropic's answer.
- **What was done:** evaluated the six models Jaxson listed (DeepSeek-R1 671B, Qwen3-32B, DeepSeek-R1-Distill-Qwen-32B, Mistral Small 3.1 24B, OLMo 3 32B Think, Qwen3-8B) plus newer open-weight releases, on: license terms for training other models on outputs (treated as a gate, per Jaxson's preference for clear distillation permission), math/science/code quality, fit with our existing prompts and Claude-API features (JSON schema, effort, Batch), hosted API cost for 50k examples, Redhawk feasibility, and reproducibility. Full analysis with sources: `docs/teacher_model_evaluations.md`.
- **Recommendation (pending a small test):** first choice **Qwen3.6-27B** (Apache 2.0; fits Redhawk at 4-bit if the old software supports it; about $64 to $421 for 50k hosted); runner-up **DeepSeek V4-Flash** (MIT, and DeepSeek's API terms explicitly allow distillation; about $7 to $80 for 50k; hosted only); third **gpt-oss-120b** (Apache 2.0; about $5 to $80; needs an H100). Best of the original six: **Qwen3-32B**. Ruled out: DeepSeek-R1 (retired from most APIs, too big, verbose), R1-Distill-Qwen-32B (dominated by Qwen3-32B), Mistral Small 3.1 (no reasoning, too weak), OLMo 3.x (weaker, no hosting; kept as a "fully open" option), Qwen3-8B (too small), Gemma 3 and Llama 4 (license conditions on models trained with their outputs).
- **Surprising findings to keep in mind:** (1) current vLLM (0.20 and later) dropped V100 support, so Redhawk would need vLLM 0.18 or earlier, or llama.cpp, built with CUDA 12.x; (2) an 8B model at FP16 does not fit on one 16 GB V100; (3) Fireworks' terms may forbid using outputs for AI training, so avoid it without written confirmation; (4) OSC offers Ohio faculty a $1,000 yearly credit at a listed $0.09 per GPU-hour, a possible H100 route through Dr. Lee.
- **Next:** wait for Anthropic; ask the same support thread whether the Claude-written *benchmark* is affected; if a switch is needed, run the small shortlist test in `docs/teacher_model_evaluations.md` Section 11 (expected under $2, to be logged in `docs/cost_log.md`).
- Files: new `docs/teacher_model_evaluations.md`; README Section 2 and Section 10 notes.

## 2026-11-04

### Qwen3.6-27B deployment test: local preparation only (nothing run on Redhawk, no paid call, $0.00)
- **Why:** if Anthropic does not allow Claude outputs for training, `docs/teacher_model_evaluations.md` recommends Qwen3.6-27B as the open-weight teacher. A pilot will run the same 100 prompt slots (BM0021-BM0120, the slots Sonnet 5.5 answered on 2026-10-15) on two deployments: a 4-bit file on Redhawk (free) and, once Talon access exists, full-precision BF16 weights on Talon (free). It is a comparison of two deployments, not a controlled test of quantization.
- **What was written (all local, uncommitted):**
  - `code/generation/open_teacher_test.py`: reuses the v6 prompt, slots, schema and checks from `generate_benchmark.py` unchanged; appends the schema text to the system message because these backends do not enforce it (no constrained decoding in either run); one attempt per slot. Commands: `run`, `validate`, `score`, `compare`.
  - **Development slots:** smoke tests use BM9001-BM9004 only, never BM0021-BM0120, so the main experiment keeps one attempt per slot.
  - **Validation is mandatory after every stage** and separates INFRASTRUCTURE failures (missing files, bad metadata, duplicate or missing slots, incomplete run; the stage fails) from MODEL-QUALITY findings (invalid JSON, truncation, wrong fields; reported as results, the stage still passes).
  - **Resume safety:** append-only saves, lock file, identical-settings check, finished slots never re-sent, errored slots re-sent only with an explicit flag, a second main folder refused.
  - `configs/redhawk/`: `probe_cluster.sh` (read-only), `fetch_source.sh`, `fetch_weights.sh` (checks free space and quota, refuses the home folder by default, verifies SHA-256), `build_llamacpp.sbatch`, `serve_and_run.sh`, `gpu_smoke_a.sbatch`, `gpu_smoke_b.sbatch`, `qwen_test.sbatch`. Redhawk paths in `configs/paths.yaml` are UNSET until the storage check; `.gitattributes` keeps Unix line endings for these scripts.
- **Pins recorded:** llama.cpp tag b11960 (commit 8642541b...), `unsloth/Qwen3.6-27B-GGUF` @ 82d411ac... (Q4_K_M, SHA-256 5ed60d0a...), Qwen chat template @ 6a9e13bd... Read-only lookups confirmed that b11960 defines the `qwen35` architecture and lists every llama-server flag used. Not confirmed: that its flash-attention code works on V100 (the only V100 evidence used a different commit plus a patch).
- **Local tests passed (kept in `code/tests/qwen_deployment_test/`, with a README; they clean up after themselves):** 46 Python checks (fake server: slot isolation, both failure categories, resume safety, 8 calls at once with no repeats, scoring through R and `verify`), 35 shell checks (job scripts with fake nvidia-smi, scontrol and llama-server: every gate and prerequisite), ShellCheck clean, memory-summary parser verified on sample data. The tests found and fixed five bugs before any cluster use.
- **Still to do (needs Jaxson's approval step by step):** cluster probe, file transfer, downloads, build, GPU smoke tests, main run; `recovery/redhawk_qwen_test.md`, the evaluation doc.

### Redhawk probe run (read-only) and the fixes it forced (2026-11-04, still $0, no job submitted)
- **What was done:** Jaxson ran the read-only `probe_cluster.sh` on a login node. The first run stopped early because the `quota` command swallowed the rest of the script (the script is sent on standard input); the probe was rewritten so no command can do that (all of it runs inside a function with standard input closed) and a second, complete run was made. The follow-up `probe_cluster_part2.sh` is written but not yet run. Findings and their meaning: `docs/cluster_selection.md` Section 7.
- **Fixes made because of the findings:** job scripts no longer use `--gres=gpu:2` (this cluster has no GPU resources defined) and take a whole node with `--nodes=1 --exclusive --exclude=mualhpcp50.mpi`; Python is called by full path (`/software/python/anaconda3-2023-python3.10/bin/python`, to be verified) because loading a Python module does not change `python`; verified module names are the defaults (`cuda-12.2`, `gcc-12.2.0`, `cmake-3.31.2`); the scripts define the `module` command themselves when a batch shell lacks it; the `sacct` hint was removed (accounting is off); Redhawk paths were set to `/home/buggjm/masters_project` (quota 480 GB, 60 KB used; `/scratch` has an unknown purge policy).
- **A test of the test:** my first check of the new probe built its fake-command folder with a `C:/` path, which splits at the colon in `PATH`, so the fakes were never used and the check passed without testing anything. It was redone with a valid path and now also runs the OLD probe against the same stubs as a control, which reproduces the real failure (the old script loses its end) while both new probes finish.
- **Schedule risk recorded:** all four V100 nodes were busy with 21 jobs waiting, so each separate Slurm job (smoke A, smoke B, main) can wait in the queue; running them as one job is an option to decide with Jaxson.

### Follow-up probe result (2026-11-04, read-only, still $0)
- `probe_cluster_part2.sh` completed. Verified: the Anaconda Python 3.10.9 at `/software/python/anaconda3-2023-python3.10/bin/python` is usable (venv, ssl, pyyaml, pip); the weights URL and the chat template are reachable from the login node and the weights file reports exactly the pinned size (16,817,244,384 bytes); git 1.8.3.1 reaches GitHub and tag b11960 resolves to the pinned commit; the `module` command is a function that a non-login batch shell must define itself (the scripts do).
- **Queue finding:** all four V100 nodes are busy until about 22 hours after the probe at the earliest; 21 waiting jobs are held by a per-user CPU cap (`QOSMaxCpuPerUserLimit`), so they are one user's backlog, not competition for a free node. Consequence recorded in `docs/cluster_selection.md` Section 7: no Redhawk GPU result is possible "by morning", and three separate jobs (smoke A, smoke B, main) would each have to queue again. Decisions pending with Jaxson: a single pipeline job instead of three, the `sbatch --test-only` check.

### The one-job pipeline built (2026-11-04, local only, still $0)
- **Why:** the probes showed all four V100 nodes busy for about another 22 hours with a backlog behind them, so three separate Slurm jobs (smoke A, smoke B, main) would each wait in the queue again. Jaxson chose one job.
- **What:** `configs/redhawk/qwen_pipeline.sbatch` (one whole GPU node, 24 hours) runs Stage A, then Stage B, then the main run, calling `serve_and_run.sh` for each so every check, gate and mandatory validation is reused. Rules: if Stage A crashes in flash attention while the setting is `auto`, it is retried once with flash attention off (decided by Jaxson) and B and main use off too; an explicit setting is never overridden; every Stage A reply being a model-quality finding stops the pipeline unless `QT_ACK_QUALITY=yes`; Stage B only if Stage A left 3 GB free per GPU, otherwise (or if B fails on infrastructure) the main run uses the tested one-sequence setting; the main run does not start with under 6 hours left (the stage-only `qwen_test.sbatch` resumes or starts it later); a summary file records every decision and is also written on SIGTERM.
- **Also changed:** `serve_and_run.sh` names its logs by job, stage and attempt (three stages in one Slurm job would have overwritten each other's logs); `common.sh` has a tested Slurm time-left parser (`10#` guards against leading-zero octal errors); `qwen_test.sbatch` is now the "resume or start the main run alone" job.
- **Tests:** new `shtest.sh` parts 3 and 4 cover the pipeline paths listed in `code/tests/qwen_deployment_test/README.md`.

### Test-only scheduler check result (2026-11-04, still $0; no job was created)
- Jaxson ran `probe_cluster_part2.sh` with `PROBE_SBATCH_TEST=yes` (after reconnecting through the Miami VPN: SSH to the cluster times out from a non-campus network; port 22 was the only blocked port).
- **Result:** the 24-hour whole-node pipeline request is accepted (per-user cap 168 CPUs; `--gres` rejected as expected) but the scheduler's estimated start is **2026-11-17 15:33 UTC, about 13 days out**, the same for 1, 12 and 24 hours. Cause: first-come-first-served scheduling with 21 earlier jobs waiting on half-node slots, so no node becomes entirely empty sooner. Details and caveats in `docs/cluster_selection.md` Section 7.
- **Decisions pending with Jaxson:** whether to continue with the Redhawk preparation and submit anyway (holding a queue position); whether to email rescomp@miamioh.edu about the queue, how GPU jobs are meant to be requested without GRES, and Talon (H100) access.

### Preparation and submission scripts built; a flawed check found and fixed (2026-11-04, still $0)
- **Decision:** Jaxson approved finishing the Redhawk preparation and submitting the pipeline now, to take a place in the queue (the scheduler is first-come-first-served and estimated a start about 13 days out). Talon (H100) access is being pursued in parallel by email (see below).
- **Built (local, tested):** `configs/redhawk/prep_cluster.sh` does the whole login-node preparation in one command (checks the copied files and the prompt hash, clones llama.cpp at the pinned commit, submits the compile job, starts the 17 GB download in the background) so only one password + Duo login is needed; `configs/redhawk/submit_pipeline.sh` re-checks that the build and the weights are really done, shows the scheduler's estimate, and submits the pipeline only then. `shtest.sh` part 5 covers both (21 checks); parts 1-4 were rerun.
- **A flawed check, found and fixed:** the "no carriage returns" checks I reported earlier used `grep -c $''`, which in Git Bash does not detect carriage returns (it returned 0 for a file that really had them). Every earlier "0" was therefore meaningless. The files were re-counted with `tr -cd '' | wc -c`, which counts the bytes themselves: all scripts and tests under `configs/redhawk/` and `code/tests/` have 0 carriage returns, so nothing pushed was broken. The one file with Windows line endings is the older `generate_benchmark.py`, which Python reads without trouble. The prep script now uses the `tr` count and checks only shell scripts. I also caught my own repair script inserting a real carriage-return byte into that check; fixed and verified byte by byte.
- **Talon findings (Miami pages, read 2026-11-04):** Talon has four GPU nodes with four H100 GPUs each. Faculty can request accounts directly and sponsor student accounts through the Research Cluster Account Sponsorships page ("Request New Sponsorship", a faculty sponsor is required; approval time not stated). Questions go to ResComp@MiamiOH.edu; Jens Mueller, Director of High Performance Computing Services (muellej@miamioh.edu), is the contact for additional capacity. No Talon-specific request steps or GPU-hour limits are published.

### First Redhawk compile failed; cause found and fixed (2026-11-04, still $0)
- **What happened:** the prep ran correctly (files intact, llama.cpp cloned at the pinned commit, build job 2510636 submitted, 17 GB weights downloaded and verified: 16,817,244,384 bytes, SHA-256 matches). The compile failed: `ggml-cpu.c: fatal error: stdatomic.h: No such file or directory`.
- **Cause (from the build log):** "The C compiler identification is GNU 4.8.5" while the C++ compiler was gcc 12.2.0. CMake looks for a C compiler named `cc`; the `gcc-12.2.0` module provides `gcc` and `g++` but no `cc`, so CMake silently used the system `/usr/bin/cc` (gcc 4.8.5, 2015), which lacks C11 `<stdatomic.h>`. The GPU part had built fine. The log also warned about clock skew on the shared file system.
- **Fix:** `build_llamacpp.sbatch` now names the compilers (`-DCMAKE_C_COMPILER`, `-DCMAKE_CXX_COMPILER`, `-DCMAKE_CUDA_HOST_COMPILER`), refuses to build unless both report gcc 12.2, wipes the build folder first (a failed one remembers its compiler), and checks CMake's cache to prove the compiler it kept. New `rebuild_llamacpp.sh` resubmits only the compile job and records the new job number so `submit_pipeline.sh` follows it. Tests (part 5, now 31 checks) include the exact failure: an old gcc is refused before CMake runs, and a CMake that substitutes the old `cc` is refused before compiling.
- **Lesson:** a compile error on the cluster costs a queue wait; the toolchain check now happens in the first seconds of the job, with a clear message, instead of after the GPU kernels have compiled.

### The rebuilt llama.cpp is good; the check that rejected it was wrong (2026-11-04, still $0)
- **Result of the rebuild (job 2510641):** the compiler fix worked (gcc 12.2.0 for C and C++, kept by CMake) and the build produced every library, including the 198 MB GPU library. The job still ended with an error because its final flag check printed all 13 flags as "missing".
- **Cause (confirmed by running the binary on the login node):** `llama-server` is linked to the NVIDIA driver library `libcuda.so.1`, which exists only on GPU nodes. On a node without it the program cannot start ("error while loading shared libraries: libcuda.so.1"), so `--help` printed nothing and every flag looked missing. With the CUDA toolkit's stub `libcuda.so` on the library path for that one call, `--help` works. Separately, with the system's libstdc++ the binary reports `GLIBCXX_3.4.30 not found`; loading the gcc-12.2.0 and cuda-12.2 modules clears all of those, so the only thing missing off a GPU node is the driver. At run time on a GPU node the job loads both modules and the node supplies the driver.
- **Fixes:** `run_llama` and `check_flags` in `common.sh` retry with the stub only when that exact error appears, and a failure now shows the program's own first lines instead of just a list of missing flags; `serve_and_run.sh` checks with `ldd` right after the flag check that no library is unresolved on the GPU node (so a module or driver problem fails in seconds, not after loading 17 GB); new `verify_build.sh` verifies the EXISTING build without recompiling and records the pinned commit and SHA-256 of the binary and the GPU library in `build_verified.txt`; `submit_pipeline.sh` accepts that record for this exact binary (a changed binary invalidates it) and loads the modules before its own check.
- **Tests:** `shtest.sh` part 5 is now 39 checks (a fake `llama-server` that refuses to start without a driver library, like the real one; the stub fallback; the failure message; verification record; submit acceptance; invalidation when the binary changes). A mistake of mine while running them: passing the work folder in `C:/...` form puts a colon in `PATH` and makes every fake command invisible, so the failures that run looked catastrophic but were caused by the invocation; rerun correctly it passed.

### Pipeline job 2510690 stopped at Stage A on my own log check; replaced by a memory check (2026-11-05, still $0)
- **What happened:** the pipeline job started on mualhpcp38 (about 09:33) and ran 84 seconds. Everything real worked: the node's driver and libraries were found, the 17 GB weights re-hashed correctly, `llama-server` started, loaded the model (the log says "model loaded" and "listening") and was ready after about 8 seconds. Then the script stopped with `FAIL_INFRA` (exit 3) before sending any question. No questions, no cost, no cluster fault.
- **Cause (confirmed from the server log and the memory samples):** after the load, `serve_and_run.sh` searched the server log for the text `arch = qwen35` and for `CUDA0` and `CUDA1`. The pinned llama.cpp build (b11960) prints a short timestamped log (10 lines in all) that contains none of these; I had assumed an older log format. So that check could never have passed on this build. I had listed it as a risk earlier ("log-format check") but had not tested it against the real log, only against my own fake server, which printed the lines the check wanted.
- **Evidence that the model really was on both GPUs:** `nvidia-smi` samples taken as the model finished loading: GPU 0 held 8,790 MiB and GPU 1 held 9,226 MiB (about 18 GB together, matching the 16.8 GB weights plus buffers, split roughly evenly as `-ts 1,1` asks).
- **Fix:** the log-wording check is gone. `common.sh` has a new `gpus_hold_model` that reads the latest memory sample of each GPU from the monitor's CSV and passes only if exactly 2 GPUs were sampled and each has at least 4,096 MiB in use (a half of the weights is about 8 GB; an idle card shows 0 to 300 MiB). It runs 6 seconds after the server reports ready. The architecture and device lines are still printed when a build has them, but only as information, never as a pass/fail test. The person-only bypass `QT_SKIP_LOGCHECK` was removed because the check no longer depends on anyone reading a log. The other places that read the server log (the crash words that trigger the flash-attention retry, and the error count) only fail when bad text appears, so a quiet log cannot stop a job.
- **Tests:** the fake `llama-server` now prints the real b11960 log (no architecture or CUDA lines). `shtest.sh` part 1 has 4 new checks (31 in all): the model on only one GPU stops Stage A with exit 3; Stage A passes with the quiet log; the real readings of job 2510690 pass the function; a CSV with one GPU fails it. All five parts pass (31, 10, 11, 10, 39); scripts have 0 carriage returns and pass `bash -n`.
- **Lesson:** a test double must print what the real program prints. The fake server had been written to satisfy the check, so the check and the fake agreed with each other and neither matched the real build. Next time any check of real output is first compared with a real sample (a 20-second `--help` or load run) before it is allowed to stop a queued job.
- **Next:** copy the updated scripts to Redhawk and resubmit the pipeline (needs approval; a new queue wait).

### Talon infrastructure prepared in advance, as drafts (2026-11-05, still $0, no cluster access)
- **Why:** a Miami Talon account (4 GPU nodes x 4 H100) now looks likely, and the 200,000-example generation that is part of the project cannot run on Redhawk. Talon is in maintenance and there is no account yet, so only local work was done: no login, no job, no download, no paid call.
- **Research (read-only):** Miami publishes the hardware but not the login host, partitions, GPU request syntax, modules, storage, internet access from nodes, pricing, allocation or quotas; all of those are marked UNVERIFIED everywhere. Qwen's model page recommends vLLM (>= 0.19.0) or SGLang, a BF16 checkpoint of about 54 GB, and an official FP8 variant.
- **Decisions (Jaxson, 2026-11-05):** vLLM with BF16 safetensors (not llama.cpp with a 4-bit file); Redhawk code and docs stay untouched, so `configs/talon/` is a copy-then-adapt twin; job scripts are DRAFTS; GPU count, tensor parallelism and concurrency have no preferred default (a 1 GPU versus 2 GPU benchmark decides); 20,480 tokens per sequence for the comparison, documented as shorter than Qwen's recommended 128K+; Talon pricing, allocation, quotas and access stay UNVERIFIED until Miami Research Computing confirms; the 200,000-example pipeline is documented but not built.
- **New files:** `configs/talon/` (settings file with every guess, `common.sh`, `serve_and_run.sh`, five job wrappers, `submit_pipeline.sh`, `prep_talon.sh`, `fetch_talon.sh`, `probe_talon.sh`, `probe_talon_part2.sh`, `probe_gpu_job.sbatch`, README); `code/generation/throughput_report.py` (successful examples per hour, GPU-hours per 1,000 examples, projection to 200,000); `code/tests/talon_deployment_test/` (shell tests, throughput and Python tests, a fake vLLM server); `docs/talon_setup.md`; `recovery/talon_ssh_access.md` (template with placeholders).
- **Small shared edits:** `configs/paths.yaml` gained four `talon_*` keys, all `UNSET`; `open_teacher_test.py` gained a `talon` backend (BF16, vLLM, free), development slot set T (BM9101-BM9132, 32 slots), `outputs_root(backend)` so a Talon run uses `talon_outputs` and a Redhawk run `redhawk_outputs` (the two cannot be swapped; backend-less commands keep the old Redhawk path), and the reasoning text is accepted under both `reasoning_content` and `reasoning`. Nothing under `configs/redhawk/` changed.
- **Safety design:** the scripts read `SETTINGS_REVIEWED` from the settings FILE, so an environment variable cannot un-draft them; no pass or fail rests on log wording (the lesson of job 2510690); `GPU_COUNT` must equal `TENSOR_PARALLEL x REPLICAS`; the submit script refuses unless the probe recorded an accepted GPU request style; downloads need `QT_CONFIRM_STORAGE=yes` and a pinned commit hash (never a branch).
- **Tests (all pass):** Redhawk shell parts 31/10/11/10/39 and the Python suite 46 (unchanged); Talon shell parts 41/19/30; throughput report 23 (every expected number hand-computed); Talon Python tests 15. The fakes are placeholders: only the first real login can check the real behaviour.
- **Next:** wait for the account; then the day-1 steps in `docs/talon_setup.md` section 9 (probe, fill the settings, review, download, stage A, throughput benchmark, comparison run), each with its own approval.

### Talon: first-connection tooling and a read-only probe, evidence labels (2026-11-05, still $0, no cluster access)
- **Trigger:** Research Computing told Jaxson the head node is `mualhphp01.hpc.miamioh.edu`, the GPU partition is `talon`, and `--nodelist=mualhpgp01.mpi` lands a job on GPU node 1. These are recorded as TOLD BY RESEARCH COMPUTING (2026-11-05), not as verified.
- **Evidence labels added** (OBSERVED, SLURM-REPORTED, TOLD BY RESEARCH COMPUTING, UNVERIFIED), used in `docs/talon_setup.md`, `recovery/talon_ssh_access.md`, `talon_settings.sh` and every section header of the probe. A scheduler's configuration (for example `Gres=gpu:h100:4`) is SLURM-REPORTED and never promotes "a GPU request is accepted" or "a GPU works" to verified.
- **`configs/talon/probe_talon.sh` rewritten** (still read-only): 13 labelled sections incl. a shared-home check (is Redhawk's home visible?), the `talon` partition with every node side by side, maintenance (`sinfo -R`, reservations), the queue, limits/QOS/billing weights, mounts and quotas. It ends with a note listing what it cannot verify, then `END OF PROBE`.
- **Read-only is enforced by tests:** a static scan (no submit/allocate/install/copy/delete/create command in command position, `scontrol`/`sacctmgr` only with `show`, no redirection except `/dev/null`) and a dynamic run with fake write-capable programs whose call log must stay empty and no file may appear.
- **New `configs/talon/run_probe_local.sh`** (runs on the PC): sends the probe through ssh's standard input (nothing copied to Talon), uses `StrictHostKeyChecking=yes`, preserves ssh's own exit status (a plain `| tee` would hide it), writes `.out/.err/.diag` under `~/talon_probe/` and calls the result COMPLETE only if ssh exited 0, the last line is `END OF PROBE` and all 13 section headers appear (otherwise INCOMPLETE; exit 3 for an incomplete output, ssh's own status otherwise). Eight fake-ssh tests cover success, refused login, timeout, host-key failure, a dropped connection, and a missing section.
- **Host key:** the first connection must not be accepted blindly. `recovery/talon_ssh_access.md` now has a procedure (display the fingerprints with `ssh-keyscan | ssh-keygen -lf -`, get Research Computing's own fingerprints by another channel, compare, then accept once) and a ready-to-send email.
- **Node choice:** `TALON_PARTITION` now defaults to `talon`; a new optional `TALON_NODELIST` (blank by default) adds `--nodelist=...` only when set, in `submit_pipeline.sh` and in the part-2 probe. Reason for the blank default (documented in `docs/talon_setup.md`): without a pinned node the scheduler may use any free GPU node, so a job is not held back by one busy, drained or reserved node; pin a node only if the nodes differ, only one is usable, or a benchmark needs identical hardware.
- **Tests:** Talon shell part 3 now has 54 checks (parts 1 and 2 unchanged at 41 and 19); other suites unchanged. Nothing under `configs/redhawk/` changed.
- **Next:** Jaxson runs the Windows commands (reachability, host-key verification, first login, the probe wrapper) and pastes the output; then settings, docs and fakes are updated from it. GPU tests (scheduler acceptance test, one GPU job) are decided afterwards.

## 2026-11-06

### Talon: meeting answers, key-pair login, probe additions (still $0, no Talon login yet)
- **Why:** Jaxson met Research Computing about getting access and starting to work on Talon. Their answers (TOLD BY RESEARCH COMPUTING, verbal, not yet in writing) are recorded in `docs/talon_setup.md`, `recovery/talon_ssh_access.md` and `configs/talon/talon_settings.sh`: same account and user name as Redhawk; VPN needed off campus; Talon costs nothing; storage limit 500 GB (ask for more if needed; there is a used/total display); one job may run at most 3 days; let the scheduler choose the node; all four GPU nodes are available; nothing changes without written notice to Jaxson; own software is allowed (conda environments); contact is Dr. Mueller. They also supplied an interactive `salloc` line (`--gres=gpu:2`, 72 h), `module load miniforge3-python3.12` and `conda create`/`activate` commands, explained in plain language in `docs/talon_setup.md`; none of them is run, and `--gres` stays UNVERIFIED until a scheduler test.
- **Host key decision:** Jaxson chose to trust the server without comparing fingerprints (the server is reachable only on the VPN). The first login will use `StrictHostKeyChecking=accept-new` (saves the key, refuses automatically if it ever changes); the probe wrapper keeps `=yes`. This replaces the earlier plan to verify fingerprints first.
- **Local setup done:** a `Host talon` entry in `~/.ssh/config` and `~/bin/talon.cmd` (`ssh -G talon` resolves to `mualhphp01.hpc.miamioh.edu`, user `buggjm`). Next: make the key pair (`ssh-keygen -t ed25519`), log in once, install the public key, test with `BatchMode`; the steps are in `recovery/talon_ssh_access.md`. Only the public key is ever shown or stored.
- **Probe additions (still read-only, tests extended):** it now also prints `module show miniforge3-python3.12`, which storage-usage commands exist (`quota`, `lfs`, `mmlsquota`, ...) and the size of the home folder, so the 500 GB limit and the used/total display can be found.
- **Code and tests simplified:** `open_teacher_test.py` now supports the two cluster backends only (Redhawk and Talon); the Python suite has 46 checks (8 calls at once without repeats, the smoke cap check and the dry run now run on the Redhawk backend). All suites pass: Python 46 / 23 / 15, Redhawk shell 31/10/11/10/39, Talon shell 41/19/55. Nothing under `configs/redhawk/` changed.
- **Next:** Jaxson runs the key-pair and first-login commands one approval at a time, then the probe wrapper and pastes the output; settings and docs are then updated from it. GPU tests stay a separate decision.

### Talon: first login and key-pair login done (2026-11-06, still $0)
- **What happened:** Jaxson made the key pair, logged in once (password and Duo push), and the public key was installed on Talon. A test with passwords forbidden (`BatchMode`) printed `KEY_LOGIN_OK`, so key login works and skips Duo. The `Host talon` entry now names the key (`IdentityFile`, `IdentitiesOnly`).
- **Observed on the first login:** the account `buggjm` is active; groups are `hpcusers` and `leed13-shared`; there was no `~/.ssh` folder on Talon before the key was installed. Recorded in `recovery/talon_ssh_access.md` (with the public-key fingerprint only).
- **Next:** run the read-only probe (`bash configs/talon/run_probe_local.sh`) and paste its output; settings and docs are then filled in from it.

### Talon: first read-only probe result (2026-11-06, still $0; the probe only reads)
- **What it found:** the home folder is shared with Redhawk (our Redhawk work is visible on Talon); the GPUs are `nvidia_h100_nvl`, 4 per node on 4 nodes, 64 cores and 515 GB RAM per node, shared between jobs; the `talon` partition allows 3-day jobs; Slurm job accounting is switched off (no account or QOS to name); the system Python is 3.9 but the module `miniforge3-python3.12` exists; the login node reaches Hugging Face and PyPI; `/home` and `/scratch` are 86% and 88% full; at the time only 3 GPUs (node 4) were free. Full table with evidence labels: `docs/talon_setup.md` ("What the first probe showed").
- **Settings filled from it:** `MOD_PYTHON=miniforge3-python3.12`, `TALON_GPU_TYPE=nvidia_h100_nvl`, `MODEL_REV` (current Hugging Face commit) and `WEIGHTS_MIB=53011`; account and QOS stay blank because none exist. `SETTINGS_REVIEWED` stays `no`; `TALON_GPU_STYLE`, the vLLM version, the Python path and the `talon_*` folders in `configs/paths.yaml` are still to be chosen.
- **Still unknown:** which disk the 500 GB limit counts and where the usage display is (`quota -s` timed out; `/etc/profile.d/quota.sh` is read next), whether compute nodes have internet (a proxy script exists), the GPU memory, whether `--gres` requests are accepted.
- **Follow-up read (same day):** the login shell sets `http_proxy`/`https_proxy` to the university web proxy (so the login node's internet goes through it); the scripts now add `127.0.0.1` and `localhost` to `no_proxy` so the model server inside a job is never sent through a proxy. The login script shows storage with `quota -s -f /home` but it printed nothing for us, so the 500 GB figure is still not seen; our group folder is `/shared/leed13_shared`. The conda module's folder holds `conda`, `pip` and `python3.12`.
- **Key also works on Redhawk** (shared home folder): the `Host redhawk` entry now uses the same key, so Redhawk logins need no password or Duo (`recovery/redhawk_ssh_access.md`). The Talon shell test harness now pins `WEIGHTS_MIB=51500` so its expected numbers do not depend on the settings default.
- **Storage result (2026-11-06):** `quota -s -v -f /home` shows 17,336 MB used, soft limit 480 GB, hard limit 500 GB on the home file system, which Redhawk and Talon share. So the 500 GB is OBSERVED, not only told, and our Redhawk work already uses 17 GB of it. `configs/paths.yaml` now sets the four Talon folders under `/home/buggjm/talon_project` (separate from `/home/buggjm/masters_project`); `fetch_talon.sh` reads this quota with a parser built on the real output (`home_quota_mib` in `common.sh`, 5 new tests) and refuses a download that would pass the soft limit. `QT_BASE_PYTHON` is set to the conda module's Python 3.12.5 (OBSERVED).

### Repository cleanup: Claude dropped, Qwen3.6-27B on Talon, README split into README + workflow.md (2026-11-06, $0, no cluster job)
- **Why:** Anthropic support confirmed that Claude outputs may not be used to train the Pythia students, so the Claude API is out of the project. The README had grown into a 356-line lab notebook mixing the overview with every detail, and the repository still held much Claude-only material. Jaxson asked for a short general README, a separate document with all specifics, an updated `CLAUDE.md`, and removal of whatever is no longer used.
- **Decisions (Jaxson, 2026-11-06):**
  - **Teacher:** Qwen3.6-27B, decided.
  - **Fallback if it underperforms:** the same model at higher precision or with more thinking, not a different model.
  - **Compute:** Talon for everything (generation, fine-tuning, evaluation); Redhawk is the fallback, and its scripts are kept unchanged.
  - **Precision comparison:** 4-bit versus BF16, both on Talon, not Redhawk versus Talon. The Talon 4-bit backend is still to be built.
  - **Benchmark:** regenerated with Qwen using the existing pipeline.
  - **Verifier:** left open (ChatGPT, Claude or another frontier model, as a checker only).
  - **Logs:** a compact cost log plus a new, detailed compute log.
  - **Layout:** no folder moves.
  - **Taxonomy:** `data/taxonomy/` left untracked and untouched.
- **Success criterion 4, dated methodological deviation:**
  - **Why:** the pre-registered wording assumed an API-only teacher whose size and hardware were unknown ("cost per query and latency"). The teacher now runs on our own GPUs.
  - **What changed:** the criterion is split into two separate requirements, both of which must be met.
    - **4a:** at least 10x fewer parameters than the teacher. Every Pythia size passes this, so it is a guard.
    - **4b:** at least 10x less GPU time per query and at least 10x lower median latency, on the same GPU. The protocol is fixed in the pilot. This is the measured requirement.
  - **Record:** the original wording is kept verbatim in `docs/workflow.md` Section 1.2.
- **Archive tag first:** the annotated tag `pre-cleanup-claude-era` was created on commit `60c3ca0` before anything was deleted. Every removed file can be read with `git show pre-cleanup-claude-era:<path>`. What the Claude trials taught, and how to recover files, is in `docs/workflow.md` Section 2.2. The total Claude spend stays $1.44.
- **README and workflow:**
  - **`README.md`:** now a one-page technical overview: question, design, criteria in brief, status, repository map.
  - **`docs/workflow.md` (new):** holds all specifics, updated for Qwen and Talon:
    - success criteria, with the deviation;
    - design and teacher deployment;
    - the archived Claude era;
    - benchmark design;
    - a new section of **safeguards for one teacher writing both benchmark and training data** (separate prompts and IDs, freeze first, slot variety, decontamination, independent answer verification, stated limitations);
    - phases 1 to 13;
    - metrics and statistics;
    - storage, including the cluster paths and the shared 500 GB home quota;
    - timeline, risks and open decisions.
  - **`CLAUDE.md`:** now holds the working rules from README Section 12, rewritten for the Qwen era. It points to `docs/workflow.md` as the source of truth, and the cost rule became two rules: a compute log and a cost log.
- **Logs:**
  - **`docs/cost_log.md`:** condensed to one line per paid run (12 Claude-era rows, $1.44; corrected 2026-11-11, this said 13); the per-trial arithmetic is in the tagged version.
  - **`docs/compute_log.md` (new):** records every cluster job and measured local run: times, node, GPUs, GPU-hours, peak memory, outcome. Backfilled entries:
    - the Pythia probe;
    - the Redhawk probes and the scheduler test;
    - build jobs 2510636 and 2510641;
    - pipeline 2510690 (stopped at stage A, about 0.05 GPU-hours);
    - pipeline **2511641** (finished, **results not yet reviewed**, and marked so);
    - the Talon probe.
- **Deleted from the working tree** (all preserved in the tag):
  - `docs/api_console_guide.md`, `docs/cost_estimate.md`, `docs/teacher_selection.md`, `docs/teacher_subscription_feasibility.md`. These were entirely about the Claude API, its pricing, the subscription idea or the Claude teacher choice.
  - `recovery/benchmark_trial_outputs.md`, the rebuild recipe for the Claude outputs.
  - `results/benchmark_trial/`: all the Claude-written trial items and logs. No test reads them.
  - `data/prompts/benchmark_generation_v1.md` to `v5.md`, the Claude-era prompt experiments.
  - **Kept on purpose:**
    - Prompt **v6, byte for byte.** Its SHA-256 `348db6ff...` is pinned by the Redhawk and Talon prep scripts and tests. Its human-only header still mentions Claude.
    - The copies outside the repository (`C:\masters_project_large\data\teacher_outputs\*sonnet*`) were not touched.
- **Code:**
  - **`generate_benchmark.py`, removed:**
    - the `trial`, `submit`, `fetch` and `replay` commands;
    - the model, effort and price settings;
    - the cost cap and the retry loop around API calls;
    - the dated Claude output folders;
    - support for prompts v1 to v5;
    - `--prompt` and `--effort`.
  - **`generate_benchmark.py`, now:** "the shared benchmark library plus the free checks" (`plan`, `check`, `verify`, `dupcheck`). `build_request` returns only the system text and user message, which are the only fields `open_teacher_test.py` used. The item-driven required-field logic in `check_item` is unchanged; its constants were renamed from `V1_REQUIRED`/`V5_REQUIRED` to `REQUIRED_WITHOUT_R_SOLUTION`/`REQUIRED_WITHOUT_WORKING`.
  - **`open_teacher_test.py`:** comments and help text only.
    - The Sonnet framing and the Redhawk-versus-Talon framing are removed.
    - The missing `docs/qwen36_precision_test_evaluation.md` reference is repointed.
    - `--ref` became a generic reference file.
  - **`pythia_probe.py`:** a one-line docstring fix.
  - **`environment/requirements.txt`:** dropped `anthropic`, `httpx2`, `pydantic` and `jiter`. It now lists `httpx==0.28.1`, which the Qwen client imports. `recovery/python_env.md` was updated to match.
- **Regression proof for the refactor:**
  - **What was built:** `code/tests/benchmark_core_regression/` (new): `capture.py`, `test_regression.py` and `snapshot_synthetic.json`. The snapshot records what the shared functions produce:
    - all slots up to BM9132;
    - the v6 prompt sections and hash;
    - the system and user text for 1,036 slots;
    - the schema;
    - 35 hand-made replies (every hard-problem kind, soft flags, rounding ties, negative zero, exponent notation, unsafe R);
    - `check_item`, `verify_item`, and the output of the `verify` command.
  - **Before any change:** the snapshot was captured. It was also run once on the 100 Claude batch items, which are kept in the session scratchpad only and not committed.
  - **After the refactor:** both snapshots matched exactly (51 and 153 parts).
  - **The one deliberate wording change:** two user-facing messages that pointed to "README Phase 3" now point to `docs/workflow.md` Phase 3. That change was made next, the only difference was confirmed to be that one line, and the committed snapshot was re-saved.
  - **A weakness found and deliberately not changed** (behavior was kept identical on purpose): a reply that omits the `r_solution` field is still checked under the old v1 rules. A number question without R code would therefore pass with the model's own key. Whether Qwen replies must always contain `r_solution` should be decided separately.
- **Doc fixes:**
  - **`docs/teacher_model_evaluations.md`:** reframed as how Qwen was chosen; the Claude-feature and Sonnet comparisons removed.
  - **`docs/pilot_plan.md`:** rewritten for Qwen on Talon.
  - **`docs/model_versions.md`:** §6 now holds the Qwen pins; the stale dtype and cluster-Python notes are fixed.
  - **`docs/pythia_behavior_analysis.md`:** §5.3 (the Sonnet cost table) replaced by a GPU-time note.
  - **`docs/cluster_selection.md`:** a current-decision note at the top; the "access not confirmed" cells dated; the comparison wording updated.
  - **`docs/talon_setup.md`:** job 2511641 is no longer "the baseline"; the unmeasured "35 tokens per second" claim removed; the comparison wording updated; the day-1 status added.
  - **`recovery/redhawk_ssh_access.md`:** a VPN note.
  - **`configs/paths.yaml`:** the missing `recovery/redhawk_qwen_test.md` reference in a comment repointed. The same stale reference in `configs/redhawk/common.sh` was **left alone**, because the Redhawk scripts are preserved byte for byte.
  - **`docs/github_notes.md`:** a tags section added.
- **Tests:** every suite ran before any change and again after all changes, with identical counts (Python 46 / 23 / 15; Redhawk shell 31/10/11/10/39; Talon shell 41/19/61; regression 51 and 153 parts).
- **Recorded as open decisions** (`docs/workflow.md` Section 10.2), on Jaxson's choice to push first and decide these later: require `r_solution` in every reply; record the Talon CUDA version; the stale comment in `configs/redhawk/common.sh`; whether to keep the Claude-era outputs outside the repository.

## 2026-11-07

### `docs/` organized into topic folders; new docs-layout rule ($0, no cluster job)
- **Why:** `docs/` had become one flat folder of 11 files mixing the method, logs, model notes, cluster notes and a Git cheat sheet. Jaxson asked for subfolders, and for a standing rule that every doc lives in a folder except this progress log.
- **New layout (moved with `git mv`, so each file keeps its history):**

| Old path | New path |
|---|---|
| `docs/workflow.md` | `docs/methodology/workflow.md` |
| `docs/pilot_plan.md` | `docs/methodology/pilot_plan.md` |
| `docs/model_versions.md` | `docs/models/model_versions.md` |
| `docs/teacher_model_evaluations.md` | `docs/models/teacher_model_evaluations.md` |
| `docs/pythia_behavior_analysis.md` | `docs/models/pythia_behavior_analysis.md` |
| `docs/cluster_selection.md` | `docs/clusters/cluster_selection.md` |
| `docs/talon_setup.md` | `docs/clusters/talon_setup.md` |
| `docs/compute_log.md` | `docs/logs/compute_log.md` |
| `docs/cost_log.md` | `docs/logs/cost_log.md` |
| `docs/github_notes.md` | `docs/guides/github_notes.md` |

  `docs/progress_update.md` stays at the `docs/` root. **Entries above this one keep the old paths, as written at the time; use this table to follow them.**
- **Rule (in `CLAUDE.md`, Working rules):**
  - Every file in `docs/` lives in a topic subfolder (`methodology/`, `models/`, `clusters/`, `logs/`, `guides/`).
  - A new, clearly named folder is made when none fits, for example `meetings/` for advisor notes or `report/` for drafts. Folders are created only when they get a file.
  - The only file at the root is this progress log.
  - Moving or renaming a doc means updating every reference to it and logging the move here.

  The layout is also described in `docs/methodology/workflow.md` Section 8.1 and in the README repository map.
- **References updated:** 155 occurrences of the old paths outside this history file were repointed by script. They were in the README, `CLAUDE.md`, the docs themselves, three recovery docs, a `configs/paths.yaml` comment, three Talon files, code docstrings and comments, and the run-log `test` metadata string in `open_teacher_test.py` (not a resume fingerprint field).
- **Redhawk scripts, comments only:**
  - `prep_cluster.sh` and `submit_pipeline.sh` now point to `docs/clusters/cluster_selection.md`.
  - In `common.sh`, the stale pointer to the never-written `recovery/redhawk_qwen_test.md` now points to the 2026-11-04 entry "The one-job pipeline built", where the flash-attention retry is described. `docs/clusters/cluster_selection.md` does not cover it.
  - This resolves the open decision recorded on 2026-11-06, which was removed from `docs/methodology/workflow.md` Section 10.2.
  - All three files pass `bash -n` and contain no carriage returns.
- **Two user-facing messages** in `generate_benchmark.py` (`check`, `verify`) now say `docs/methodology/workflow.md` Phase 3.
  - The regression test first failed on exactly that one line of the `verify` output; the exit code and the written file were identical.
  - The snapshot was then re-saved. The scratchpad snapshot of the 100 Claude batch items was re-saved the same way.
- **Tests:** all suites rerun after the move, all passing with unchanged counts: Python 46 / 23 / 15; Redhawk shell 31/10/11/10/39; Talon shell 41/19/61; regression 51 and 153 parts.

## 2026-11-11

### Corrections to the 2026-11-06/07 cleanup ($0, no cluster access, no paid call)
- **Why:** a review of the cleanup found six problems that the cleanup itself introduced. Only those were fixed. No methodology, validation rule or design was changed, and no preexisting issue was touched.
- **1. Carriage-return commands restored in this log.**
  - The 2026-11-04 entry "Preparation and submission scripts built; a flawed check found and fixed" quotes two commands that contain a literal carriage-return byte: `grep -c $'<CR>'` and `tr -cd '<CR>'`. A carriage return is the invisible "\r" character that Windows line endings add.
  - When the 2026-11-07 entry was appended, the file was read with Python's universal-newline mode. That mode turns a lone carriage return into a line break, so the commands were split across three lines.
  - The two original bytes were restored from the tag `pre-cleanup-claude-era`. Every entry written before the cleanup (the first 355 lines) is again byte-identical to the tag.
  - From now on this file is edited byte by byte (or with the editor), never with a universal-newline read.
- **2. Claude trial counts corrected.** `docs/methodology/workflow.md` Section 2.2 said "eight 20-question trials and one 100-question batch: 120 trial questions in total". `docs/methodology/pilot_plan.md` said "120 questions in total". The original run logs and item files under the tag show:
  - **six 20-question trials** (prompts v1 to v6); the v4 run was refused and returned no items;
  - **three 1-question probes**; one was rejected with an access error and returned nothing;
  - **a 2-question test batch**;
  - **the 100-question batch.**

  That is **204 items** covering **120 distinct slots** (BM0001 to BM0120). Both documents now say so.
- **3. Cost-log row count.** The 2026-11-06 entry said the condensed cost log has 13 Claude-era rows. It has **12** (the original ledger had 14 rows: the 12 paid runs plus a $0 setup row and a $0 Pythia probe row). Corrected in place, with a note.
- **4. Partition of compile jobs 2510636 and 2510641.** The new compute log listed them under the Redhawk `gpu` partition. The job script `configs/redhawk/build_llamacpp.sbatch` requests `#SBATCH --partition=batch` (8 CPUs, 16 GB, 1.5 hours, no GPU) at both commits that submitted them: `3cbbaf2` (`prep_cluster.sh`) and `bcedc66` (`rebuild_llamacpp.sh`). Both submit commands run `sbatch` with no override. `docs/logs/compute_log.md` now says `batch` (**requested**), and states that the partition actually used was **not observed**: Slurm accounting is off, and the jobs' logs on Redhawk were not checked.
- **5. Redhawk wording clarified.** `docs/clusters/talon_setup.md` said "nothing under `configs/redhawk/` was changed", and the risk table in `docs/methodology/workflow.md` said "unchanged". Since 2026-11-07, three comment lines there differ.
  - **How it was verified:** `git diff pre-cleanup-claude-era -- configs/redhawk` shows exactly those three comment lines and no other changed line. With comment lines removed, `common.sh`, `prep_cluster.sh` and `submit_pipeline.sh` are identical to the tag (and to `fbe29e2`, where the Talon work began).
  - **New wording:** both places now say the executable logic is unchanged and only comments were repointed.
- **6. Regression fixture for a reply with no `r_solution` field.**
  - **What was added:** a new `absent_r_solution` part in `code/tests/benchmark_core_regression/capture.py`, and two named checks in `test_regression.py`. The existing case "number without r_solution" has the field present but empty, which takes a different code path. The new cases are three number replies in which the field is missing entirely.
  - **What it records (the behavior is kept, the loophole is not fixed):** such a reply passes `process_reply` with no hard problem and keeps the model's own key. `verify` flags it. The only remaining check is the key against the last number in the explanation.
  - **Proof it is the original behavior:** the same three replies give identical results with the pre-cleanup `generate_benchmark.py` from the tag.
  - **Proof nothing else changed:** the re-saved snapshot differs from the previous one only by the added part; every earlier part is identical.
  - **Documentation:** the open decision in `docs/methodology/workflow.md` Section 10.2 now points to the fixture.
- **Tests:** see the summary below.

### Pilot plan decided: Pythia 70M on 1k examples, end to end (2026-11-11, $0, no cluster access)
- **Why:** Jaxson wants to run the whole pipeline once at the smallest scale (Pythia 70M, 1,000 training examples) so the identical process can then be repeated for larger sizes and data sets. A ten-stage plan was agreed, from Talon bring-up to a go/no-go review. The decisions below are recorded in `docs/methodology/workflow.md`, `docs/methodology/pilot_plan.md` and `docs/models/model_versions.md`.
- **Benchmark:** the pilot is scored on the real ~1,000-question benchmark, generated, verified and frozen before any training data. It is reported as **teacher-generated**.
- **Teacher precision:**
  - **One precision for all generation**, chosen on Talon before the benchmark is written: BF16 (the reference), FP8 or 4-bit, all served by vLLM.
  - **Decision rule:** the lowest-compute option that is non-inferior to BF16 by a 3-point margin on both usability and independently checked answer correctness, with a multiplicity adjustment for the two comparisons.
  - **The margin:** provisional. Its scientific rationale must be written down before the run.
  - **Cost of the stricter margin:** estimated at 0.4 to 9 extra hours of generation over a 5-point margin, depending on the unmeasured Talon speed. That is within the one day Jaxson set as the threshold for choosing 3 points.
- **Verification:**
  - **The teacher checking itself:** R computes keys where it can. A Qwen blind re-solve is a consistency check only.
  - **Everything R cannot settle:** a triage step sends it to an open-weight verifier from a different family, which is not OpenAI or Anthropic and whose terms allow this use (DeepSeek is the likely choice, Mistral another candidate). It runs through a paid API, logged in the cost log.
  - **Choosing and testing the verifier:** chosen once the precision-test outputs exist. It is tested on 100 to 200 reference items, including deliberately wrong answers, with a declared false-acceptance threshold.
  - **Manual audit:** Jaxson audits about 150 random benchmark items, stratified by category and including items that passed every check. A claim about the error rate after corrections needs a fresh sample.
- **Development set and confirmatory rule:**
  - **What the development set is for:** a separate ~200-item development set (DV) is used for hyperparameter choice and for debugging the evaluation.
  - **Freezing:** everything is frozen in a dated pre-registration before the evaluated training run.
  - **After the first benchmark evaluation:** only documented bug fixes are allowed. Follow-up experiments prompted by the scores are labeled exploratory and never replace the confirmatory results.
- **Topic coverage:** the benchmark, development set and training data share one taxonomy and target proportions. Questions, numbers and scenarios are sampled independently, and subtopics are not split between the sets. A held-out-subtopic benchmark is a possible later study.
- **`r_solution`:**
  - **The field:** required in every reply. The legacy path that accepted a missing field will be removed.
  - **Its content:** substantive R only where R can compute the answer, and an explicit "not applicable" otherwise.
  - **The regression fixture:** updated deliberately when this is implemented.
- **Training:**
  - **Method:** Hugging Face `Trainer`, full fine-tune, every setting explicit. Chosen after a review of the transformers 5.19 documentation and source.
  - **Requirements from that review:**
    - load in float32 with BF16 mixed precision;
    - pad with `<|padding|>` (id 1), never the end token;
    - build our own labels;
    - `save_only_model=False`, so a run can resume;
    - pin `accelerate`.
  - **Pre-pilot tests:** the label masking; the precision; gradient-accumulation equivalence on gradients and updates, with unequal lengths; resume; and the length limit.
  - **Training precision recipe:** float32 weights with BF16 mixed precision, recorded in `docs/models/model_versions.md` Section 3. This closes that open item.
- **Context limit:** `max_position_embeddings` is 2048 in all four pinned Pythia configs (read today). Examples over 2,048 tokens are rejected or deliberately shortened, never silently truncated, and the evaluation prompt plus new tokens must fit too.
- **Evaluation:**
  - vLLM for the students and the teacher, on the same GPU type;
  - the end token as the main stop, with a token cap as backstop;
  - no blank-line stop, because it could cut off the `Final answer:` line;
  - a missing final-answer line counted as a format failure;
  - short-text items kept tightly constrained, with open-ended ones needing a rubric and semantic grading;
  - the teacher in thinking mode with the model-card sampling.
- **Not yet started:** the cluster work, the paid verifier calls and the code changes. Each cluster step and each paid call needs Jaxson's approval first.

### `.gitignore` exceptions for `docs/logs/` and `docs/models/` (2026-11-11)
- **What went wrong:** when `docs/` was split into topic folders on 2026-11-07, two of the new folder names matched old ignore rules. `logs/` was meant for large raw log folders and `models/` for model weights. The moved files stayed tracked, because they were moved with `git mv`, but `git add` refused to update them, and any **new** file in those folders would have been silently left out of Git. This was found while committing the 2026-11-11 corrections.
- **Fix:** exceptions `!docs/logs/` and `!docs/models/` were added right after those rules. `git check-ignore` confirms that both folders are tracked again, while `logs/` and `models/` folders elsewhere are still ignored, and weight files (`*.safetensors`, `*.bin`, `*.pt`) stay ignored everywhere, including in `docs/models/`.

### Regression fixture: question text now matches its R code (2026-11-11)
- **What changed:** in `code/tests/benchmark_core_regression/capture.py` the sample number question "Two dice are rolled. Find the probability." was replaced with "In five independent Bernoulli trials, each with success probability 0.5, find the probability of exactly two successes. Round to 3 decimal places."
- **Why:** the new question actually matches the fixture's `r_solution`, `dbinom(2, 5, 0.5)` = 0.3125, which gives the key 0.313. The rounding instruction is kept, so the checks still read 3 decimals.
- **Proof the behavior is the same:** only the 9 reply cases and 3 absent-`r_solution` cases that use this question were regenerated. Putting the new question text into the old snapshot makes the two identical, so every key, check result and verdict is unchanged. `test_regression.py` passes (52 parts).

### Talon bring-up, step 1: repository copied, GPU request style tested (2026-11-11, $0, no job created)
- **What:** Jaxson copied the committed repository to Talon (`~/talon_project/repo`, commit `4d24384`, with `git archive` over ssh), then ran the part-2 probe in check-only mode. It asks the scheduler with `sbatch --test-only` whether four GPU request forms would be accepted, without creating any job.
- **Result:** all four forms were accepted on partition `talon`, with an immediate estimated start on `mualhpgp01`. `TALON_GPU_STYLE=gres` was set in `configs/talon/talon_settings.sh`, matching Research Computing's example. `SETTINGS_REVIEWED` stays `no` until the full review.
- **Recorded in:** `docs/logs/compute_log.md` entry 9, and `docs/clusters/talon_setup.md` (the facts table and the Section 9 status).
- **Why `git archive`:** it sends exactly the committed files. On this PC it gives text files Windows line endings, which is what the v6 prompt's pinned SHA-256 was computed on, and gives shell scripts Unix line endings (forced by `.gitattributes`).
- **Next:** the 5-minute GPU probe job, which needs approval because it uses GPU time. It shows the GPU actually received, the driver and CUDA version, and whether compute nodes reach Hugging Face and PyPI.

### Talon bring-up, step 2: the GPU probe job (job 196, 2026-11-12 02:35 UTC, about 0.0003 GPU-hours)
- **What:** with Jaxson's approval, one small job requested one H100 (`--gres=gpu:1`, partition `talon`, 10-minute limit). It loaded no model and wrote only its own log. It started after about 1 s in the queue on `mualhpgp01` and finished in about 1 s.
- **Facts gained** (recorded in `docs/logs/compute_log.md` entry 10 and `docs/clusters/talon_setup.md`):
  - each H100 NVL has 95,830 MiB (about 94 GB);
  - driver 610.57.04;
  - GPUs 0-1 and 2-3 are NVLink pairs;
  - compute nodes reach Hugging Face and PyPI;
  - local `/tmp` has 500 GB.
- **Findings that change the scripts:**
  - **(1) GPU isolation is by `CUDA_VISIBLE_DEVICES` only.** The job was assigned one GPU (`CUDA_VISIBLE_DEVICES=1`) but `nvidia-smi` showed all four. The probe's `GPUS_SEEN=4` counts visible GPUs, not assigned ones. `configs/talon/serve_and_run.sh` counts and samples GPUs with `nvidia-smi`, so it would also measure GPUs used by other people. It must be fixed to use only the assigned GPUs before Stage A.
  - **(2) A job gets one CPU unless it asks, and its memory limit is unknown.** `--cpus-per-task` and `--mem` must be set (`TALON_EXTRA_SBATCH`).
  - **(3) The CUDA version line was empty.** It is still to be read.
- **Not changed yet:** the script fix and the CPU and memory values are decided with Jaxson in the settings review. `SETTINGS_REVIEWED` stays `no`.
