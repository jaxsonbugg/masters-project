# Masters Project: Distilling a Large Language Model into Small Domain-Specialized Models for Statistics and R

**Author:** Jaxson Bugg (buggjm@miamioh.edu)

**Advisor:** Dr. Donghyung Lee

**Institution:** Miami University

**Duration:** Two semesters (from September 2026)

**Status (2026-11-12):** Teacher (Qwen3.6-27B, BF16, vLLM 0.32.0) deployed on Talon: smoke test and throughput benchmark complete. Evaluation design revised: training data is retained without correctness-based filtering, and a frontier-model grader scores the benchmark. Benchmark generation pending.

## Overview

This project measures how much domain capability a frontier-class teacher model can transfer to much smaller student models through knowledge distillation, and at what cost. A 27B-parameter open-weight teacher writes statistics and R questions and worked solutions. These become supervised fine-tuning data for four Pythia students that range from 70M to 1B parameters. Each student is evaluated before and after fine-tuning on a frozen, held-out benchmark. The result is a size-by-data-quantity map of accuracy and inference efficiency, used to locate the point where further compression causes disproportionate loss.

## Research question

**How small can a specialized language model be, distilled from a large teacher, and still retain useful capability in statistics and R programming?**

1. How does post-distillation accuracy scale with student size (70M, 160M, 410M, 1B)?
2. How does it scale with distillation-set size (1k to 200k examples)?
3. Is there a knee in the size-performance curve?
4. What are the efficiency gains (parameters, memory, latency, GPU time per query) relative to the teacher?
5. Which differences are statistically significant (paired tests with multiplicity correction, bootstrap CIs)?

## Experimental design

| Factor | Setting |
|---|---|
| Teacher | Qwen3.6-27B (Apache 2.0), BF16 weights served by vLLM on Talon; revision pinned |
| Students | Pythia 70M / 160M / 410M / 1B, deduped variants, final `step143000` checkpoints pinned by commit SHA |
| Distillation data | Nested sets of 1k, 10k, 50k, 100k, 200k teacher-generated examples (50k is the minimum fallback), retained without correctness-based filtering: format, duplicate, decontamination and length checks only. Their correctness is unknown and may vary by category, by design |
| Benchmark | ~1,000 held-out questions in five categories and three difficulty levels. Answers are independently checked where computationally possible (R recomputes numeric keys and tests R-code items), every question is screened for ambiguity by a frontier model with owner review, and a stratified 150-item sample is audited by hand. Frozen and hashed before any training |
| Grading | Codex (frontier model) judges each final answer against the reference key, blind to the answering model; teacher and students are graded identically. Validity thresholds are fixed on development data before evaluation; calibration answers, a human audit and a deterministic cross-check are reported alongside |
| Code execution | Model-written R runs only in a sandbox (WSL2 + bubblewrap: no network, no access to the repository or personal files, resource limits) |
| Conditions | 4 untrained baselines + up to 20 fine-tuned students (4 sizes x 5 data sizes) + the teacher |
| Compute | Talon (4 nodes x 4 H100 NVL) for generation, training and evaluation; Redhawk (V100) as the fallback |

**Why Pythia.** All Pythia sizes are trained on the same deduplicated data in the same order. Differences between students can therefore be attributed to size rather than to pretraining data.

**Controls.**
- Identical training data, hyperparameter recipe and evaluation protocol across sizes.
- Nested training sets, so data-size effects are not confounded with content.
- Benchmark and training data come from separate prompts, with decontamination between them.
- Hyperparameters are chosen on a separate development set (held-out loss), never on the benchmark; the grader never influences training.

## Success criteria (pre-registered 2026-09-29)

A (student size, data size) pair counts as a successful specialization only if it meets all of the following:

1. **Retained accuracy.** The lower bound of the bootstrap 95% CI of student/teacher accuracy reaches a tier: Useful >= 70%, Strong >= 85%, Near-parity >= 95%. The student also needs an absolute floor of 60%. Answers are graded by the grader against the reference key. The original execution-based grading of R items is kept as a cross-check (dated deviation, 2026-11-12).
2. **Gain over baseline.** The student is significantly better than its own untrained version (McNemar's test, Holm-corrected).
3. **Usable output.** At least 90% of responses are well-formed and at least 90% of R code runs (executed in the sandbox).
4. **Efficiency.** This criterion is now two separate requirements, recorded as a dated deviation (2026-11-06) because the teacher became a local model:
   - **4a:** at least 10x fewer parameters than the teacher.
   - **4b:** at least 10x less GPU time per query and at least 10x lower median latency on the same GPU.

The full definitions, the original wording and the measurement protocol are in [docs/methodology/workflow.md](docs/methodology/workflow.md).

## Current status and next steps

- **Complete:**
  - Research design and pre-registration.
  - Student checkpoints pinned.
  - Base-model behavior probe.
  - Question-generation pipeline: prompt v6, R-computed numeric keys, automatic validity checks, regeneration.
  - Redhawk llama.cpp deployment.
  - Talon bring-up: vLLM 0.32.0 pinned, BF16 weights downloaded and hashed, smoke test and throughput benchmark (about 6 GPU-hours per 1,000 examples on one H100).
- **Next:**
  - Set up the R sandbox.
  - Choose the teacher precision (BF16 against FP8 and a conditional community 4-bit checkpoint), with sample sizes and a feasibility gate fixed in advance.
  - Fix slot diversity (the near-duplicate questions found in testing).
- **Then:**
  - Generate, check and freeze the benchmark.
  - Set up and validate the Codex grader.
  - Run the end-to-end pilot (1k examples, Pythia 70M).
  - Scale to all sizes.

## Repository map

| Path | Contents |
|---|---|
| [docs/methodology/workflow.md](docs/methodology/workflow.md) | Full methodology: criteria, phase checklists, benchmark and data safeguards, metrics, statistics, risks, open decisions |
| [docs/progress_update.md](docs/progress_update.md) | Dated log of every change and decision |
| [docs/logs/compute_log.md](docs/logs/compute_log.md) / [docs/logs/cost_log.md](docs/logs/cost_log.md) | Cluster jobs and measured local runs / paid and plan-metered calls (the Codex grader) |
| `docs/` | Organized by topic: `methodology/` (workflow, pilot plan), `models/` (model versions, teacher evaluation, Pythia behavior), `clusters/` (cluster selection, Talon setup), `logs/` (compute and cost logs), `guides/` (Git notes), `archive/` (retired methods, reference only); only `progress_update.md` sits at the root |
| `code/generation/` | Benchmark slot blueprint, validity checks and the R key step for benchmark items (`generate_benchmark.py`); teacher client for the cluster deployments (`open_teacher_test.py`); throughput report |
| `code/evaluation/`, `code/tests/` | Pythia probe; local test suites for the pipeline and the cluster job scripts |
| `configs/` | `paths.yaml` (all storage locations) and the Redhawk and Talon Slurm scripts |
| `data/prompts/` | Generation prompt (v6, SHA-256 pinned by the job scripts) |
| `recovery/` | Rebuild procedures for everything stored outside the repository |
| `results/`, `environment/` | Small result files; pinned Python packages |

Large artifacts (weights, teacher outputs, environments) are kept outside Git, in `C:\masters_project_large\` and on the clusters. Each one has a rebuild procedure in `recovery/`.
