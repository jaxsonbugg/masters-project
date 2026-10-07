# Pilot Plan: a 1k Example, 70M Model, End-to-End Run (Phases 3 and 4)

Prepared 2026-10-06. This document explains in plain language what the pilot does and why, in the order things happen. Status of each step lives in the README checklists (Phase 3 and Phase 4); money spent lives in `cost_log.md`.

## The big idea

The full project asks how small a model can be and still be good at statistics and R. To answer that we will eventually train four small models (Pythia 70M, 160M, 410M, 1B) on up to 200,000 examples written by Claude, and test them all on the same set of questions. That is a lot of money, compute and time. Before committing, we run the **whole pipeline once, at the smallest scale**: one small model (70M), 1,000 training examples, and the real test questions. If something is broken, or far more expensive than we assumed, we find out for tens of dollars instead of thousands.

**Distillation** is the name for what we are doing. A big, expensive "teacher" model (Claude Sonnet 5.5) writes example questions with good answers. A tiny "student" model (Pythia 70M) is then trained to imitate those answers. The hope is that the student picks up useful skill from the teacher while being far cheaper to run. **Fine-tuning** is the training step itself: take the student, which already knows general English text from its original training, and keep training it on our examples so it specializes.

## Step 0 (done 2026-10-06): see how the student actually behaves

Before writing any benchmark or training data, we watched the four Pythia models answer 16 mixed questions in three prompt formats (script `code/evaluation/pythia_probe.py`, data in `results/pythia_probe/`, full write-up in `pythia_behavior_analysis.md`). It ran on this PC's CPU, called no API, and cost $0.00.

**Why:** Pythia models are **base models**. A base model was trained only to predict the next piece of text, so it treats a question as the start of a web page and keeps writing; it was never taught to answer once and stop. We wanted to see that for ourselves, because it decides how the data should be written.

**What we found, in plain terms:**
- **They never stop.** In all 192 generations the model ran to the 128-token limit instead of ending, often inventing its own next question. So every training example has to end with the special end-of-text token, or the fine-tuned model will not learn to stop.
- **The 1B model's own settings name the wrong stop token** (the character `!` instead of end-of-text). The training and evaluation code must set the end token explicitly for all four sizes.
- **The prompt format changes what the model writes.** The same question became a forum answer, a C++ file or a math drill depending on framing. One fixed template, used for every example and every size, removes that.
- **Bigger helps recall, not calculation.** 410M and 1B know simple facts; every size got `17 + 25` wrong and the 70M model mostly produced loops. A 1,000-example fine-tune is expected to teach the *answer format* much more than new knowledge, so the pilot tests whether the pipeline works, not whether the 70M model becomes good.
- **Cost hint:** answers can be short, and short answers are cheap. If the teacher writes a few sentences instead of long reasoning, the cost per example could drop from about $0.013 to somewhere between $0.001 and $0.006 (to be measured, see `cost_log.md` and `pythia_behavior_analysis.md` section 5.3).

**How this changed the steps below:** benchmark answers are short and checkable, the training template is fixed, answers end with the end-of-text token, and the output is cut at a stop rule before grading.

## Step 1 (Phase 3): build the benchmark first

The **benchmark** is the final exam: about 1,000 statistics and R questions with known correct answers. We build it before anything else, for two reasons.

1. **It must be fixed in advance.** If we looked at results and then changed the exam, we could unknowingly make it easier for our model. So we **freeze** it: compute a checksum (a short fingerprint of the file that changes if even one character changes), store it, and mark the file read-only.
2. **It must be separate from the training data.** If the student trains on questions that also appear on the exam, a high score only shows memorization, not skill. This is called **contamination** or leakage. We prevent it by writing the exam prompts and the training prompts separately, and by running a **decontamination** check afterward (searching the training set for any text that overlaps with, or is nearly identical to, an exam question).

**First trial run (2026-10-07).** Before writing 1,000 questions we wrote 20, using the real prompt (`data/prompts/benchmark_generation_v1.md`) and the real script (`code/generation/generate_benchmark.py`), with a hard spending cap of $3. It cost **$0.13**, about $0.0064 per question, so 1,000 questions through the half-price Batch API should cost about $3 (see `cost_log.md`). Every reply was well-formed, the answers were short, nothing was cut off, and the correct choice letters rotated A to D as intended.

**The important result was not the cost.** Reading the 20 questions with a calculator showed **3 of the 8 numerical answer keys were wrong**. In plain terms: the model wrote a question, worked out a solution in its explanation, and then wrote an answer key that did not match. For example, question BM0005 asks for a correlation coefficient. Its own explanation computes 36 / sqrt(40 x 60) = 0.735, but the key says 0.8 (the right value is 0.7348). BM0013's key says 12 while running the code gives 25. BM0020's key says 0.272, but P(Z > 0.4851) is 0.314, and here the explanation itself had the arithmetic error. One R check (BM0007) tested the answer key instead of the student's answer, so it would have passed anything.

**Why this matters:** a wrong key marks a correct student answer as wrong, and a small model that happens to guess the wrong key as right. Left unnoticed in a 1,000-question benchmark, these errors would quietly lower every score and blur the comparison between model sizes. This is the problem the "independence ladder" in the README (Section 9) exists for, and the trial is a concrete example that the same model checking its own work is not enough: in the BM0020 case a model re-reading its own explanation would likely agree with it. What we do about it: (1) the script now has free automatic checks (a key must match the last number in its own explanation, an R check must use the student's answer) and flagged 3 of the problem items (BM0005, BM0007 and BM0013) without spending anything, but it misses BM0020; (2) prompt v2 will put the worked calculation before the key and ask for R code that recomputes every numerical answer; (3) R (already installed, version 4.3.1) is used to run that code, which would have caught all three wrong keys; (4) a different-family model and a hand check on a sample come after that.

**Second trial: let R produce the key (2026-10-07).** The fix for wrong keys is to stop trusting the number the model types. In prompt v2 the model first writes out its calculation, then writes a few lines of R code that recompute the answer using R's own functions, and only then writes the key. Our `verify` command runs that R code on this computer and compares what R prints with the key. Worked example, BM0020: the first trial's key was 0.272; R's `pnorm(0.4851, lower.tail = FALSE)` prints 0.3138, so the key is flagged and R's number is the proposed correction. For R-coding questions, `verify` also feeds the answer checker the key (must pass) and three deliberately wrong answers (must fail); a checker that passes a wrong answer, like BM0007's, is flagged. Rerunning the same 20 slots cost $0.18; R confirmed 12 items, flagged one for a rounding difference (0.3125 rounds to 0.312 in R but 0.313 by the usual rule), and 7 multiple-choice or conceptual items have no code to run, so they still need the blind re-solve and the other-family check. What R does not tell us: whether the model's code answers the question as it was asked. Two independent routes to the same number (the model's working and R) agreeing is strong evidence, not proof, so the hand-checked sample and the reported error rate stay.

Because of what Step 0 showed, every question gets a **short canonical answer** (a number, a choice, a few words, or R code that can be run against tests) so it can be graded from the first line of a model's output. A question whose "correct answer" is a paragraph is hard to grade even for a good model and meaningless for a 70M one.

The questions are generated by the Claude API. That makes the exam cheap to build, but it creates a risk: the teacher both writes the exam and is later graded on it, and its answer keys may contain the same mistakes it would make when answering. A new API call does not remember writing a question, which removes one kind of bias, but it is the same model with the same blind spots, so a fresh call cannot be trusted to catch everything. To limit the damage we check the answer keys in layers, strongest first:

1. **Run the code.** For numeric answers and R code questions, run R and compare. A computer running R does not share Claude's blind spots.
2. **Blind re-solve.** A separate API call solves each question without being shown the key. Where it disagrees with the key, we look by hand. This catches careless errors but not systematic ones.
3. **A different model family.** A ChatGPT model checks a sample of the keys, since it was trained differently.
4. **Your own spot-check** of a sample, which is also how you learn what the questions look like.

Even after all this we report that the teacher's score on its own exam is probably a bit optimistic.

Expected cost: about $3 to $13 for generating 1,000 questions and about $3 to $13 for the re-solve pass (see `cost_log.md` for how these are computed).

## Step 2 (Phase 4): get the cluster working

Training happens on Miami's **Redhawk** cluster, which is a shared set of computers with graphics cards (GPUs). You do not run programs directly on it; you submit a **job** to a scheduler (Slurm) that queues it and runs it when a GPU is free. The first jobs are tests: does the Python environment load, can the job see a GPU, how long do we wait in the queue? Free, but essential, because the cluster's rules (internet access, storage limits) are not fully known yet.

## Step 3: generate 1,000 training examples

The teacher writes about 1,000 new questions on statistics and R, each with a worked answer, using prompts kept apart from the benchmark prompts. Each example follows one fixed template (`Question: ...`, then `Answer: ...`) with a short answer that ends in a clearly marked final answer, and the training code will add the end-of-text token (id 0) after every answer so the student learns to stop. Loss is counted only on the answer and that end token, so the student is graded on writing the answer, not on copying the question. We record the `usage` numbers the API returns for every response, because they tell us the true tokens per example and therefore the true cost per example. Then we:

- **Decontaminate** against the frozen benchmark (see Step 1).
- **Lightly verify** the set: run the R code to see that it actually works, and hand-check a sample. The heavy verification with ChatGPT is Phase 7 of the full project, not needed for a 1,000 example pilot.
- Drop anything that fails. Because some items will fail, we plan to generate 10 to 25% more than we need.

If this set passes, it will later become the 1,000 example subset of the bigger training sets, so we do not pay for it twice.

Expected cost: about $3 to $13 (plus up to about $3 for the extra items).

## Step 4: train the 70M student

We take the original Pythia 70M model (the pinned checkpoint described in `model_versions.md`) and fine-tune it on the 1,000 examples on Redhawk. We record how long it takes, how much GPU memory it uses at its peak, and the queue wait. Peak memory matters because the biggest model (1B) might not fit on one GPU, and the pilot's numbers for the small model help us predict that.

## Step 5: take the exam

We run the frozen benchmark through three things and compare their scores. The protocol is fixed in advance (same prompt format, cut each output at the first blank line or at a new `Question:`, at most a set number of new tokens, greedy decoding), because Step 0 showed untrained models do not stop by themselves and their scores swing with the prompt format:

- **Untrained Pythia 70M** (free): the starting point. Any improvement has to be measured against this.
- **Fine-tuned Pythia 70M**: did training on 1,000 examples help?
- **The teacher (Claude Sonnet 5.5)**, once (about $3 to $13): the ceiling we compare against. The project's main metric is the student's accuracy as a fraction of the teacher's.

Do not expect a 70M model trained on 1,000 examples to do well. A tiny model on a tiny dataset may score near zero on hard questions. The pilot is not testing whether the model is good; it is testing whether **every part of the pipeline runs and gives numbers we can trust**, and whether any improvement over untrained is visible at all.

## Step 6: the go/no-go review

We then answer these questions and write the results in the README and `progress_update.md`:

- Did every step run end to end without hand-fixing?
- What did a training example really cost, and what does that make 50,000, 100,000 and 200,000 examples cost? Does the funding request still make sense?
- How long did a training run take and how long was the queue, so how long will the full grid of 20 models take?
- Are the R-code and format success thresholds (90% in the README) realistic for these models?
- Did the answer keys hold up under the layered checks, or do we need a stronger process before scaling?

If the answers are acceptable, we scale up. If not, we fix the weakest part first.

## Expected pilot cost

About **$13 to $57** in total (four runs of 1,000 items at $3 to $13 each, plus up to about $3 for replacement items). Everything is logged in `cost_log.md` as it is spent, and the table there compares expected and actual.
