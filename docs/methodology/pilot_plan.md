# Pilot Plan: a 1k Example, 70M Model, End-to-End Run (Phases 3 and 4)

Prepared 2026-10-06; rewritten 2026-11-07 for the current plan (teacher Qwen3.6-27B on Miami's Talon cluster, Redhawk as the fallback); revised 2026-11-12, when the checking of training data for correctness was dropped and Codex became the grader. This document explains in plain language what the pilot does and why, in the order things happen. The status of each step lives in the Phase 3 and Phase 4 checklists in `docs/methodology/workflow.md` Section 5. Cluster jobs and GPU time are recorded in `docs/logs/compute_log.md`. Codex usage (the grader, the only service that is not free) is recorded in `docs/logs/cost_log.md`.

**The one idea behind the 2026-11-12 revision.** The study's main test is whether distillation lets a small student *approach its teacher*, not whether it produces a perfect student. So the two kinds of data are treated differently.
- **The training data** is the teacher's output, used as it is. Qwen-generated training examples are retained without correctness-based filtering; their correctness is unknown and may vary by question category. That is intentional, and the students are evaluated independently on a frozen benchmark.
- **The benchmark** is the measuring instrument, so it is checked as carefully as is reasonably possible (Step 1).
- **One grader** scores everyone's answers on it: Codex, a frontier model.

## The big idea

The full project asks how small a model can be and still be good at statistics and R. To answer that we will eventually train four small models (Pythia 70M, 160M, 410M, 1B) on up to 200,000 examples written by a teacher model, and test them all on the same set of questions. That is a lot of GPU time and calendar time. Before committing, we run the **whole pipeline once, at the smallest scale**: one small model (70M), 1,000 training examples, and the real test questions. If something is broken, or far slower than we assumed, we find out after a few GPU-hours instead of after weeks of cluster jobs.

**Distillation** is the name for what we are doing. A big "teacher" model (Qwen3.6-27B, an open-weight model with about 27 billion parameters) writes example questions with good answers. A tiny "student" model (Pythia 70M, about 70 million parameters) is then trained to imitate those answers. The hope is that the student picks up useful skill from the teacher while being far cheaper to run. **Fine-tuning** is the training step itself: take the student, which already knows general English text from its original training, and keep training it on our examples so it specializes.

**Why Qwen and not Claude.** The project started with Claude as the teacher, but Anthropic confirmed that Claude outputs may not be used to train the students. Qwen3.6-27B's license (Apache 2.0) allows it, and because its weights are public we run it on Miami's own GPUs. That changes what "cost" means in this pilot: cluster time is free, so generation, training and evaluation cost no dollars. The real budget is GPU-hours, queue waits, the 3-day job limit and storage, and those are what we measure. The full reasoning is in `docs/methodology/workflow.md` Sections 2.1 and 2.2.

**Where things run.** **Talon** (Miami; 4 nodes, each with 4 NVIDIA H100 NVL GPUs) is the primary cluster for generation, fine-tuning and evaluation. **Redhawk** (Miami; older V100 GPUs with 16 GB of memory each) is the fallback. Both are shared computers that you do not use directly: you submit a **job** to a scheduler (Slurm), which queues it and runs it when the requested GPUs are free. Cluster facts are in `docs/clusters/cluster_selection.md` and `docs/clusters/talon_setup.md`.

## Step 0 (done 2026-10-06): see how the student actually behaves

Before writing any benchmark or training data, we watched the four Pythia models answer 16 mixed questions in three prompt formats (script `code/evaluation/pythia_probe.py`, data in `results/pythia_probe/`, full write-up in `pythia_behavior_analysis.md`). It ran on this PC's CPU and cost nothing.

**Why:** Pythia models are **base models**. A base model was trained only to predict the next piece of text, so it treats a question as the start of a web page and keeps writing; it was never taught to answer once and stop. We wanted to see that for ourselves, because it decides how the data should be written.

**What we found, in plain terms:**
- **They never stop.** In all 192 generations the model ran to the 128-token limit instead of ending, often inventing its own next question. So every training example has to end with the special end-of-text token, or the fine-tuned model will not learn to stop.
- **The 1B model's own settings name the wrong stop token** (the character `!` instead of end-of-text). The training and evaluation code must set the end token explicitly for all four sizes.
- **The prompt format changes what the model writes.** The same question became a forum answer, a C++ file or a math drill depending on framing. One fixed template, used for every example and every size, removes that.
- **Bigger helps recall, not calculation.** 410M and 1B know simple facts; every size got `17 + 25` wrong and the 70M model mostly produced loops. A 1,000-example fine-tune is expected to teach the *answer format* much more than new knowledge, so the pilot tests whether the pipeline works, not whether the 70M model becomes good.
- **Short answers are enough.** The students only need a short final answer, so the teacher's training examples can be short too. Short examples take less teacher GPU time to write and less student GPU time to train on.

**How this changed the steps below:** benchmark answers are short and checkable, the training template is fixed, answers end with the end-of-text token, and the output is cut at a stop rule before grading.

## Step 1 (Phase 3): build the benchmark first

The **benchmark** is the final exam: about 1,000 statistics and R questions, each with a reference answer (the *key*) that is checked as carefully as is reasonably possible (below). We build it before anything else, for two reasons.

1. **It must be fixed in advance.** If we looked at results and then changed the exam, we could unknowingly make it easier for our model. So we **freeze** it: compute a checksum (a SHA-256 hash, a short fingerprint of the file that changes if even one character changes), store it, and mark the file read-only.
2. **It must be separate from the training data.** If the student trains on questions that also appear on the exam, a high score only shows memorization, not skill. This is called **contamination** or leakage. We prevent it by writing the exam and the training data with separate prompts and separate IDs, and by running a **decontamination** check afterward (Step 3).

Because of what Step 0 showed, every question gets a **short canonical answer** (a number, a choice, a few words, or R code that can be run against tests) so it can be graded from the first line of a model's output. A question whose "correct answer" is a paragraph is hard to grade even for a good model and meaningless for a 70M one.

### What the Claude-era trials taught us

Between 2026-10-07 and 2026-10-15 the question-writing pipeline was built and tested with Claude in small runs (six 20-question trials, three 1-question probes, a 2-question test batch and a 100-question batch: 204 items covering 120 distinct question slots, $1.44, none of them in the benchmark; archived under the Git tag `pre-cleanup-claude-era`, summary in `docs/methodology/workflow.md` Section 2.2). Qwen now uses the same pipeline and the same prompt (v6, SHA-256 `348db6ff84da29d22b2fcdeec9c13191df9d828b6af64b61146f2794b1888cc4`). Four lessons carry over:

- **R writes the number keys.** In the first trial, 3 of the 8 numerical keys the model typed were wrong even when its own working was right. Example: a question asked for a correlation; the working computed 36 / sqrt(40 x 60) = 0.735, but the typed key said 0.8. Now the model writes R code that recomputes the answer, our scripts run that code (from now on only inside the R sandbox, below), and R's printed number becomes the key. The model's typed number is kept only for comparison.
- **Rounding comes last.** The chance of exactly 2 heads in 5 fair tosses is exactly 0.3125. The usual rule rounds it to 0.313, but R's `round(0.3125, 3)` gives 0.312 (R rounds an exact tie toward the even digit). So R prints the exact value, the key has the decimals the question asks for, and grading allows an error of half the last decimal place, so a student who rounds a tie either way is marked right.
- **Some keys no automatic check can catch.** In one multiple-choice item the key claimed a confidence interval gets wider when the degrees of freedom go from 17.4 to 18; R's own numbers show it gets slightly narrower. Nothing in the code path touches a multiple-choice statement. Items like this are why every benchmark question is also screened for problems and a sample is audited by hand (below).
- **Duplicates.** The slot design (a *slot* is a description of one question to write, such as "numerical / binomial probability / intro / number answer") has only 138 distinct category, subtopic and difficulty combinations for 1,000 slots, so 86% of slots repeat a combination, about 7 questions per combination on average. Given the same combination again, the model writes a near-copy of an earlier question (for example the same binomial setup with one number changed). A benchmark full of near-copies tests fewer skills than its size suggests.

### What has to happen before the 1,000-question run

1. **Fix slot variety.** Change the slot design so no combination repeats more than necessary (more subtopics, varied settings and contexts), then re-run `dupcheck`, which compares every question with every earlier one by text similarity, once with numbers kept and once with numbers masked, and lists near-copies for review. Success looks like few or no flagged pairs on a development batch.
2. **Bring up Talon.** Pin the vLLM version (vLLM is the program that loads the model onto the GPUs and answers requests; the model card requires 0.19.0 or later), settle how jobs request GPUs, review the settings file, run a scheduler acceptance test, download the BF16 weights, then run smoke stage A (a few questions, to see that everything works) and the throughput stage T (how many tokens per second Talon delivers). The exact steps are in `docs/clusters/talon_setup.md` Section 9. Talon's nodes are shared between jobs and a job may run for at most 3 days, so long runs are split into pieces that can be restarted.
3. **Review the Redhawk fallback run.** Redhawk job 2511641 (the Qwen pipeline with the 4-bit model) has finished but nobody has looked at its results. It is reviewed and recorded in `docs/logs/compute_log.md`, because it shows whether the fallback deployment works.
4. **Choose the teacher precision on Talon** (decided 2026-11-11; protocol in `docs/methodology/workflow.md` Section 2.1).
   - **What precision means here:** BF16 is a 16-bit number format, about 2 bytes per parameter, so the full Qwen weights are about 53,011 MiB. FP8 uses about 1 byte per parameter and a 4-bit version about half a byte; both are smaller and usually faster, but compression can cost quality.
   - **One precision for everything:** whichever is chosen is used for the benchmark and for every training set, so the data sizes are never written by different teacher setups.
   - **How it is tested:** all three are run on the same development slots on Talon, served by the same engine. FP8 and 4-bit are each compared with BF16 on two things:
     - **usable questions**, measured automatically on every slot;
     - **answer correctness**, checked independently on a sample: by R where the answer can be computed, and by you by hand otherwise.

     Both are needed because a compressed model can write perfectly formatted answers that are more often wrong. No language model judges this test, because the precision decides how all the training data is made.
   - **How many slots are needed, worked out first.** The test asks whether the cheaper precision is "not worse by more than 3 percentage points". How many paired slots that needs depends on how often the two precisions disagree, the *discordance*. If they disagree on 10% of slots, about 873 slots are needed at 80% power. The correctness half then needs roughly 873 slots × 3 precisions × 70% (the share R cannot check) ≈ 1,830 judgments by hand (the formula is in `docs/methodology/workflow.md` Section 2.1).
   - **The feasibility gate.** Before any test output exists, you write down how many hand judgments are practical.
     - **If the calculation needs more:** BF16 is used for everything. The cheaper precisions may still be run on a smaller sample, but only as an *exploratory* comparison that cannot change the choice.
     - **The margin stays fixed:** the 3-point margin is never loosened to make the sample smaller.
   - **The rule:** if the gate passes, the cheapest precision that is not worse than BF16 by more than 3 percentage points on both measures is chosen. The margin's scientific justification is written down first.
5. **Set up the R sandbox** (done 2026-11-12: self-test 13 of 13; `recovery/r_sandbox.md`).
   - **Why:** the R code in a teacher reply was written by a model, so it is treated as untrusted. It could by mistake delete files, read personal files or reach the internet.
   - **How:** before any more model-written R is run, an isolated Linux environment (WSL2 with the bubblewrap sandbox) is set up on this PC. There, R runs with no network, no view of the Windows drives (so no repository, credentials or personal files), and limits on memory, time and output.
   - **How it is tested:** a self-test tries each forbidden action from inside the sandbox and must see it fail.
   - **Same answers:** R 4.3.1, the same version as now, so the keys come out identical.

   Details are in `docs/methodology/workflow.md` Section 4, safeguard 10.

### Generating and checking the benchmark

Qwen then writes about 1,000 questions on Talon. Each question that fails the automatic checks (for example thinking aloud in the question text, an answer that appears in its own question, or an R check that never tests the student's answer) is asked for again with the same prompt, up to 3 attempts. The prompt does not say what went wrong, so the first-attempt pass rate stays an honest measure of the prompt. Then `verify` (R, in the sandbox) and `dupcheck` run on the whole set.

**Why the benchmark gets extra care.** Qwen writes the exam and later takes it. If one of its answer keys is wrong, every model that answers that question correctly is marked wrong, so a wrong key damages the measurement itself. The training data is different: there, a teacher mistake is simply part of what the student learns from, and that is accepted. So the benchmark, and only the benchmark, gets four layers of checks:

1. **Run the code.**
   - **Number answers:** R recomputes each key from the teacher's own code.
   - **R code questions:** each R check must accept the key and reject deliberately wrong answers; one that accepts a wrong answer is flagged.
   - **The limit:** this checks arithmetic and code behavior, not whether the teacher read the question correctly.
2. **Codex screens every question** for ambiguity, missing information or invalid statistical assumptions. It sees the question only, not the answer.
   - *Example:* "A sample of 30 observations has a sample standard deviation of 12. What is the exact probability that the sample mean exceeds 50?" is flagged, because neither the population distribution nor its mean is given.
   - **What you do:** you look at every flagged question and fix it, replace it, or keep it with a note.
3. **Your own audit of about 150 random benchmark items.**
   - **The sample:** stratified by category, and including items that passed every check.
   - **Per item:** you work out each answer yourself and record whether the key is right, the question is clear, and exactly one answer is correct.
   - **What it tells us:** this covers what R cannot (consistent code for a misread question), and it estimates how many errors remain. If 0 of 150 are wrong, the error rate is probably below about 2%.
   - **After fixes:** a new random sample is needed to claim anything about the error rate after the fixes.
4. **Honest wording.** The benchmark's answers are described as *independently checked where computationally possible, screened for ambiguity, and audited on a stratified 150-item sample*, never as "all verified".

The benchmark is then frozen (hashed and stored read-only) before any training example exists. The development set (about 200 items) gets the same automatic checks, but not the screen or the audit, because it is not the measuring instrument.

**What was dropped on 2026-11-12, and why.** The earlier plan had more layers:
- a second Qwen call re-solving each question;
- a paid "verifier" model from another company (DeepSeek or Mistral), checking the training data too;
- a triage step choosing what the verifier saw.

These existed to make the *training data* correct. The study no longer needs that, so they are retired (archived in `docs/archive/retired_verification_2026-11-12.md`).

## Step 2 (Phase 4): get the training environment working on Talon

The teacher setup from Step 1 serves Qwen; training Pythia needs a different setup: Python (Talon offers Python 3.12 through the `miniforge3-python3.12` module), a CUDA build of PyTorch so training can use the H100s, and the libraries pinned in `environment/requirements.txt`. The pinned Pythia files are copied from this PC to the shared home folder and re-checked with `sha256sum` against the hashes in `model_versions.md` Section 4. A first short job loads Pythia 70M on one GPU, confirms it loads in `float16`, and confirms the end-of-text id is 0. If Talon is not usable, the same steps run on Redhawk.

## Step 3: generate 1,000 training examples

The teacher writes about 1,000 new questions on statistics and R, each with a worked answer. This only starts after the benchmark is frozen. Four things keep it apart from the benchmark and keep it useful:

- **A separate prompt.** Training data uses its own prompt file (for example `data/prompts/training_generation_v1.md`, still to be written), never the benchmark prompt. Each example follows one fixed template (`Question: ...`, then `Answer: ...`) with a short answer that ends in a clearly marked final answer. The training code adds the end-of-text token (id 0) after every answer so the student learns to stop. Loss (the error the training tries to reduce) is counted only on the answer and that end token, so the student is graded on writing the answer, not on copying the question.
- **Separate IDs and folders.** Training examples get their own prefix (for example `TR000001`) and dated run folders; benchmark IDs are `BM0001` to `BM1000`.
- **Variety.** The same slot-variety fix applies, so the 1,000 examples cover many different skills instead of many copies of a few.
- **Decontamination** against the frozen benchmark. Every training example is compared with every benchmark question in two ways: shared word sequences (for example any shared run of 8 or more words) and embedding similarity (a small model turns each text into a list of numbers, and two texts with very similar numbers say the same thing in different words). Worked example: if benchmark item BM0412 asks for P(X = 2) when X ~ Binomial(5, 0.4), a training example asking for P(X = 3) with the same setup scores 0.93 on `dupcheck` with numbers masked and is dropped; a Poisson question with similar wording scores 0.55 and stays, because it trains the same skill without copying the exam. Matches are removed from the training set, never from the frozen benchmark, and the thresholds and counts are logged.

We record the token counts the engine reports for every response and the GPU time of every generation job, because together they give the true GPU time per example, which is what the full-scale projection needs. Then we:

- **Keep the teacher's answers as they are.** Qwen-generated training examples are retained without correctness-based filtering. Their correctness is unknown and may vary by question category. This is intentional: the question is how close the student gets to the teacher, mistakes included.
- **Check everything except correctness:**
  - the format (a complete, parseable reply for its slot);
  - duplicates;
  - decontamination (above).
- **Check the length.** Pythia can only read 2,048 tokens at once (its `max_position_embeddings`).
  - **How each example is measured:** the whole example (question, working, final answer and end token) is measured with the Pythia tokenizer.
  - **What happens to one that is too long:** it is rejected or deliberately shortened, never cut off silently, because cutting would remove the final answer or the end token.
  - **What is recorded:** the share affected.
- **Set aside about 150 extra examples** that are never trained on. They measure the *held-out loss* that picks the training settings (Step 4).
- Drop anything that fails a check. Because some items will fail, we generate 10 to 25% more than we need.

If this set passes its checks, it later becomes the 1,000 example subset of the bigger training sets, so the GPU time is not spent twice.

## Step 4: train the 70M student

We take the original Pythia 70M model (the pinned checkpoint described in `model_versions.md`) and fine-tune it on the 1,000 examples on Talon (Redhawk as the fallback). Training uses the Hugging Face `Trainer` (a standard, well-tested training loop) with every setting written out. The model is loaded in float32 and trained with BF16 mixed precision, which the H100 supports; this recipe, decided 2026-11-11, is the same for all four sizes (`model_versions.md` Section 3).

**Choosing the training settings first.** *Hyperparameters* are the settings we pick ourselves, such as the learning rate (how big each adjustment to the weights is) and the number of epochs (how many times the model reads the training set). Before the real run, a small list of *candidates* is declared, each one combination of settings. Each candidate is trained on the 1,000 examples, and the winner is picked on the development set, never on the benchmark.
- **The scorecard is the held-out loss:** how surprised each trained student is by the teacher's text on the 150 set-aside examples. Lower means closer to the teacher.
- **Next to it, the teacher-answer match:** how often the student's final answer on the 200 development questions agrees with the teacher's. Numbers must be within the allowed rounding, multiple-choice answers must have the same letter, and R expressions are compared by what they do (each item's R check, run in the sandbox).
- *Example:* candidates A, B and C reach losses of 1.42, 1.18 and 1.21, so B's settings are frozen and used for the real run.

Codex is never used to choose settings. We record in `docs/logs/compute_log.md` how long the job took, how many GPUs it held, the GPU-hours (GPUs x hours: one GPU for 30 minutes is 0.5 GPU-hours), the peak GPU memory and the queue wait. Peak memory matters because it helps predict how the 1B model and the larger data sets will fit.

## Step 5: take the exam

We run the frozen benchmark through three models and compare their scores. The protocol is fixed in advance. It uses:
- the same prompt format for every model;
- **the end-of-text token as the main stop**, with a maximum number of new tokens as a backstop (prompt plus new tokens within 2,048);
- cutting off any invented follow-up `Question:`;
- greedy decoding, meaning the model always picks its single most likely next token;
- reading the answer from the `Final answer:` line.

It deliberately does **not** stop at the first blank line, because a model may put a blank line between its working and the final answer. A response with no `Final answer:` line counts as a format failure, recorded separately from a wrong answer. All of this is fixed because Step 0 showed untrained models do not stop by themselves and their scores swing with the prompt format.

**How the answers are graded.** One grader, Codex, scores every answer of every model, the teacher included (`docs/methodology/workflow.md` Section 2.3).
- **What it judges:** for each answer it sees the question, the benchmark's key and the model's final answer, and judges whether they are equivalent. A correct answer written differently from the key, such as `sum(x, na.rm = TRUE) / sum(!is.na(x))` for `mean(x, na.rm = TRUE)`, still counts as correct.
- **Blind grading:** the answers of all three models are mixed together under random labels, so Codex never knows which model wrote what.
- **The isolated workspace:** each batch runs in an empty folder outside the repository, so Codex can see nothing but the batch.
- **How it is checked:**
  - about 40 answers whose truth is known in advance (20 right, 20 deliberately wrong) are hidden in the batches;
  - you grade about 180 answers (60 per model) yourself without seeing Codex's verdict;
  - simple rules (a number within tolerance, the multiple-choice letter, the R check) re-grade every item they can.

  All three are reported next to the scores.
- **Thresholds and failure rules are decided before the benchmark is graded.** How well Codex must do is decided on development data, together with what happens if it fails.
  - **If it fails on development data:** the instructions are revised there, or a pre-registered fallback grading by rules and by hand becomes the main score.
  - **If it fails on the benchmark:** the failure is reported as such, and the main conclusions use the pre-registered fallback scores (rules for numbers, letters and R expressions, plus your blind grading of short-text answers). That fallback is computed every time anyway. Codex's scores are still reported, labeled as having failed. Which score counts is decided by the frozen thresholds alone, checked before anyone looks at the per-model results, so neither method can be picked for giving the "better" answer. The instructions are never changed after benchmark results are seen.

**The benchmark is used only for this prespecified evaluation.** The hyperparameters and the evaluation code are chosen and debugged on a separate development set of about 200 items, and frozen in a dated pre-registration before the training run that is evaluated. After the benchmark scores are seen, only documented bug fixes are allowed. Any further experiment prompted by the scores is labeled exploratory and never replaces these results.

The three models are:

- **Untrained Pythia 70M**: the starting point. Any improvement has to be measured against this.
- **Fine-tuned Pythia 70M**: did training on 1,000 examples help?
- **The teacher (Qwen3.6-27B)**, run once on Talon: the ceiling we compare against. The project's main metric is the student's accuracy as a fraction of the teacher's. A teacher score below 80% is a red flag (`docs/methodology/workflow.md` Section 1.1); the first remedy is the same Qwen model at a higher precision or with more thinking, not a different model.

**Timing for criterion 4b.** The same runs also measure speed. Criterion 4b (`docs/methodology/workflow.md` Section 1.2) asks that a student use at least 10x less GPU time per benchmark question than the teacher and have at least 10x lower median latency (the time from sending one question to receiving the full answer), measured on the same GPU type (H100 NVL) with the same serving settings and the same maximum number of new tokens. Worked example from the workflow: if the teacher on 2 H100s answers the 1,000 questions in 50 minutes, that is 2 x 3,000 s / 1,000 = 6.0 GPU-seconds per question; if a student on 1 H100 takes 4 minutes, that is 0.24 GPU-seconds, and 6.0 / 0.24 = 25x passes. The pilot fixes the measurement protocol (engine and version, batch size, warm-up runs excluded, number of repeated timings) before any real student result counts.

Do not expect a 70M model trained on 1,000 examples to do well. A tiny model on a tiny dataset may score near zero on hard questions. The pilot is not testing whether the model is good; it is testing whether **every part of the pipeline runs and gives numbers we can trust**, and whether any improvement over untrained is visible at all.

## Step 6: the go/no-go review

We then answer these questions and write the results in `docs/methodology/workflow.md` and `progress_update.md`:

- Did every step run end to end without hand-fixing?
- How much GPU time did one training example take to write, and what does that make 50,000, 100,000 and 200,000 examples take? Does that fit within the 3-day job limit (split into restartable pieces) and the project timeline?
- How long did a training run take and how long was the queue, so how long will the full grid of 20 models take?
- Is the storage plan safe? The shared home folder has a 480 GB soft quota (about 17 GB used so far).
- Are the R-code and format success thresholds (90% each, `docs/methodology/workflow.md` Section 1.1) realistic for these models?
- How many benchmark questions did the screen flag, what error rate did the 150-item audit find, and is the benchmark good enough to keep?
- Did Codex pass its validity thresholds, and did it agree with you and with the simple rules equally well for every model?
- How much Codex usage did the screen and the grading take, and what does that project to for the full grid (about 25,000 answers)? Does it fit the plan's allowance?
- Did the criterion-4b timing protocol give stable, repeatable numbers?

If the answers are acceptable, we scale up. If not, we fix the weakest part first.

## The order of work (revised 2026-11-12)

1. **Talon bring-up.** Done so far: the probe, the BF16 download, the smoke test (Stage A) and the throughput test (Stage T). Remaining: the FP8 and 4-bit downloads, and the training environment.
2. **Generation code:**
   - `r_solution` and `working` required in benchmark replies;
   - slot variety;
   - the full-size generator;
   - decontamination;
   - the fix for the "No:" false alarm;
   - **the R sandbox**.
3. **Teacher precision:**
   1. sample sizes and the feasibility gate;
   2. the precision-test slots;
   3. usability on all slots, and correctness on a sample (R in the sandbox, plus you);
   4. the decision.
4. **Benchmark and development set:**
   1. generate;
   2. R keys, `verify`, `dupcheck`;
   3. Codex setup: you install it and confirm the terms; the batch tool is built and tested;
   4. the Codex usage pilot;
   5. the Codex screen, and your review of the flags;
   6. the 150-item audit;
   7. fixes;
   8. freeze.
5. **The 1k training set** plus about 150 held-out examples: format, length and decontamination checks, with no correctness filtering.
6. **Training script and its tests.**
7. **The evaluation harness, on the development set:**
   - the deterministic graders;
   - the "R code runs" check;
   - the held-out loss and teacher match;
   - Codex grading;
   - grader validation and its thresholds;
   - the calibration sets.
8. **Choose the hyperparameters** on the development set, then freeze everything, including the grader setup and its failure rules.
9. **The confirmatory run:**
   1. train once;
   2. three models answer the benchmark;
   3. Codex grades them blind;
   4. the calibration answers, the cross-check and your 180-answer audit;
   5. the analysis.
10. **The go/no-go review** (Step 6).

## Expected pilot cost

Generation, training and evaluation run on Miami's clusters and cost **no money**; their cost is GPU-hours, which are logged per job in `docs/logs/compute_log.md` and summed there.

The one service that is not free is **Codex**, which screens the benchmark questions and grades the answers.
- **What it costs:** it runs on your workspace subscription, so its use counts against the plan's included allowance, and work beyond that may need purchased credits. It is not assumed to be free.
- **The usage pilot:** a small run on development items measures how much it uses per question.
- **Before every run:** the expected usage is written down.
- **Afterward:** the actual usage is logged in `docs/logs/cost_log.md`.
