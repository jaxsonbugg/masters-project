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

**GPU-hours used to date: about 2.67:** about 0.05 (Redhawk job 6), about 0.0003 (Talon job 196), about 0.17 (Talon job 204), about 0.08 (Talon job 207, cancelled) and about 2.37 (Talon job 209), plus Redhawk job 7 once it is reviewed.

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
