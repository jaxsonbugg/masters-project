# Masters Project: Distilling a Large Language Model into Small Domain-Specialized Models for Statistics and R

**Author:** Jaxson Bugg (buggjm@miamioh.edu)

**Advisor:** Dr. Donghyung Lee

**Institution:** Miami University

**Duration:** Two semesters (from September 2026)

**Status (2026-11-06):** Talon (H100) account active and probed. Teacher deployment (Qwen3.6-27B, vLLM, BF16) in preparation. Benchmark generation pending.

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
| Distillation data | Nested sets of 1k, 10k, 50k, 100k, 200k verified examples (50k is the minimum fallback) |
| Benchmark | ~1,000 held-out questions in five categories and three difficulty levels; frozen and hashed before any training |
| Answer verification | R execution writes numeric keys; R checks test code answers; an independent frontier-model verifier (to be selected) and manual spot checks for the rest |
| Conditions | 4 untrained baselines + up to 20 fine-tuned students (4 sizes x 5 data sizes) + the teacher |
| Compute | Talon (4 nodes x 4 H100 NVL) for generation, training and evaluation; Redhawk (V100) as the fallback |

**Why Pythia.** All Pythia sizes are trained on the same deduplicated data in the same order. Differences between students can therefore be attributed to size rather than to pretraining data.

**Controls.**
- Identical training data, hyperparameter recipe and evaluation protocol across sizes.
- Nested training sets, so data-size effects are not confounded with content.
- Benchmark and training data come from separate prompts, with decontamination between them.

## Success criteria (pre-registered 2026-09-29)

A (student size, data size) pair counts as a successful specialization only if it meets all of the following:

1. **Retained accuracy.** The lower bound of the bootstrap 95% CI of student/teacher accuracy reaches a tier: Useful >= 70%, Strong >= 85%, Near-parity >= 95%. The student also needs an absolute floor of 60%.
2. **Gain over baseline.** The student is significantly better than its own untrained version (McNemar's test, Holm-corrected).
3. **Usable output.** At least 90% of responses are well-formed and at least 90% of R code runs.
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
  - Talon access and read-only probe.
- **Next (Talon bring-up):**
  - Pin the vLLM version and GPU request syntax.
  - Review the settings.
  - Run a scheduler acceptance test.
  - Download the BF16 weights.
  - Run the smoke test and the throughput benchmark.
- **Then:**
  - Compare Qwen at 4-bit and BF16 on Talon.
  - Fix slot diversity (the near-duplicate questions found in testing).
  - Generate and freeze the benchmark.
  - Run the end-to-end pilot (1k examples, Pythia 70M).
  - Scale to all sizes.

## Repository map

| Path | Contents |
|---|---|
| [docs/methodology/workflow.md](docs/methodology/workflow.md) | Full methodology: criteria, phase checklists, benchmark and data safeguards, metrics, statistics, risks, open decisions |
| [docs/progress_update.md](docs/progress_update.md) | Dated log of every change and decision |
| [docs/logs/compute_log.md](docs/logs/compute_log.md) / [docs/logs/cost_log.md](docs/logs/cost_log.md) | Cluster jobs and measured local runs / paid API calls |
| `docs/` | Organized by topic: `methodology/` (workflow, pilot plan), `models/` (model versions, teacher evaluation, Pythia behavior), `clusters/` (cluster selection, Talon setup), `logs/` (compute and cost logs), `guides/` (Git notes); only `progress_update.md` sits at the root |
| `code/generation/` | Benchmark slot blueprint, validity checks and R key verification (`generate_benchmark.py`); teacher client for the cluster deployments (`open_teacher_test.py`); throughput report |
| `code/evaluation/`, `code/tests/` | Pythia probe; local test suites for the pipeline and the cluster job scripts |
| `configs/` | `paths.yaml` (all storage locations) and the Redhawk and Talon Slurm scripts |
| `data/prompts/` | Generation prompt (v6, SHA-256 pinned by the job scripts) |
| `recovery/` | Rebuild procedures for everything stored outside the repository |
| `results/`, `environment/` | Small result files; pinned Python packages |

Large artifacts (weights, teacher outputs, environments) are kept outside Git, in `C:\masters_project_large\` and on the clusters. Each one has a rebuild procedure in `recovery/`.
