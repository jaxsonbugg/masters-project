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
| 10 | 2026-11-12 02:35 | Talon `talon`, `mualhpgp01` | 196 | GPU probe job (`probe_gpu_job.sbatch`), `--gres=gpu:1` | 1 x H100 NVL, ~1 s | ~0.0003 | PASS (see the GPU-visibility finding) |
| 11 | 2026-11-12 ~05:30 | Talon login node | none (background process) | vLLM 0.32.0 environment and Qwen3.6-27B BF16 weights download and verification (`prep_talon.sh`, attempt 2) | none (no GPU) | 0 | PASS (attempt 1 stopped by our version check; nothing downloaded) |
| 12 | 2026-11-12 15:37 | Talon `talon`, `mualhpgp02` | 204 | **Stage A smoke test**: Qwen3.6-27B BF16 on vLLM 0.32.0, 2 development questions | 1 x H100 NVL, ~10.5 min | ~0.17 | PASS (answers read: sensible) |
| 13 | 2026-11-12 16:13 | Talon `talon` | 207 | Stage T throughput test, first submission (cancelled by Jaxson to resubmit with a longer client time limit) | 1 x H100 NVL, ~5 min | ~0.08 | CANCELLED (server loaded in 130 s; no replies) |
| 14 | 2026-11-12 16:18 | Talon `talon`, `mualhpgp02` | 209 | **Stage T throughput test**: Qwen3.6-27B BF16 on vLLM 0.32.0, 32 development questions at concurrency 1, 4, 8 and 16 | 1 x H100 NVL, ~2 h 22 min | ~2.37 | PASS with quality warnings (1 cut-off, 1 false alarm) |
| 15 | 2026-11-19 02:19 | Talon `talon`, `mualhpgp01` | 287 | **Stage K, the thinking on/off check**: Qwen3.6-27B BF16 on vLLM 0.32.0; set K written with thinking on and off, shared set built, both modes answered it 3 times | 1 x H100 NVL, ~45 min | ~0.75 | PASS with quality warnings (31 of 360 replies; infrastructure clean) |

**GPU-hours used to date: about 3.42:** about 0.05 (Redhawk job 6), about 0.0003 (Talon job 196), about 0.17 (Talon job 204), about 0.08 (Talon job 207, cancelled), about 2.37 (Talon job 209) and about 0.75 (Talon job 287), plus Redhawk job 7 once it is reviewed.

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

### 10. Talon job 196: the GPU probe job, 2026-11-12 02:35 UTC (2026-11-11 evening, local time)
- **Purpose:** see what a real Talon GPU job receives (Stage 1, step 2 of the pilot plan). Approved by Jaxson, who ran it.
- **Submission:** `QT_SUBMIT=yes bash configs/talon/probe_talon_part2.sh` from `~/talon_project/repo` (commit `4d24384`). The four `--test-only` checks were repeated (all accepted), then the job was submitted with `--nodes=1 --time=00:10:00 --partition=talon --gres=gpu:1`. It was recorded with `probe_talon_part2.sh record`, which wrote `talon_verified.txt` on Talon.
- **Timing:**
  - submitted 02:35:32 UTC;
  - started 02:35:33 UTC on `mualhpgp01`, so the queue wait was about 1 s;
  - ended 02:35:34 UTC, so the wall time was about 1 s;
  - GPU-hours: 1 GPU x about 1 s = about 0.0003.
- **What the job received:**
  - **GPU type and memory:** NVIDIA H100 NVL, **95,830 MiB of memory per GPU** (about 94 GB). This settles the "80 GB or 94 GB" question.
  - **Driver:** 610.57.04. The CUDA version line (`nvidia-smi | grep "CUDA Version"`) printed nothing, so **the CUDA version is still not recorded.** This driver's header format may differ; read it directly in the next GPU job.
  - **GPUs actually assigned:** `CUDA_VISIBLE_DEVICES=1`, so Slurm assigned **one** GPU (index 1).
  - **GPU visibility (important):** `nvidia-smi` nevertheless listed all **four** GPUs of the node. Slurm on Talon does not hide the other GPUs from a job; it only sets `CUDA_VISIBLE_DEVICES`, which programs such as vLLM and PyTorch respect. So `GPUS_SEEN=4` in `talon_verified.txt` counts visible GPUs, not assigned ones. Our Talon scripts count and sample GPUs with `nvidia-smi` (`serve_and_run.sh`), so they would include GPUs used by other people; this must be fixed before Stage A.
  - **GPU links:** GPU 0 and GPU 1 are joined by NVLink (`NV12`), as are GPU 2 and GPU 3. Other pairs talk over PCIe and the link between the two processor sockets (`SYS`). A 2-GPU tensor-parallel job runs best on a linked pair.
  - **CPUs:** `nproc` = **1**. A job that does not ask for CPUs gets one core, too few for vLLM, so jobs must request `--cpus-per-task` explicitly.
  - **Memory:** `free` showed the whole node, 503 GB total and 478 GB available. That is not the job's own memory limit, which is still unknown; request `--mem` explicitly.
  - **Disk and libraries:** local `/tmp` is 500 GB with 497 GB free; glibc 2.34.
  - **Internet from the compute node:** Hugging Face HTTP 200 and PyPI HTTP 200, so compute nodes can download.
  - **vLLM wheel check:** skipped, because the vLLM version is not pinned yet.
- **Outcome:** PASS. It also produced the GPU-visibility and CPU findings above, which feed the settings review and a script fix.

### 11. Talon: vLLM environment and BF16 weights, 2026-11-12 (login node, no GPU, no Slurm job)
- **Purpose:** install the pinned engine and download the pinned teacher weights (Stage 1, step 3 of the pilot plan). Approved by Jaxson, who ran it.
- **What ran:** `QT_CONFIRM_STORAGE=yes QT_ALLOW_HOME=yes bash -l configs/talon/prep_talon.sh` from `~/talon_project/repo`. It checked the copied files (scripts parse, no carriage returns, prompt SHA-256 `348db6ff...`), then ran `fetch_talon.sh` in the background on the login node.
- **Attempt 1** (repository at `c2914a5`): quota check passed; the environment installed; then it **stopped** at our own version check, which read "3.12" from the output of `vllm --version`. That command crashes on a node without a GPU ("Failed to infer device type"). Nothing was downloaded. Fixed in `5dca92a` (the version is now read from Python's package records); see the progress log.
- **Attempt 2** (repository at `5dca92a`, `QT_PREP_AGAIN=yes`):
  - **Environment:** reused. The package list was recorded at 2026-11-12T05:32:27Z: 199 packages, Python 3.12.5, `vllm==0.32.0`, `torch==2.13.0` (CUDA 13.0 build), `transformers==5.19.0`. The `venv_pip_freeze.txt` SHA-256 is `96977b7fd97d9e886930fa2c2a423e64651bf0354bbe892646e6ab27f4f9867a`.
  - **Download:** `Qwen/Qwen3.6-27B` @ `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9`, 29 files in **about 82 seconds**. That is about 54 GB, so roughly 0.65 GB/s from the login node, without a Hugging Face token.
  - **Verification:** all 29 files match the sizes Hugging Face publishes for that commit, and every large file matches its published SHA-256.
  - **Manifest:** `weights_manifest.sha256` (29 files) has SHA-256 `8e3e1fc0103c85a66c1516343b645a80d667e47a8152b8b38a24e67e218d1d33`. The total is 53,220 MiB (the setting `WEIGHTS_MIB` is 53,011; a 0.4% difference, left unchanged).
  - **Ended with:** `OK: weights verified`.
- **Storage afterwards:** weights 52 GB and environment 8.5 GB. The home quota stands at **82,982 MiB of the 480 GB soft limit** (about 17%), with about 108,000 files.
- **Rebuild recipe:** `recovery/talon_qwen_weights.md`.
- **GPU time:** none.

### 12. Talon job 204: Stage A smoke test, 2026-11-12 (cluster local time 10:37; UTC 15:37)
- **Purpose:** the first run of the teacher on a GPU: does Qwen3.6-27B (BF16) load on one H100 under vLLM 0.32.0, answer two development questions, and produce replies we can save and check? Approved by Jaxson, who submitted it with `QT_SUBMIT=yes GPU_COUNT=1 TENSOR_PARALLEL=1 REPLICAS=1 MAX_NUM_SEQS=1 CLIENT_CONCURRENCY=1 bash configs/talon/submit_pipeline.sh smoke_a`.
- **Software:** repository copy at commit `58c2dc3`. vLLM 0.32.0, torch 2.13.0 (CUDA 13.0 build), transformers 5.19.0, Python 3.12.5. Model `Qwen/Qwen3.6-27B` @ `6a9e13bd`, BF16; weights manifest SHA-256 `8e3e1fc0...`.
- **Request:** `--nodes=1 --partition=talon --gres=gpu:nvidia_h100_nvl:1 --time=01:00:00 --cpus-per-task=16 --mem=120G`, one GPU on `mualhpgp02`.
- **Timing:**
  - **Submitted and started:** submitted 10:37:58 and started 10:37:59 (cluster local time; this is UTC 15:37, inferred from the result file's UTC stamp), so the queue wait was **1 s**.
  - **Ended:** the result file is stamped 15:48:27 UTC, so the wall time was about **10 min 28 s**.
  - **GPU-hours:** 1 GPU x 628 s = about **0.17**.
  - **Weight check:** about 2 min 20 s for the job to re-hash the 29 weight files against the manifest and start the server.
  - **Server load:** the server was ready after **242 s**. This includes a one-time `torch.compile` step of 35 s, which vLLM caches in `~/.cache/vllm` (about 35 MB). Later loads may be faster.
  - **The two questions:** BM9001 took 151.3 s and BM9002 took 104.8 s, asked one at a time.
- **What the job saw (job log):**
  - **GPU:** assigned `CUDA_VISIBLE_DEVICES=0` (index 0), NVLink pairing not applicable.
  - **CUDA:** `nvidia-smi` header: driver 610.57.04, **CUDA UMD version 13.3**. This closes the open "CUDA version" item.
  - **Peak GPU memory:** 89,607 MiB used of 95,830, with 6,223 MiB free. vLLM reserves a fixed share of the GPU at start, so this is expected.
  - **Server log:** zero error words.
- **Engine choices vLLM made (server log, not our settings):**
  - **Attention:** main attention uses **FlashAttention 3** (`FLASH_ATTN`, chosen out of FLASH_ATTN, FLASHINFER, TRITON_ATTN and FLEX_ATTENTION).
  - **FlashInfer:** still used for the model's GDN (linear-attention) prefill kernel and for top-p/top-k sampling. Its precompiled kernels are missing, so vLLM warns that the GDN kernel is JIT-compiled on first use. The job passed.
  - **Other defaults:** chunked prefill with `max_num_batched_tokens=8192`, prefix caching on (Mamba cache mode `align`), attention block size 784.
  - **The vLLM issue #63505** concerned a race in the FlashInfer attention backend. This run does not use that backend for attention. It is not settled that the bug is irrelevant, since FlashInfer is still used in the two places above.
- **Outcome:** `RESULT: PASS (stage A)`; validation: infrastructure PASS, 2 of 2 slots with a reply, 2 strictly valid JSON, 2 with separate reasoning, 0 quality findings. The result file records `GPU_IDS=0`, `NVLINK_PAIR=not applicable (1 GPU(s))`, `LAYOUT_FP=1/1/1/1/0.32.0/6a9e13bd.../8e3e1fc0.../20480`.
- **The answers (read from `responses.jsonl`):**
  - **BM9001** (numerical, intro): P(exactly 2 heads in 5 flips with p = 0.6), 3 decimals. Key 0.230, `r_solution` `cat(dbinom(2, size = 5, prob = 0.6))`. The exact value is 0.2304, so the key is correct.
  - **BM9002** (conceptual, intro): the meaning of a p-value of 0.03, multiple choice, correct letter C (the slot's preferred letter). Option C is the standard definition, and the other three are standard misreadings. `r_solution` is empty, as intended for a conceptual item.
  - **R scoring, done the same day on the PC** (`open_teacher_test.py score`, then `generate_benchmark.py verify`): 2 of 2 slots format valid and passed every automatic check on the first attempt; none cut off. BM9001's key came from R (`r_value` 0.2304, rounded half up to **0.230**), the same as the number the model typed, with no soft flag. `verify` reported it `ok`. BM9002 is `not_machine_checkable`, as expected for a multiple-choice item (it needs the different-family verifier). The small result copies are in `results/open_teacher_test/`.
- **Tokens (one question at a time, so these are single-stream speeds):**
  - **BM9001:** 1,362 tokens in, 4,537 out (13,174 characters of thinking, 866 of answer), about **30 tokens/s**.
  - **BM9002:** 1,240 in, 3,025 out (10,902 characters of thinking, 1,375 of answer), about **29 tokens/s**.
  - **Share of thinking:** about 95% of the output is thinking.
- **Output folder:** `/home/buggjm/talon_project/teacher_outputs/2026-11-12_qwen3-6-27b-talon-bf16_smokeA01` (`responses.jsonl`, `run_log.json`, `gpu_peak.txt`); development slots only, marked test material, never benchmark data.
- **Related progress entry:** "Talon Stage A passed" (2026-11-12).

### 13. Talon job 207: Stage T, first submission, cancelled, 2026-11-12 (cluster local time 11:13; UTC 16:13)
- **Purpose:** the throughput test (Stage T), submitted with the default client time limit.
- **Why it was cancelled:** the estimate of the run's length was close to the default 90-minute client time limit (`QT_PY_TIMEOUT`). Jaxson cancelled the job and resubmitted it as job 209 with `QT_PY_TIMEOUT=150m`, so the run could not be cut off partway.
- **Timing:**
  - started 11:13:11 and cancelled 11:18:15 (cluster local time, UTC−5, so 16:13:11 to 16:18:15 UTC);
  - about 5 min of wall time on 1 H100, which is about **0.08 GPU-hours**.
- **What it did:** the server became ready after **130 s** (model load; `repo/qt_talon_T_207.log`). No question was answered before the cancel. Its output folder holds only `run.lock` and `run_log.json`, and contains no replies.
- **Outcome:** CANCELLED by the owner; nothing to review.
- **Related progress entry:** "Talon Stage T" (2026-11-12).

### 14. Talon job 209: Stage T throughput test, 2026-11-12 (cluster local time 11:18; UTC 16:18)
- **Purpose:** measure how many examples per GPU-hour Qwen3.6-27B (BF16, vLLM 0.32.0) produces on one H100. The 32 development questions of set T (BM9101 to BM9132; never benchmark or training slots) are sent once at each client concurrency (1, 4, 8 and 16 requests in flight) on one server start. This is the number that projects the 200,000-example generation.
- **Settings:**
  - `GPU_COUNT=1 TENSOR_PARALLEL=1 REPLICAS=1 MAX_NUM_SEQS=16`, sweep concurrency 1, 4, 8 and 16, and `QT_PY_TIMEOUT=150m`;
  - the model-card sampling (temperature 1.0, top_p 0.95, top_k 20), max 16,384 output tokens, context 20,480;
  - model `Qwen/Qwen3.6-27B` @ `6a9e13bd`, BF16; prompt v6 (`348db6ff...`).
- **Node:** `mualhpgp02.hpc.miamioh.edu`, one GPU.
- **Timing:**
  - started 11:18:57 cluster local time (16:18:57 UTC); the submit time was not recorded separately. It was submitted right after job 207 was cancelled, so the queue wait was seconds.
  - Ended: the result file is stamped **18:41:19 UTC**, so the wall time was about **2 h 22 min**, which on 1 H100 is about **2.37 GPU-hours**.
  - The server was ready after **86 s** (model load; `repo/qt_talon_T_209.log`). That is faster than job 207's 130 s and Stage A's 242 s, because the compile cache and file cache were warm.
- **GPU memory:** the lowest free memory on the assigned GPU was **5,485 MiB** (`MIN_FREE_MIB`), so the peak use was about 90,345 of 95,830 MiB. vLLM reserves a fixed share of the card at start, so this is expected.
- **Throughput** (from `throughput_report.py` on the run folders):

  | Client concurrency | Output tokens per second (total) | GPU-hours per 1,000 successful examples |
  |---|---|---|
  | 1 | 29.4 | 47.5 |
  | 4 | 109.7 | 12.36 |
  | 8 | 191.9 | 6.99 |
  | 16 | 226.6 | 6.14 |

  - **What the table means:** running more questions at once costs little extra time per question on an H100, so the total speed grows almost 8-fold from 1 to 16 requests in flight (226.6 / 29.4 = 7.7). The last step gains less (8 to 16: 6.99 to 6.14 GPU-hours per 1,000), partly because the final few long questions run nearly alone at the end of a batch (the "tail").
  - **Per example:** about 4,850 output tokens on average, about 95% of them thinking.
- **Projection at concurrency 16:** 6.14 GPU-hours per 1,000 examples × 200 = about **1,228 GPU-hours** for 200,000 examples. That is about 51 GPU-days, or about 13 days of clock time with 4 single-GPU jobs side by side (allowed by Research Computing, 2026-11-12). It is a planning estimate: 32 questions of one prompt family, with no queue waits, retries or reloads included.
- **Outcome:** `RESULT=PASS_QUALITY_WARN`. The infrastructure passed. There are two quality findings:
  - **BM9118** was cut off at the 16,384-token output limit (1 of 128 replies, about 0.8%). Thinking used up the budget, so the reply had no usable answer.
  - **BM9115** was flagged as "thinking aloud" by the `\bno:` pattern in `check_item`. On reading the reply, this is a **false alarm**: the question contains a table whose row label is "No:". A fix (count `no:` only in lowercase, mid-sentence) is noted for the generation-code stage and needs approval before it is made.
- **Output:**
  - the dated Stage T run folders under `/home/buggjm/talon_project/teacher_outputs/` (one per concurrency level);
  - the result file `teacher_outputs/stage_results/stageT.txt`.

  These are development slots only, marked test material, never benchmark data.
- **Related progress entry:** "Talon Stage T" (2026-11-12).

### 15. Talon job 287: Stage K, the thinking on/off check, 2026-11-19 (cluster local time 2026-11-18 21:19; UTC 2026-11-19 02:19)
- **Purpose:** the quick observational check of whether the teacher writes and answers almost as well with thinking off, for far less GPU time (`docs/methodology/workflow.md` Section 2.1, item 3). Approved by Jaxson, who refreshed the Talon copy and submitted it with `QT_SUBMIT=yes GPU_COUNT=1 TENSOR_PARALLEL=1 REPLICAS=1 MAX_NUM_SEQS=16 CLIENT_CONCURRENCY=16 bash configs/talon/submit_pipeline.sh thinking`.
- **Software:**
  - repository copy at commit `021ad26`, refreshed build-then-swap; the old copy was kept on Talon;
  - vLLM 0.32.0; model `Qwen/Qwen3.6-27B` @ `6a9e13bd`, BF16; context 20,480, output limit 16,384;
  - prompts: v6 (`348db6ff...`) for writing, and `teacher_answer_v1.md` (SHA-256 of the LF-normalized text `984ee088...`) for answering;
  - 3 samples per question;
  - sampling: thinking on uses temperature 1.0, top_p 0.95, top_k 20, presence penalty 0; thinking off uses temperature 0.7, top_p 0.80, top_k 20, presence penalty 1.5.
- **Request:** 1 GPU (`--gres=gpu:nvidia_h100_nvl:1`, the throughput wall time of 4 h), on `mualhpgp01`, GPU index 0 (H100 NVL, 95,830 MiB, driver 610.57.04, CUDA 13.3).
- **Timing:**
  - **Submitted and started:** 21:19:02 local, so the queue wait was **0 s**.
  - **Ended:** the result file is stamped **03:04:15 UTC**, so the wall time was about **45 min 13 s**, which is about **0.75 GPU-hours**.
  - **Weight check and server load:** about 5 minutes in total. The server was ready after **130 s**.
- **The four client runs** (client time only, start-up excluded):

  | Run | UTC | Wall | Replies | Output tokens | Finish |
  |---|---|---|---|---|---|
  | Writing, thinking on (BM8001–BM8060) | 02:24:13–02:35:50 | 697.1 s | 60/60 | 280,266 | 60 stop |
  | Writing, thinking off | 02:35:51–02:37:24 | 92.8 s | 60/60 | 37,123 | 60 stop |
  | Answering, thinking on (40 x 3) | 02:37:25–02:59:38 | 1,332.7 s | 120/120 | 516,943 | 112 stop, **8 cut off at 16,384** |
  | Answering, thinking off (40 x 3) | 02:59:38–03:04:14 | 276.2 s | 120/120 | 98,522 | 120 stop |

  **The shared set:** all 40 positions were filled, with 0 replacements and 0 unfilled.
- **Validation:** infrastructure PASS for every run. **Thinking off was confirmed from the records:** 60 of 60 writing replies and 120 of 120 answers had no reasoning field, no `<think>` text and no reasoning tokens. There were 31 model-quality findings in 360 replies:
  - 1 thinking-off writing reply had invalid JSON (BM8020, which lies outside the thinking-off half of the set);
  - 13 thinking-on and 17 thinking-off answers had no `Final answer:` line.
- **GPU memory and the server log:** peak 89,751 of 95,830 MiB (6,079 MiB free); 0 error words in the server log.
- **The confidential-computing record failed.** `CC_MODE` captured "ECC Mode … Enabled", which is the GPU's memory error correction, not confidential computing: the search pattern "CC Mode" also matches "ECC Mode". A direct check (`srun --overlap … nvidia-smi conf-compute -f`) was tried after the job had already ended, so it was refused. The confidential-computing state of this run is therefore not recorded. Its known risk is garbled output, and none was seen: every reply was structured text. The search pattern is to be fixed.
- **Outcome:** `RESULT=PASS_QUALITY_WARN`, "31 of 360 repl(ies) have model-quality findings". Graded on the PC with `answer_check.py` (see the progress log).
- **Output:**
  - **On Talon:** `/home/buggjm/talon_project/teacher_outputs/2026-11-19_qwen3-6-27b-talon-bf16_{smokeK01, smokeK-thinkoff01, answersetK01, answersK01, answersK-thinkoff01}`.
  - **On the PC:** copied to `C:\masters_project_large\data\teacher_outputs\` under the same names, plus `2026-11-19_stageK_job287_logs\` (job log, `stageK.txt`, client, validation and server logs, GPU memory CSV).
  - These are development slots only, marked test material.
- **Related progress entry:** "Thinking check run on Talon" (2026-11-19).

### 16. Local: embedding-model verification and CPU benchmark, 2026-11-20 (this PC, no cluster job)
- **Purpose:** before decontamination uses the sentence-embedding model on real data, check that the project's implementation gives the same vectors as the official library, and measure its speed on the PC's CPU (approved plan of 2026-11-19, Step 7, item 4; `docs/methodology/workflow.md` Section 4, safeguard 5).
- **Model:** `sentence-transformers/all-MiniLM-L6-v2` @ `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, float32 on the CPU (`recovery/embedding_model.md`). Downloaded 2026-11-20, about 92 MB; weights SHA-256 `53aa5117...`, equal to Hugging Face's listing.
- **Software:** project environment (`C:\masters_project_large\envs\probe`): transformers 5.19.0, torch 2.14.1+cpu, 14 threads. Reference: a throwaway virtual environment in the session scratchpad with sentence-transformers 6.3.0, torch 2.15.0+cpu, transformers 5.23.0, deleted afterwards.
- **Run 1, verification** (`embedding_check.py texts`, `reference`, `verify`), about 01:40 to 02:00 UTC, seconds of compute: 100 sample texts (4 longer than 256 word pieces). Lowest cosine between the two implementations 0.99999988, required at least 0.9999; largest difference in any number 9e-8. **PASS.**
- **Run 2, CPU benchmark** (`embedding_check.py bench --n 5000`), about 02:05 UTC: 5,000 training-like texts in 129.3 s, **38.7 texts per second**, batch 64, peak memory 867 MB, 7.3 MB of vectors. Projection: about **112 minutes** and 381 MB of vectors for 260,000 texts. A Talon GPU job is not needed.
- **Peak GPU memory:** none (CPU only). **GPU-hours:** 0.
- **Output:** `data/verification_logs/2026-11-20_embedding_check/` (texts, results, the reference environment's versions).
- **Outcome:** reviewed; the implementation is accepted for decontamination.
- **Related progress entry:** "Full-size generator, Talon stage G and decontamination built and tested locally" (2026-11-20).

### 17. Talon jobs 291 and 293: stage G smoke test of the full-size generator, 2026-11-20 (cluster local time 18:40; UTC 23:40)
- **Purpose:** the first real run of `code/generation/generate_set.py` (stage G) before any benchmark or training data: do benchmark prompt v7 and training prompt v1 produce usable replies, how long are the training texts, how fast is it, and does stage G (sharding, validation, result files) work on Talon (approved plan of 2026-11-19, Step 10). Approved by Jaxson on 2026-11-20; he refreshed the Talon copy to `b695da0` and submitted both jobs with `QT_SUBMIT=yes GPU_COUNT=1 TENSOR_PARALLEL=1 REPLICAS=1 MAX_NUM_SEQS=16 CLIENT_CONCURRENCY=16 GEN_SLOTS=data/slots/smoke_slots.jsonl GEN_SHARD=1/1 ... bash configs/talon/submit_pipeline.sh generate`.
- **Software:** repository copy at `b695da0` (build-then-swap; the previous copy kept as `repo_old_<UTC time>`); vLLM 0.32.0; model `Qwen/Qwen3.6-27B` @ `6a9e13bd`, BF16, weights manifest `8e3e1fc0...` (re-hashed by each job); context 20,480, output limit 16,384; thinking on, temperature 1.0, top_p 0.95, top_k 20, presence penalty 0; up to 3 attempts per slot; client concurrency 16.
- **Slots:** `data/slots/smoke_slots.jsonl` (seed `smoke-2026-11-20`, slots_sha256 `8a292d84...`), development material only.
- **Request:** 1 GPU each (`--gres`, wall time 1 day), both on `mualhpgp01`: job 291 on GPU index 0, job 293 on GPU index 1 (H100 NVL, 95,830 MiB, driver 610.57.04).

  | | Job 291 | Job 293 |
  |---|---|---|
  | Prompt, slots | benchmark v7 (`980f5570...`), SM0001-SM0020 | training v1 (`db9ca660...`), SM0021-SM0040 |
  | Submitted / started (UTC) | 23:40:06 / 23:40:06 (wait 0 s) | 23:40:07 / 23:40:09 (wait 2 s) |
  | Server ready after | 105 s | 110 s |
  | Client (UTC), wall | 23:43:14-23:48:28, 313.1 s | 23:43:19-23:46:49, 209.3 s |
  | Job end (result file, UTC) | 23:48:28 | 23:46:49 |
  | Job wall, GPU-hours | about 8 min 22 s, **0.14** | about 6 min 40 s, **0.11** |
  | Calls, usable, attempts | 20 calls, 20 usable, all on attempt 1 | 20 calls, 20 usable, all on attempt 1 |
  | Output tokens (incl. thinking) | 98,187 (median 5,037 per reply, max 7,488) | 79,151 (median 3,820, max 7,287) |
  | Aggregate output speed | 314 tokens/s | 378 tokens/s |
  | Peak GPU memory | 89,747 MiB (6,083 free) | 88,963 MiB (6,867 free) |

- **Validation:** both `RESULT=PASS`, infrastructure PASS, complete, 0 model-quality findings, 0 cut-offs, 0 error words in the server logs; re-validated on the PC against the slot file with the same result. The confidential-computing line read "not reported by nvidia-smi -q" (the fixed search no longer mistakes ECC for it; the state itself remains unrecorded); no garbled output was seen in any reply.
- **Generation cost implied** (small runs, so the batch was never full for long; an upper-side estimate): about 4.3 GPU-hours per 1,000 benchmark-v7 replies and 2.9 per 1,000 training-v1 replies, client time only. Total for the smoke test: about **0.25 GPU-hours**.
- **Output:**
  - **On Talon:** `/home/buggjm/talon_project/teacher_outputs/2026-11-20_qwen3-6-27b-talon-bf16_smoke_benchmark_bfa35577_shard1of1` and `..._smoke_training_c98f27c1_shard1of1`; result files `stage_results/stageG_smoke-*_job29{1,3}.txt`.
  - **On the PC:** the same two folders in `C:\masters_project_large\data\teacher_outputs\`, plus `2026-11-20_stageG_smoke_jobs291-293_logs\` (job logs, result files, client, validation and server logs, GPU memory CSVs). Copied by Claude with `scp` (read-only on Talon).
  - Development slots only, never benchmark or training data.
- **Outcome:** reviewed; both PASS. Findings are in the progress log.
- **Related progress entry:** "Stage G smoke test on Talon (jobs 291 and 293)" (2026-11-20).

### 18. Talon jobs 295 and 297: second stage G smoke test (prompts v8 and training v2), 2026-11-21 (cluster local time 2026-11-20 20:47; UTC 01:47)
- **Purpose:** check the owner's decisions of 2026-11-20 on real hardware before any benchmark is generated: the plain-text rule (benchmark prompt v8, training prompt v2) and the printout consistency check, on the same 40 smoke slots as jobs 291 and 293, so the two prompt versions can be compared slot by slot. Approved by Jaxson on 2026-11-20; he refreshed the Talon copy to `9cc9232` and submitted both jobs with the same command as entry 17.
- **Software:** repository copy `9cc9232`; vLLM 0.32.0; `Qwen/Qwen3.6-27B` @ `6a9e13bd`, BF16; context 20,480, output limit 16,384; thinking on, temperature 1.0, top_p 0.95, top_k 20; up to 3 attempts; concurrency 16. Prompts: benchmark v8 `0ba834e2...`, training v2 `412d1eb4...`. Slots: `data/slots/smoke_slots.jsonl` (`8a292d84...`).
- **Request:** 1 GPU each, wall time 1 day, both on `mualhpgp01`: job 295 on GPU index 0, job 297 on GPU index 1.

  | | Job 295 | Job 297 |
  |---|---|---|
  | Prompt, slots | benchmark v8, SM0001-SM0020 | training v2, SM0021-SM0040 |
  | Submitted / started (UTC) | 01:47:43 / 01:47:43 (wait 0 s) | 01:47:45 / 01:47:46 (wait 1 s) |
  | Server ready after | 85 s | 90 s |
  | Client (UTC), wall | 01:50:29-02:05:38, 908.6 s | 01:50:34-01:54:48, 253.3 s |
  | Job end (result file, UTC) | 02:05:39 | 01:54:48 |
  | Job wall, GPU-hours | about 17 min 56 s, **0.30** | about 7 min 2 s, **0.12** |
  | Calls; usable | 22; 20 of 20 (19 on attempt 1; SM0018 on attempt 3) | 21; 20 of 20 (19 on attempt 1; SM0038 on attempt 2) |
  | Output tokens (incl. thinking) | 125,964 (median 4,969 per reply) | 87,957 (median 4,351) |
  | Peak GPU memory, minimum free | 6,083 MiB free | 9,221 MiB free |

- **Why job 295 took longer:** SM0018 (R generation, "weekdays and months") wrote an answer key longer than the limit twice, so it was asked three times, each with about 9,000 to 10,500 tokens of thinking (about 4 to 5 minutes each), one after the other at the end of the run. The other 19 replies were done after about 4 minutes.
- **Validation:** both `RESULT=PASS_QUALITY_WARN` (the findings are the failed attempts that were then asked again), infrastructure PASS, both complete, 0 cut-offs, 0 error words in the server logs; re-validated on the PC with the same result. Confidential computing: "not reported by nvidia-smi -q"; no garbled output seen.
- **Output:** on Talon `/home/buggjm/talon_project/teacher_outputs/2026-11-21_qwen3-6-27b-talon-bf16_smoke_benchmark-v8_bfa35577_shard1of1` and `..._smoke_training-v2_c98f27c1_shard1of1`; on the PC the same folders in `C:\masters_project_large\data\teacher_outputs\` plus `2026-11-21_stageG_smoke2_jobs295-297_logs\`. Development material only.
- **Total:** about **0.42 GPU-hours**. **Outcome:** reviewed; findings in the progress log. **Related progress entry:** "Second smoke test: plain text and printout check work" (2026-11-21).

### 19. Talon jobs 299-309: the benchmark, development and TV sets (stage G), 2026-11-21 (cluster local time 2026-11-20 21:28; UTC 02:28)
- **Purpose:** generate the benchmark (BM0001-BM1150, 1,000 + 150 spares), the development set (DV0001-DV0230) and the held-out training-style set (TV0001-TV0180), approved by Jaxson on 2026-11-20 (the development and TV sets in the same session: a logged change of order). He refreshed the Talon copy to `00b6dd3` (fingerprints checked: prompts `0ba834e2`, `412d1eb4`; slots `b2d9197f`, `cd7f7e57`, `ff6d0d04`) and submitted six jobs with `QT_SUBMIT=yes GPU_COUNT=1 TENSOR_PARALLEL=1 REPLICAS=1 MAX_NUM_SEQS=16 CLIENT_CONCURRENCY=16 GEN_SLOTS=... GEN_PROMPT=... GEN_SHARD=... bash configs/talon/submit_pipeline.sh generate`.
- **Software:** vLLM 0.32.0; `Qwen/Qwen3.6-27B` @ `6a9e13bd`, BF16; context 20,480, output limit 16,384; thinking on (temperature 1.0, top_p 0.95, top_k 20); up to 3 attempts per slot; concurrency 16 per job. Benchmark and development: prompt benchmark-v8 with the plain-text and printout checks; TV: training-v2.
- **Requests:** 1 GPU each, wall time 1 day; all started within 2 s of submission (queue wait 0 to 2 s).

  | Job | Set, shard | Node, GPU | UTC start-end | GPU-hours | Calls | Usable / failed all 3 | Output tokens | Min. free GPU memory |
  |---|---|---|---|---|---|---|---|---|
  | 299 | benchmark 1/4 (288) | mualhpgp01, 0 | 02:28:49-03:28:42 | 1.00 | 308 | 285 / 3 | 1,605,419 | 6,079 MiB |
  | 301 | benchmark 2/4 (288) | mualhpgp01, 1 | 02:28:49-03:10:29 | 0.69 | 308 | 283 / 5 | 1,502,472 | 6,867 MiB |
  | 303 | benchmark 3/4 (287) | mualhpgp02, 0 | 02:28:52-03:27:02 | 0.97 | 290 | 286 / 1 | 1,268,531 | 4,798 MiB |
  | 305 | benchmark 4/4 (287) | mualhpgp02, 1 | 02:28:53-03:30:04 | 1.02 | 304 | 283 / 4 | 1,623,569 | 4,339 MiB |
  | 307 | development (230) | mualhpgp02, 2 | 02:28:53-03:16:47 | 0.80 | 235 | 230 / 0 | 1,141,243 | 3,636 MiB |
  | 309 | TV (180) | mualhpgp02, 3 | 02:28:55-02:51:05 | 0.37 | 182 | 180 / 0 | 740,965 | 5,029 MiB |

- **Total: about 4.85 GPU-hours** (estimate before the run: 8 to 10). Server load 91 to 121 s per job. Client time per 1,000 usable replies: benchmark about 3.0 GPU-hours, development 3.2, TV 1.7.
- **Validation:** every job `RESULT=PASS_QUALITY_WARN` (the findings are failed attempts that were asked again), infrastructure PASS, every shard complete, 0 transport errors, 0 error words in the server logs; re-validated on the PC against the slot files with identical counts. The most common reason for a second attempt was an inconsistent printout (the new check; for example t = -4.90 on 996 df printed p = 1.2e-05 where 1.1e-06 is right), then answer keys over the length limit and invalid JSON.
- **Output:** on Talon `/home/buggjm/talon_project/teacher_outputs/2026-11-21_qwen3-6-27b-talon-bf16_{benchmark_benchmark-v8_*_shard{1..4}of4, dev_benchmark-v8_cd7f7e57_shard1of1, tv_training-v2_ff6d0d04_shard1of1}`; on the PC the same folders in `C:\masters_project_large\data\teacher_outputs\` plus `2026-11-21_stageG_bm-dv-tv_jobs299-309_logs\` (job logs, result files, client, validation and server logs, GPU memory CSVs). Copied by Claude with `scp` (read-only on Talon). Recovery: `recovery/teacher_outputs.md`.
- **Outcome:** reviewed; collection, repairs and spare filling in the progress log. **Related progress entry:** "Benchmark and development set collected: R keys, verify, repairs and spares" (2026-11-21).

### 20. Talon jobs 311, 313 and 315: replacement loop round 1 (stage G, same-subtopic candidates), 2026-11-21 (UTC 21:12)
- **Status: reviewed** (2026-11-21). All three ended normally, each shard complete.

  | Job | Shard | Node, GPU | UTC start-end | GPU-hours | Usable / failed all 3 | Replies | Min. free GPU memory |
  |---|---|---|---|---|---|---|---|
  | 311 | 1/3 (164) | mualhpgp01, 0 | 21:12:19-21:54:10 | 0.70 | 157 / 7 | 187 | 6,079 MiB |
  | 313 | 2/3 (164) | mualhpgp01, 1 | 21:12:22-21:44:34 | 0.54 | 153 / 11 | 197 | 6,867 MiB |
  | 315 | 3/3 (164) | mualhpgp02, 0 | 21:12:22-22:05:47 | 0.89 | 154 / 10 | 200 | 4,794 MiB |

  Queue wait 0 to 2 s. **Total 2.13 GPU-hours** (estimate 1.9; budget 4.0). Every job `INFRA=PASS`, re-validated on the PC. After `collect --r-keys`: 436 usable, 28 failed all attempts, 24 verify-flagged (broken R check), 4 R failures.
- **Purpose:** round 1 of the approved replacement loop (plan "resolve the Codex flags", revision 2; execution configuration approved by Jaxson 2026-11-21): 3 same-subtopic Qwen candidates for each of 164 open benchmark positions (BM1151-BM1642 in `data/slots/benchmark_replacements.jsonl`, SHA-256 `03f30592...`). Submitted by the controller `code/verification/replacement_loop.py` under the standing approval.
- **Request:** 1 GPU each (H100 NVL), `TIME_GENERATE=01:00:00` (Slurm wall-time limit), `GEN_MARGIN_SECONDS=600`; `GPU_COUNT=1 TENSOR_PARALLEL=1 REPLICAS=1 MAX_NUM_SEQS=16 CLIENT_CONCURRENCY=16`; `GEN_SLOTS=data/slots/benchmark_replacements.jsonl GEN_PROMPT=benchmark GEN_FIRST=1 GEN_COUNT=492 GEN_SHARD=1/3, 2/3, 3/3` (164 slots each).
- **Software:** vLLM 0.32.0; `Qwen/Qwen3.6-27B` @ `6a9e13bd`, BF16; prompt benchmark-v8 (`0ba834e2`); thinking on (temperature 1.0, top_p 0.95, top_k 20); output limit 16,384; up to 3 attempts per slot. Talon repository copy `00b6dd3` (run code unchanged since).
- **Estimate before the run:** about 0.62 GPU-hours per job, 1.9 in total (budget 4.0).
- **Output:** on Talon `/home/buggjm/talon_project/teacher_outputs/2026-11-21_qwen3-6-27b-talon-bf16_benchmark_benchmark-v8_{3343fe61_shard1of3, 86d58d79_shard2of3, 9dafcafa_shard3of3}`; on the PC the same folders in `C:\masters_project_large\data\teacher_outputs\` plus `2026-11-21_replacement_loop_stageG_r1_logs\`. Ledger: `C:\masters_project_large\data\benchmark_work\2026-11-21_replacement_loop\ledger.json`.

### 21. Talon job 317: replacement loop round 2, shard 1 of 2 (stage G), 2026-11-21 (UTC 22:42)
- **Status: reviewed.** Ended normally 2026-11-21 (UTC start 22:42, end about 23:19); 0.606 GPU-hours; shard complete; `INFRA=PASS`; 99 usable / 11 failed all 3 attempts (143 replies). Queue wait under 1 minute. The controller was stopped twice while it ran (budget rule, then a VPN drop) and resumed; the job itself was unaffected.
- **Purpose:** round 2 of the approved replacement loop: 3 same-subtopic candidates for each of the 73 positions round 1 left open (BM1643-BM1861, `benchmark_replacements.jsonl` SHA-256 `37d990fd...`); this job is shard 1 of 2 (about 110 slots). Submitted by `replacement_loop.py` under the standing approval.
- **Request and software:** as entry 20 (1 GPU, `TIME_GENERATE=01:00:00`, `GEN_MARGIN_SECONDS=600`, `GEN_FIRST=493 GEN_COUNT=219 GEN_SHARD=1/2`; vLLM 0.32.0, Qwen3.6-27B @ `6a9e13bd` BF16, prompt v8, thinking on).
- **Shard 2/2 was not submitted:** the controller's budget rule stopped it (2.12 GPU-hours measured + 1.0 charged for job 317 while it runs + 1.0 for the next job > 4.0). Round 1 outcome: 91 of 164 positions filled.

### 22. Talon job 319: replacement loop round 2, shard 2 of 2 (stage G), 2026-11-21 (UTC 23:20)
- **Status: reviewed.** Ended normally 2026-11-22 (UTC about 00:00); 0.649 GPU-hours; shard complete; `INFRA=PASS`; 93 usable / 16 failed all 3 attempts (152 replies). Loop total after this job: 3.38 of 4.0 GPU-hours.
- **Purpose:** shard 2 of 2 of round 2 (about 110 of the 219 candidates BM1643-BM1861). Submitted by the controller after job 317 was measured (2.73 GPU-hours used + 1.0 for this job = 3.73, within the 4.0 budget).
- **Request and software:** as entries 20 and 21 (`GEN_FIRST=493 GEN_COUNT=219 GEN_SHARD=2/2`; 1 GPU, `TIME_GENERATE=01:00:00`).

### 23. Talon job 321: replacement loop round 3 (stage G), 2026-11-22 (UTC 01:10)
- **Status: reviewed.** Reached its 1-hour Slurm limit (UTC end about 02:03): 0.88 GPU-hours; `INFRA=PASS`, `GEN_COMPLETE=no`: 132 usable, 19 failed all 3 attempts, **2 unfinished** (219 replies). Loop total 4.26 GPU-hours. The 2 unfinished slots are finished by a resume job under the same identifier (Jaxson raised the budget to 5.3 for it).
- **Purpose:** round 3, the last round of the replacement loop: 3 same-subtopic candidates for each of the 51 positions still open after round 2 (BM1862-BM2014, `benchmark_replacements.jsonl` SHA-256 `3a1694c0...`), one job of 153 slots. Submitted by the controller after Jaxson raised the loop's GPU budget from 4.0 to 5.0 (ledger amendment, 2026-11-22); 3.38 GPU-hours used before this job.
- **Request and software:** as entries 20-22 (`GEN_FIRST=712 GEN_COUNT=153 GEN_SHARD=1/1`; 1 GPU, `TIME_GENERATE=01:00:00`, `GEN_MARGIN_SECONDS=600`; vLLM 0.32.0, Qwen3.6-27B @ `6a9e13bd` BF16, prompt v8, thinking on).
