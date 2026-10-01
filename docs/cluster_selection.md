# Cluster Selection (Phase 3)

Prepared 2026-10-01. Which compute resource should run the project's computational work (baseline evaluation, teacher-output handling, and fine-tuning of the Pythia deduped students)? Everything below is from public pages or arithmetic, plus what you confirmed about your own access. A "Pending login findings" section at the end is filled in after the login probe.

## Recommendation (preliminary)

1. **Use Redhawk now.** It is the only option with confirmed access, and it is enough for the Phase 3 pilot and for evaluation of all four students.
2. **Treat 1B full fine-tuning on Redhawk as undetermined until measured.** A standard full-fine-tuning recipe for 1B is likely too tight for a single 16 GB V100, but that is an estimate, not a result. The Phase 3 pilot must measure actual peak memory for all four sizes, at the real sequence length and batch size, before deciding between sharding, gradient checkpointing, an 8-bit optimizer, LoRA, or a larger GPU.
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
- **Not yet probed:** login node name, storage and quota, partitions and GPU types (`sinfo`), modules (Python, PyTorch, CUDA), outbound internet from the login node, and GPU type actually delivered by Slurm. Command and results will be added here.
