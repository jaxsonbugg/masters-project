# Retired: verification of the teacher's training data, and the external verifier (archived 2026-11-12)

**What this file is.** On 2026-11-12 the project stopped checking the correctness of the teacher's *training* data. The training examples Qwen writes are now retained without correctness-based filtering. Their correctness is unknown and may vary by question category. This is an intentional property of the experimental design, because the study asks whether distillation lets a student approach the teacher, not whether it produces a perfect student. The students are evaluated independently on a frozen benchmark.

**What was retired:**
- the external, different-family verifier (DeepSeek or Mistral, through a paid API);
- the triage step that chose which items it would see;
- the blind re-solve by Qwen;
- the phase that verified the training data (old Phase 7).

**What was not retired:**
- the benchmark quality procedure: R-computed number keys, R checks, a Codex screen of every question and a 150-item manual audit;
- the format, duplicate, decontamination and length checks on training data;
- all of the code. None of the retired methods had been built; they existed only in the documents.

**What replaced the verifier as a model-based judge:** a frontier model (Codex) grades the teacher's and the students' benchmark answers against the benchmark's reference key. It is used only for evaluation and for the benchmark screen. See `docs/methodology/workflow.md` Sections 2.3 and 4, and the progress entry of 2026-11-12.

**Why keep this file.** It records what the plan was before the change, in the words used then, so the history can be read without digging through Git. It is reference material only and is not part of the workflow.

**How to see the full files as they were.** Every file is preserved unchanged under the annotated Git tag `pre-verification-removal`:
- `git show pre-verification-removal:docs/methodology/workflow.md` prints the old workflow;
- `git checkout pre-verification-removal -- <path>` restores a file into the working tree.

The line numbers below refer to the files at that tag. Each excerpt is copied exactly and shown as a quotation (each line starts with `> `). It still uses the old section and safeguard numbers, and references inside it point to the old documents.

---

## Section 2.1: the teacher-precision protocol as it stood (endpoint 2 relied on the verifier)

*From `docs/methodology/workflow.md`, lines 100-117, verbatim (quoted):*

> **Choosing the teacher precision (decided 2026-11-11; protocol pre-registered before it runs).** *Precision* is how many bits store each of the model's numbers: BF16 uses 16, FP8 uses 8, a 4-bit version uses 4. Fewer bits mean a smaller, faster model, and possibly a slightly worse one.
> - **One precision is used for all generation.** The benchmark and every training set come from the same teacher setup. Mixing precisions across data sizes would add a second difference between the conditions being compared.
> - **What is compared.** BF16 (the reference), FP8 and 4-bit, all on Talon and all served by vLLM, so neither the engine nor the hardware differs. This replaces the earlier plan to compare Redhawk's 4-bit file with Talon's BF16.
> - **Two endpoints, measured on the same development slots (BM8xxx, never benchmark or training):**
>   - **Usability:** the item is usable on the first attempt, and a number item also has an R-verified key.
>   - **Answer correctness:** checked on a stratified sample, by R where possible and otherwise by the validated verifier, with every disagreement adjudicated by hand. Usability alone is not enough, because a well-formatted answer with runnable R can still misread the question.
> - **The statistics.** Two comparisons against BF16 (FP8 vs BF16, 4-bit vs BF16) with a multiplicity adjustment (Holm, or Bonferroni at one-sided α = 0.025 each). This is a non-inferiority test: a lower precision passes if the confidence interval for its paired difference from BF16 stays above −3 percentage points on **both** endpoints.
>   - The 3-point margin is provisional. Before the run, it must be justified in writing as the largest loss of teacher quality that would not change the study's conclusions, not only by the GPU time it saves.
>   - Sample sizes are computed before the run, at an assumed share of slots where the two precisions disagree. They are re-estimated from a 100-slot first run.
> - **The 4-bit arm (decided 2026-11-12).** Qwen publishes no official 4-bit release of Qwen3.6-27B, so the 4-bit arm uses a **community-quantized** checkpoint. It is kept only if all of the following are verified before download:
>   - **Provenance:** prefer a reproducible checkpoint quantized **directly from the official BF16 weights**, with **no additional fine-tuning**.
>   - **License:** compatible with this use.
>   - **Quantization method:** documented.
>   - **vLLM `0.32.0` compatibility on H100:** confirmed. For example, a GPTQ checkpoint with `desc_act=True` is served incorrectly by vLLM 0.30 and later.
>
>   The exact quantization configuration is recorded with the results: method, bits, group size, symmetric or asymmetric, calibration data, the quantization tool and its version, and the repository commit. The comparison is reported as one between **specific model deployments** (this checkpoint served this way), not as a universal comparison of 4 bits against 16. It uses the **same pre-registered non-inferiority criteria** as FP8 against BF16. **If no candidate passes the provenance and compatibility checks, the 4-bit arm is dropped rather than delaying the pilot;** the test then compares FP8 with BF16 only. Candidates found on 2026-11-12, still to be checked: `cyankiwi/Qwen3.6-27B-AWQ-INT4`, `btbtyler09/Qwen3.6-27B-GPTQ-4bit`, `Lorbus/Qwen3.6-27B-int4-AutoRound` (`docs/models/model_versions.md` Section 6).
> - **Decision rule.** Use the lowest-compute precision that is non-inferior to BF16 on both endpoints. If neither FP8 nor 4-bit passes, use BF16. The chosen precision's projected total GPU time must fit the timeline, run in resumable jobs shorter than the 3-day limit.
> - **Worked example (hypothetical numbers).** On 1,000 paired slots, BF16 is usable on 88% and 4-bit on 87.2%, a difference of −0.8 points. If the adjusted lower confidence bound is −2.6 (above −3) for usability, and the correctness sample gives a lower bound of −2.1, then 4-bit passes both endpoints and is chosen. A lower bound of −3.4 on either endpoint would mean 4-bit fails.

---

## Section 2.1: the fallback line (it referred to the Phase 7 pass rate)

*From `docs/methodology/workflow.md`, line 119, verbatim (quoted):*

> **Fallback if the teacher underperforms.** If teacher accuracy on the benchmark is below 80%, or the Phase 7 pass rate is poor, the first step is the same model with a higher precision or more thinking, not a different model. The alternatives ranked in `docs/models/teacher_model_evaluations.md` stay documented but are not the plan.

---

## Section 2.3: the external verifier

*From `docs/methodology/workflow.md`, lines 153-172, verbatim (quoted):*

> ### 2.3 The verifier (chosen later, validated before use)
>
> **What and why.** Qwen writes the questions and answers, so checking Qwen with Qwen is not independent. The *verifier* is a second language model, from a different family, that checks the items our own checks (R, the re-solve) cannot settle.
>
> **Requirements (hard gates):**
> - open weights;
> - relatively inexpensive;
> - provider terms that allow using its verdicts to filter training data (DeepSeek's terms explicitly allow distillation);
> - not OpenAI or Anthropic;
> - a different model family from Qwen.
>
> **Candidates:** DeepSeek (the likely front-runner) and Mistral, with others from `docs/models/teacher_model_evaluations.md`. It runs through a paid API, so its expected cost is stated before every run and every call is logged in `docs/logs/cost_log.md`.
>
> **When.** The verifier is chosen after the first real data exists: the outputs of the precision test (Section 2.1). The choice is recorded in `docs/models/verifier_selection.md`.
>
> **Validation before it is trusted.**
> - **Connectivity test (about 20 items).** This checks only that the API works, the JSON verdicts parse and costs are logged.
> - **Reliability test (100 to 200 reference items).** The set mixes independently checked correct answers with deliberately wrong ones: wrong numbers, wrong keys, plausible misconceptions. It is built from development items, never the benchmark.
> - **What is measured:** the **false-acceptance rate** (a wrong answer accepted), the false-rejection rate and the abstention rate.
> - **The priority is low false acceptance,** because the verifier exists to remove wrong training examples. A threshold is declared before the test. A verifier that misses it is not used, and the next candidate is tested.

---

## Section 3: ground truth as it stood

*From `docs/methodology/workflow.md`, lines 191-195, verbatim (quoted):*

> - **Ground truth.**
>   - Number items are auto-graded within a tolerance; their keys come from R (Section 2.2).
>   - Multiple-choice items are graded by letter.
>   - R code items are graded by running the code against an R check that receives the student's answer as `candidate`.
>   - Free-text explanations are not graded for accuracy.

---

## Section 4: problem 2 as it stood

*From `docs/methodology/workflow.md`, line 209, verbatim (quoted):*

> 2. **Shared mistakes:** if Qwen gets a kind of question wrong, the wrong answer can appear in both the training data and the answer key. The student is then rewarded for copying the teacher's error.

---

## Section 4: safeguards 6 (triaged verification) and 7 (reporting rule) as they stood

*From `docs/methodology/workflow.md`, lines 231-239, verbatim (quoted):*

> 6. **Independent answer verification, triaged** (decided 2026-11-11).
>    - (a) **R computes every number key** from the teacher's own code, so arithmetic slips cannot survive. The `r_solution` field must be present in every reply. It must contain substantive executable R wherever R can compute the answer. Where R does not apply (for example a conceptual question), it is an explicit "not applicable" empty value, so the model is never pushed into writing meaningless R.
>    - (b) **R checks** test every code answer against the key and against deliberately wrong answers; a check that accepts a wrong answer is flagged as "vacuous".
>    - (c) **A blind re-solve by Qwen** answers each question without seeing the key. It is a **consistency check only**: two Qwen outputs can share the same misunderstanding, so an agreeing re-solve never counts as independent validation.
>    - (d) **Triage, then the verifier.** Items whose key R established and whose re-solve agrees need no LLM check. Everything R cannot settle goes to the different-family verifier (Section 2.3): every multiple-choice, conceptual, short-text and output-interpretation item, every soft flag, and every re-solve disagreement. Disagreements are adjudicated by hand. The verifier only checks; it never writes training text. Triage keeps the verifier's usage, and its cost at 200k examples, small.
>    - (e) **A manual audit** of a representative random sample of about **150 benchmark items**, stratified by category and **including items that passed every automated check**. It covers what R cannot: code that is consistent but answers a misread question.
>      - **What is reported:** the audit's error rate describes the benchmark **before** corrections, and the original results are kept.
>      - **The residual error rate:** a claim about it after corrections needs a fresh, independent random sample.
> 7. **Reporting rule.** The benchmark is reported as **teacher-generated**, kept distinct from any externally sourced evaluation, together with its independent-key methods and audit error rate. Teacher accuracy is always reported with the caveat that the teacher wrote the benchmark, and the verifier's agreement rate is reported next to it.

---

## Section 4: the limitations as they stood

*From `docs/methodology/workflow.md`, lines 253-257, verbatim (quoted):*

> **Limitations that remain, stated honestly.**
> - Shared blind spots cannot be removed completely. The verifier is a different model family, but large models make some of the same mistakes.
> - R checks the arithmetic, not whether the code answers the question as written. A misread question with consistent code gets a "correct" key.
> - Decontamination thresholds trade leakage against over-removal. Any threshold leaves some near-paraphrases in, and removes some harmless examples.
> - The benchmark measures skill *as Qwen frames it*. Results say how well students learn from this teacher, not how well they would do on an independent human-written exam.

---

## Section 5, Phase 3: the verification items as they stood

*From `docs/methodology/workflow.md`, lines 290-299, verbatim (quoted):*

> - [ ] Require the `r_solution` and `working` fields in every reply ("not applicable" where R does not apply), then update the regression fixture (Section 4, safeguard 6a)
> - [ ] Choose the teacher precision (BF16, FP8 or 4-bit) with the pre-registered protocol in Section 2.1, before any benchmark generation
> - [ ] Choose and validate the verifier on the precision-test outputs (Section 2.3)
> - [ ] Fix slot variety before any 1,000-question run (Section 4, safeguard 4), then re-run `dupcheck`
> - [ ] Blind re-solve command (a consistency check) and the verification triage (Section 4, safeguard 6)
> - [ ] Decide whether output-interpretation items need an automatic consistency check of the printed output, or should have R generate the printout. About a third of the trial items had small inconsistencies; no keys were affected.
> - [ ] Generate about 1,000 benchmark questions and the ~200-item development set with Qwen on Talon at the chosen precision; regenerate failures; `verify` and `dupcheck` the whole set
> - [ ] Keep short-text items tightly constrained (a name, a term, a value); rewrite open-ended ones as multiple choice or drop them
> - [ ] Manual audit of about 150 random benchmark items (Section 4, safeguard 6e)
> - [ ] Make every answer key checkable, strongest check first (Section 4, safeguard 6)

---

## Section 5, Phase 4: the training-data verification item

*From `docs/methodology/workflow.md`, line 307, verbatim (quoted):*

> - [ ] Generate about 1,250 training questions and teacher answers on Talon; R checks, triage, verifier on the uncertain items (a rehearsal for 200k)

---

## Section 5, Phase 7: verify teacher-generated data

*From `docs/methodology/workflow.md`, lines 333-339, verbatim (quoted):*

> ### Phase 7: Verify teacher-generated data
> - [ ] Use the verifier chosen and validated in Phase 3 (Section 2.3); log every paid call in `docs/logs/cost_log.md` with the expected cost stated first
> - [ ] Have the verifier grade the teacher outputs
> - [ ] Objective numerical answers must be verified correct; R code should be improved where needed
> - [ ] Execute R code where possible to check that it runs and produces the stated output
> - [ ] Score answers, then manually review the ones flagged wrong to understand why (error taxonomy)
> - [ ] Fix or drop failing items; record the pass rate and error categories

---

## Section 6: the data-quality metrics as they stood

*From `docs/methodology/workflow.md`, lines 385-388, verbatim (quoted):*

> **Data quality**
> - First-attempt pass rate of generated questions, soft-flag rate, duplicate rate
> - Verifier pass rate and error-type breakdown for teacher-generated data
> - Number of training examples removed by decontamination

---

## Section 10.1: the risks table as it stood

*From `docs/methodology/workflow.md`, lines 465-477, verbatim (quoted):*

> | Risk | Mitigation |
> |---|---|
> | GPU time and queue waits on Talon (shared nodes, 3-day job limit; Research Computing confirmed in writing on 2026-11-12 that there is no GPU-hour cap, but the fair-share policy lengthens waits after heavy use) | Throughput stage T measures examples per GPU-hour before the big runs; the 200k run is split into resumable jobs under 3 days, using up to 4 single-GPU jobs side by side (allowed); run 50k across all sizes first |
> | Talon unavailable or the settings wrong | Redhawk llama.cpp pipeline kept as a fallback, with its executable logic unchanged (only three comment lines were repointed on 2026-11-07); every Talon script is a draft until reviewed |
> | Shared 500 GB home quota (Redhawk and Talon together) | `fetch_talon.sh` reads the quota and refuses a download that would pass the soft limit; ask Research Computing for more space before the 200k run |
> | Same teacher writes the benchmark and the training data | Section 4: separate prompts and IDs, freeze first, decontamination, independent verification, stated limitations |
> | Teacher answer keys wrong in ways R cannot see | Blind re-solve, other-family verifier, hand checks; report teacher accuracy with the caveat |
> | Near-duplicate questions at scale | Slot-variety redesign and `dupcheck` before the 1,000-question run |
> | Pythia models are base models (not instruction-tuned), have a 2,048-token context and never stop on their own | One fixed `Question:`/`Answer:` template, short answers, explicit end-of-text token id 0, a pre-declared stop rule |
> | Very small models may score near zero, hiding differences | Easier items, plus partial-credit and validity metrics |
> | Benchmark contamination | Decontamination, checksum freeze, a separate dev set |
> | Verifier errors or blind spots shared with the teacher | Execute R code, spot-check by hand, review flagged disagreements manually |
> | Confounded comparisons across sizes | Identical recipe, data, seeds and evaluation for all students |

---

## Section 10.2: the verifier open decision

*From `docs/methodology/workflow.md`, line 481, verbatim (quoted):*

> - [ ] **Verifier model, budget and false-acceptance threshold** (Section 2.3). Gates are decided (open weights, terms allow it, not OpenAI or Anthropic, different family); the model is chosen once the precision-test outputs exist.

---

## Section 10.2: grading of short-text answers (the verifier as a semantic grader)

*From `docs/methodology/workflow.md`, lines 514-516, verbatim (quoted):*

> - [ ] **Grading of short-text answers.**
>   - **Constrained answers** (a function name, a single term) use a normalized match against the key plus listed accepted variants. Benchmark short-text items are kept constrained.
>   - **Any open-ended item** that remains needs a predeclared rubric, independently checked reference answers, the verifier as a semantic grader, and manual adjudication. Exact string matching would undercount correct answers worded differently.

---

## Pilot plan Step 1: the precision step, benchmark checking and the layered checks (re-solve, verifier, triage)

*From `docs/methodology/pilot_plan.md`, lines 53-73, verbatim (quoted):*

> 4. **Choose the teacher precision on Talon** (decided 2026-11-11; protocol in `docs/methodology/workflow.md` Section 2.1).
>    - **What precision means here:** BF16 is a 16-bit number format, about 2 bytes per parameter, so the full Qwen weights are about 53,011 MiB. FP8 uses about 1 byte per parameter and a 4-bit version about half a byte; both are smaller and usually faster, but compression can cost quality.
>    - **One precision for everything:** whichever is chosen is used for the benchmark and for every training set, so the data sizes are never written by different teacher setups.
>    - **How it is tested:** all three are run on the same development slots on Talon, served by the same engine. FP8 and 4-bit are each compared with BF16 on two things: usable questions, and answer correctness checked independently on a sample.
>    - **The rule:** the cheapest one that is not worse than BF16 by more than 3 percentage points on both (a margin whose scientific justification is written down first) is chosen.
>
> ### Generating and checking the benchmark
>
> Qwen then writes about 1,000 questions on Talon. Each question that fails the automatic checks (for example thinking aloud in the question text, an answer that appears in its own question, or an R check that never tests the student's answer) is asked for again with the same prompt, up to 3 attempts. The prompt does not say what went wrong, so the first-attempt pass rate stays an honest measure of the prompt. Then `verify` and `dupcheck` run on the whole set.
>
> **The same-teacher risk.** Qwen writes the exam, later takes it to set the teacher score, and also writes the training data. Its answer keys may contain exactly the mistakes it would make when answering, and those mistakes could also appear in the training data, so a student would be rewarded for copying them. A new request to Qwen does not remember writing a question, which removes one kind of bias, but it is the same model with the same blind spots, so a fresh Qwen call cannot be trusted to catch everything. To limit the damage we check the answer keys in layers, strongest first:
>
> 1. **Run the code.** For numeric answers and R code questions, R computes the key or runs the check. An R check must accept the key and reject three deliberately wrong answers; one that accepts a wrong answer is flagged. A computer running R does not share Qwen's blind spots.
> 2. **Blind re-solve.** A separate Qwen call solves each question without being shown the key. Where it disagrees with the key, we look by hand. This catches careless errors but not systematic ones.
> 3. **A different model family, only where needed.** Items R cannot settle go to a *verifier*: an open-weight model from a different family than Qwen, inexpensive, and from a provider whose terms allow this use (not OpenAI or Anthropic). DeepSeek is the likely choice, because its terms explicitly allow distillation; Mistral is another candidate.
>    - **Which items it gets:** every multiple-choice, conceptual and output-interpretation item, every soft flag and every re-solve disagreement. A *triage* step selects these, so the verifier only sees what our own checks cannot settle, which keeps its usage small even at 200,000 examples.
>    - **When it is chosen:** once the first real data exists (the precision test). It is tested first on 100 to 200 reference items, some deliberately wrong, to measure how often it accepts a wrong answer.
>    - **Its role:** it only checks, and never writes training text or questions. Its calls are paid, so the expected cost is stated first and every call is logged in `docs/logs/cost_log.md`.
> 4. **Your own audit of about 150 random benchmark items**, stratified by category and including items that passed every check. This covers what R cannot: code that is consistent but answers a misread question. It also measures the leftover error rate. If errors are found and fixed, a new random sample is needed to claim anything about the error rate after the fixes.
>
> Even after all this we report that the teacher's score on its own exam is probably a bit optimistic, with the verifier's agreement rate next to it. The benchmark is then frozen (hashed and stored read-only) before any training example exists.

---

## Pilot plan Step 3: verifying the training set

*From `docs/methodology/pilot_plan.md`, lines 88-94, verbatim (quoted):*

> We record the token counts the engine reports for every response and the GPU time of every generation job, because together they give the true GPU time per example, which is what the full-scale projection needs. Then we:
>
> - **Verify** the set the same way as the benchmark, at small scale: run the R code, triage, and send the uncertain items to the verifier. This is a rehearsal that measures the real triage rate and cost per item before 200,000 examples.
> - **Check the length.** Pythia can only read 2,048 tokens at once (its `max_position_embeddings`). Every example (question, working, final answer and end token) is measured with the Pythia tokenizer. One that is too long is rejected or deliberately shortened, never cut off silently, because cutting would remove the final answer or the end token. The share affected is recorded.
> - Drop anything that fails. Because some items will fail, we generate 10 to 25% more than we need.
>
> If this set passes, it later becomes the 1,000 example subset of the bigger training sets, so the GPU time is not spent twice.

---

## Pilot plan Step 6 and the expected cost, as they stood

*From `docs/methodology/pilot_plan.md`, lines 123-139, verbatim (quoted):*

> ## Step 6: the go/no-go review
>
> We then answer these questions and write the results in `docs/methodology/workflow.md` and `progress_update.md`:
>
> - Did every step run end to end without hand-fixing?
> - How much GPU time did one training example take to write, and what does that make 50,000, 100,000 and 200,000 examples take? Does that fit within the 3-day job limit (split into restartable pieces) and the project timeline?
> - How long did a training run take and how long was the queue, so how long will the full grid of 20 models take?
> - Is the storage plan safe? The shared home folder has a 480 GB soft quota (about 17 GB used so far).
> - Are the R-code and format success thresholds (90% each, `docs/methodology/workflow.md` Section 1.1) realistic for these models?
> - Did the answer keys hold up under the layered checks, or do we need a stronger process before scaling? What would the verifier cost at full scale?
> - Did the criterion-4b timing protocol give stable, repeatable numbers?
>
> If the answers are acceptable, we scale up. If not, we fix the weakest part first.
>
> ## Expected pilot cost
>
> Generation, training and evaluation run on Miami's clusters and cost **no money**; their cost is GPU-hours, which are logged per job in `docs/logs/compute_log.md` and summed there. The only possible paid item is the different-family verifier, which is still to be decided. Before any paid verifier run, its expected cost is written down, and afterward the actual cost is compared in `docs/logs/cost_log.md`.
