# Compute Log

This is the record of every cluster job, scheduler test and measured local run in the project. Cluster time on Talon and Redhawk costs no money, but it is the project's real budget: it is limited by queue waits, the 3-day job limit and the shared storage quota. The numbers here also feed the efficiency results (criterion 4b, `docs/methodology/workflow.md` Section 1.2) and the Phase 10 training-cost measurements. Paid API calls go in `docs/logs/cost_log.md` instead.

**Rule.** Add an entry in the same session as the job, including jobs that failed, were cancelled, or have not been reviewed yet (mark those clearly). Read-only probes and scheduler tests are logged too, with zero GPU time, because they explain what each later job could assume.

## How to read an entry

- **Times** are UTC. *Submitted* is when `sbatch` accepted the job. *Started* is when it got a node. *Ended* is when it finished.
- **Queue wait** = started minus submitted. On Redhawk this was the main bottleneck (an estimated 13 days on 2026-11-04).
- **Wall time** = ended minus started, the real time the job held its resources.
- **GPU-hours** = number of GPUs held x wall time in hours. Example: a job holding 2 GPUs for 90 minutes uses 2 x 1.5 = 3.0 GPU-hours. A Redhawk whole-node job holds all GPUs on the node (2 V100s), whether it uses them or not, because Redhawk has no per-GPU requests.
- **Peak GPU memory** is the highest memory use seen on each GPU (from `nvidia-smi` samples), in MiB (1 MiB = 1,048,576 bytes). It shows how close a job came to running out of memory, which decides which models fit on which GPUs.
- **Outcome**:
  - **PASS** = did what it was meant to do.
  - **FAIL_INFRA** = stopped by the job scripts' own safety checks or by the system (no science result).
  - **FAIL_QUALITY** = the run worked but the model's outputs were unusable.
  - **NOT REVIEWED** = finished, but nobody has looked at the results yet.
- **Accounting.** Slurm job accounting (`sacct`) is switched off on both clusters, so the scheduler keeps no history. Every number here comes from the job's own logs, its `summary` file, or the submit and probe output saved at the time. Copy it in promptly.

## Summary

| # | Date (UTC) | Where | Job ID | What | GPUs x wall time | GPU-hours | Outcome |
|---|---|---|---|---|---|---|---|
| 1 | 2026-10-07 | This PC (CPU) | n/a | Pythia base-model probe | none (CPU) | 0 | PASS |
| 2 | 2026-11-04 | Redhawk login node | n/a | Read-only cluster probe (`probe_cluster.sh`, two runs) and `probe_cluster_part2.sh` | none | 0 | PASS (first run incomplete, rerun) |
| 3 | 2026-11-04 21:47 | Redhawk scheduler | none created | `sbatch --test-only` for the pipeline request | none | 0 | Accepted; estimated start 2026-11-17 |
| 4 | 2026-11-04 | Redhawk `batch` partition (requested) | 2510636 | Compile llama.cpp b11960 | CPU compile job | not recorded | FAIL (compiler) |
| 5 | 2026-11-04 | Redhawk `batch` partition (requested) | 2510641 | Recompile llama.cpp with named gcc 12.2 | CPU compile job | not recorded | Build PASS; job's final check falsely failed |
| 6 | 2026-11-05 ~09:33 | Redhawk `mualhpcp38` | 2510690 | Qwen pipeline (stage A, B, main) | 2 x V100, 84 s | ~0.05 | FAIL_INFRA at stage A (log-wording check) |
| 7 | 2026-11-05/06 | Redhawk | 2511641 | Qwen pipeline, resubmitted | 2 x V100, to fill in | to fill in | **NOT REVIEWED** |
| 8 | 2026-11-06 | Talon login node | n/a | Read-only probe (`run_probe_local.sh`) and follow-up reads | none | 0 | PASS |
| 9 | 2026-11-11 ~21:18 | Talon login node | none created | Repository copy to `~/talon_project/repo` (commit `4d24384`) and GPU request-style test (`sbatch --test-only`, 4 forms) | none | 0 | PASS (all 4 forms accepted) |

**GPU-hours used to date: about 0.05** (job 6), plus job 7 once it is reviewed.

## Entries

### 1. Pythia base-model probe (local CPU), 2026-10-07 00:15 UTC
- **Purpose:** learn how the four base students behave before designing the benchmark and training data (Phase 2).
- **Where:** this PC's CPU.
- **Software:** venv `C:\masters_project_large\envs\probe`, torch 2.14.1+cpu, transformers 5.19.0.
- **Models:** Pythia 70M, 160M, 410M and 1B (deduped, `step143000`), loaded as `float16`.
- **Settings:** 16 questions x 3 prompt formats x 4 sizes = 192 generations; greedy decoding; 128 new tokens.
- **Speeds measured:** the 1B model ran at about 9.5 tokens per second on this CPU (`docs/models/pythia_behavior_analysis.md` Section 4).
- **Outputs:** `results/pythia_probe/2026-10-07_0015Z_probe.*`.
- **Outcome:** PASS. An earlier run the same evening had a stop-token bug for the 1B model; it was deleted and rerun (`docs/progress_update.md`, 2026-10-06).

### 2. Redhawk read-only probes, 2026-11-04
- **Purpose:** find the scheduler setup, GPU nodes, modules, quotas and internet access before any job.
- **What ran:**
  - `configs/redhawk/probe_cluster.sh` twice. The first run stopped early because `quota` consumed the script's standard input; the probe was rewritten.
  - `probe_cluster_part2.sh`.
- **Results:** Slurm `gpu` partition with 4 V100 nodes (`mualhpcp38` to `41`); no GPU resource defined, so jobs take a whole node with `--exclusive`; 3-day limit; accounting off; home quota 480 GB soft. Details in `docs/clusters/cluster_selection.md` Section 7.
- **GPU time:** none.

### 3. Redhawk scheduler test, 2026-11-04 21:47 UTC (no job created)
- **What:** `sbatch --test-only` with the pipeline's exact request (one whole GPU node, 24 hours). This checks a request and estimates a start without creating a job.
- **Result:** request accepted; estimated start **2026-11-17 15:33 UTC on `mualhpcp38`, about 13 days away**. The estimate was the same for 1, 12 and 24 hours, because the wait came from first-come-first-served scheduling behind 21 waiting jobs, not from the request's length.

### 4. Job 2510636: llama.cpp compile, 2026-11-04
- **Purpose:** build llama.cpp tag b11960 (commit `8642541b...`) for the V100 (`sm_70`).
- **Script:** `configs/redhawk/build_llamacpp.sbatch`, submitted by `prep_cluster.sh`.
- **Partition:** `batch`, as **requested** by the script's `#SBATCH --partition=batch` line (version at commit `3cbbaf2`; 8 CPUs, 16 GB, 1.5 h limit, no GPU). `prep_cluster.sh` runs `sbatch configs/redhawk/build_llamacpp.sbatch` with no partition override. The partition the job actually ran in was **not observed**: Slurm accounting is off, and the job's own log on Redhawk has not been checked.
- **Outcome:** FAIL: `ggml-cpu.c: fatal error: stdatomic.h: No such file or directory`. CMake used the system C compiler (gcc 4.8.5) because the `gcc-12.2.0` module provides no `cc`.
- **Fix:** name the compilers explicitly (`docs/progress_update.md`, 2026-11-04).
- **Times and wall time:** not recorded.
- **Same session:** the 17 GB Q4_K_M weights were downloaded on the login node and verified (16,817,244,384 bytes, SHA-256 matches).

### 5. Job 2510641: llama.cpp recompile, 2026-11-04
- **Purpose:** rebuild with gcc 12.2.0 named for C, C++ and CUDA host code.
- **Script and partition:** `configs/redhawk/build_llamacpp.sbatch`, submitted by `rebuild_llamacpp.sh` (commit `bcedc66`) with no partition override. The script **requests** `#SBATCH --partition=batch` (8 CPUs, 16 GB, 1.5 h limit, no GPU). The partition actually used was **not observed**, for the same reasons as job 2510636.
- **Outcome:** the build succeeded (all libraries, including the 198 MB GPU library). The job still ended in error because its final flag check ran `llama-server --help` on a node without the NVIDIA driver library, so every flag looked "missing".
- **Follow-up:** the build was then verified without recompiling (`verify_build.sh`, record in `build_verified.txt`).
- **Times:** not recorded.

### 6. Job 2510690: Qwen pipeline, stage A, 2026-11-05 about 09:33 UTC
- **Purpose:** first GPU run of Qwen3.6-27B (Q4_K_M, llama.cpp b11960) on the 100-slot comparison, starting with smoke stage A.
- **Script:** `configs/redhawk/qwen_pipeline.sbatch` (one whole node, 24 h requested).
- **Node:** `mualhpcp38`, 2 x V100 16 GB.
- **Wall time:** 84 s. GPU-hours: 2 x 84 / 3,600, about 0.05.
- **Peak GPU memory (after load):** GPU 0 8,790 MiB, GPU 1 9,226 MiB. The model was split across both cards as intended.
- **Outcome:** FAIL_INFRA (exit 3) before any question was sent. The model loaded and the server was ready after about 8 s, but the script's check for certain text in the server log could never pass with this llama.cpp build. That check was replaced by a measured memory check on both GPUs (`docs/progress_update.md`, 2026-11-05).
- **Queue wait:** not recorded.

### 7. Job 2511641: Qwen pipeline, resubmitted (NOT REVIEWED)
- **Purpose:** the same pipeline as job 6, with the memory-check fix.
- **Status:** the job has finished, but its results have **not been checked**.
- **To fill in when reviewed:** submit, start and end times; node; stages reached (A, B, main); the decisions in the pipeline summary file; peak memory per GPU; tokens per second; output folders; outcome.
- **Note:** under the current plan this Redhawk run is no longer the comparison baseline (the 4-bit vs BF16 comparison is done on Talon). Its results still document the fallback deployment.

### 8. Talon read-only probe, 2026-11-06
- **Purpose:** learn Talon's real setup after the first login.
- **What ran:** `configs/talon/probe_talon.sh`, through `configs/talon/run_probe_local.sh` (sent over SSH, nothing copied to Talon), plus follow-up reads of the login scripts, the proxy setup and the home quota.
- **Results:**
  - partition `talon`: 4 nodes x 4 `nvidia_h100_nvl` GPUs, 64 cores and 515 GB RAM per node, shared between jobs;
  - 3-day limit; accounting off;
  - system Python 3.9; module `miniforge3-python3.12`;
  - login node reaches Hugging Face and PyPI through the university proxy;
  - home folder shared with Redhawk: 500 GB hard quota, about 17 GB used.

  Evidence labels and the full table are in `docs/clusters/talon_setup.md` Section 2.
- **GPU time:** none.

### 9. Talon repository copy and GPU request-style test, 2026-11-11 about 21:18 UTC (no job created)
- **Purpose:** put the committed code on Talon and find which GPU request forms the scheduler accepts (Stage 1, step 1 of the pilot plan).
- **Repository copy** (run by Jaxson in Git Bash on this PC): `git archive --format=tar HEAD | ssh talon 'test ! -e ~/talon_project/repo && mkdir -p ~/talon_project/repo && tar -x -C ~/talon_project/repo'`.
  - **What was copied:** commit `4d24384`, to `/home/buggjm/talon_project/repo` (the `talon_repo` path). Untracked files such as `data/taxonomy/` are not included.
  - **Line endings:** `git archive` on this PC writes text files with Windows line endings, so the v6 prompt matches its pinned SHA-256 `348db6ff...`. Shell scripts get Unix line endings, which `.gitattributes` forces. The guard refuses to overwrite an existing copy, so a later update must replace the folder deliberately.
- **Test:** `bash configs/talon/probe_talon_part2.sh` (check-only mode) ran `sbatch --test-only --nodes=1 --time=00:10:00 --partition=talon` with each of four GPU request forms. `--test-only` makes the scheduler validate a request and estimate its start without creating a job; the job numbers it prints (188 to 191) are hypothetical.
- **Result:** all four forms **ACCEPTED**: `--gres=gpu:1`, `--gres=gpu:nvidia_h100_nvl:1`, `--gpus=1`, `--gpus=nvidia_h100_nvl:1`. Each was estimated to start immediately (2026-11-11T21:18) on `mualhpgp01.mpi`.
  - **Setting chosen:** `TALON_GPU_STYLE=gres` in `configs/talon/talon_settings.sh`, matching Research Computing's example.
  - **What this does not show:** acceptance says nothing about whether a job actually receives a working H100. That is the next step, the 5-minute probe job, which needs separate approval.
- **GPU time:** none.
