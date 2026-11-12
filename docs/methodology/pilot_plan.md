# Pilot Plan: a 1k Example, 70M Model, End-to-End Run (Phases 3 and 4)

Prepared 2026-10-06; rewritten 2026-11-07 for the current plan (teacher Qwen3.6-27B on Miami's Talon cluster, Redhawk as the fallback). This document explains in plain language what the pilot does and why, in the order things happen. The status of each step lives in the Phase 3 and Phase 4 checklists in `docs/methodology/workflow.md` Section 5. Cluster jobs and GPU time are recorded in `docs/logs/compute_log.md`; any paid call (only the verifier could be one) is recorded in `docs/logs/cost_log.md`.

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

The **benchmark** is the final exam: about 1,000 statistics and R questions with known correct answers. We build it before anything else, for two reasons.

1. **It must be fixed in advance.** If we looked at results and then changed the exam, we could unknowingly make it easier for our model. So we **freeze** it: compute a checksum (a SHA-256 hash, a short fingerprint of the file that changes if even one character changes), store it, and mark the file read-only.
2. **It must be separate from the training data.** If the student trains on questions that also appear on the exam, a high score only shows memorization, not skill. This is called **contamination** or leakage. We prevent it by writing the exam and the training data with separate prompts and separate IDs, and by running a **decontamination** check afterward (Step 3).

Because of what Step 0 showed, every question gets a **short canonical answer** (a number, a choice, a few words, or R code that can be run against tests) so it can be graded from the first line of a model's output. A question whose "correct answer" is a paragraph is hard to grade even for a good model and meaningless for a 70M one.

### What the Claude-era trials taught us

Between 2026-10-07 and 2026-10-15 the question-writing pipeline was built and tested with Claude in small runs (six 20-question trials, three 1-question probes, a 2-question test batch and a 100-question batch: 204 items covering 120 distinct question slots, $1.44, none of them in the benchmark; archived under the Git tag `pre-cleanup-claude-era`, summary in `docs/methodology/workflow.md` Section 2.2). Qwen now uses the same pipeline and the same prompt (v6, SHA-256 `348db6ff84da29d22b2fcdeec9c13191df9d828b6af64b61146f2794b1888cc4`). Four lessons carry over:

- **R writes the number keys.** In the first trial, 3 of the 8 numerical keys the model typed were wrong even when its own working was right. Example: a question asked for a correlation; the working computed 36 / sqrt(40 x 60) = 0.735, but the typed key said 0.8. Now the model writes R code that recomputes the answer, our `verify` command runs that code on this computer, and R's printed number becomes the key. The model's typed number is kept only for comparison.
- **Rounding comes last.** The chance of exactly 2 heads in 5 fair tosses is exactly 0.3125. The usual rule rounds it to 0.313, but R's `round(0.3125, 3)` gives 0.312 (R rounds an exact tie toward the even digit). So R prints the exact value, the key has the decimals the question asks for, and grading allows an error of half the last decimal place, so a student who rounds a tie either way is marked right.
- **Some keys no automatic check can catch.** In one multiple-choice item the key claimed a confidence interval gets wider when the degrees of freedom go from 17.4 to 18; R's own numbers show it gets slightly narrower. Nothing in the code path touches a multiple-choice statement. Those items need a **blind re-solve** and a **different-family verifier** (below).
- **Duplicates.** The slot design (a *slot* is a description of one question to write, such as "numerical / binomial probability / intro / number answer") has only 138 distinct category, subtopic and difficulty combinations for 1,000 slots, so 86% of slots repeat a combination, about 7 questions per combination on average. Given the same combination again, the model writes a near-copy of an earlier question (for example the same binomial setup with one number changed). A benchmark full of near-copies tests fewer skills than its size suggests.

### What has to happen before the 1,000-question run

1. **Fix slot variety.** Change the slot design so no combination repeats more than necessary (more subtopics, varied settings and contexts), then re-run `dupcheck`, which compares every question with every earlier one by text similarity, once with numbers kept and once with numbers masked, and lists near-copies for review. Success looks like few or no flagged pairs on a development batch.
2. **Bring up Talon.** Pin the vLLM version (vLLM is the program that loads the model onto the GPUs and answers requests; the model card requires 0.19.0 or later), settle how jobs request GPUs, review the settings file, run a scheduler acceptance test, download the BF16 weights, then run smoke stage A (a few questions, to see that everything works) and the throughput stage T (how many tokens per second Talon delivers). The exact steps are in `docs/clusters/talon_setup.md` Section 9. Talon's nodes are shared between jobs and a job may run for at most 3 days, so long runs are split into pieces that can be restarted.
3. **Review the Redhawk fallback run.** Redhawk job 2511641 (the Qwen pipeline with the 4-bit model) has finished but nobody has looked at its results. It is reviewed and recorded in `docs/logs/compute_log.md`, because it shows whether the fallback deployment works.
4. **Choose the teacher precision on Talon** (decided 2026-11-11; protocol in `docs/methodology/workflow.md` Section 2.1).
   - **What precision means here:** BF16 is a 16-bit number format, about 2 bytes per parameter, so the full Qwen weights are about 53,011 MiB. FP8 uses about 1 byte per parameter and a 4-bit version about half a byte; both are smaller and usually faster, but compression can cost quality.
   - **One precision for everything:** whichever is chosen is used for the benchmark and for every training set, so the data sizes are never written by different teacher setups.
   - **How it is tested:** all three are run on the same development slots on Talon, served by the same engine. FP8 and 4-bit are each compared with BF16 on two things: usable questions, and answer correctness checked independently on a sample.
   - **The rule:** the cheapest one that is not worse than BF16 by more than 3 percentage points on both (a margin whose scientific justification is written down first) is chosen.

### Generating and checking the benchmark

Qwen then writes about 1,000 questions on Talon. Each question that fails the automatic checks (for example thinking aloud in the question text, an answer that appears in its own question, or an R check that never tests the student's answer) is asked for again with the same prompt, up to 3 attempts. The prompt does not say what went wrong, so the first-attempt pass rate stays an honest measure of the prompt. Then `verify` and `dupcheck` run on the whole set.

**The same-teacher risk.** Qwen writes the exam, later takes it to set the teacher score, and also writes the training data. Its answer keys may contain exactly the mistakes it would make when answering, and those mistakes could also appear in the training data, so a student would be rewarded for copying them. A new request to Qwen does not remember writing a question, which removes one kind of bias, but it is the same model with the same blind spots, so a fresh Qwen call cannot be trusted to catch everything. To limit the damage we check the answer keys in layers, strongest first:

1. **Run the code.** For numeric answers and R code questions, R computes the key or runs the check. An R check must accept the key and reject three deliberately wrong answers; one that accepts a wrong answer is flagged. A computer running R does not share Qwen's blind spots.
2. **Blind re-solve.** A separate Qwen call solves each question without being shown the key. Where it disagrees with the key, we look by hand. This catches careless errors but not systematic ones.
3. **A different model family, only where needed.** Items R cannot settle go to a *verifier*: an open-weight model from a different family than Qwen, inexpensive, and from a provider whose terms allow this use (not OpenAI or Anthropic). DeepSeek is the likely choice, because its terms explicitly allow distillation; Mistral is another candidate.
   - **Which items it gets:** every multiple-choice, conceptual and output-interpretation item, every soft flag and every re-solve disagreement. A *triage* step selects these, so the verifier only sees what our own checks cannot settle, which keeps its usage small even at 200,000 examples.
   - **When it is chosen:** once the first real data exists (the precision test). It is tested first on 100 to 200 reference items, some deliberately wrong, to measure how often it accepts a wrong answer.
   - **Its role:** it only checks, and never writes training text or questions. Its calls are paid, so the expected cost is stated first and every call is logged in `docs/logs/cost_log.md`.
4. **Your own audit of about 150 random benchmark items**, stratified by category and including items that passed every check. This covers what R cannot: code that is consistent but answers a misread question. It also measures the leftover error rate. If errors are found and fixed, a new random sample is needed to claim anything about the error rate after the fixes.

Even after all this we report that the teacher's score on its own exam is probably a bit optimistic, with the verifier's agreement rate next to it. The benchmark is then frozen (hashed and stored read-only) before any training example exists.

## Step 2 (Phase 4): get the training environment working on Talon

The teacher setup from Step 1 serves Qwen; training Pythia needs a different setup: Python (Talon offers Python 3.12 through the `miniforge3-python3.12` module), a CUDA build of PyTorch so training can use the H100s, and the libraries pinned in `environment/requirements.txt`. The pinned Pythia files are copied from this PC to the shared home folder and re-checked with `sha256sum` against the hashes in `model_versions.md` Section 4. A first short job loads Pythia 70M on one GPU, confirms it loads in `float16`, and confirms the end-of-text id is 0. If Talon is not usable, the same steps run on Redhawk.

## Step 3: generate 1,000 training examples

The teacher writes about 1,000 new questions on statistics and R, each with a worked answer. This only starts after the benchmark is frozen. Four things keep it apart from the benchmark and keep it useful:

- **A separate prompt.** Training data uses its own prompt file (for example `data/prompts/training_generation_v1.md`, still to be written), never the benchmark prompt. Each example follows one fixed template (`Question: ...`, then `Answer: ...`) with a short answer that ends in a clearly marked final answer. The training code adds the end-of-text token (id 0) after every answer so the student learns to stop. Loss (the error the training tries to reduce) is counted only on the answer and that end token, so the student is graded on writing the answer, not on copying the question.
- **Separate IDs and folders.** Training examples get their own prefix (for example `TR000001`) and dated run folders; benchmark IDs are `BM0001` to `BM1000`.
- **Variety.** The same slot-variety fix applies, so the 1,000 examples cover many different skills instead of many copies of a few.
- **Decontamination** against the frozen benchmark. Every training example is compared with every benchmark question in two ways: shared word sequences (for example any shared run of 8 or more words) and embedding similarity (a small model turns each text into a list of numbers, and two texts with very similar numbers say the same thing in different words). Worked example: if benchmark item BM0412 asks for P(X = 2) when X ~ Binomial(5, 0.4), a training example asking for P(X = 3) with the same setup scores 0.93 on `dupcheck` with numbers masked and is dropped; a Poisson question with similar wording scores 0.55 and stays, because it trains the same skill without copying the exam. Matches are removed from the training set, never from the frozen benchmark, and the thresholds and counts are logged.

We record the token counts the engine reports for every response and the GPU time of every generation job, because together they give the true GPU time per example, which is what the full-scale projection needs. Then we:

- **Verify** the set the same way as the benchmark, at small scale: run the R code, triage, and send the uncertain items to the verifier. This is a rehearsal that measures the real triage rate and cost per item before 200,000 examples.
- **Check the length.** Pythia can only read 2,048 tokens at once (its `max_position_embeddings`). Every example (question, working, final answer and end token) is measured with the Pythia tokenizer. One that is too long is rejected or deliberately shortened, never cut off silently, because cutting would remove the final answer or the end token. The share affected is recorded.
- Drop anything that fails. Because some items will fail, we generate 10 to 25% more than we need.

If this set passes, it later becomes the 1,000 example subset of the bigger training sets, so the GPU time is not spent twice.

## Step 4: train the 70M student

We take the original Pythia 70M model (the pinned checkpoint described in `model_versions.md`) and fine-tune it on the 1,000 examples on Talon (Redhawk as the fallback). Training uses the Hugging Face `Trainer` (a standard, well-tested training loop) with every setting written out. The model is loaded in float32 and trained with BF16 mixed precision, which the H100 supports; this recipe, decided 2026-11-11, is the same for all four sizes (`model_versions.md` Section 3). Before this run, the hyperparameters are chosen on the development set, never on the benchmark. We record in `docs/logs/compute_log.md` how long the job took, how many GPUs it held, the GPU-hours (GPUs x hours: one GPU for 30 minutes is 0.5 GPU-hours), the peak GPU memory and the queue wait. Peak memory matters because it helps predict how the 1B model and the larger data sets will fit.

## Step 5: take the exam

We run the frozen benchmark through three models and compare their scores. The protocol is fixed in advance. It uses:
- the same prompt format for every model;
- **the end-of-text token as the main stop**, with a maximum number of new tokens as a backstop (prompt plus new tokens within 2,048);
- cutting off any invented follow-up `Question:`;
- greedy decoding, meaning the model always picks its single most likely next token;
- reading the answer from the `Final answer:` line.

It deliberately does **not** stop at the first blank line, because a model may put a blank line between its working and the final answer. A response with no `Final answer:` line counts as a format failure, recorded separately from a wrong answer. All of this is fixed because Step 0 showed untrained models do not stop by themselves and their scores swing with the prompt format.

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
- Did the answer keys hold up under the layered checks, or do we need a stronger process before scaling? What would the verifier cost at full scale?
- Did the criterion-4b timing protocol give stable, repeatable numbers?

If the answers are acceptable, we scale up. If not, we fix the weakest part first.

## Expected pilot cost

Generation, training and evaluation run on Miami's clusters and cost **no money**; their cost is GPU-hours, which are logged per job in `docs/logs/compute_log.md` and summed there. The only possible paid item is the different-family verifier, which is still to be decided. Before any paid verifier run, its expected cost is written down, and afterward the actual cost is compared in `docs/logs/cost_log.md`.
