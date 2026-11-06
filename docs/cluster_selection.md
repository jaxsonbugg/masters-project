# Cluster Selection (Phase 4 pilot)

Prepared 2026-10-01. Which compute resource should run the project's computational work (baseline evaluation, teacher-output handling, and fine-tuning of the Pythia deduped students)? Everything below is from public pages or arithmetic, plus what you confirmed about your own access. A "Pending login findings" section at the end is filled in after the login probe.

## Recommendation (preliminary)

1. **Use Redhawk now.** It is the only option with confirmed access, and it is enough for the Phase 4 pilot and for evaluation of all four students.
2. **Treat 1B full fine-tuning on Redhawk as undetermined until measured.** A standard full-fine-tuning recipe for 1B is likely too tight for a single 16 GB V100, but that is an estimate, not a result. The Phase 4 pilot must measure actual peak memory for all four sizes, at the real sequence length and batch size, before deciding between sharding, gradient checkpointing, an 8-bit optimizer, LoRA, or a larger GPU.
3. **Ask for Talon access in parallel.** Talon (H100 GPUs) is the natural fallback for the 1B student, and its access time is unknown, so the request should start now rather than after the pilot.
4. OSC and local runs are not recommended (reasons below).

This recommendation changes if the login probe shows Redhawk cannot run a GPU PyTorch job at all, or if the pilot shows the smaller students also do not fit.

## 1. Candidates

| Option | What is known | Source |
|---|---|---|
| **Redhawk** (access confirmed by you) | Slurm; partitions `batch`, `gpu`, `bigmem`. 4 GPU nodes, each 24 cores, 96 GB RAM, 2x NVIDIA Tesla V100-PCIE-16GB (8 GPUs total, shared with the whole campus). About 120 TB shared storage. 2 login nodes. Login host `redhawk.hpc.muohio.edu`. | [Redhawk cluster page](https://www.miamioh.edu/research/research-computing-support/services/hpc-cluster), [batch usage](https://miamioh.edu/research-innovation/research-computing-support/batch-cluster-usage.html), [interactive usage](https://miamioh.edu/research-innovation/research-computing-support/interactive-cluster-usage.html), [Slurm page](https://miamioh.edu/research-innovation/research-computing-support/slurm-resource-manager.html) |
| **Talon** (access not confirmed) | 4 GPU nodes, each with 4x NVIDIA H100 (16 GPUs) plus 20 compute nodes; turned over to researchers around end of June 2026. NSF-funded. Students get accounts through a faculty sponsor. No public documentation for login host, partitions, quotas or modules. | [Talon news (2026-06)](https://miamioh.edu/news/2026/06/new-talon-cluster-a-major-leap-forward-in-accelerated-computing-ai-technology-infrastructure-at-miami.html), [Talon news (2025-11)](https://miamioh.edu/it-services/news-media/2025/11/talon-cluster.html), [resource overview](https://miamioh.teamdynamix.com/TDClient/1813/Portal/KB/ArticleDet?ID=169669), [account requests](https://miamioh.teamdynamix.com/TDClient/1813/Portal/KB/Article/128277/Request-and-manage-sponsored-High-Performance-Computing-HPC-cluster-accounts-for-students-staff-and) |
| **Ohio Supercomputer Center (OSC)** | Ascend: A100 40 GB nodes. Cardinal: nodes with 4x H100 (94 GB). Fully subsidized accounts are for faculty/research scientists at Ohio institutions; graduate students need an eligible principal investigator. Miami's overview mentions a $1,000 annual OSC research credit per PI. | [OSC Ascend](https://www.osc.edu/node/6363), [Cardinal article](https://www.nextplatform.com/hpc/2024/02/20/osc-blends-intel-hbm-cpus-and-nvidia-hbm-gpus-for-cardinal-supercomputer/1654975), [Miami resource overview](https://miamioh.teamdynamix.com/TDClient/1813/Portal/KB/ArticleDet?ID=169669) |
| **This PC** | Intel Iris Xe and Intel Arc A370M graphics, no NVIDIA/CUDA GPU (checked 2026-10-01). | checked locally |

GPU facts used below:
- NVIDIA lists H100 at 80 GB (SXM) and 94 GB (NVL), with FP16, BF16 and FP8 tensor-core support: [NVIDIA H100](https://www.nvidia.com/en-us/data-center/h100/). Which H100 variant Talon uses is not public.
- V100 tensor cores operate on FP16 inputs; there is no native BF16: see the tensor-core summary at [Glenn Klockwood's notes](https://glennklockwood.com/garden/tensor-cores) (secondary source; check NVIDIA's V100 whitepaper before relying on it in the report).

## 2. Memory arithmetic for fine-tuning

A common mixed-precision recipe with Adam uses about 16 bytes per parameter before activations (FP16 weights 2 + FP16 gradients 2 + FP32 master weights 4 + two FP32 Adam states 8). The actual recipe is not chosen (README: Phase 8; `docs/model_versions.md`, concept 3), so this is a range for planning only, not a decision.

| Size | Official params | FP16 weights alone | About 16 bytes/param, before activations | Fits one 16 GB V100? |
|---|---|---|---|---|
| 70M | 70,426,624 | 0.14 GB | 1.1 GB | Expected yes |
| 160M | 162,322,944 | 0.32 GB | 2.6 GB | Expected yes |
| 410M | 405,334,016 | 0.81 GB | 6.5 GB | Expected yes (activations at long sequence length need checking) |
| 1B | 1,011,781,632 | 2.02 GB | 16.2 GB | Likely too tight; undetermined until measured |

Activations, the CUDA context and fragmentation all add to this, and a 16 GB V100 does not offer the full 16 GB to the model. Options if 1B does not fit, each of which is a logged deviation from "identical recipe across sizes" (README Section 2 and Section 12): sharding across the 2 GPUs of one Redhawk node, gradient checkpointing, an 8-bit or paged optimizer, LoRA instead of full fine-tuning (README Section 10 lists full fine-tune as the cleaner choice), or moving the 1B run to an H100 node on Talon/OSC. **The pilot measures peak memory per size before any of these is chosen.**

## 3. Decision matrix

Ratings are qualitative (good / fair / poor / unknown), each tied to the evidence above. They are not scores to add up.

| Factor | Redhawk | Talon | OSC | This PC |
|---|---|---|---|---|
| Access now | **Good**: confirmed | **Unknown**: sponsor request needed, timing unknown | **Fair**: needs Dr. Lee as PI and an OSC account | Good |
| GPU memory for 70M to 410M | Fair to good: 16 GB, expected to fit | Good: H100 80/94 GB | Good: A100 40 GB or H100 | Poor: no CUDA GPU |
| GPU memory for 1B full fine-tune | Unknown until measured (likely tight) | Good if H100 has 80 GB or more | Good | Poor |
| Precision hardware | FP16 only (matches the FP16 load decision; mixed-precision training needs loss scaling; no BF16) | FP16 and BF16 | FP16 and BF16 | n/a |
| Capacity and queue | Fair: 8 V100s shared by campus; load unknown | Unknown: 16 GPUs shared; load unknown | Unknown | n/a |
| Throughput per run | Fair (V100 is older) | Good | Good | Poor |
| Software | Unknown until login: documented `module load anaconda-python3`; PyTorch/CUDA modules, pip/venv rules unconfirmed | Unknown | Documented by OSC | Python 3.11 installed (CPU only) |
| Internet from nodes | Unknown (probe pending); plan does not need it (files copied with `scp`) | Unknown | Unknown | Good |
| Cost | Free with sponsorship | Free with sponsorship | Free for eligible PIs; credits otherwise | Free |
| Reproducibility | Good: one fixed GPU type for all runs | Good once chosen | Good | n/a |
| Support | rescomp@miamioh.edu | rescomp@miamioh.edu | OSC help desk | n/a |

Reading of the matrix:
- This PC is ruled out for training and baseline evaluation of anything larger than the smallest models (no CUDA GPU). It remains useful for writing code and small CPU tests.
- OSC is ruled out as the first choice: it needs an eligible PI and a separate account, adds a second environment, and offers nothing Talon would not, if Talon access is granted. It stays a back-up if Miami's clusters are too busy.
- Redhawk vs Talon is not a choice between rivals but a sequencing: Redhawk is available now; Talon is better hardware for the 1B student but unconfirmed.

## 4. Consistency across students

Same hardware for all sizes is the cleanest design (README Section 2: identical recipe, data and evaluation). If 1B must move to Talon while the other three stay on Redhawk, the GPU type becomes a difference between sizes. In that case the hardware and any numerical differences (V100 FP16 vs H100) must be logged as a deviation, or the smaller sizes rerun on Talon too. This is a reason to start the Talon request early: if Talon is granted, the whole grid could run on one GPU type.

## 5. Risks

| Risk | Mitigation |
|---|---|
| 1B does not fit in 16 GB | Measure in the pilot; options listed in section 2; Talon request now |
| Redhawk GPU queue is long (8 shared GPUs) | Measure queue wait in the pilot; run the 50k set across all sizes first (README Section 9) |
| Talon access is slow or refused | Keep Redhawk-only fallback (LoRA or sharding for 1B, logged) |
| Software (PyTorch/CUDA modules, pip, internet) is restricted | Probe on login; if needed, ask rescomp@miamioh.edu; envs live in `C:\masters_project_large\envs` or cluster home |
| FP16 training instability on V100 (loss scaling) | Phase 8 recipe decision, after the cluster environment is known |

## 6. What stays open

- Pilot peak-memory measurements for all four sizes.
- Whether Talon access is granted, and its H100 memory size and queue.
- Cluster policy: internet from login/compute nodes, home and scratch quotas, PyTorch/CUDA modules.
- Training precision recipe (Phase 8).

## 7. Pending login findings

To be filled in after the login probe (host name of the login node, storage and quota, partitions and GPU types from `sinfo`, available modules, outbound internet from the login node):

- **Login confirmed (2026-10-01):** Jaxson ran `ssh redhawk` from this PC (host `redhawk.hpc.muohio.edu`, user `buggjm`) and logged in with password + Duo. The command output itself was not captured, so the login node name is not recorded yet.
- **Shortcut:** typing `redhawk` in a new terminal runs `ssh redhawk` (config in `~/.ssh/config`, command in `C:\Users\Buggb\bin\redhawk.cmd`); see `recovery/redhawk_ssh_access.md`.
- **Duo on every login:** still required. Whether Research Computing can relax this is a question for rescomp@miamioh.edu.
- **First probe (2026-10-01, partial output pasted by Jaxson, not a full capture):**
  - Login node: `mualhplp02.hpc.miamioh.edu`.
  - Home storage: `muanasp05-4001.mcs.miamioh.edu:p05_nfs_oel_rh3_home` mounted at `/home`, an NFS share of 63 TB with 51 TB used and 12 TB free (81% full). It is shared across users; no per-user quota figure was shown.
  - The probe printed `Stale file handle` before the host name. That is an NFS error (a handle to a file or directory that the server no longer recognizes), not a login failure; the login itself worked. Cause unknown. If it repeats, report it to Research Computing, since jobs that read data or code from `/home` could fail the same way.
- **Not yet seen:** quota, partitions and GPU types (`sinfo`), modules (Python, PyTorch, CUDA), outbound internet from the login node, user/group (`id`), and the GPU type actually delivered by Slurm. Those parts of the probe printed nothing in the pasted output. Non-interactive `ssh host "command"` sessions often lack the `module` command, so those are to be re-run inside an interactive session.

- **Full login-node probe (2026-11-04, `configs/redhawk/probe_cluster.sh`, read-only).** What it found, and what each finding means:
  - **System.** CentOS 7, glibc 2.17, git 1.8.3.1, bash and coreutils of the same age. Old, so every script was written to avoid newer shell features, and a modern Python must come from a module path (see below).
  - **GPU nodes.** The `gpu` partition (3-day limit, no default time, so every job must pass `--time`) has five nodes. `mualhpcp38`-`41` are the four V100 nodes (24 cores, 95 GB); `mualhpcp50` (48 cores, 515 GB) is drained and not a V100 node. **At probe time all four V100 nodes were fully allocated, with 7 jobs running and 21 waiting**, so queue wait, not run time, is the main schedule risk.
  - **GPUs are not a Slurm resource here.** `GresTypes = (null)` and every node shows `Gres=(null)`, although Miami's Slurm page documents `--gres=gpu:<count>`. A request with `--gres` would very likely be rejected, and a job that does not take a node exclusively could share the two V100s with another user's job (a 16 GB card shared by two jobs runs out of memory). So the job scripts take a whole node: `--nodes=1 --exclusive --exclude=mualhpcp50.mpi`. A `sbatch --test-only` run (validates a request without submitting) would confirm this; it needs approval.
  - **Job accounting is off.** `sacct` fails (its database host `mualhplp01` does not resolve). Queue wait is therefore read with `scontrol show job` while the job runs.
  - **Modules.** `cuda-12.2`, `gcc-12.2.0` and `cmake-3.31.2` load together (nvcc 12.2.140). The system `python3` is 3.6.8 and loading a Python module does not change `python` (still 2.7.5), because those modules only print a `source .../conda.sh` hint. The scripts therefore call `/software/python/anaconda3-2023-python3.10/bin/python` by full path (to be verified by `probe_cluster_part2.sh`).
  - **Storage.** `/home` has a personal quota of **480 GB** (500 GB hard limit), 60 KB used; the 85% shown by `df` is the whole shared disk (9.4 TB free). `/scratch` has no per-user quota or folder, is 86% full (686 GB free) and its purge policy is unknown. The project therefore lives in `/home/buggjm/masters_project` (`redhawk_*` in `configs/paths.yaml`); the 17 GB model file is under 4% of the quota.
  - **Internet from the login node.** Hugging Face, GitHub and PyPI answer (HTTP 200). `cdn-lfs.huggingface.co` does not resolve, but that is an old host name; the follow-up probe checks the real weights URL with a headers-only request. Compute-node internet is not tested and not needed (downloads happen on the login node).
  - **Not usable:** `quota` without arguments fails on an unrelated mount (`/mnt/moab/shared`), so quota is queried per file system.
- **Follow-up probe (2026-11-04, `probe_cluster_part2.sh`, read-only; only HTTP headers of the weights file were requested).**
  - **Python verified.** `/software/python/anaconda3-2023-python3.10/bin/python` is Python 3.10.9 with venv, ensurepip, ssl (OpenSSL 1.1.1t), pyyaml 6.0 and pip 22.3.1. This is the interpreter the scripts use. (The `miniforge3-python3.12` path does not exist under `/software/python`; it is not needed.)
  - **`module` command.** It is a shell function from Environment Modules 3.2.10 (`MODULESHOME=/usr/share/Modules`, `/etc/profile.d/modules.sh` exists). Batch jobs start a non-login shell, so the scripts source those init files themselves if the function is missing (tested with a fake init file).
  - **Download path works.** The pinned weights URL redirects (302) to `us.aws.cdn.hf.co` and ends in HTTP 200 with content-length **16,817,244,384**, exactly the pinned size. The chat template answers 200 (7,764 bytes). The Xet storage hosts resolve. Old `git` 1.8.3.1 reaches GitHub, and `refs/tags/b11960` is a plain tag pointing at **8642541b255bfb5dc39cd351a178be09013a55d6**, the pinned commit.
  - **Reading the queue.** Four V100 nodes hold 96 cores. Seven jobs run: six use 12 cores (half a node each, ending in about 1 day 0 h 24 min, 1 day 7 h 39 min) and one uses all 24 cores of a node (22 h 7 min left). Twenty-one jobs wait, **all identical (1 node, 12 cores, 3-day limit) and all with the reason `QOSMaxCpuPerUserLimit`**. That reason means they are held by a per-user CPU cap, not by a shortage of free resources: they look like one user's job array that is already at the cap with the six running 12-core jobs (6 x 12 = 72 cores). They will not compete with a request until that user's running jobs end.
  - **What that means for a whole-node request.** Nothing can start before roughly 22 hours from the probe (the 24-core job ends first; the paired 12-core jobs end about two hours later), unless a job ends early (time limits are upper bounds). After that, a whole-node request has few competitors, but if a later job of ours has to queue again, the held jobs may be released and take the freed half-nodes first. This is why running smoke A, smoke B and the main run as ONE job (one wait) is the safer plan. Not yet known: the per-user CPU cap itself (our 24-core request must fit under it) and the scheduler's own start estimate; `sbatch --test-only` would show both without submitting.
  - **Still unknown until the first GPU job:** the NVIDIA driver version on the V100 nodes (CUDA 12.2 needs a driver of about 525 or newer; a mismatch would make the first smoke test fail at start-up).
- **Scheduler check, `sbatch --test-only` (2026-11-04 21:47 UTC; validates a request and estimates a start; no job was created).**
  - **Accepted.** The pipeline's request (`--partition=gpu --nodes=1 --exclusive --exclude=mualhpcp50.mpi --time=24:00:00`) passes every policy check. The per-user CPU cap in the QOS listing is `cpu=168`, far above the 24 cores a whole node needs. `--gres=gpu:2` was rejected with "Invalid generic resource (gres) specification", which confirms that GPUs are not a Slurm resource here and that `--exclusive` is the right way to claim both V100s.
  - **Estimated start: 2026-11-17 15:33 UTC on `mualhpcp38`, about 13 days away.** The estimate is identical for 24 hours, 12 hours and 1 hour, so the limit is node availability, not the length of the request.
  - **Why so far away.** The scheduler is first-come-first-served (`PriorityType=priority/basic`, `SchedulerType=sched/backfill`). The 21 identical waiting jobs (12 cores, 3 days each, held only by their owner's per-user cap) were submitted before ours, so the scheduler plans for them to start first as their owner's running jobs end. They are three-day jobs on half-nodes that keep refilling, so a node is rarely entirely empty. A whole-node request needs an entirely empty node.
  - **How to read it.** Backfill estimates assume every job runs to its full time limit; jobs that end early, or backlog jobs that are cancelled, move a real start earlier, so 13 days is closer to a worst case than a forecast. It could not be shorter than about 17 hours (the first node with a 24-core job on it frees then). New submissions by others queue behind ours, so ours is not pushed back. Nothing in the scheduler's own estimate can be trusted to the day.
  - **Consequence for the project.** A Redhawk result from the pilot is days to about two weeks away, and a long (50k example) generation run on Redhawk would face the same queue, which counts against Redhawk as the main teacher-generation engine. Talon (H100) access and a hosted API are the alternatives to weigh in the final recommendation.

## 8. Talon (added 2026-11-05; prepared in advance, nothing run yet)

Talon access is now "likely but not confirmed": the cluster is in maintenance and no account exists. Because the 200,000-example generation cannot be done on Redhawk, the Talon side was prepared in advance. **No Talon fact below beyond the hardware has been verified.** Full explanation: `docs/talon_setup.md`; scripts: `configs/talon/`.

- **What is documented.** 4 GPU nodes with 4 H100 each plus 20 CPU nodes (Miami IT news, Nov 2025); student accounts through the sponsorship page; contacts ResComp@MiamiOH.edu and Jens Mueller. Not published: login host, VPN/Duo rules, partitions, time limits, GPU request syntax, modules, storage, internet from the nodes, pricing, allocation, quotas, the H100 memory variant, the end of maintenance. All of these are marked UNVERIFIED in the scripts.
- **Design consequence.** Because almost everything is a guess, all guesses live in one file (`configs/talon/talon_settings.sh`) and every script is a draft that refuses to run until a person has replaced the guesses with the probe output and set `SETTINGS_REVIEWED=yes` (the lesson of Redhawk job 2510690).
- **Engine and precision (decision 2026-11-05).** vLLM with BF16 safetensors, the engine Qwen's model page recommends (`vllm>=0.19.0`), instead of llama.cpp with a 4-bit file. BF16 is also what Novita advertises, so Talon becomes a third comparison point (Redhawk 4-bit, Talon BF16, Novita BF16).
- **GPU layout.** No preferred default: GPU count, tensor parallelism, concurrency are settings; a throughput benchmark (stage T: successful examples per hour and GPU-hours per 1,000 examples) chooses them and projects the 200,000-example workload.
- **Update 2026-11-05 (message from Research Computing, not yet checked).** The head node is `mualhphp01.hpc.miamioh.edu`, the GPU partition is `talon`, and `--nodelist=mualhpgp01.mpi` places a job on GPU node 1 (a way to choose a node, not a requirement; the default is no node pinned). These are labelled TOLD BY RESEARCH COMPUTING; the read-only probe (`configs/talon/run_probe_local.sh`) will make some OBSERVED and others SLURM-REPORTED (configuration only, not proof that a request is accepted or a GPU works). Evidence labels are explained in `docs/talon_setup.md`.
- **Separation from Redhawk.** Separate folder, separate `talon_*` path keys, separate output directory (a Talon run can never write under `redhawk_outputs`, tested in both directions). `configs/redhawk/` is unchanged and its tests still pass.
