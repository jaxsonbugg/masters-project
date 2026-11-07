# Workflow: the full method, phase by phase

This is the detailed companion to the README. It holds the research question and the exact success criteria, the experimental design, the phase checklists, the safeguards for benchmark and training data, the metrics and statistics, storage, risks and open decisions. When work is completed or a decision changes, update this file and add a dated entry to `docs/progress_update.md` (the history). Cluster jobs go in `docs/compute_log.md` and paid calls in `docs/cost_log.md`.

Terms used throughout, defined once:

- **Teacher:** the large model (here Qwen3.6-27B) that writes questions and worked answers.
- **Student:** a small model (here Pythia 70M, 160M, 410M or 1B) that learns from the teacher's examples.
- **Distillation:** the whole process of passing a teacher's ability to a student through examples the teacher wrote.
- **Fine-tuning:** continuing to train a pretrained model's weights on new examples. A 70M model has 70 million adjustable numbers (parameters), a 27B model 27 billion.
- **Token:** the unit a model reads and writes, roughly three quarters of an English word. "standard deviation" is about 2 to 3 tokens.
- **Thinking tokens:** tokens a reasoning model writes privately before its final answer. They cost GPU time like any other output.
- **Benchmark:** the fixed set of about 1,000 test questions every model is graded on. It is never used for training.
- **Slot:** a description of one question to be written, such as "numerical / binomial probability / intro / number answer". The teacher turns each slot into one question.

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

A student, meaning one (model size, data size) pair, is a **successful specialization** only if it meets **all** of the criteria below. The thresholds were fixed before any student results exist. Any later change must be logged in `docs/progress_update.md` with a reason, as was done for criterion 4 (Section 1.2).

1. **Retained accuracy.** The ratio is student accuracy divided by teacher accuracy on the frozen benchmark. The lower bound of the bootstrap 95% CI of that ratio must reach a tier: **Useful >= 70%**, **Strong >= 85%**, **Near-parity >= 95%**. Accuracy is macro-averaged across benchmark categories, and R code items are graded by execution. Results are reported at all three tiers.
   - *Weak-teacher safeguard.* Teacher and student absolute accuracies are always reported with CIs next to every ratio. A student must also reach an **absolute accuracy floor of 60%** to earn any tier. A teacher below **80%** on the benchmark is a red flag. In that case, pause and review benchmark difficulty and the teacher settings, using the dev set and not the frozen benchmark, before distillation. The first remedy is Qwen3.6-27B at a higher precision or with more thinking (Section 2.1).
2. **Real gain over its own baseline.** The student must be significantly better than the same student untrained (McNemar's test, Holm correction across model pairs).
3. **Usable output.** A minimum share of well-formed, parseable responses and a minimum share of R code that runs. The starting value is 90% each; it is confirmed in the Phase 4 pilot, and any change is logged before Phase 5 results.
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

---

## 2. Experimental design

| Factor | Levels |
|---|---|
| Teacher | Qwen3.6-27B (Apache 2.0 license), BF16 weights served by vLLM on Talon (Section 2.1) |
| Student size | Pythia 70M, 160M, 410M, 1B: deduped variants, final `step143000` checkpoints, pinned by commit SHA (`docs/model_versions.md`) |
| Distillation set size | 1k, 10k, 50k, 100k, 200k (stretch). **50k is the fallback single size** |
| Verifier | A different-family frontier model, to be decided (most likely ChatGPT or Claude used as a checker, never as a source of training text) |
| Benchmark | Frozen held-out set of about 1,000 statistics and R questions |
| Compute | Talon (Miami, 4 nodes x 4 NVIDIA H100 NVL) for generation, training and evaluation; Redhawk (Miami, V100) as the fallback |

**Conditions per student:** an untrained baseline, plus one fine-tuned model per training-set size. The full grid is 4 sizes x up to 5 data sizes = 20 fine-tuned models, plus 4 baselines and the teacher. If compute is limited, all 4 sizes run at 50k first, then the data-size axis is expanded.

**Why Pythia.** All Pythia sizes are trained on the same data in the same order, and the suite is designed for controlled scaling experiments. Differences between students are therefore attributable to size rather than to training-data differences. Only the deduped variants are used (all four sizes saw the same globally deduplicated Pile in the same order), never the standard variants.

**Design principles.**
- Same benchmark, same training data and same hyperparameter recipe across all student sizes.
- Nested training sets (the 1k set is a subset of the 10k set, and so on), so data-size effects are not confounded by content.
- Multiple random seeds per condition if compute allows, so seed-to-seed variance can be estimated.

### 2.1 The teacher: Qwen3.6-27B

**What and why.** Qwen3.6-27B is a 27-billion-parameter reasoning model with open weights under the Apache 2.0 license, which allows training other models on its outputs. It was the first choice of the open-weight evaluation in `docs/teacher_model_evaluations.md` (license, math and code quality, fit with our prompt, ability to run on Miami hardware).

**Deployment.**
- **Talon (primary):** vLLM serving the full BF16 weights. BF16 is a 16-bit number format, so the model runs as released, without compression. Repository `Qwen/Qwen3.6-27B`, revision `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9`, about 53,011 MiB of weights. The vLLM version is still to be pinned (the model card requires vLLM 0.19.0 or later). Settings are in `configs/talon/talon_settings.sh`, explained in `docs/talon_setup.md`.
- **Redhawk (fallback):** llama.cpp tag `b11960` (commit `8642541b...`) serving a 4-bit GGUF file (`unsloth/Qwen3.6-27B-GGUF` @ `82d411ac...`, `Qwen3.6-27B-Q4_K_M.gguf`, SHA-256 `5ed60d0a...`) on two 16 GB V100s. Pins are in `configs/redhawk/common.sh`.
- **Sampling** (the model card's recommended thinking-mode settings, identical on both clusters): temperature 1.0, top_p 0.95, top_k 20, min_p 0, presence penalty 0. The output limit is 16,384 tokens per call, thinking included. The context is 20,480 tokens per sequence, which is a comparison setting and not the model's maximum (`docs/talon_setup.md` Section 7).

**Planned deployment comparison (4-bit vs BF16, both on Talon).** Before the full benchmark run, the same development slots are answered twice on Talon: once with the BF16 weights and once with a 4-bit version. The comparison measures whether compressing the teacher to 4 bits changes the share of usable questions and correct keys, and how much faster it is. It is done on one cluster, so hardware does not differ between the two runs. The Talon 4-bit backend (format and engine) is not built yet (Section 10). Redhawk's 4-bit run is no longer a comparison point; Redhawk is a fallback only.

**Fallback if the teacher underperforms.** If teacher accuracy on the benchmark is below 80%, or the Phase 7 pass rate is poor, the first step is the same model with a higher precision or more thinking, not a different model. The alternatives ranked in `docs/teacher_model_evaluations.md` stay documented but are not the plan.

### 2.2 Why the teacher changed (the Claude era, archived)

The project began with Claude Sonnet 5.5 as the teacher, through the paid Claude API. Anthropic's commercial terms bar using outputs "to train competing AI models". When asked directly, Anthropic support confirmed that Claude outputs may not be used to train the Pythia students. The project therefore switched to an open-weight teacher, and Claude can no longer write either training data or benchmark questions.

**What the Claude trials were.** Between 2026-10-07 and 2026-10-15, Claude wrote eight 20-question trials and one 100-question batch: 120 trial questions in total, never part of the frozen benchmark. The total spend was **$1.44** (`docs/cost_log.md`). The trials developed and tested the question-generation pipeline that Qwen now uses unchanged:

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
- **Short, checkable answers.** Every question has a canonical answer of about 20 tokens or less, so grading works on the first line of a model's output. The Pythia probe showed the students do not stop on their own (`docs/pythia_behavior_analysis.md`).
- **Ground truth.**
  - Number items are auto-graded within a tolerance; their keys come from R (Section 2.2).
  - Multiple-choice items are graded by letter.
  - R code items are graded by running the code against an R check that receives the student's answer as `candidate`.
  - Free-text explanations are not graded for accuracy.
- **Integrity rules.**
  - Freeze before any training: store the file and its SHA-256 checksum in `benchmark/`.
  - Never generate training data from benchmark prompts, slots or paraphrases.
  - Run n-gram and embedding decontamination between the benchmark and every training set (Section 4).
  - Do not tune hyperparameters on the benchmark. If tuning is needed, carve out a separate small dev set.

---

## 4. Safeguards: one teacher writes both the benchmark and the training data

**The problem in plain terms.** Qwen writes the benchmark (the exam) and the training data (the study material). Without care, three things can go wrong:

1. **Leakage:** a training example is the same as, or a close paraphrase of, an exam question, so a student "remembers" the answer instead of solving it.
2. **Shared mistakes:** if Qwen gets a kind of question wrong, the wrong answer can appear in both the training data and the answer key. The student is then rewarded for copying the teacher's error.
3. **Flattering the teacher:** the teacher's accuracy on an exam it wrote itself is optimistic, because the questions sit inside its comfort zone. That inflates the denominator of the retained-accuracy ratio.

**Safeguards, in the order they apply.**

1. **Separate generation prompts.** The benchmark is written only with `data/prompts/benchmark_generation_v6.md`. Training data will use its own prompt file (for example `data/prompts/training_generation_v1.md`, to be written in Phase 4). That prompt asks for a different format: a worked answer ending in a marked final answer, in the `Question:` / `Answer:` template. Neither prompt is ever used for the other purpose.
2. **Separate IDs and folders.**
   - Benchmark questions carry IDs `BM0001` to `BM1000`. Development and smoke-test slots use `BM9001` and up and are never part of either set.
   - Training examples get their own prefix (for example `TR000001`) and their own dated run folders.
   - The code refuses to mix smoke and main slots, and the same rule will be added for training slots.
3. **Freeze first.** The benchmark is finished, hashed (SHA-256) and stored read-only before any training example is generated. A changed hash means the benchmark was touched, and the run stops.
4. **Variety before scale.** The slot design is changed so that no (category, subtopic, difficulty) combination repeats more than necessary. The taxonomy draft in `data/taxonomy/` (not yet committed) and a planned `variety.py` are the start of this. `dupcheck` (in `generate_benchmark.py`) compares every new question with earlier ones by text similarity, with numbers kept and with numbers masked, so near-copies are listed for review.
5. **Decontamination of every training set.** Before a training set is used, every training example is compared with every benchmark question.
   - **n-gram overlap:** shared word sequences, for example any shared run of 8 or more words.
   - **Embedding similarity:** a sentence-embedding model turns each text into a vector, and a high cosine similarity means "says the same thing in other words".

   Matches above the threshold are removed from the **training** set, never from the benchmark (it is frozen). The thresholds and the counts removed are logged.
6. **Independent answer verification.**
   - (a) R computes every number key from the teacher's own code, so arithmetic slips cannot survive.
   - (b) R checks test every code answer against the key and against deliberately wrong answers; a check that accepts a wrong answer is flagged as "vacuous".
   - (c) A blind re-solve: a separate call answers the question without seeing the key, and disagreements go to a person.
   - (d) A different-family frontier verifier (ChatGPT, Claude or another, to be decided) checks all multiple-choice and conceptual keys and a sample of the training data. Used as a checker only, it never writes training text.
   - (e) Hand spot checks of a random sample.
7. **Reporting rule.** Teacher accuracy is always reported with the caveat that the teacher wrote the benchmark, and the verifier's agreement rate is reported next to it.

**Worked example.**
- Benchmark item BM0412 asks for P(X = 2) when X ~ Binomial(5, 0.4).
- A training example generated later asks for P(X = 3) when X ~ Binomial(5, 0.4). With numbers masked, `dupcheck` scores the pair 0.93 (same template). The embedding check also flags it. The training example is dropped.
- A third training example asks for a Poisson probability with similar wording. It scores 0.55 and stays: it trains the same skill without copying the exam.

**Limitations that remain, stated honestly.**
- Shared blind spots cannot be removed completely. The verifier is a different model family, but frontier models make some of the same mistakes.
- R checks the arithmetic, not whether the code answers the question as written. A misread question with consistent code gets a "correct" key.
- Decontamination thresholds trade leakage against over-removal. Any threshold leaves some near-paraphrases in, and removes some harmless examples.
- The benchmark measures skill *as Qwen frames it*. Results say how well students learn from this teacher, not how well they would do on an independent human-written exam.

---

## 5. Phases and checklists

### Phase 1: Define the research question
- [x] Domain: statistics and R programming (final)
- [x] Define "successful specialization" with four criteria (Section 1)
- [x] Pre-register the success thresholds and primary metrics (dated 2026-09-29; criterion 4 deviation dated 2026-11-06)

### Phase 2: Choose teacher and student models
- [x] Students: Pythia 70M, 160M, 410M, 1B (deduped only), final `step143000` checkpoints pinned by commit SHA (`docs/model_versions.md`)
- [x] Probe how the base models behave (local CPU, 2026-10-06): `code/evaluation/pythia_probe.py`, results in `results/pythia_probe/`, findings in `docs/pythia_behavior_analysis.md`. Key findings:
  - the models never stop on their own (0 of 192 generations ended with the end token);
  - outputs loop;
  - arithmetic is wrong at every size;
  - the 1B config names the wrong stop token.
- [x] Teacher: Qwen3.6-27B, decided 2026-11-06 after Anthropic ruled out Claude (Section 2.1, `docs/teacher_model_evaluations.md`)
- [ ] Pin the vLLM version for the Talon deployment and record it in `docs/model_versions.md`

### Phase 3: Create the evaluation benchmark
The benchmark comes before the pilot because the pilot needs something frozen to score against. It is the real, full-size benchmark for the whole project.
- [x] Generation pipeline built and tested (Claude era, Section 2.2): blueprint, prompt v6, R-written number keys, automatic checks, regeneration, `verify`, `dupcheck`
- [x] Qwen client for the cluster deployments: `code/generation/open_teacher_test.py`, with `redhawk` and `talon` backends. It appends the schema text to the system prompt because these engines do not enforce it.
- [ ] Talon bring-up (`docs/talon_setup.md` Section 9):
  - pin the vLLM version and the GPU request style (`--gres` or `--gpus`);
  - set `SETTINGS_REVIEWED=yes` after a review;
  - run a scheduler acceptance test;
  - download the BF16 weights;
  - run smoke stage A;
  - run the throughput stage T.
- [ ] Review the Redhawk pipeline job 2511641 (finished, results not yet checked) and record it in `docs/compute_log.md`
- [ ] 4-bit vs BF16 comparison on Talon (Section 2.1; the 4-bit backend still has to be built)
- [ ] Fix slot variety before any 1,000-question run (Section 4, safeguard 4), then re-run `dupcheck`
- [ ] Blind re-solve command and other-family check for multiple-choice and conceptual items (R cannot check them)
- [ ] Decide whether output-interpretation items need an automatic consistency check of the printed output, or should have R generate the printout. About a third of the trial items had small inconsistencies; no keys were affected.
- [ ] Generate about 1,000 questions with Qwen on Talon; regenerate failures; `verify` and `dupcheck` the whole set
- [ ] Make every answer key checkable, strongest check first (Section 4, safeguard 6)
- [ ] **Freeze** the benchmark (hash it, store read-only) before any training data exists
- [ ] Record every cluster job in `docs/compute_log.md`

### Phase 4: Pilot (1k examples, Pythia 70M, end to end)
Goal: prove the whole pipeline on Talon at small scale and measure real GPU time before committing to the full grid. Plain-language walkthrough: `docs/pilot_plan.md`.
- [x] Cluster access: Redhawk (2026-10-01), Talon (account active and probed 2026-11-06)
- [ ] Write the training-data prompt (separate from the benchmark prompt, Section 4). Use one fixed template (`Question: ...` / `Answer: ...`) with short answers ending in a marked final answer. Every example ends with the end-of-text token, id 0, set explicitly because the 1B config names the wrong token. Reasons: `docs/pythia_behavior_analysis.md` Sections 3.2 and 5.
- [ ] Generate about 1k training questions and teacher answers on Talon; decontaminate against the frozen benchmark
- [ ] Light verification of the 1k set: run the R code, hand spot-check a sample (the full verifier stays in Phase 7)
- [ ] Fine-tune Pythia 70M on the 1k set on Talon (Redhawk as the fallback)
- [ ] Evaluate the untrained and fine-tuned 70M on the frozen benchmark; run the teacher on the benchmark once, so the retained-accuracy ratio and criterion 4b can be computed
- [ ] Fix the evaluation protocol and the criterion-4b measurement protocol (Section 1.2, Section 10)
- [ ] Record GPU-hours, queue wait and peak GPU memory for every job in `docs/compute_log.md`
- [ ] Go/no-go review:
  - Does the pipeline run end to end?
  - Is the projected GPU time for 50k to 200k acceptable?
  - Are the validity thresholds sensible?
- Reuse rule: if the pilot 1k set passes verification, it becomes the 1k subset of the nested sets in Phase 6 (log the reuse).

### Phase 5: Measure baseline performance
- [ ] Evaluate each pretrained student before specialization
- [ ] Evaluate the teacher on the same benchmark
- [ ] Record correctness, response validity, runtime, memory use and the other efficiency measures (Section 6)

### Phase 6: Create the distillation training set
- [ ] Generate a large pool of domain-specific questions with the training prompt (never the benchmark prompt)
- [ ] Have the teacher generate answers, explanations and R code
- [ ] Deduplicate, and decontaminate against the frozen benchmark (Section 4)
- [ ] Use the same verified set for every student size
- [ ] Build nested subsets (1k, 10k, 50k, 100k, 200k as feasible; 50k minimum). The 200k generation plan is in `docs/talon_setup.md` Section 8.

### Phase 7: Verify teacher-generated data
- [ ] Choose the verifier model and effort (ChatGPT, Claude or another frontier model); log any paid calls in `docs/cost_log.md` with the expected cost stated first
- [ ] Have the verifier grade the teacher outputs
- [ ] Objective numerical answers must be verified correct; R code should be improved where needed
- [ ] Execute R code where possible to check that it runs and produces the stated output
- [ ] Score answers, then manually review the ones flagged wrong to understand why (error taxonomy)
- [ ] Fix or drop failing items; record the pass rate and error categories

### Phase 8: Specialize the student models
- [ ] Fine-tune each Pythia student on the verified dataset (Talon)
- [ ] Keep the training procedure consistent across sizes: optimizer, schedule, epochs, sequence length, seeds
- [ ] Decide and document the training precision recipe (Section 10)
- [ ] Compare training-set sizes

### Phase 9: Re-evaluate specialized students
- [ ] Run the same frozen benchmark
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
- [ ] Written report: methodology, verification process, statistical analysis, efficiency results, limitations (Section 4)
- [ ] Presentation
- [ ] Discussion of the practical implications of small specialized models versus large general-purpose ones

---

## 6. Metrics

**Quality**
- Accuracy (primary; macro-averaged across categories), broken down by category and difficulty
- Retained fraction of teacher accuracy, using the lower bound of the bootstrap 95% CI, judged against the 70 / 85 / 95% tiers
- Response validity: well-formed, parseable, R code that runs
- Optional: pass@k for code tasks (the share of questions where at least one of k attempts is correct)

**Efficiency** (teacher and students on the same GPU type, Section 1.2)
- Parameter count and on-disk model size (criterion 4a)
- Peak GPU memory at inference
- GPU time per query and median latency per query (criterion 4b); tokens per second
- Training cost: GPU-hours and wall-clock time
- Derived: accuracy per parameter, accuracy per GPU-hour

**Data quality**
- First-attempt pass rate of generated questions, soft-flag rate, duplicate rate
- Verifier pass rate and error-type breakdown for teacher-generated data
- Number of training examples removed by decontamination

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
| `docs/` | This workflow, the progress, compute and cost logs, and supporting studies |
| `recovery/` | Rebuild instructions for everything stored outside the repository, one file per item, written from `_TEMPLATE.md` |
| `benchmark/` | The frozen benchmark, its checksum and grading scripts (empty until Phase 3 ends) |
| `data/prompts/` | Generation prompts (benchmark v6; the training prompt later) |
| `data/verification_logs/` | Verifier scores and error analysis of teacher outputs (Phase 7) |
| `code/generation/` | Benchmark blueprint and checks, the teacher client, the throughput report |
| `code/verification/`, `code/training/`, `code/analysis/` | Verifier code, fine-tuning code, statistics and plots (later phases) |
| `code/evaluation/` | Benchmark runners and metrics; currently the Pythia probe |
| `code/tests/` | Local test suites: the Redhawk and Talon job scripts with fake cluster programs, the teacher client, the throughput report, and the regression snapshot of the shared benchmark functions |
| `configs/` | `paths.yaml`, and the Redhawk (`configs/redhawk/`) and Talon (`configs/talon/`) Slurm and setup scripts |
| `environment/` | Pinned Python packages |
| `results/` | Metrics, tables, figures and small logs |
| `report/` | Final paper and slides |

### 8.2 Outside the repository (not backed up)

**This PC, `C:\masters_project_large\`:**

| Folder | Purpose |
|---|---|
| `models/pythia/` | The four base checkpoints, files kept exactly as distributed (`recovery/pythia_base_models.md`) |
| `models/finetuned/` | Fine-tuned students, by size and data size |
| `data/teacher_outputs/` | Raw teacher generations, including the archived Claude-era trials |
| `data/verified/` | Verified training sets (1k to 200k) |
| `cache/`, `logs/`, `envs/` | Caches, large logs, Python virtual environments (`recovery/python_env.md`) |

**Clusters.** Redhawk and Talon **share one home folder** (`/home/buggjm`). It has a 500 GB hard quota and a 480 GB soft quota; about 17 GB was in use on 2026-11-06.
- Redhawk work lives in `/home/buggjm/masters_project`.
- Talon work lives in its own folder, `/home/buggjm/talon_project` (repo, models, teacher_outputs), so the two can never overwrite each other.

**Teacher outputs are expensive to recreate.** They cost GPU-hours and are not deterministic (sampling at temperature 1.0), so a compressed backup of the verified 50k set is kept.

---

## 9. Timeline (two semesters)

| Period | Focus |
|---|---|
| Semester 1, early | Design, teacher choice, cluster access, build and freeze the benchmark (Phase 3), 1k / 70M pilot (Phase 4) |
| Semester 1, mid | Baselines for all students and the teacher; go/no-go on scaling up |
| Semester 1, late | Generate and verify distillation data (50k first) |
| Semester 2, early | Fine-tune all students; re-evaluate; expand the data-size axis if feasible |
| Semester 2, mid | Efficiency measurements, statistical analysis, tradeoff analysis |
| Semester 2, late | Report and presentation |

Dates are placeholders until the program's real deadlines are known.

---

## 10. Risks and open decisions

### 10.1 Risks and mitigations

| Risk | Mitigation |
|---|---|
| GPU time and queue waits on Talon (shared nodes, 3-day job limit, total GPU-hours allowed unknown) | Throughput stage T measures examples per GPU-hour before the big runs; the 200k run is split into resumable jobs under 3 days; run 50k across all sizes first |
| Talon unavailable or the settings wrong | Redhawk llama.cpp pipeline kept as a fallback, unchanged; every Talon script is a draft until reviewed |
| Shared 500 GB home quota (Redhawk and Talon together) | `fetch_talon.sh` reads the quota and refuses a download that would pass the soft limit; ask Research Computing for more space before the 200k run |
| Same teacher writes the benchmark and the training data | Section 4: separate prompts and IDs, freeze first, decontamination, independent verification, stated limitations |
| Teacher answer keys wrong in ways R cannot see | Blind re-solve, other-family verifier, hand checks; report teacher accuracy with the caveat |
| Near-duplicate questions at scale | Slot-variety redesign and `dupcheck` before the 1,000-question run |
| Pythia models are base models (not instruction-tuned), have a 2,048-token context and never stop on their own | One fixed `Question:`/`Answer:` template, short answers, explicit end-of-text token id 0, a pre-declared stop rule |
| Very small models may score near zero, hiding differences | Easier items, plus partial-credit and validity metrics |
| Benchmark contamination | Decontamination, checksum freeze, a separate dev set |
| Verifier errors or blind spots shared with the teacher | Execute R code, spot-check by hand, review flagged disagreements manually |
| Confounded comparisons across sizes | Identical recipe, data, seeds and evaluation for all students |

### 10.2 Open decisions

- [ ] **Verifier:** which frontier model (ChatGPT, Claude or another) and at what effort; any paid use is logged in `docs/cost_log.md`
- [ ] **Talon 4-bit vs BF16 comparison:** which 4-bit format and engine (for example a 4-bit GGUF with llama.cpp, or a 4-bit or FP8 checkpoint with vLLM), which slots, and which measures decide it
- [ ] **Talon settings still unverified:**
  - the vLLM version pin;
  - `TALON_GPU_STYLE` (whether `--gres` or `--gpus` requests are accepted);
  - whether compute nodes have internet access (a proxy is set on the login node);
  - the GPU memory per card (H100 NVL: 94 GB expected);
  - total GPU-hours allowed;
  - GPU count and tensor parallelism (decided by the throughput benchmark).
- [ ] **Slot variety:** taxonomy, a `variety.py` slot dealer, and the `dupcheck` thresholds
- [ ] **Require `r_solution` in every reply (decide before the benchmark run).**
  - **The gap:** `check_item` in `generate_benchmark.py` decides which fields to require by looking at what a reply contains. A reply that leaves out the `r_solution` field entirely is checked under the old prompt-v1 rules. So a number question with no R code would pass, keeping the model's own typed key instead of a key computed by R. That undoes the main protection described in Section 2.2.
  - **Why it is still there:** the 2026-11-06 cleanup kept this behavior on purpose, because the refactor had to be proven identical.
  - **Recommended fix:** require `r_solution` (and `working`) for all v6 replies, then re-save the regression snapshot. Only the cases that test missing fields should change.
- [ ] **Talon CUDA version:** not recorded yet. Read it during the Talon bring-up (driver and toolkit from `nvidia-smi` in the first GPU job) and add it to `docs/model_versions.md` Section 5, next to the vLLM pin above.
- [ ] **Stale reference in a Redhawk script:** a comment in `configs/redhawk/common.sh` (line 47) still points to `recovery/redhawk_qwen_test.md`, which was never written. It is harmless (a comment only) and was left alone because the Redhawk scripts are kept byte for byte. Fix it the next time a Redhawk script has to change for another reason, then rerun the Redhawk shell tests.
- [ ] **Claude-era outputs outside the repository:** the raw Sonnet replies in `C:\masters_project_large\data\teacher_outputs\*_sonnet-5-5_*` are not in Git and were not touched. Keep them as part of the archive, or delete them (owner's decision; the items themselves are preserved in the Git tag `pre-cleanup-claude-era`).
- [ ] **Benchmark blueprint** (proposal in Section 3, to confirm with Dr. Lee)
- [ ] **Training-data template and answer length.** Proposed from the Pythia probe: one fixed `Question:`/`Answer:` template, short answers with a marked final answer, end-of-text id 0 on every example, loss on the answer and end token only. To confirm in the pilot and with Dr. Lee.
- [ ] **Evaluation protocol** for all students and baselines: prompt format, stop rule (such as the first blank line or `Question:`), max new tokens, greedy decoding. Declared before any results.
- [ ] **Criterion-4b measurement protocol:** GPU, engine version, batch size and concurrency, max new tokens, warm-up, repetitions
- [ ] Whether to add a multiple-choice slice to the benchmark scored by answer likelihood. This works for base models without generation and would be reported separately from generation accuracy.
- [ ] Grading method for free-text answers
- [ ] Fine-tuning approach: full fine-tune or LoRA (full fine-tuning is cleaner for small models)
- [ ] Number of seeds per condition
- [ ] Exact validity thresholds (default 90% well-formed and 90% R code runs), confirmed in the pilot
- [ ] Which data sizes to run beyond 50k, based on measured GPU time
- [ ] Training precision recipe for Phase 8: mixed precision (AMP), gradient and optimizer-state precision, BF16 or FP16. Decided once the Talon environment is set up.
- [ ] Peak GPU memory of all four students in training (pilot), to choose the 1B setup if one GPU is too small

**Known cluster facts** (details and evidence labels in `docs/cluster_selection.md` and `docs/talon_setup.md`):
- **Redhawk:** Slurm; 4 V100 nodes; whole-node jobs with `--exclusive`, because no GPU resource is defined; 3-day limit; accounting off; long queue waits observed (about 13 days estimated on 2026-11-04).
- **Talon:**
  - Slurm partition `talon` with 4 nodes x 4 H100 NVL, 64 cores and 515 GB RAM per node, shared between jobs.
  - 3-day job limit; accounting off.
  - Login node reaches Hugging Face and PyPI through the university proxy.
  - System Python 3.9; module `miniforge3-python3.12` (Python 3.12.5).
  - Free to use; same account as Redhawk; key-based login works.
