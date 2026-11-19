# Retired: the teacher precision test (archived 2026-11-18)

**What this file is.** The project had planned to test whether a compressed copy of the teacher (official FP8, or a community 4-bit checkpoint) could write the data instead of BF16. The plan used two measures (usable replies and independently checked answer correctness), a non-inferiority margin of 3 percentage points, sample sizes computed in advance, and a feasibility gate on hand-judging.

**Why it was retired (owner decision, 2026-11-16 to 2026-11-18).**
- **4-bit** was dropped first, because community checkpoints have thin documentation and need extra provenance work.
- **The FP8 trade-off.** Published evidence (research of 2026-11-16) suggests official FP8 is close to BF16 and about 1.4 to 1.8 times faster, but nothing proves it for this project's setup. A proper test would cost about 1 to 2 weeks and 5 to 15 hours of hand-judging, to save roughly 400 to 630 GPU-hours (about 4 to 7 cluster days on 4 GPUs) if all 200,000 examples are generated.
- **The decision:** BF16 for all generation, without a test. BF16 is the model as released, affordable (about 1,425 GPU-hours for everything) and was already the protocol's default. FP8 and 4-bit are recorded as not tested and not used.

**What replaced it.** A quick, observational check of thinking on against thinking off (`docs/methodology/workflow.md` Section 2.1).

**How to see the full files as they were.** Commit `770dc4d` (the last one before this decision) holds them unchanged: `git show 770dc4d:docs/methodology/workflow.md`. Each excerpt below is copied exactly and shown as a quotation (each line starts with `> `); its section and line references point to the old documents.

---

## Section 2.1: the precision-test protocol (two endpoints, sample sizes, feasibility gate, 4-bit rule, decision rule)

*From `docs/methodology/workflow.md`, lines 122-161, as of 2026-11-18 before the change, verbatim (quoted):*

> **Choosing the teacher precision (decided 2026-11-11; protocol pre-registered before it runs).** *Precision* is how many bits store each of the model's numbers: BF16 uses 16, FP8 uses 8, a 4-bit version uses 4. Fewer bits mean a smaller, faster model, and possibly a slightly worse one.
> - **One precision is used for all generation.** The benchmark and every training set come from the same teacher setup. Mixing precisions across data sizes would add a second difference between the conditions being compared.
> - **What is compared.** BF16 (the reference), FP8 and 4-bit, all on Talon and all served by vLLM, so neither the engine nor the hardware differs. This replaces the earlier plan to compare Redhawk's 4-bit file with Talon's BF16.
> - **Two endpoints, measured on the same development slots (BM8xxx, never benchmark or training):**
>   - **Usability, on all slots:** the item is usable on the first attempt. That means a complete, parseable reply that passes the automatic checks, and for a number item, a key that R could recompute from the item's own code (run in the R sandbox, Section 4, safeguard 10).
>   - **Answer correctness, on a stratified sample:** checked independently of the teacher. A computable answer is checked by R in the sandbox, and anything else by the owner by hand, with every disagreement adjudicated.
>     - **Why usability alone is not enough:** a compressed model can write perfectly formatted answers that are more often wrong.
>     - **Why no language model judges this endpoint:** the precision decides how all the training data is made, so a model grader's verdicts are kept out of it (Section 2.3).
> - **The statistics.** Two comparisons against BF16 (FP8 vs BF16, 4-bit vs BF16) with a multiplicity adjustment (Holm, or Bonferroni at one-sided α = 0.025 each). This is a non-inferiority test: a lower precision passes if the confidence interval for its paired difference from BF16 stays above −3 percentage points on **both** endpoints.
>   - The 3-point margin is provisional. Before the run, it must be justified in writing as the largest loss of teacher quality that would not change the study's conclusions, not only by the GPU time it saves.
>   - **The margin is never widened to make the sample smaller.**
> - **Sample sizes, calculated before any precision-test output exists.**
>   - **What is computed.** For each comparison and each endpoint, the number of paired slots needed to show non-inferiority with the declared power. A *paired* slot is one question slot answered by both precisions. The *discordance* ψ (psi) is the share of slots where the two precisions disagree: one is usable or correct and the other is not. If the two precisions truly perform the same, the approximate number of slots is
>
>     n ≈ (z₁₋α + z_power)² × ψ / Δ²
>
>     Here Δ = 0.03 is the margin. z₁₋α = 1.96 is the normal quantile for one-sided α = 0.025, which is used for every comparison, even if the 4-bit arm is dropped. z_power is 0.84 for 80% power and 1.28 for 90%.
>   - **Worked numbers.**
>
>     | Assumed discordance ψ | Slots at 80% power | Slots at 90% power |
>     |---|---|---|
>     | 0.05 | 437 | 584 |
>     | 0.10 | 873 | 1,168 |
>     | 0.15 | 1,309 | 1,752 |
>
>   - **What is declared before the run:** the power (80% is proposed), and each assumed ψ with its source. The usability ψ is re-estimated from a 100-slot first run.
>   - **The manual workload** of the correctness endpoint is roughly the number of slots × the number of arms × the share of items R cannot check. That share is about 70% if only number items are computable. *Example:* ψ = 0.10 at 80% power with three arms (BF16, FP8, 4-bit) is about 873 × 3 × 0.7 ≈ 1,830 judgments by hand.
> - **Feasibility gate.** Before any precision-test output exists, the owner writes down the largest number of hand judgments that is practical.
>   - **If the calculation needs more:** BF16 is used for all generation. FP8 and 4-bit may still be run on a feasible sample, but only as an **exploratory**, descriptive comparison that cannot change the choice.
>   - The −3 margin is not widened to fit the workload. BF16 is the safe default because it is the model as released, and its GPU time is affordable: about 1,228 GPU-hours for 200,000 examples, from Stage T, with no GPU-hour cap.
> - **The 4-bit arm (decided 2026-11-12).** Qwen publishes no official 4-bit release of Qwen3.6-27B, so the 4-bit arm uses a **community-quantized** checkpoint. It is kept only if all of the following are verified before download:
>   - **Provenance:** prefer a reproducible checkpoint quantized **directly from the official BF16 weights**, with **no additional fine-tuning**.
>   - **License:** compatible with this use.
>   - **Quantization method:** documented.
>   - **vLLM `0.32.0` compatibility on H100:** confirmed. For example, a GPTQ checkpoint with `desc_act=True` is served incorrectly by vLLM 0.30 and later.
>
>   The exact quantization configuration is recorded with the results: method, bits, group size, symmetric or asymmetric, calibration data, the quantization tool and its version, and the repository commit. The comparison is reported as one between **specific model deployments** (this checkpoint served this way), not as a universal comparison of 4 bits against 16. It uses the **same pre-registered non-inferiority criteria** as FP8 against BF16. **If no candidate passes the provenance and compatibility checks, the 4-bit arm is dropped rather than delaying the pilot;** the test then compares FP8 with BF16 only. Candidates found on 2026-11-12, still to be checked: `cyankiwi/Qwen3.6-27B-AWQ-INT4`, `btbtyler09/Qwen3.6-27B-GPTQ-4bit`, `Lorbus/Qwen3.6-27B-int4-AutoRound` (`docs/models/model_versions.md` Section 6).
> - **Decision rule.** If the feasibility gate passes, use the lowest-compute precision that is non-inferior to BF16 on both endpoints. If neither FP8 nor 4-bit passes, or the gate fails, use BF16. The chosen precision's projected total GPU time must fit the timeline, run in resumable jobs shorter than the 3-day limit.
> - **Worked example (hypothetical numbers).** On 1,000 paired slots, BF16 is usable on 88% and 4-bit on 87.2%, a difference of −0.8 points. If the adjusted lower confidence bound is −2.6 (above −3) for usability, and the correctness sample gives a lower bound of −2.1, then 4-bit passes both endpoints and is chosen. A lower bound of −3.4 on either endpoint would mean 4-bit fails.

---

## Section 10.2: the open items of the precision test

*From `docs/methodology/workflow.md`, lines 715-724, as of 2026-11-18 before the change, verbatim (quoted):*

> - [ ] **Teacher precision details** (Section 2.1).
>   - **FP8:** an official FP8 checkpoint exists (`Qwen/Qwen3.6-27B-FP8`).
>   - **4-bit:** no official release exists; the rule for a community checkpoint is decided (Section 2.1). Still open: which candidate, if any, passes the checks (done at Stage 1.3, before download).
>   - **Still to write:**
>     - the rationale for the 3-point margin;
>     - the power (80% proposed);
>     - the assumed discordance values and their source;
>     - the owner's cap on hand judgments for the feasibility gate.
>
>     The sample sizes follow from these.

---

## Pilot plan Step 1, item 4: the precision step in plain language

*From `docs/methodology/pilot_plan.md`, lines 58-70, as of 2026-11-18 before the change, verbatim (quoted):*

> 4. **Choose the teacher precision on Talon** (decided 2026-11-11; protocol in `docs/methodology/workflow.md` Section 2.1).
>    - **What precision means here:** BF16 is a 16-bit number format, about 2 bytes per parameter, so the full Qwen weights are about 53,011 MiB. FP8 uses about 1 byte per parameter and a 4-bit version about half a byte; both are smaller and usually faster, but compression can cost quality.
>    - **One precision for everything:** whichever is chosen is used for the benchmark and for every training set, so the data sizes are never written by different teacher setups.
>    - **How it is tested:** all three are run on the same development slots on Talon, served by the same engine. FP8 and 4-bit are each compared with BF16 on two things:
>      - **usable questions**, measured automatically on every slot;
>      - **answer correctness**, checked independently on a sample: by R where the answer can be computed, and by you by hand otherwise.
>
>      Both are needed because a compressed model can write perfectly formatted answers that are more often wrong. No language model judges this test, because the precision decides how all the training data is made.
>    - **How many slots are needed, worked out first.** The test asks whether the cheaper precision is "not worse by more than 3 percentage points". How many paired slots that needs depends on how often the two precisions disagree, the *discordance*. If they disagree on 10% of slots, about 873 slots are needed at 80% power. The correctness half then needs roughly 873 slots × 3 precisions × 70% (the share R cannot check) ≈ 1,830 judgments by hand (the formula is in `docs/methodology/workflow.md` Section 2.1).
>    - **The feasibility gate.** Before any test output exists, you write down how many hand judgments are practical.
>      - **If the calculation needs more:** BF16 is used for everything. The cheaper precisions may still be run on a smaller sample, but only as an *exploratory* comparison that cannot change the choice.
>      - **The margin stays fixed:** the 3-point margin is never loosened to make the sample smaller.
>    - **The rule:** if the gate passes, the cheapest precision that is not worse than BF16 by more than 3 percentage points on both measures is chosen. The margin's scientific justification is written down first.
