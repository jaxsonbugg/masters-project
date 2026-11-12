# Workflow: the full method, phase by phase

This is the detailed companion to the README. It holds the research question and the exact success criteria, the experimental design, the phase checklists, the safeguards for benchmark and training data, the metrics and statistics, storage, risks and open decisions. When work is completed or a decision changes, update this file and add a dated entry to `docs/progress_update.md` (the history). Cluster jobs go in `docs/logs/compute_log.md` and paid calls in `docs/logs/cost_log.md`.

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
| Student size | Pythia 70M, 160M, 410M, 1B: deduped variants, final `step143000` checkpoints, pinned by commit SHA (`docs/models/model_versions.md`) |
| Distillation set size | 1k, 10k, 50k, 100k, 200k (stretch). **50k is the fallback single size** |
| Verifier | An open-weight model from a different family than Qwen, relatively inexpensive, from a provider whose terms allow using its verdicts to filter training data (not OpenAI or Anthropic). DeepSeek is the likely front-runner (its terms explicitly allow distillation); Mistral is another candidate. Run through a paid API on a triaged subset only; chosen and validated once the first real data exists (Section 2.3, Section 4) |
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
- **Talon (primary):** vLLM serving the full BF16 weights. BF16 is a 16-bit number format, so the model runs as released, without compression. Repository `Qwen/Qwen3.6-27B`, revision `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9`, about 53,011 MiB of weights. The vLLM version is still to be pinned (the model card requires vLLM 0.19.0 or later). Settings are in `configs/talon/talon_settings.sh`, explained in `docs/clusters/talon_setup.md`.
- **Redhawk (fallback):** llama.cpp tag `b11960` (commit `8642541b...`) serving a 4-bit GGUF file (`unsloth/Qwen3.6-27B-GGUF` @ `82d411ac...`, `Qwen3.6-27B-Q4_K_M.gguf`, SHA-256 `5ed60d0a...`) on two 16 GB V100s. Pins are in `configs/redhawk/common.sh`.
- **Sampling** (the model card's recommended thinking-mode settings, identical on both clusters): temperature 1.0, top_p 0.95, top_k 20, min_p 0, presence penalty 0. The output limit is 16,384 tokens per call, thinking included. The context is 20,480 tokens per sequence, which is a comparison setting and not the model's maximum (`docs/clusters/talon_setup.md` Section 7).

**Choosing the teacher precision (decided 2026-11-11; protocol pre-registered before it runs).** *Precision* is how many bits store each of the model's numbers: BF16 uses 16, FP8 uses 8, a 4-bit version uses 4. Fewer bits mean a smaller, faster model, and possibly a slightly worse one.
- **One precision is used for all generation.** The benchmark and every training set come from the same teacher setup. Mixing precisions across data sizes would add a second difference between the conditions being compared.
- **What is compared.** BF16 (the reference), FP8 and 4-bit, all on Talon and all served by vLLM, so neither the engine nor the hardware differs. This replaces the earlier plan to compare Redhawk's 4-bit file with Talon's BF16.
- **Two endpoints, measured on the same development slots (BM8xxx, never benchmark or training):**
  - **Usability:** the item is usable on the first attempt, and a number item also has an R-verified key.
  - **Answer correctness:** checked on a stratified sample, by R where possible and otherwise by the validated verifier, with every disagreement adjudicated by hand. Usability alone is not enough, because a well-formatted answer with runnable R can still misread the question.
- **The statistics.** Two comparisons against BF16 (FP8 vs BF16, 4-bit vs BF16) with a multiplicity adjustment (Holm, or Bonferroni at one-sided α = 0.025 each). This is a non-inferiority test: a lower precision passes if the confidence interval for its paired difference from BF16 stays above −3 percentage points on **both** endpoints.
  - The 3-point margin is provisional. Before the run, it must be justified in writing as the largest loss of teacher quality that would not change the study's conclusions, not only by the GPU time it saves.
  - Sample sizes are computed before the run, at an assumed share of slots where the two precisions disagree. They are re-estimated from a 100-slot first run.
- **Decision rule.** Use the lowest-compute precision that is non-inferior to BF16 on both endpoints. If neither FP8 nor 4-bit passes, use BF16. The chosen precision's projected total GPU time must fit the timeline, run in resumable jobs shorter than the 3-day limit.
- **Worked example (hypothetical numbers).** On 1,000 paired slots, BF16 is usable on 88% and 4-bit on 87.2%, a difference of −0.8 points. If the adjusted lower confidence bound is −2.6 (above −3) for usability, and the correctness sample gives a lower bound of −2.1, then 4-bit passes both endpoints and is chosen. A lower bound of −3.4 on either endpoint would mean 4-bit fails.

**Fallback if the teacher underperforms.** If teacher accuracy on the benchmark is below 80%, or the Phase 7 pass rate is poor, the first step is the same model with a higher precision or more thinking, not a different model. The alternatives ranked in `docs/models/teacher_model_evaluations.md` stay documented but are not the plan.

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

### 2.3 The verifier (chosen later, validated before use)

**What and why.** Qwen writes the questions and answers, so checking Qwen with Qwen is not independent. The *verifier* is a second language model, from a different family, that checks the items our own checks (R, the re-solve) cannot settle.

**Requirements (hard gates):**
- open weights;
- relatively inexpensive;
- provider terms that allow using its verdicts to filter training data (DeepSeek's terms explicitly allow distillation);
- not OpenAI or Anthropic;
- a different model family from Qwen.

**Candidates:** DeepSeek (the likely front-runner) and Mistral, with others from `docs/models/teacher_model_evaluations.md`. It runs through a paid API, so its expected cost is stated before every run and every call is logged in `docs/logs/cost_log.md`.

**When.** The verifier is chosen after the first real data exists: the outputs of the precision test (Section 2.1). The choice is recorded in `docs/models/verifier_selection.md`.

**Validation before it is trusted.**
- **Connectivity test (about 20 items).** This checks only that the API works, the JSON verdicts parse and costs are logged.
- **Reliability test (100 to 200 reference items).** The set mixes independently checked correct answers with deliberately wrong ones: wrong numbers, wrong keys, plausible misconceptions. It is built from development items, never the benchmark.
- **What is measured:** the **false-acceptance rate** (a wrong answer accepted), the false-rejection rate and the abstention rate.
- **The priority is low false acceptance,** because the verifier exists to remove wrong training examples. A threshold is declared before the test. A verifier that misses it is not used, and the next candidate is tested.

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
   - Benchmark questions carry IDs `BM0001` to `BM1000`.
   - The **development set** (about 200 items, `DV0001`+) is built with the same pipeline and the same checks, and is used for hyperparameter choice, troubleshooting and evaluation debugging (safeguard 8).
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
6. **Independent answer verification, triaged** (decided 2026-11-11).
   - (a) **R computes every number key** from the teacher's own code, so arithmetic slips cannot survive. The `r_solution` field must be present in every reply. It must contain substantive executable R wherever R can compute the answer. Where R does not apply (for example a conceptual question), it is an explicit "not applicable" empty value, so the model is never pushed into writing meaningless R.
   - (b) **R checks** test every code answer against the key and against deliberately wrong answers; a check that accepts a wrong answer is flagged as "vacuous".
   - (c) **A blind re-solve by Qwen** answers each question without seeing the key. It is a **consistency check only**: two Qwen outputs can share the same misunderstanding, so an agreeing re-solve never counts as independent validation.
   - (d) **Triage, then the verifier.** Items whose key R established and whose re-solve agrees need no LLM check. Everything R cannot settle goes to the different-family verifier (Section 2.3): every multiple-choice, conceptual, short-text and output-interpretation item, every soft flag, and every re-solve disagreement. Disagreements are adjudicated by hand. The verifier only checks; it never writes training text. Triage keeps the verifier's usage, and its cost at 200k examples, small.
   - (e) **A manual audit** of a representative random sample of about **150 benchmark items**, stratified by category and **including items that passed every automated check**. It covers what R cannot: code that is consistent but answers a misread question.
     - **What is reported:** the audit's error rate describes the benchmark **before** corrections, and the original results are kept.
     - **The residual error rate:** a claim about it after corrections needs a fresh, independent random sample.
7. **Reporting rule.** The benchmark is reported as **teacher-generated**, kept distinct from any externally sourced evaluation, together with its independent-key methods and audit error rate. Teacher accuracy is always reported with the caveat that the teacher wrote the benchmark, and the verifier's agreement rate is reported next to it.
8. **Development set vs confirmatory evaluation** (decided 2026-11-11).
   - **What the benchmark is for:** only **prespecified evaluations**. Hyperparameters are chosen, and the evaluation harness is debugged, on the **development set** only.
   - **What is frozen first:** the hyperparameters, seed, evaluation protocol, scoring rules and analysis are frozen in a dated pre-registration **before** the training run that is evaluated.
   - **After the first benchmark evaluation:** no performance-motivated change is allowed within the confirmatory experiment. Documented implementation bug fixes remain permitted; each is logged with its evidence, and the affected step is re-run.
   - **Follow-up experiments** motivated by benchmark results are labeled **exploratory** everywhere, reported separately, and never replace the confirmatory findings.

   **Why this matters, with an example:** suppose the 70M scores poorly and the learning rate is raised and the model retrained until the score improves. No benchmark question was ever trained on, but the benchmark has still been used to tune the experiment, so its score is no longer an honest test.

**Worked example.**
- Benchmark item BM0412 asks for P(X = 2) when X ~ Binomial(5, 0.4).
- A training example generated later asks for P(X = 3) when X ~ Binomial(5, 0.4). With numbers masked, `dupcheck` scores the pair 0.93 (same template). The embedding check also flags it. The training example is dropped.
- A third training example asks for a Poisson probability with similar wording. It scores 0.55 and stays: it trains the same skill without copying the exam.

**Limitations that remain, stated honestly.**
- Shared blind spots cannot be removed completely. The verifier is a different model family, but large models make some of the same mistakes.
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
- [x] Students: Pythia 70M, 160M, 410M, 1B (deduped only), final `step143000` checkpoints pinned by commit SHA (`docs/models/model_versions.md`)
- [x] Probe how the base models behave (local CPU, 2026-10-06): `code/evaluation/pythia_probe.py`, results in `results/pythia_probe/`, findings in `docs/models/pythia_behavior_analysis.md`. Key findings:
  - the models never stop on their own (0 of 192 generations ended with the end token);
  - outputs loop;
  - arithmetic is wrong at every size;
  - the 1B config names the wrong stop token.
- [x] Teacher: Qwen3.6-27B, decided 2026-11-06 after Anthropic ruled out Claude (Section 2.1, `docs/models/teacher_model_evaluations.md`)
- [ ] Pin the vLLM version for the Talon deployment and record it in `docs/models/model_versions.md`

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
- [ ] Require the `r_solution` and `working` fields in every reply ("not applicable" where R does not apply), then update the regression fixture (Section 4, safeguard 6a)
- [ ] Choose the teacher precision (BF16, FP8 or 4-bit) with the pre-registered protocol in Section 2.1, before any benchmark generation
- [ ] Choose and validate the verifier on the precision-test outputs (Section 2.3)
- [ ] Fix slot variety before any 1,000-question run (Section 4, safeguard 4), then re-run `dupcheck`
- [ ] Blind re-solve command (a consistency check) and the verification triage (Section 4, safeguard 6)
- [ ] Decide whether output-interpretation items need an automatic consistency check of the printed output, or should have R generate the printout. About a third of the trial items had small inconsistencies; no keys were affected.
- [ ] Generate about 1,000 benchmark questions and the ~200-item development set with Qwen on Talon at the chosen precision; regenerate failures; `verify` and `dupcheck` the whole set
- [ ] Keep short-text items tightly constrained (a name, a term, a value); rewrite open-ended ones as multiple choice or drop them
- [ ] Manual audit of about 150 random benchmark items (Section 4, safeguard 6e)
- [ ] Make every answer key checkable, strongest check first (Section 4, safeguard 6)
- [ ] **Freeze** the benchmark (hash it, store read-only) before any training data exists
- [ ] Record every cluster job in `docs/logs/compute_log.md`

### Phase 4: Pilot (1k examples, Pythia 70M, end to end)
Goal: prove the whole pipeline on Talon at small scale and measure real GPU time before committing to the full grid. Plain-language walkthrough: `docs/methodology/pilot_plan.md`.
- [x] Cluster access: Redhawk (2026-10-01), Talon (account active and probed 2026-11-06)
- [ ] Write the training-data prompt (separate from the benchmark prompt, Section 4). Use one fixed template (`Question: ...` / `Answer: ...`) with short answers ending in a marked final answer. Every example ends with the end-of-text token, id 0, set explicitly because the 1B config names the wrong token. Reasons: `docs/models/pythia_behavior_analysis.md` Sections 3.2 and 5.
- [ ] Generate about 1,250 training questions and teacher answers on Talon; R checks, triage, verifier on the uncertain items (a rehearsal for 200k)
- [ ] Check every training example against the Pythia **2,048-token** limit (its `max_position_embeddings`): reject or deliberately shorten an over-length example, never truncate it silently; record the share affected
- [ ] Decontaminate against the frozen benchmark and the development set; keep the final 1,000
- [ ] Write the training script (Hugging Face `Trainer`, full fine-tune, every setting explicit) and its pre-pilot tests; a Talon training smoke run
- [ ] Build and debug the evaluation harness on the development set only
- [ ] Choose the hyperparameters on the development set; then freeze the hyperparameters, seed, evaluation protocol, scoring rules and analysis in a dated pre-registration (Section 4, safeguard 8)
- [ ] Confirmatory run: fine-tune Pythia 70M once with the frozen settings; evaluate the untrained and fine-tuned 70M and the teacher on the frozen benchmark (retained accuracy, McNemar, criterion 4b)
- [ ] Record GPU-hours, queue wait and peak GPU memory for every job in `docs/logs/compute_log.md`
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
- [ ] Build nested subsets (1k, 10k, 50k, 100k, 200k as feasible; 50k minimum). The 200k generation plan is in `docs/clusters/talon_setup.md` Section 8.

### Phase 7: Verify teacher-generated data
- [ ] Use the verifier chosen and validated in Phase 3 (Section 2.3); log every paid call in `docs/logs/cost_log.md` with the expected cost stated first
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
| `docs/` | Project documents in topic subfolders: `methodology/` (this workflow, the pilot plan), `models/` (model versions, teacher evaluation, Pythia behavior), `clusters/` (cluster selection, Talon setup), `logs/` (compute and cost logs), `guides/` (Git notes). The only file at the `docs/` root is `progress_update.md`. New kinds of document get a new, clearly named folder (for example `meetings/`, `report/`) |
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
| Talon unavailable or the settings wrong | Redhawk llama.cpp pipeline kept as a fallback, with its executable logic unchanged (only three comment lines were repointed on 2026-11-07); every Talon script is a draft until reviewed |
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

- [ ] **Verifier model, budget and false-acceptance threshold** (Section 2.3). Gates are decided (open weights, terms allow it, not OpenAI or Anthropic, different family); the model is chosen once the precision-test outputs exist.
- [ ] **Teacher precision details** (Section 2.1): whether official FP8 and 4-bit (AWQ or GPTQ) Qwen3.6-27B checkpoints exist with vLLM support and a usable license; the written rationale for the 3-point margin; the sample sizes.
- [ ] **Talon settings still unverified:**
  - the vLLM version pin;
  - `TALON_GPU_STYLE` (whether `--gres` or `--gpus` requests are accepted);
  - whether compute nodes have internet access (a proxy is set on the login node);
  - the GPU memory per card: resolved 2026-11-12, each H100 NVL has 95,830 MiB (job 196);
  - the CUDA version supported by driver 610.57.04, still to be read;
  - CPUs and memory per job: a job gets 1 CPU unless it asks, so choose `--cpus-per-task` and `--mem`;
  - the Talon scripts must use only the GPUs in `CUDA_VISIBLE_DEVICES`, because Slurm does not hide the other GPUs on the node from a job;
  - total GPU-hours allowed;
  - GPU count and tensor parallelism (decided by the throughput benchmark).
- [ ] **Slot variety:** taxonomy, a `variety.py` slot dealer, and the `dupcheck` thresholds
- [x] **Require `r_solution` in every reply** (decided 2026-11-11). The field must always be present. It holds substantive R wherever R can compute the answer, and an explicit "not applicable" empty value otherwise. The legacy path that accepted a reply without the field is removed, and the `absent_r_solution` regression fixture is updated deliberately (Section 4, safeguard 6a).
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
- [ ] **Grading of short-text answers.**
  - **Constrained answers** (a function name, a single term) use a normalized match against the key plus listed accepted variants. Benchmark short-text items are kept constrained.
  - **Any open-ended item** that remains needs a predeclared rubric, independently checked reference answers, the verifier as a semantic grader, and manual adjudication. Exact string matching would undercount correct answers worded differently.
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
