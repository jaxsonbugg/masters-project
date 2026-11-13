# Workflow: the full method, phase by phase

This is the detailed companion to the README. It holds the research question and the exact success criteria, the experimental design, the phase checklists, the safeguards for benchmark and training data, the metrics and statistics, storage, risks and open decisions. When work is completed or a decision changes, update this file and add a dated entry to `docs/progress_update.md` (the history). Cluster jobs go in `docs/logs/compute_log.md`, and paid or plan-metered calls (the Codex grader) go in `docs/logs/cost_log.md`.

Terms used throughout, defined once:

- **Teacher:** the large model (here Qwen3.6-27B) that writes questions and worked answers.
- **Student:** a small model (here Pythia 70M, 160M, 410M or 1B) that learns from the teacher's examples.
- **Distillation:** the whole process of passing a teacher's ability to a student through examples the teacher wrote.
- **Fine-tuning:** continuing to train a pretrained model's weights on new examples. A 70M model has 70 million adjustable numbers (parameters), a 27B model 27 billion.
- **Token:** the unit a model reads and writes, roughly three quarters of an English word. "standard deviation" is about 2 to 3 tokens.
- **Thinking tokens:** tokens a reasoning model writes privately before its final answer. They cost GPU time like any other output.
- **Benchmark:** the fixed set of about 1,000 test questions every model is graded on. It is never used for training.
- **Slot:** a description of one question to be written, such as "numerical / binomial probability / intro / number answer". The teacher turns each slot into one question.
- **Reference key:** the answer stored with each benchmark question. It is checked by the benchmark quality procedure (Section 4, safeguard 6). It is not claimed that every key is independently verified.
- **Grader:** the model that decides whether an answer is correct. Here that is Codex, a frontier model (Section 2.3).

---

## 1. Research question and success criteria

**Primary question.** How small can a specialized language model be, distilled from a large teacher, and still retain useful capability in statistics and R programming?

**Sub-questions.**
1. How does post-distillation accuracy change with student size (70M, 160M, 410M, 1B)?
2. How does accuracy change with the amount of distillation data (1k to 200k examples)?
3. Is there a "knee" in the size-performance curve where shrinking the model causes substantial loss?
4. What are the efficiency gains (parameters, memory, latency, GPU time) relative to the teacher, and what does each unit of accuracy cost?
5. Are the differences between models statistically significant?

### 1.1 Definition of success (pre-registered 2026-09-29)

A student, meaning one (model size, data size) pair, is a **successful specialization** only if it meets **all** of the criteria below. The thresholds were fixed before any student results exist. Any later change must be logged in `docs/progress_update.md` with a reason, as was done for criterion 4 (Section 1.2) and for how criterion 1 is graded (Section 1.3).

1. **Retained accuracy.** The ratio is student accuracy divided by teacher accuracy on the frozen benchmark. The lower bound of the bootstrap 95% CI of that ratio must reach a tier: **Useful >= 70%**, **Strong >= 85%**, **Near-parity >= 95%**. Accuracy is macro-averaged across benchmark categories. Every answer, the teacher's and the students', is graded by the grader against the reference key (Section 2.3). For R code items, the execution-based check is reported as a cross-check (Section 1.3). Results are reported at all three tiers.
   - *Weak-teacher safeguard.* Teacher and student absolute accuracies are always reported with CIs next to every ratio. A student must also reach an **absolute accuracy floor of 60%** to earn any tier. A teacher below **80%** on the benchmark is a red flag. In that case, pause and review benchmark difficulty and the teacher settings, using the dev set and not the frozen benchmark, before distillation. The first remedy is Qwen3.6-27B at a higher precision or with more thinking (Section 2.1).
2. **Real gain over its own baseline.** The student must be significantly better than the same student untrained (McNemar's test, Holm correction across model pairs).
3. **Usable output.** A minimum share of well-formed, parseable responses and a minimum share of R code that runs. The R code is executed only in the R sandbox (Section 4, safeguard 10). The starting value is 90% each; it is confirmed in the Phase 4 pilot, and any change is logged before Phase 5 results.
4. **Efficiency.** See Section 1.2. The original wording is kept there verbatim, followed by the current two-part definition.

**Answer to the primary question:** the smallest (size, data size) pair that reaches each tier. The Phase 12 knee analysis shows where accuracy falls off below it. No general-purpose small-model comparator is used unless an open-weight model that matches the Pythia sizes in parameter count and purpose is found.

**Worked example of criterion 1.** Suppose the teacher scores 84% (macro-averaged) and the 410M student trained on 50k examples scores 66%. The point ratio is 66 / 84 = 0.786. A bootstrap resamples the benchmark questions with replacement, say 10,000 times, recomputes the ratio each time, and takes the 2.5th percentile as the lower bound, for example 0.74. Since 0.74 >= 0.70 and the student's 66% is above the 60% floor, this student reaches **Useful** but not **Strong**. If the teacher had scored only 62%, the same student would look near-parity by ratio. The 60% floor and the 80% teacher red flag exist to stop that kind of misleading result.

### 1.2 Criterion 4: original wording and the 2026-11-06 deviation

> **As pre-registered 2026-09-29:** "**At least 10x cheaper/smaller than the teacher.** Compared on measured inference cost per query and latency (the teacher is API-only, so parameter count and memory are not directly comparable). Also report training GPU-hours, memory, and throughput. The exact measurement protocol is fixed in the pilot. At these student sizes this criterion is a guard more than a differentiator; the accuracy tiers carry the analysis."

**Methodological deviation, 2026-11-06.** The pre-registered wording assumed a teacher reachable only through a paid API, whose size and hardware are unknown. The teacher is now Qwen3.6-27B, an open-weight model that runs on our own GPUs. Its size is known, and its speed and memory can be measured on exactly the hardware the students use. "Cost per query" in dollars no longer exists, because cluster time is free. The old single criterion mixed two different things, being smaller and being faster, so it is split into two separate requirements. **Both must be met.**

- **4a. Size reduction.** The student has **at least 10x fewer parameters** than the teacher. Qwen3.6-27B has about 27 billion parameters, so a student must have at most about 2.7 billion. The on-disk size of the model files is reported alongside. Every Pythia size passes 4a (the largest, 1B, is 27x smaller), so 4a is a guard that records the size gap, not a result.
- **4b. Measured inference efficiency.** On the **same GPU type** with the **same serving settings**, two conditions must hold:
  - the student uses **at least 10x less GPU time per benchmark query** than the teacher;
  - its **median latency per query** is at least 10x lower.

  Peak GPU memory and throughput (queries per second) are reported for both. This is the requirement that actually measures something.

  *GPU time per query* is the wall-clock time the GPUs are busy, multiplied by the number of GPUs, divided by the number of queries answered. *Latency* is the time from sending one question to receiving the full answer.
- **Measurement protocol.** Fixed in the Phase 4 pilot before any student result:
  - the GPU model (H100 NVL on Talon);
  - the engine and its version;
  - batch size and concurrency;
  - max new tokens, which must be the same for teacher and student;
  - warm-up runs excluded;
  - the number of repeated timings.

**Worked example of 4b.** Say the teacher, on 2 H100s, answers the 1,000 benchmark questions in 50 minutes. That is 2 GPUs x 3,000 s / 1,000 = 6.0 GPU-seconds per query. Say the 410M student, on 1 H100, answers them in 4 minutes: 1 x 240 / 1,000 = 0.24 GPU-seconds per query. The ratio is 6.0 / 0.24 = 25x, so 4b's GPU-time condition is met. Latency is checked the same way, from the median of the per-question times.

**What could go wrong.** The student is not given a shorter answer budget than the teacher. A student that rambles until its token limit will look slower, which is a real cost and is reported as such. Timing noise is handled by repeated runs; the protocol states how many.

### 1.3 Criterion 1: how answers are graded (deviation of 2026-11-12)

> **Wording before this change** (this file, criterion 1): "Accuracy is macro-averaged across benchmark categories, and R code items are graded by execution."

**Methodological deviation, 2026-11-12.** Every benchmark answer, the teacher's and every student's, is now graded by one grader, Codex. Codex reads the question, the reference key and the model's final answer, and decides whether the answer is correct (Section 2.3). For R code items, the execution-based check is no longer the score. It is still run, in the R sandbox, and reported next to the score as a cross-check. Nothing else in criterion 1 changes: the tiers, the 60% floor, the 80% teacher red flag and the bootstrap lower bound are as pre-registered.

**Why.**
- **Correct R code can be written in many ways.** Grading by execution means running the item's `r_check`, which the teacher wrote. A check that is too strict marks a correct but differently written answer wrong; one that is too loose marks a wrong answer right.
- **A grader judges equivalence the way a person would.** For example, `sum(x, na.rm = TRUE) / sum(!is.na(x))` and `mean(x, na.rm = TRUE)` give the same mean for an ordinary numeric vector with at least one non-missing value.
- **One grader for every answer type and every model** keeps the comparison between the teacher and the students like for like.

**What it costs.** The grader can make mistakes. They are measured before and during the evaluation:
- calibration answers whose truth is known in advance;
- a blind human audit;
- the deterministic cross-check;
- validity thresholds, with pre-registered rules for what happens if the grader fails them (Section 2.3).

No student result existed when this change was made.

---

## 2. Experimental design

| Factor | Levels |
|---|---|
| Teacher | Qwen3.6-27B (Apache 2.0 license), BF16 weights served by vLLM on Talon (Section 2.1) |
| Student size | Pythia 70M, 160M, 410M, 1B: deduped variants, final `step143000` checkpoints, pinned by commit SHA (`docs/models/model_versions.md`) |
| Distillation set size | 1k, 10k, 50k, 100k, 200k (stretch). **50k is the fallback single size** |
| Grader | Codex, a frontier model run through the Codex command-line tool on the owner's workspace subscription. It judges each benchmark answer against the reference key, blind to which model wrote it, and also screens the benchmark questions for ambiguity. It is used only for evaluation and for the screen, never for training data, data filtering, hyperparameters or the teacher setup (Section 2.3) |
| Training data checks | Qwen-generated training examples are retained without correctness-based filtering: format, duplicate, decontamination and length checks only (Section 4, safeguard 9) |
| Benchmark | Frozen held-out set of about 1,000 statistics and R questions |
| Compute | Talon (Miami, 4 nodes x 4 NVIDIA H100 NVL) for generation, training and evaluation; Redhawk (Miami, V100) as the fallback |

**Conditions per student:** an untrained baseline, plus one fine-tuned model per training-set size. The full grid is 4 sizes x up to 5 data sizes = 20 fine-tuned models, plus 4 baselines and the teacher. If compute is limited, all 4 sizes run at 50k first, then the data-size axis is expanded.

**Why Pythia.** All Pythia sizes are trained on the same data in the same order, and the suite is designed for controlled scaling experiments. Differences between students are therefore attributable to size rather than to training-data differences. Only the deduped variants are used (all four sizes saw the same globally deduplicated Pile in the same order), never the standard variants.

**Design principles.**
- Same benchmark, same training data and same hyperparameter recipe across all student sizes.
- Nested training sets (the 1k set is a subset of the 10k set, and so on), so data-size effects are not confounded by content.
- Multiple random seeds per condition if compute allows, so seed-to-seed variance can be estimated.

### 2.1 The teacher: Qwen3.6-27B

**What and why.** Qwen3.6-27B is a 27-billion-parameter reasoning model with open weights under the Apache 2.0 license, which allows training other models on its outputs. It was the first choice of the open-weight evaluation in `docs/models/teacher_model_evaluations.md` (license, math and code quality, fit with our prompt, ability to run on Miami hardware).

**Deployment.**
- **Talon (primary):** vLLM serving the full BF16 weights. BF16 is a 16-bit number format, so the model runs as released, without compression. Repository `Qwen/Qwen3.6-27B`, revision `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9`, about 53,011 MiB of weights. Engine pinned 2026-11-12: `vllm==0.32.0` (the model card requires 0.19.0 or later; details in `docs/models/model_versions.md` Section 6). Settings are in `configs/talon/talon_settings.sh`, explained in `docs/clusters/talon_setup.md`.
- **Redhawk (fallback):** llama.cpp tag `b11960` (commit `8642541b...`) serving a 4-bit GGUF file (`unsloth/Qwen3.6-27B-GGUF` @ `82d411ac...`, `Qwen3.6-27B-Q4_K_M.gguf`, SHA-256 `5ed60d0a...`) on two 16 GB V100s. Pins are in `configs/redhawk/common.sh`.
- **Sampling** (the model card's recommended thinking-mode settings, identical on both clusters): temperature 1.0, top_p 0.95, top_k 20, min_p 0, presence penalty 0. The output limit is 16,384 tokens per call, thinking included. The context is 20,480 tokens per sequence, which is a comparison setting and not the model's maximum (`docs/clusters/talon_setup.md` Section 7).

**Choosing the teacher precision (decided 2026-11-11; protocol pre-registered before it runs).** *Precision* is how many bits store each of the model's numbers: BF16 uses 16, FP8 uses 8, a 4-bit version uses 4. Fewer bits mean a smaller, faster model, and possibly a slightly worse one.
- **One precision is used for all generation.** The benchmark and every training set come from the same teacher setup. Mixing precisions across data sizes would add a second difference between the conditions being compared.
- **What is compared.** BF16 (the reference), FP8 and 4-bit, all on Talon and all served by vLLM, so neither the engine nor the hardware differs. This replaces the earlier plan to compare Redhawk's 4-bit file with Talon's BF16.
- **Two endpoints, measured on the same development slots (BM8xxx, never benchmark or training):**
  - **Usability, on all slots:** the item is usable on the first attempt. That means a complete, parseable reply that passes the automatic checks, and for a number item, a key that R could recompute from the item's own code (run in the R sandbox, Section 4, safeguard 10).
  - **Answer correctness, on a stratified sample:** checked independently of the teacher. A computable answer is checked by R in the sandbox, and anything else by the owner by hand, with every disagreement adjudicated.
    - **Why usability alone is not enough:** a compressed model can write perfectly formatted answers that are more often wrong.
    - **Why no language model judges this endpoint:** the precision decides how all the training data is made, so a model grader's verdicts are kept out of it (Section 2.3).
- **The statistics.** Two comparisons against BF16 (FP8 vs BF16, 4-bit vs BF16) with a multiplicity adjustment (Holm, or Bonferroni at one-sided α = 0.025 each). This is a non-inferiority test: a lower precision passes if the confidence interval for its paired difference from BF16 stays above −3 percentage points on **both** endpoints.
  - The 3-point margin is provisional. Before the run, it must be justified in writing as the largest loss of teacher quality that would not change the study's conclusions, not only by the GPU time it saves.
  - **The margin is never widened to make the sample smaller.**
- **Sample sizes, calculated before any precision-test output exists.**
  - **What is computed.** For each comparison and each endpoint, the number of paired slots needed to show non-inferiority with the declared power. A *paired* slot is one question slot answered by both precisions. The *discordance* ψ (psi) is the share of slots where the two precisions disagree: one is usable or correct and the other is not. If the two precisions truly perform the same, the approximate number of slots is

    n ≈ (z₁₋α + z_power)² × ψ / Δ²

    Here Δ = 0.03 is the margin. z₁₋α = 1.96 is the normal quantile for one-sided α = 0.025, which is used for every comparison, even if the 4-bit arm is dropped. z_power is 0.84 for 80% power and 1.28 for 90%.
  - **Worked numbers.**

    | Assumed discordance ψ | Slots at 80% power | Slots at 90% power |
    |---|---|---|
    | 0.05 | 437 | 584 |
    | 0.10 | 873 | 1,168 |
    | 0.15 | 1,309 | 1,752 |

  - **What is declared before the run:** the power (80% is proposed), and each assumed ψ with its source. The usability ψ is re-estimated from a 100-slot first run.
  - **The manual workload** of the correctness endpoint is roughly the number of slots × the number of arms × the share of items R cannot check. That share is about 70% if only number items are computable. *Example:* ψ = 0.10 at 80% power with three arms (BF16, FP8, 4-bit) is about 873 × 3 × 0.7 ≈ 1,830 judgments by hand.
- **Feasibility gate.** Before any precision-test output exists, the owner writes down the largest number of hand judgments that is practical.
  - **If the calculation needs more:** BF16 is used for all generation. FP8 and 4-bit may still be run on a feasible sample, but only as an **exploratory**, descriptive comparison that cannot change the choice.
  - The −3 margin is not widened to fit the workload. BF16 is the safe default because it is the model as released, and its GPU time is affordable: about 1,228 GPU-hours for 200,000 examples, from Stage T, with no GPU-hour cap.
- **The 4-bit arm (decided 2026-11-12).** Qwen publishes no official 4-bit release of Qwen3.6-27B, so the 4-bit arm uses a **community-quantized** checkpoint. It is kept only if all of the following are verified before download:
  - **Provenance:** prefer a reproducible checkpoint quantized **directly from the official BF16 weights**, with **no additional fine-tuning**.
  - **License:** compatible with this use.
  - **Quantization method:** documented.
  - **vLLM `0.32.0` compatibility on H100:** confirmed. For example, a GPTQ checkpoint with `desc_act=True` is served incorrectly by vLLM 0.30 and later.

  The exact quantization configuration is recorded with the results: method, bits, group size, symmetric or asymmetric, calibration data, the quantization tool and its version, and the repository commit. The comparison is reported as one between **specific model deployments** (this checkpoint served this way), not as a universal comparison of 4 bits against 16. It uses the **same pre-registered non-inferiority criteria** as FP8 against BF16. **If no candidate passes the provenance and compatibility checks, the 4-bit arm is dropped rather than delaying the pilot;** the test then compares FP8 with BF16 only. Candidates found on 2026-11-12, still to be checked: `cyankiwi/Qwen3.6-27B-AWQ-INT4`, `btbtyler09/Qwen3.6-27B-GPTQ-4bit`, `Lorbus/Qwen3.6-27B-int4-AutoRound` (`docs/models/model_versions.md` Section 6).
- **Decision rule.** If the feasibility gate passes, use the lowest-compute precision that is non-inferior to BF16 on both endpoints. If neither FP8 nor 4-bit passes, or the gate fails, use BF16. The chosen precision's projected total GPU time must fit the timeline, run in resumable jobs shorter than the 3-day limit.
- **Worked example (hypothetical numbers).** On 1,000 paired slots, BF16 is usable on 88% and 4-bit on 87.2%, a difference of −0.8 points. If the adjusted lower confidence bound is −2.6 (above −3) for usability, and the correctness sample gives a lower bound of −2.1, then 4-bit passes both endpoints and is chosen. A lower bound of −3.4 on either endpoint would mean 4-bit fails.

**Fallback if the teacher underperforms.** If teacher accuracy on the benchmark is below 80%, the first step is the same model with a higher precision or more thinking, not a different model. The alternatives ranked in `docs/models/teacher_model_evaluations.md` stay documented but are not the plan.

### 2.2 Why the teacher changed (the Claude era, archived)

The project began with Claude Sonnet 5.5 as the teacher, through the paid Claude API. Anthropic's commercial terms bar using outputs "to train competing AI models". When asked directly, Anthropic support confirmed that Claude outputs may not be used to train the Pythia students. The project therefore switched to an open-weight teacher, and Claude can no longer write either training data or benchmark questions.

**What the Claude trials were.** Between 2026-10-07 and 2026-10-15 there were nine trial runs and two Batch runs, all on the same slot blueprint:
- **Six 20-question trials**, one per prompt version v1 to v6, all on slots BM0001 to BM0020. The v4 run was refused by the API and returned no items.
- **Three 1-question probes.** One was rejected with an access error and returned nothing.
- **A 2-question test batch** (BM0021 and BM0022).
- **The 100-question batch** (BM0021 to BM0120).

Together they produced 204 items covering 120 distinct question slots (BM0001 to BM0120). None of them is part of the frozen benchmark. The total spend was **$1.44** (`docs/logs/cost_log.md`). The trials developed and tested the question-generation pipeline that Qwen now uses unchanged:

- **Prompt v1 to v6.**
  - v1 put the key before any working: 3 of its 8 numeric keys were wrong.
  - v2 added R code that recomputes each number.
  - v3 added rounding rules.
  - v4 put a reasoning field first and was refused by the API.
  - v5 dropped the working field and got worse.
  - **v6** (v3 plus rules for one fully correct multiple-choice option, consistent printed output and a finished question text) is the prompt now in use.
- **R writes the number keys.** The script runs the teacher's own R code and uses R's rounded output as the key, keeping the teacher's typed number only for comparison. In the 100-question batch this corrected one typed slip (207.01 vs R's 207.02).
- **Regeneration without hints.** A question that fails the automatic checks is asked for again with the same prompt, up to 3 attempts. The prompt does not say what failed, so the first-attempt pass rate stays an honest measure of the prompt.
- **Automatic checks.** These were tuned on real failures: thinking aloud in the question text, trailing ellipses, an answer contained in its own question, R checks that never test the student's answer, and rounding mismatches.
- **The duplicate finding.** This was the most important result for scaling. The slot design repeats category, subtopic and difficulty combinations: only 138 distinct combinations exist for 1,000 slots, so 86% of slots repeat one. The model writes near-identical questions for repeated combinations. This must be fixed before the 1,000-question run (Phase 3).

**How to recover any Claude-era file.** Everything was removed from the working tree on 2026-11-06 but is preserved in Git under the annotated tag **`pre-cleanup-claude-era`** (commit `60c3ca0`). This covers the trial outputs in `results/benchmark_trial/`, prompts v1 to v5, the Claude-only docs and the Claude API code in `generate_benchmark.py`.

- `git show pre-cleanup-claude-era:<path>` prints a file as it was.
- `git checkout pre-cleanup-claude-era -- <path>` restores it into the working tree.
- `git ls-tree -r --name-only pre-cleanup-claude-era` lists every file at that point.

The raw replies and run logs also remain outside the repository in `C:\masters_project_large\data\teacher_outputs\` (folders named `*_sonnet-5-5_*`). The prompt file `data/prompts/benchmark_generation_v6.md` still says in its human-only header that it was written for Claude. It is kept byte for byte because its SHA-256 (`348db6ff...`) is pinned in the Redhawk and Talon job scripts.

### 2.3 The grader (Codex): how benchmark answers are scored (decided 2026-11-12)

**What and why.** Every model's benchmark answers, the teacher's and every student's, are scored by one *grader*: Codex, a frontier model from OpenAI, run through the Codex command-line tool. For each answer the grader reads:
- the question;
- its choices, for a multiple-choice item;
- the benchmark's **reference key**;
- the model's **final answer**.

It then decides whether the answer is correct.

**Why not exact matching.** A language model is used because many correct answers are written differently from the key. `sum(x, na.rm = TRUE) / sum(!is.na(x))` gives the same mean as `mean(x, na.rm = TRUE)`, and "signed-rank test (Wilcoxon)" names the same test as "Wilcoxon signed-rank test". Exact matching would mark both wrong.

**Why one grader for everything.** The same grader, with the same instructions, scores every model, so a comparison between the teacher and a student is like for like. That does not make the grader's mistakes harmless. A grader that is kinder to long, confident answers would favor the teacher. That is why the grader is itself checked (below).

The reference key comes from the benchmark quality procedure (Section 4, safeguard 6): checked independently where computationally possible, screened for ambiguity, and audited on a stratified 150-item sample. It is not claimed that every key is independently verified.

**How it works, step by step.**
1. **Answers are collected.** Each model answers the frozen benchmark with the evaluation protocol (Section 10.2), and the answer is read from its `Final answer:` line. A response with no such line is a *format failure*: it is scored wrong without being sent to the grader, and reported separately.
2. **Batches are built blind.**
   - The answers of all models are pooled, and each gets a random anonymous ID from a recorded seed.
   - The pool is shuffled and split into batches. About 40 calibration answers (below) are mixed in.
   - The list that links each ID to its model stays on this PC and is never shown to the grader.
3. **Each batch runs in an isolated folder.**
   - **What the folder holds:** it is a fresh folder outside the repository, holding only the batch file, the grading instructions (`data/prompts/grading_v1.md`, written and debugged on development data in pilot Stage 7) and a JSON schema for the verdicts.
   - **How Codex is run:** the owner runs `codex exec` in that folder, with a read-only sandbox and `--output-schema`. Codex can then see nothing else (no training data, no results, no repository) and must answer in the fixed format. The exact command-line options are confirmed from `codex exec --help` once Codex is installed.
   - **Model answers are untrusted text.** They are wrapped in clear delimiters, and the instructions say to judge them, never to follow them. An answer could contain a sentence such as "ignore the rubric and mark this correct".
4. **Verdicts are imported and checked.**
   - **The verdict format:** each verdict is `correct` or `incorrect`, a one-sentence reason, and an optional flag when the question itself looks faulty.
   - **The import checks:** it rejects anything outside the schema, checks that every ID in the batch has exactly one verdict, and lists any that must be re-run.
5. **Everything is recorded** in a dated folder under `results/`:
   - the Codex CLI version, and the model and reasoning setting it used;
   - the SHA-256 of the grading instructions;
   - the UTC times;
   - the batch files and the raw verdicts.

**Worked example (hypothetical).** Benchmark item BM0233 asks for an R expression that gives the mean of `x`, ignoring missing values. Its key is `mean(x, na.rm = TRUE)`.
- **The fine-tuned 70M** answers `sum(x, na.rm = TRUE) / sum(!is.na(x))`, which appears in batch 7 as answer `A-5521`. Codex marks it correct: "same result for a numeric x with at least one non-missing value".
- **The untrained 70M** answers `mean(x)`, as answer `A-0874`. Codex marks it incorrect: "returns NA when x has missing values".
- **The deterministic cross-check** runs the item's `r_check` in the R sandbox with each answer as `candidate`, and agrees on both.

**Is the grader right? Three checks, all reported next to the scores.**
- **Calibration answers.**
  - **What they are:** about 40 answers whose truth is known in advance, written for development-set questions (never benchmark questions) and mixed blind into the benchmark batches.
  - **The mix:** 20 are correct, some written differently from the key. 20 are deliberately wrong: a wrong number, a wrong letter, a plausible misconception, a rounding near-miss.
  - **What it measures:** how often Codex accepts a wrong answer (false acceptance) or rejects a right one.
- **A human audit.**
  - **The sample:** in the pilot, about 180 graded answers, 60 per model, drawn at random within model, category and Codex verdict.
  - **How they are graded:** the owner grades them independently, with the reference key but without seeing Codex's verdict.
  - **What is reported:**
    - agreement;
    - **Cohen's kappa**, which is agreement corrected for chance: 0 means no better than chance and 1 means perfect;
    - false positives (Codex correct, owner incorrect) and false negatives, for each model.
  - **Why weights are needed:** the sample is stratified, so an overall error rate is computed with sampling weights. For example, if "incorrect" verdicts are oversampled, each audited "incorrect" answer counts for fewer real answers.
- **The deterministic cross-check.** For items a rule can grade, the rule's verdict is compared with Codex's on every answer, which gives hundreds of comparisons per model. The rules:
  - a number item is right if it is within the item's tolerance;
  - a multiple-choice item is right if it has the key's letter;
  - an R expression is right if the item's `r_check` accepts it as `candidate`, run in the R sandbox.

**Validity thresholds, and what happens if the grader fails** (fixed before the confirmatory evaluation; Section 4, safeguard 8).

- **The development check (pilot Stage 7).** Codex grades development-set answers from the teacher, the untrained 70M and the candidate students. Alongside it run a separate development calibration set (about 40 known-truth answers) and the deterministic cross-check, and the owner grades a blind sample of about 120.
- **The thresholds.** From these results, explicit thresholds are proposed, approved and written into the pre-registration before any benchmark answer is graded. They cover:
  - calibration accuracy, and the share of deliberately wrong answers that are accepted;
  - agreement with the deterministic cross-check on the items it can grade;
  - agreement with the owner, and Cohen's kappa;
  - **systematic bias:** the difference between models in how often Codex disagrees with the deterministic and human checks. This is judged mainly on the deterministic cross-check, which has hundreds of items per model, because 60 audited answers per model can only reveal large differences.

  The values stay blank until the development data exists.
- **The fallback grading method**, written into the pre-registration before any benchmark answer is graded, in full.
  - **The rules:** number, multiple-choice and R-expression items are graded against the reference key by the deterministic rules above.
  - **Short-text items** are graded by the owner, blind: answers from all models are pooled under the same anonymous IDs, against the reference key, using a written rubric.
  - **Computed every time:** the fallback score is computed for every benchmark evaluation, whether or not it is needed, so it never has to be built after results are known.
- **One rule decides which score is primary, and it is mechanical.** The validity checks are computed by a script, against the frozen thresholds, and recorded **before** the per-model accuracy table is produced.
  - **All thresholds met:** the Codex scores are the primary result.
  - **Any threshold missed:** this is a **grader-validity failure**. The main accuracy conclusions (criteria 1 and 2, and the analysis in Section 7) then use the **fallback scores**. The Codex scores are still kept, reported in full and labeled as having failed validation.
  - **Why this cannot favor one method:** nobody chooses between the two methods after seeing which gives better student results. The thresholds and the fallback are both frozen in advance.
- **If Codex fails on development data**, before any benchmark grading.
  - **First:** the grading instructions may be revised using development data only, and re-tested on development answers held back for that purpose, for at most a declared number of rounds.
  - **If it still fails:** the fallback becomes the primary method for the confirmatory evaluation from the start. Codex may still be run, but only as a reported secondary measure.
- **If the checks fail on the benchmark.** The result is reported as a grader-validity failure, and the fallback scores carry the main conclusions (above).
  - The grading instructions are never changed after benchmark results have been seen.
  - Any re-grading with revised instructions is **exploratory** (safeguard 8) and never replaces either pre-registered score.
- **An implementation bug,** for example answers mapped to the wrong model, is a documented bug fix: it is logged with its evidence, and the affected step is re-run. It is not a validity failure.

**What the grader is allowed to touch.**
- Codex grades benchmark answers and screens benchmark questions (safeguard 6c), and it does nothing else.
- Its outputs never enter training data, never filter training data, never choose hyperparameters and never choose the teacher setup.
- Before the first call, the owner confirms that OpenAI's terms allow this evaluation-only use, and the confirmation is recorded here.

**Usage and cost.** Codex runs on the owner's workspace subscription. Its use counts against the plan's included allowance, and work beyond that may need purchased credits, so it is **not assumed to be free**.
- **The usage pilot.** About 100 development questions are screened and about 100 development answers graded. This measures the tokens per judgment, the time, and the share of the allowance used. It then projects:
  - the benchmark screen (about 1,000 questions);
  - the pilot grading (3 models × 1,000 answers, plus about 40 calibration answers);
  - the full grid (25 models × 1,000, about 25,000 answers).
- **Before and after every run:** the expected usage is stated before it, and every batch is logged in `docs/logs/cost_log.md`.

**What could go wrong.**
- **Leniency or harshness**, overall or for one answer type. For example, it might accept a number that is right but rounded differently from what the question asks.
- **Favoring style:** long, confident answers (the teacher's) may be judged more kindly than terse ones (the students').
- **Nondeterminism:** the same batch run twice can give a few different verdicts. The first complete run is the one used, and any re-runs are recorded.
- **A faulty question** (ambiguous, or missing information) can make any answer look wrong. The screen and the audit (safeguard 6) reduce this, and the grader's question flag records suspected cases.
- **Version drift:** the model behind Codex can change over time. The CLI version and the model are recorded with every batch, and the grading for one comparison is done in one window with one setup.

---

## 3. Benchmark design

- **Size:** about 1,000 questions, held out and frozen.
- **Content mix (proposal, to confirm with Dr. Lee):**

  | Category | Share |
  |---|---|
  | Numerical problems with one correct number | 30% |
  | Conceptual (multiple choice) | 20% |
  | R code generation | 20% |
  | R code interpretation and debugging | 15% |
  | Interpretation of statistical output | 15% |

  Difficulty: intro 40%, intermediate 35%, graduate 25%. Answer types: number, multiple choice, R expression, short text. The 20-slot pattern in `code/generation/generate_benchmark.py` (`PATTERN`, `blueprint`) implements this mix, so any 20 consecutive slots have it.
- **Short, checkable answers.** Every question has a canonical answer of about 20 tokens or less, so grading works on the first line of a model's output. The Pythia probe showed the students do not stop on their own (`docs/models/pythia_behavior_analysis.md`).
- **Reference keys and grading.**
  - **The keys.** Every item has a reference key, made and checked by the benchmark quality procedure (Section 4, safeguard 6). The check is honest about its limits: independent where computationally possible (R recomputes number keys and tests R-code items), a screen of every question for ambiguity, and a stratified 150-item manual audit. It is not claimed that every key is independently verified.
  - **The score.** Every answer, the teacher's and the students', is graded by the grader (Section 2.3). It judges whether the final answer is equivalent to the reference key, with rounding judged as the question asks.
  - **The deterministic cross-check.** A number item is checked within the item's tolerance, a multiple-choice item by its letter, and an R code item by running the item's `r_check` (in the R sandbox) with the answer as `candidate`. This is reported separately and never replaces the grader's score.
  - **Not graded:** free-text explanations are not graded for accuracy.
- **Integrity rules.**
  - Freeze before any training: store the file and its SHA-256 checksum in `benchmark/`.
  - Never generate training data from benchmark prompts, slots or paraphrases.
  - Run n-gram and embedding decontamination between the benchmark and every training set (Section 4).
  - Do not tune hyperparameters on the benchmark. If tuning is needed, carve out a separate small dev set.

---

## 4. Safeguards: one teacher writes both the benchmark and the training data

**The problem in plain terms.** Qwen writes the benchmark (the exam) and the training data (the study material). Without care, three things can go wrong:

1. **Leakage:** a training example is the same as, or a close paraphrase of, an exam question, so a student "remembers" the answer instead of solving it.
2. **Shared mistakes:** if Qwen gets a kind of question wrong, the wrong answer can appear in the training data and in the benchmark key.
   - **In the training data, this is accepted by design** (safeguard 9): the study measures how close a student gets to its teacher, mistakes included.
   - **In the benchmark, it is not:** a wrong key would mark a right answer wrong for every model, so the keys go through the benchmark quality procedure (safeguard 6).
3. **Flattering the teacher:** the teacher's accuracy on an exam it wrote itself is optimistic, because the questions sit inside its comfort zone. That inflates the denominator of the retained-accuracy ratio.

**Safeguards, in the order they apply.**

1. **Separate generation prompts.** The benchmark is written only with `data/prompts/benchmark_generation_v6.md`. Training data will use its own prompt file (for example `data/prompts/training_generation_v1.md`, to be written in Phase 4). That prompt asks for a different format: a worked answer ending in a marked final answer, in the `Question:` / `Answer:` template. Neither prompt is ever used for the other purpose.
2. **Separate IDs and folders.**
   - Benchmark questions carry IDs `BM0001` to `BM1000`.
   - The **development set** (about 200 items, `DV0001`+) is built with the same automated pipeline: R keys, `verify` and `dupcheck` (safeguard 6a and 6b). It skips the screen and the manual audit, because it is not the measuring instrument. It is used for hyperparameter choice, troubleshooting, evaluation debugging and grader validation (safeguard 8, Section 2.3).
   - Precision-test slots use `BM8xxx`. Smoke-test slots use `BM9001` and up. Neither is ever part of the benchmark or the training data.
   - Training examples get their own prefix (for example `TR000001`) and their own dated run folders.
   - The code refuses to mix smoke and main slots, and the same rule will be added for training slots.
3. **Freeze first.** The benchmark is finished, hashed (SHA-256) and stored read-only before any training example is generated. A changed hash means the benchmark was touched, and the run stops.
4. **Variety before scale, with matching topic coverage.**
   - **Shared taxonomy:** the benchmark, the development set and the training data use the **same taxonomy and target proportions**, so a poor benchmark score cannot simply mean the training data never covered the topic.
   - **Independent sampling:** each set's questions, parameters, numbers and scenarios are sampled independently, from separate seeds. Subtopics are **not** split between the sets. (A separate benchmark with held-out subtopics, to test generalization, is a possible later study.)
   - **Fewer repeats:** the slot design is changed so that no (category, subtopic, difficulty) combination repeats more than necessary. The taxonomy draft in `data/taxonomy/` (not yet committed) and a planned `variety.py` are the start of this. `dupcheck` (in `generate_benchmark.py`) compares every new question with earlier ones by text similarity, with numbers kept and with numbers masked, so near-copies are listed for review.
5. **Decontamination of every training set.** Before a training set is used, every training example is compared with every benchmark question and every development-set question.
   - **n-gram overlap:** shared word sequences, for example any shared run of 8 or more words.
   - **Embedding similarity:** a sentence-embedding model turns each text into a vector, and a high cosine similarity means "says the same thing in other words".

   Matches above the threshold are removed from the **training** set, never from the benchmark (it is frozen). The thresholds and the counts removed are logged.
6. **The benchmark quality procedure (benchmark only; decided 2026-11-12).**

   The benchmark is the measuring instrument, so its questions and keys are made as accurate as is reasonably possible. Its answers are **independently checked where computationally possible, screened for ambiguity, and subjected to a stratified 150-item manual audit**. It is not claimed that every key is independently verified.

   - (a) **R recomputes the number keys.**
     - **How:** each number item comes with R code (`r_solution`) that recomputes the answer. The script runs that code in the R sandbox (safeguard 10), and R's printed value, rounded as the question asks, becomes the key. This catches arithmetic and typing slips; in a Claude-era trial, for example, a typed 207.01 where the calculation gives 207.02.
     - **The field rule:** the `r_solution` field must be present in every benchmark reply. Where R cannot compute the answer, for example a conceptual question, it is an explicit "not applicable" empty value, so the model is never pushed into writing meaningless R.
   - (b) **R checks test the R code items.**
     - **How:** each R-expression item has an `r_check` that receives an answer as `candidate`. `verify` runs it, in the sandbox, against the key, which it must accept, and against deliberately wrong answers, which it must reject. This way each R item has a well-defined expected behavior.
     - **A flagged check:** one that accepts a wrong answer is flagged as "vacuous".
   - **What (a) and (b) cannot show.** R runs the teacher's own code, so it checks arithmetic and code behavior, not whether the teacher read the question correctly. Consistent code for a misread question gives a consistent wrong key. Steps (c) and (d) cover that.
   - (c) **Codex screens every question.**
     - **How:** the grader (Section 2.3) reads each benchmark question, without its answer, and flags ambiguity, missing information or invalid statistical assumptions, with a reason. The owner reviews **every** flagged question and fixes it, replaces it, or keeps it with a note.
     - **What is recorded:** the flag rate and the decisions go in `data/verification_logs/`.
     - *Example:* "A sample of 30 observations has a sample standard deviation of 12. What is the exact probability that the sample mean exceeds 50?" is flagged, because neither the population distribution nor its mean is given. A careful answer would say it cannot be determined.
   - (d) **A manual audit of 150 items.**
     - **The sample:** a seeded random sample, stratified by category in proportion to the benchmark mix, that **includes items that passed every automated check**.
     - **Per item:** the owner works out the answer independently and records whether the key is correct, whether the question is clear, and whether exactly one answer is right.
     - **What is reported:** the audit's error rate, with its confidence interval, describes the benchmark **before** corrections. The original results are kept.
     - **After corrections:** errors are fixed, and a claim about the error rate after the fixes needs a fresh, independent random sample.
     - *Worked example:* if 0 of 150 audited items are wrong, the approximate 95% upper bound on the error rate is 3 / 150 = 2% (the "rule of three").
   - **Retired 2026-11-12.** The blind re-solve by Qwen, the triage step and the external different-family verifier (`docs/archive/retired_verification_2026-11-12.md`).
7. **Reporting rule.**
   - **The benchmark** is reported as **teacher-generated**, kept distinct from any externally sourced evaluation, together with how its keys were checked: R where computable, the screen and its flag rate, and the audit and its error rate.
   - **Teacher accuracy** is always reported with the caveat that the teacher wrote the benchmark.
   - **The scores** are reported with the grader's calibration results, the human audit (agreement, kappa, and false positives and negatives by model) and the deterministic cross-check next to them.
   - **The training data** is described as teacher output retained without correctness-based filtering, whose correctness is unknown (safeguard 9).
8. **Development set vs confirmatory evaluation** (decided 2026-11-11).
   - **What the benchmark is for:** only **prespecified evaluations**. Hyperparameters are chosen, and the evaluation harness is debugged, on the **development set** only.
   - **What is frozen first:** the hyperparameters, seed, evaluation protocol, scoring rules and analysis are frozen in a dated pre-registration **before** the training run that is evaluated.
   - **After the first benchmark evaluation:** no performance-motivated change is allowed within the confirmatory experiment. Documented implementation bug fixes remain permitted; each is logged with its evidence, and the affected step is re-run.
   - **Follow-up experiments** motivated by benchmark results are labeled **exploratory** everywhere, reported separately, and never replace the confirmatory findings.

   **Why this matters, with an example:** suppose the 70M scores poorly and the learning rate is raised and the model retrained until the score improves. No benchmark question was ever trained on, but the benchmark has still been used to tune the experiment, so its score is no longer an honest test.

   **How the development set chooses the hyperparameters (decided 2026-11-12).**
   - **What a candidate is.** *Hyperparameters* are the training settings we choose ourselves, such as the learning rate (how big each weight adjustment is) and the number of epochs (how many times the model reads the training set). A *candidate* is one combination of settings from a small list declared in advance. Each candidate is trained separately and gives its own student, and the scorecard below picks the winner.
   - **Primary scorecard: held-out loss.**
     - **What is held out:** about 150 extra training-style examples (question, the teacher's worked answer, final answer, end token) are kept out of training and decontaminated like the rest.
     - **What loss measures:** how surprised the student is by the teacher's text, token by token (cross-entropy). Lower is closer to the teacher. The Hugging Face `Trainer` computes it automatically.
   - **Supplementary scorecard: teacher-answer match** on the 200 development items. This is how often the student's final answer agrees with the teacher's key:
     - a number within the item's tolerance;
     - the same multiple-choice letter;
     - an R expression by its behavior (the item's `r_check`, run in the R sandbox, with the student's answer as `candidate`);
     - short text by a normalized match (lowercase, spaces removed).
   - **Codex is never used to choose hyperparameters** (Section 2.3).
   - *Example:* candidates A, B and C reach held-out losses of 1.42, 1.18 and 1.21, so B wins. Its teacher-match rate (say 29% against 23% and 28.5%) is reported with it.
9. **Training data is retained without correctness-based filtering (decided 2026-11-12).**

   Qwen-generated training examples are retained without correctness-based filtering. Their correctness is unknown and may vary by question category. This is an intentional property of the experimental design: the study asks whether distillation lets a student approach the teacher, not whether it produces a perfect student. The resulting student models are evaluated independently on a frozen benchmark.
   - **What is still checked on every training example:**
     - format and parse: a complete, parseable reply tied to its slot, with no thinking aloud in the question;
     - duplicates (`dupcheck`);
     - decontamination against the benchmark and the development set (safeguard 5);
     - the 2,048-token limit.

     The `r_solution` field stays in each reply, but its correctness is not required.
   - **What this means for the results.** A student can learn the teacher's mistakes, and that is part of what is measured. *Example:* suppose the teacher answers 95% of the binomial questions on the benchmark correctly but only 70% of the output-interpretation questions. Its training examples on output interpretation probably contain more errors too, so a student's weakness there may partly be inherited. The teacher's graded accuracy by category, on a benchmark whose keys were checked (safeguard 6), shows where this is likely.
10. **Model-written R code runs only in a sandbox (decided 2026-11-12).**

    R code written by a model (the teacher's `r_solution` and `r_check`, and later the students' R answers) is *untrusted*: by mistake or otherwise, it could delete files, read personal files or reach the internet. The pattern screen in `generate_benchmark.py` (`UNSAFE_R`, which refuses calls such as `system()` or `download.file()`) stays as an extra layer. A list of patterns can always be bypassed, so it is not relied on.
    - **How the sandbox works.**
      - **Where it runs:** every such run happens inside WSL2 (a Linux system that runs inside Windows), under *bubblewrap*, a small sandboxing program.
      - **What it blocks:** no network; no Windows drives (automount is off, so the repository, credentials and personal files are not visible); and no access to anything except a temporary work folder.
      - **Its limits:** memory, CPU time, output size and number of processes, plus a hard time limit that is also enforced from the Windows side.
      - **How code goes in and out:** the code goes in on standard input, and the printed result comes back on standard output.
    - **It fails closed.** If the sandbox is not set up, or its self-test fails, the scripts refuse to run R. They never fall back to running R directly, not even for the repository's own tests.
    - **It is tested.** A self-test runs R code inside the sandbox that tries to:
      - open a URL;
      - read a planted "canary" file;
      - see the Windows drive;
      - write outside the work folder;
      - use too much memory;
      - loop forever;
      - leave a background process running;
      - write too much output.

      Each attempt must fail. The self-test runs before first use and before every batch.
    - **It gives the same answers.** R 4.3.1, the version used so far, is installed inside the sandbox, and the regression snapshot must reproduce identical R output through it.
    - **Status: set up and tested on 2026-11-12** (`code/generation/r_sandbox.py`; rebuild steps in `recovery/r_sandbox.md`).
      - **The setup:** WSL2 Ubuntu 24.04, bubblewrap 0.9.0, R 4.3.1.
      - **The limits on each run:** 4096 MB of address space (R needs about 4 GB reserved just to start), 10 CPU seconds, 20 wall seconds, 1 MB of output, 16 MB per file, 64 MB of `/tmp`, and 256 processes.
      - **The self-test:** all 13 checks pass. It found one gap while being built: the box's own root folder was writable, though in memory only. That root is now read-only.
      - **Earlier runs:** the two Stage A replies scored earlier on 2026-11-12 ran in Windows R behind the pattern screen only, before this rule existed.

**Worked example.**
- Benchmark item BM0412 asks for P(X = 2) when X ~ Binomial(5, 0.4).
- A training example generated later asks for P(X = 3) when X ~ Binomial(5, 0.4). With numbers masked, `dupcheck` scores the pair 0.93 (same template). The embedding check also flags it. The training example is dropped.
- A third training example asks for a Poisson probability with similar wording. It scores 0.55 and stays: it trains the same skill without copying the exam.

**Limitations that remain, stated honestly.**
- **The students learn the teacher's mistakes.** The training data is not filtered for correctness (safeguard 9), so how well a student can do is limited by how often its teacher is right. That is part of the design, and it is reported by category.
- **Some benchmark keys may still be wrong.** R checks arithmetic and code behavior, not whether the code answers the question as written, so a misread question with consistent code gets a consistent wrong key. The screen and the 150-item audit reduce this, and the audit's error rate estimates what remains. They cannot remove it.
- **The grader can be wrong, and not equally for every model.** The calibration answers, the human audit and the deterministic cross-check measure this (Section 2.3). They cannot remove it, and 60 audited answers per model can only reveal large differences between models.
- Decontamination thresholds trade leakage against over-removal. Any threshold leaves some near-paraphrases in, and removes some harmless examples.
- The benchmark measures skill *as Qwen frames it*. Results say how well students learn from this teacher, not how well they would do on an independent human-written exam.

---

## 5. Phases and checklists

### Phase 1: Define the research question
- [x] Domain: statistics and R programming (final)
- [x] Define "successful specialization" with four criteria (Section 1)
- [x] Pre-register the success thresholds and primary metrics (dated 2026-09-29; criterion 4 deviation dated 2026-11-06)

### Phase 2: Choose teacher and student models
- [x] Students: Pythia 70M, 160M, 410M, 1B (deduped only), final `step143000` checkpoints pinned by commit SHA (`docs/models/model_versions.md`)
- [x] Probe how the base models behave (local CPU, 2026-10-06): `code/evaluation/pythia_probe.py`, results in `results/pythia_probe/`, findings in `docs/models/pythia_behavior_analysis.md`. Key findings:
  - the models never stop on their own (0 of 192 generations ended with the end token);
  - outputs loop;
  - arithmetic is wrong at every size;
  - the 1B config names the wrong stop token.
- [x] Teacher: Qwen3.6-27B, decided 2026-11-06 after Anthropic ruled out Claude (Section 2.1, `docs/models/teacher_model_evaluations.md`)
- [x] Pin the vLLM version for the Talon deployment: `vllm==0.32.0`, decided 2026-11-12 and recorded in `docs/models/model_versions.md`

### Phase 3: Create the evaluation benchmark
The benchmark comes before the pilot because the pilot needs something frozen to score against. It is the real, full-size benchmark for the whole project.
- [x] Generation pipeline built and tested (Claude era, Section 2.2): blueprint, prompt v6, R-written number keys, automatic checks, regeneration, `verify`, `dupcheck`
- [x] Qwen client for the cluster deployments: `code/generation/open_teacher_test.py`, with `redhawk` and `talon` backends. It appends the schema text to the system prompt because these engines do not enforce it.
- [ ] Talon bring-up (`docs/clusters/talon_setup.md` Section 9):
  - pin the vLLM version and the GPU request style (`--gres` or `--gpus`);
  - set `SETTINGS_REVIEWED=yes` after a review;
  - run a scheduler acceptance test;
  - download the BF16 weights;
  - run smoke stage A;
  - run the throughput stage T.
- [ ] Review the Redhawk pipeline job 2511641 (finished, results not yet checked) and record it in `docs/logs/compute_log.md`
- [ ] Require the `r_solution` and `working` fields in every benchmark reply ("not applicable" where R does not apply), then update the regression fixture (Section 4, safeguard 6a)
- [x] **Set up the R sandbox** (WSL2 plus bubblewrap) and pass its security self-test before any further model-written R is run (Section 4, safeguard 10): done 2026-11-12, 13 of 13 checks
- [ ] Choose the teacher precision (BF16, FP8 or 4-bit) with the pre-registered protocol in Section 2.1, before any benchmark generation. The sample-size calculation and the feasibility gate come first.
- [ ] Fix slot variety before any 1,000-question run (Section 4, safeguard 4), then re-run `dupcheck`
- [ ] Decide whether output-interpretation items need an automatic consistency check of the printed output, or should have R generate the printout. About a third of the trial items had small inconsistencies; no keys were affected.
- [ ] Generate about 1,000 benchmark questions and the ~200-item development set with Qwen on Talon at the chosen precision; regenerate failures; `verify` (R in the sandbox) and `dupcheck` the whole set
- [ ] Keep short-text items tightly constrained (a name, a term, a value); rewrite open-ended ones as multiple choice or drop them
- [ ] **Codex setup** (Section 2.3). You install the Codex CLI and confirm OpenAI's terms. The batch tool is built: isolated workspace, verdict schema, validating import, tests with a fake `codex`. The usage pilot runs on development items.
- [ ] **Codex screen of every benchmark question**; the owner reviews every flag (Section 4, safeguard 6c)
- [ ] Manual audit of about 150 random benchmark items (Section 4, safeguard 6d)
- [ ] Check every answer key where computationally possible, strongest check first (Section 4, safeguard 6)
- [ ] **Freeze** the benchmark (hash it, store read-only) before any training data exists
- [ ] Record every cluster job in `docs/logs/compute_log.md`

### Phase 4: Pilot (1k examples, Pythia 70M, end to end)
Goal: prove the whole pipeline on Talon at small scale and measure real GPU time before committing to the full grid. Plain-language walkthrough: `docs/methodology/pilot_plan.md`.
- [x] Cluster access: Redhawk (2026-10-01), Talon (account active and probed 2026-11-06)
- [ ] Write the training-data prompt (separate from the benchmark prompt, Section 4). Use one fixed template (`Question: ...` / `Answer: ...`) with short answers ending in a marked final answer. Every example ends with the end-of-text token, id 0, set explicitly because the 1B config names the wrong token. Reasons: `docs/models/pythia_behavior_analysis.md` Sections 3.2 and 5.
- [ ] Generate about 1,250 training questions and teacher answers on Talon, plus about 150 held-out examples for the development loss. They are retained without correctness-based filtering: format checks only (Section 4, safeguard 9).
- [ ] Check every training example against the Pythia **2,048-token** limit (its `max_position_embeddings`): reject or deliberately shorten an over-length example, never truncate it silently; record the share affected
- [ ] Decontaminate against the frozen benchmark and the development set; keep the final 1,000
- [ ] Write the training script (Hugging Face `Trainer`, full fine-tune, every setting explicit) and its pre-pilot tests; a Talon training smoke run
- [ ] Build and debug the evaluation harness on the development set only. It includes:
  - the deterministic cross-check graders;
  - the "R code runs" check, in the sandbox;
  - the development scorecard (held-out loss and teacher match);
  - Codex grading, with grading instructions `grading_v1`;
  - both calibration sets;
  - the grader validation that sets the validity thresholds (Section 2.3).
- [ ] Choose the hyperparameters on the development set (Section 4, safeguard 8). Then freeze, in a dated pre-registration:
  - the hyperparameters and seed;
  - the evaluation protocol, scoring rules and analysis;
  - the grader setup, its validity thresholds, the fallback grading method and the rule that picks the primary score, and the audit design.
- [ ] Confirmatory run:
  - fine-tune Pythia 70M once with the frozen settings;
  - evaluate the untrained and fine-tuned 70M and the teacher on the frozen benchmark;
  - Codex grades in blind batches with the calibration answers; the deterministic cross-check runs, and the owner audits about 180 answers;
  - analyze retained accuracy, McNemar and criterion 4b.
- [ ] Record GPU-hours, queue wait and peak GPU memory for every job in `docs/logs/compute_log.md`
- [ ] Go/no-go review:
  - Does the pipeline run end to end?
  - Is the projected GPU time for 50k to 200k acceptable?
  - Are the validity thresholds sensible?
  - Did the grader pass its validity thresholds, and what will Codex usage be for the full grid?
- Reuse rule: if the pilot 1k set passes its format, length and decontamination checks, it becomes the 1k subset of the nested sets in Phase 6 (log the reuse).

### Phase 5: Measure baseline performance
- [ ] Evaluate each pretrained student before specialization
- [ ] Evaluate the teacher on the same benchmark
- [ ] Record correctness (graded by Codex, Section 2.3), response validity, runtime, memory use and the other efficiency measures (Section 6)

### Phase 6: Create the distillation training set
- [ ] Generate a large pool of domain-specific questions with the training prompt (never the benchmark prompt)
- [ ] Have the teacher generate answers, explanations and R code
- [ ] Deduplicate, and decontaminate against the frozen benchmark (Section 4)
- [ ] Use the same checked set for every student size. It is retained without correctness-based filtering (Section 4, safeguard 9).
- [ ] Build nested subsets (1k, 10k, 50k, 100k, 200k as feasible; 50k minimum). The 200k generation plan is in `docs/clusters/talon_setup.md` Section 8.

### Phase 7: Check teacher-generated training data (no correctness filtering)
Training examples are retained without correctness-based filtering (Section 4, safeguard 9); this phase checks everything except correctness. The earlier plan to verify the training data with an external model is archived in `docs/archive/retired_verification_2026-11-12.md`.
- [ ] Format and parse checks on every example; regenerate or drop failures
- [ ] Duplicates (`dupcheck`), and decontamination against the frozen benchmark and the development set (Section 4, safeguard 5)
- [ ] The 2,048-token limit: reject or deliberately shorten an over-length example, never truncate it silently
- [ ] Record the pass rate, the duplicate and decontamination removals and the length distribution

### Phase 8: Specialize the student models
- [ ] Fine-tune each Pythia student on the checked dataset (Talon)
- [ ] Keep the training procedure consistent across sizes: optimizer, schedule, epochs, sequence length, seeds
- [ ] Decide and document the training precision recipe (Section 10)
- [ ] Compare training-set sizes

### Phase 9: Re-evaluate specialized students
- [ ] Run the same frozen benchmark
- [ ] Grade with Codex (Section 2.3): blind batches with calibration answers, the deterministic cross-check and the human audit; check the results against the pre-registered validity thresholds
- [ ] Compare each student before and after specialization
- [ ] Compare students with each other and with the teacher

### Phase 10: Measure computational efficiency
- [ ] Record parameter count, model file size, peak GPU memory, latency, GPU time per query and training GPU-hours for every student and the teacher, on the same GPU type (criterion 4)
- [ ] Analyze performance gained or lost as a function of model size and data amount

### Phase 11: Statistical analysis
- [ ] Apply the tests in Section 7 to decide which differences are significant

### Phase 12: Identify the size-performance tradeoff
- [ ] Locate any point where shrinking the model causes substantial performance loss
- [ ] Assess whether very small specialized models retain useful capability relative to the teacher

### Phase 13: Report results
- [ ] Written report: methodology, the benchmark quality procedure, grading and its validation, statistical analysis, efficiency results, limitations (Section 4)
- [ ] Presentation
- [ ] Discussion of the practical implications of small specialized models versus large general-purpose ones

---

## 6. Metrics

**Quality**
- Accuracy (primary; macro-averaged across categories; graded by Codex against the reference key, Section 2.3), broken down by category and difficulty
- Retained fraction of teacher accuracy, using the lower bound of the bootstrap 95% CI, judged against the 70 / 85 / 95% tiers
- Deterministic cross-check accuracy, reported separately (Section 3)
- Response validity: well-formed, parseable, R code that runs (in the sandbox)
- Optional: pass@k for code tasks (the share of questions where at least one of k attempts is correct)

**Efficiency** (teacher and students on the same GPU type, Section 1.2)
- Parameter count and on-disk model size (criterion 4a)
- Peak GPU memory at inference
- GPU time per query and median latency per query (criterion 4b); tokens per second
- Training cost: GPU-hours and wall-clock time
- Derived: accuracy per parameter, accuracy per GPU-hour

**Data quality**
- First-attempt pass rate of generated questions, soft-flag rate, duplicate rate
- Benchmark quality: R-check outcomes, the Codex screen's flag rate and the owner's decisions, the manual audit's error rate with its CI (Section 4, safeguard 6)
- Number of training examples removed by decontamination, and the share rejected or shortened for length

**Grader validity** (Section 2.3)
- Calibration accuracy and the false-acceptance rate on deliberately wrong answers
- Agreement with the deterministic cross-check, by model
- Human audit: agreement, Cohen's kappa, false positives and false negatives by model, with sampling weights for any overall rate

**Development set** (hyperparameter choice only, Section 4, safeguard 8)
- Held-out loss (primary) and the teacher-answer match rate

---

## 7. Statistical analysis

Planned approach, to refine with Dr. Lee:
- **McNemar's test** for paired comparisons of binary correctness between two models on the same benchmark items. It looks only at the items where the two models disagree.
- **Bootstrap confidence intervals** (resampling benchmark questions) for accuracy, for differences in accuracy, and for the student/teacher ratio.
- **Mixed-effects logistic regression** of correctness on model size and data size, with question as a random effect, to model the size-performance relationship while allowing some questions to be harder than others.
- **Multiple-comparison correction** (Holm, or Benjamini-Hochberg) across model pairs.
- Seed-to-seed variance where multiple seeds are run.
- **Curve fitting** (for example log-size against accuracy) and changepoint/knee analysis to locate the tradeoff point.

---

## 8. Storage layout

Storage is split in two. **Small, important items live in the project repository** at `C:\dev\masters-project`, the main working copy, backed up to the private GitHub repository `jaxsonbugg/masters-project`. **Large items live outside the repository** so they stay out of Git. Because they are not backed up, each one must be reproducible from a recovery doc in `recovery/`. All locations are read from `configs/paths.yaml`; code never hardcodes a path.

### 8.1 Project repository (`C:\dev\masters-project\`, backed up on GitHub)

| Folder | Purpose |
|---|---|
| `docs/` | Project documents in topic subfolders: `methodology/` (this workflow, the pilot plan), `models/` (model versions, teacher evaluation, Pythia behavior), `clusters/` (cluster selection, Talon setup), `logs/` (compute and cost logs), `guides/` (Git notes), `archive/` (retired methods, kept for reference only). The only file at the `docs/` root is `progress_update.md`. New kinds of document get a new, clearly named folder (for example `meetings/`, `report/`) |
| `recovery/` | Rebuild instructions for everything stored outside the repository, one file per item, written from `_TEMPLATE.md` |
| `benchmark/` | The frozen benchmark, its checksum and a README (empty until Phase 3 ends) |
| `data/prompts/` | Prompts: benchmark generation v6; the training prompt and the grading instructions (`grading_v1`) later |
| `data/verification_logs/` | Benchmark quality records: R-check results, the Codex screen's flags with the owner's decisions, and the manual audit (Section 4, safeguard 6) |
| `code/generation/` | Benchmark blueprint and checks (including the R key step), the teacher client, the throughput report |
| `code/verification/`, `code/training/`, `code/analysis/` | Benchmark quality tools (screen import, audit sampler) and decontamination; fine-tuning code; statistics and plots (later phases) |
| `code/evaluation/` | Benchmark runners and metrics; currently the Pythia probe |
| `code/tests/` | Local test suites: the Redhawk and Talon job scripts with fake cluster programs, the teacher client, the throughput report, and the regression snapshot of the shared benchmark functions |
| `configs/` | `paths.yaml`, and the Redhawk (`configs/redhawk/`) and Talon (`configs/talon/`) Slurm and setup scripts |
| `environment/` | Pinned Python packages |
| `results/` | Metrics, tables, figures and small logs, including the dated grading folders (batches, verdicts, Codex setup) |
| `report/` | Final paper and slides |

### 8.2 Outside the repository (not backed up)

**This PC, `C:\masters_project_large\`:**

| Folder | Purpose |
|---|---|
| `models/pythia/` | The four base checkpoints, files kept exactly as distributed (`recovery/pythia_base_models.md`) |
| `models/finetuned/` | Fine-tuned students, by size and data size |
| `data/teacher_outputs/` | Raw teacher generations, including the archived Claude-era trials |
| `data/training_sets/` | Training sets (1k to 200k), retained without correctness-based filtering (`training_data` in `configs/paths.yaml`; created when the first set is built) |
| `cache/`, `logs/`, `envs/` | Caches, large logs, Python virtual environments (`recovery/python_env.md`) |
| Codex grading workspace | A fresh folder per batch, outside the repository (its location is added to `configs/paths.yaml` when the batch tool is built) |

**The R sandbox** is a WSL2 Ubuntu system on this PC, outside the repository (Section 4, safeguard 10; `recovery/r_sandbox.md`).

**Clusters.** Redhawk and Talon **share one home folder** (`/home/buggjm`). It has a 500 GB hard quota and a 480 GB soft quota; about 17 GB was in use on 2026-11-06.
- Redhawk work lives in `/home/buggjm/masters_project`.
- Talon work lives in its own folder, `/home/buggjm/talon_project` (repo, models, teacher_outputs), so the two can never overwrite each other.

**Teacher outputs are expensive to recreate.** They cost GPU-hours and are not deterministic (sampling at temperature 1.0), so a compressed backup of the 50k training set is kept.

---

## 9. Timeline (two semesters)

| Period | Focus |
|---|---|
| Semester 1, early | Design, teacher choice, cluster access, build and freeze the benchmark (Phase 3), 1k / 70M pilot (Phase 4) |
| Semester 1, mid | Baselines for all students and the teacher; go/no-go on scaling up |
| Semester 1, late | Generate and check distillation data (50k first) |
| Semester 2, early | Fine-tune all students; re-evaluate; expand the data-size axis if feasible |
| Semester 2, mid | Efficiency measurements, statistical analysis, tradeoff analysis |
| Semester 2, late | Report and presentation |

Dates are placeholders until the program's real deadlines are known.

---

## 10. Risks and open decisions

### 10.1 Risks and mitigations

| Risk | Mitigation |
|---|---|
| GPU time and queue waits on Talon (shared nodes, 3-day job limit; Research Computing confirmed in writing on 2026-11-12 that there is no GPU-hour cap, but the fair-share policy lengthens waits after heavy use) | Throughput stage T measures examples per GPU-hour before the big runs; the 200k run is split into resumable jobs under 3 days, using up to 4 single-GPU jobs side by side (allowed); run 50k across all sizes first |
| Talon unavailable or the settings wrong | Redhawk llama.cpp pipeline kept as a fallback, with its executable logic unchanged (only three comment lines were repointed on 2026-11-07); every Talon script is a draft until reviewed |
| Shared 500 GB home quota (Redhawk and Talon together) | `fetch_talon.sh` reads the quota and refuses a download that would pass the soft limit; ask Research Computing for more space before the 200k run |
| Same teacher writes the benchmark and the training data | Section 4: separate prompts and IDs, freeze first, decontamination, the benchmark quality procedure, stated limitations |
| Benchmark keys wrong in ways R cannot see | Codex screen of every question with the owner's review, a 150-item manual audit with its error rate reported; teacher accuracy reported with the caveat |
| Teacher errors in the training data | Retained by design (Section 4, safeguard 9) and reported; the teacher's graded accuracy by category shows where its examples are likely weak |
| Near-duplicate questions at scale | Slot-variety redesign and `dupcheck` before the 1,000-question run |
| Pythia models are base models (not instruction-tuned), have a 2,048-token context and never stop on their own | One fixed `Question:`/`Answer:` template, short answers, explicit end-of-text token id 0, a pre-declared stop rule |
| Very small models may score near zero, hiding differences | Easier items, plus partial-credit and validity metrics |
| Benchmark contamination | Decontamination, checksum freeze, a separate dev set |
| Grader errors or bias (leniency, or favoring the teacher's longer answers) | Reference key, blind pooled batches, calibration answers, the human audit, the deterministic cross-check, and validity thresholds with pre-registered failure rules (Section 2.3) |
| Codex usage limits (included allowance; credits may be needed) | A usage pilot and projection before the screen and the grading; the expected usage stated before every run |
| Untrusted model-written R code | Runs only in the sandbox, which fails closed (Section 4, safeguard 10) |
| Precision correctness sample too large to judge by hand | Feasibility gate: BF16 by default and any comparison exploratory; the margin is never widened (Section 2.1) |
| Confounded comparisons across sizes | Identical recipe, data, seeds and evaluation for all students |

### 10.2 Open decisions

- [ ] **Grader setup** (Section 2.3), fixed before the confirmatory evaluation:
  - the Codex CLI version, the model and its reasoning setting;
  - the grading instructions `grading_v1` and the batch size;
  - the owner's confirmation that OpenAI's terms allow this evaluation-only use;
  - the usage-pilot results and the projection for the full grid.
- [ ] **Grader validity thresholds, the fallback grading method (including the short-text rubric) and the primary-score rule** (Section 2.3), set on development data and frozen before any benchmark answer is graded.
- [ ] **Grader audit design for the full grid** (beyond the pilot's 180 answers), set after the pilot.
- [ ] **Teacher precision details** (Section 2.1).
  - **FP8:** an official FP8 checkpoint exists (`Qwen/Qwen3.6-27B-FP8`).
  - **4-bit:** no official release exists; the rule for a community checkpoint is decided (Section 2.1). Still open: which candidate, if any, passes the checks (done at Stage 1.3, before download).
  - **Still to write:**
    - the rationale for the 3-point margin;
    - the power (80% proposed);
    - the assumed discordance values and their source;
    - the owner's cap on hand judgments for the feasibility gate.

    The sample sizes follow from these.
- [x] **R sandbox limits** (decided and tested 2026-11-12): 4096 MB address space, 10 s CPU, 20 s wall, 1 MB output, 16 MB per file, 64 MB `/tmp`, 256 processes (Section 4, safeguard 10; `configs/paths.yaml`).
- [ ] **Talon settings still unverified:**
  - the vLLM version pin: resolved 2026-11-12, `vllm==0.32.0`;
  - `TALON_GPU_STYLE`: resolved 2026-11-11, `gres` (both styles accepted by Slurm);
  - whether compute nodes have internet access (a proxy is set on the login node);
  - the GPU memory per card: resolved 2026-11-12, each H100 NVL has 95,830 MiB (job 196);
  - the CUDA version supported by driver 610.57.04: resolved 2026-11-12, CUDA 13.3 (Stage A job 204);
  - CPUs and memory per job: a job gets 1 CPU unless it asks, so choose `--cpus-per-task` and `--mem`;
  - the Talon scripts must use only the GPUs in `CUDA_VISIBLE_DEVICES`, because Slurm does not hide the other GPUs on the node from a job: resolved 2026-11-12, all GPU checks and the memory monitor are limited to the assigned GPUs, and 2-GPU jobs record NVLink pairing;
  - total GPU-hours allowed: resolved 2026-11-12, no cap (the only limit is the 3-day time per job; Research Computing, in writing);
  - whether GPUs on more than one node may be used at once (the written answer says all 4 GPUs of a node);
  - storage beyond 500 GB, and the account's lifetime and renewal (not asked yet);
  - GPU count and tensor parallelism (decided by the throughput benchmark).
- [ ] **Teacher thinking budget** (decide before the precision test). In Stage A about 95% of Qwen's output tokens were thinking: 4,537 output tokens for a one-line binomial question, of which about 250 were the answer. Qwen3.6-27B can run with thinking on or off, and thinking changes both answer quality and the GPU time per example (and therefore the 200,000-example projection). The options are: thinking on as now (the model card's recommended setting), a cap on thinking length, or thinking off for training-data generation. Whatever is chosen is part of the teacher setup and is fixed before the precision test.
- [ ] **Slot variety:** taxonomy, a `variety.py` slot dealer, and the `dupcheck` thresholds
- [x] **Require `r_solution` in every benchmark reply** (decided 2026-11-11). The field must always be present. It holds substantive R wherever R can compute the answer, and an explicit "not applicable" empty value otherwise. The legacy path that accepted a reply without the field is removed, and the `absent_r_solution` regression fixture is updated deliberately (Section 4, safeguard 6a). Training replies keep the field, but its correctness is not required (safeguard 9).
- [ ] **Talon CUDA version:** not recorded yet. Read it during the Talon bring-up (driver and toolkit from `nvidia-smi` in the first GPU job) and add it to `docs/models/model_versions.md` Section 5, next to the vLLM pin above.
- [ ] **Claude-era outputs outside the repository:** the raw Sonnet replies in `C:\masters_project_large\data\teacher_outputs\*_sonnet-5-5_*` are not in Git and were not touched. Keep them as part of the archive, or delete them (owner's decision; the items themselves are preserved in the Git tag `pre-cleanup-claude-era`).
- [ ] **Benchmark blueprint** (proposal in Section 3, to confirm with Dr. Lee)
- [ ] **Training-data template and answer length.** Proposed from the Pythia probe: one fixed `Question:`/`Answer:` template, short answers with a marked final answer, end-of-text id 0 on every example, loss on the answer and end token only. To confirm in the pilot and with Dr. Lee.
- [ ] **Evaluation protocol** for all students and baselines. Decided parts (2026-11-11):
  - **Engine:** vLLM for the students and the teacher, on the same H100 NVL type.
  - **Students:** loaded in float16, greedy decoding.
  - **Stopping:** the end token (id 0) is the primary stop, with a maximum number of new tokens as the backstop. Prompt plus new tokens must stay within 2,048 tokens. An invented follow-up `Question:` is cut off and recorded. There is **no** blank-line stop, because a blank line can fall before the `Final answer:` line.
  - **Extraction:** the answer is read from the `Final answer:` line, and a missing line is recorded as a format failure, separately from a wrong answer.
  - **Teacher:** thinking mode with the model-card sampling, graded on its final-answer line.
  - **Still open:** the maximum number of new tokens. Frozen before any benchmark result (Section 4, safeguard 8).
- [ ] **Criterion-4b measurement protocol:** GPU, engine version, batch size and concurrency, max new tokens, warm-up, repetitions
- [ ] Whether to add a multiple-choice slice to the benchmark scored by answer likelihood. This works for base models without generation and would be reported separately from generation accuracy.
- [x] **Grading of short-text answers:** superseded 2026-11-12. Every answer, short text included, is graded by Codex against the reference key (Section 2.3). Benchmark short-text items are still kept tightly constrained.
- [x] **Development-set scorecard** (decided 2026-11-12): held-out loss is primary, the teacher-answer match is supplementary, and no Codex is used (Section 4, safeguard 8).
- [x] **Training data** (decided 2026-11-12): retained without correctness-based filtering (Section 4, safeguard 9). The external verifier, the triage step and the blind re-solve are retired (`docs/archive/retired_verification_2026-11-12.md`).
- [x] **Fine-tuning approach** (decided 2026-11-11): full fine-tune with the Hugging Face `Trainer`, every setting explicit, the same for all four sizes. Chosen after a review of the transformers 5.19 documentation and source. The review's main requirements:
  - pad with `<|padding|>` (id 1), never with the end token (id 0), so the real end token keeps its training signal;
  - build our own labels (question tokens masked, answer and end token kept);
  - `save_only_model=False`, so a run can be resumed;
  - pin `accelerate`.

  Pre-pilot tests check the label masking, the precision, the equivalence of gradient accumulation on gradients and parameter updates, resume, and the 2,048-token limit.
- [ ] Number of seeds per condition
- [ ] Exact validity thresholds (default 90% well-formed and 90% R code runs), confirmed in the pilot
- [ ] Which data sizes to run beyond 50k, based on measured GPU time
- [x] **Training precision recipe** (decided 2026-11-11, for all sizes):
  - **Training:** load the model in **float32** and train with BF16 mixed precision (`bf16=True`). Master weights, gradients and AdamW states stay in float32, and the matrix math runs in BF16. Loading in float16 and training with `bf16=True` would keep weights, gradients and optimizer states in float16, which is not real mixed precision and loses small updates.
  - **Evaluation:** students are still loaded in float16 (`docs/models/model_versions.md` Section 3).
- [ ] Peak GPU memory of all four students in training (pilot), to choose the 1B setup if one GPU is too small

**Known cluster facts** (details and evidence labels in `docs/clusters/cluster_selection.md` and `docs/clusters/talon_setup.md`):
- **Redhawk:** Slurm; 4 V100 nodes; whole-node jobs with `--exclusive`, because no GPU resource is defined; 3-day limit; accounting off; long queue waits observed (about 13 days estimated on 2026-11-04).
- **Talon:**
  - Slurm partition `talon` with 4 nodes x 4 H100 NVL, 64 cores and 515 GB RAM per node, shared between jobs.
  - 3-day job limit; accounting off.
  - Login node reaches Hugging Face and PyPI through the university proxy.
  - System Python 3.9; module `miniforge3-python3.12` (Python 3.12.5).
  - Free to use; same account as Redhawk; key-based login works.
