# shellcheck shell=bash
# talon_settings.sh - EVERY Talon-specific guess lives in this one file. It is SOURCED by common.sh, never run.
#
# WHY ONE FILE. Nothing about Talon was published when these scripts were written (no login host, partition names, GPU
# request syntax, module names, storage paths or limits were findable). Every value below is therefore a GUESS or a blank,
# and each is marked UNVERIFIED. On the first login, probe_talon.sh and probe_talon_part2.sh print the real values; they
# are copied INTO THIS FILE (and nowhere else), then a person reads the file and sets SETTINGS_REVIEWED=yes. Until then every
# job script, the submit script and the download script refuse to run ("DRAFT"). This is the lesson of the first Redhawk
# pipeline job, which stopped because a check had been written against a guess about a program's output instead of its
# real output: here the guesses are collected in one place and replaced by measurements before anything runs.
#
# HOW A VALUE CAN BE CHANGED FOR ONE JOB. Layout and tuning values use `${NAME-default}`: a value in the environment wins
# (that is how the throughput sweep tries other GPU counts without editing this file), and an EMPTY default means "a person
# must choose" and the scripts stop with a plain message. SETTINGS_REVIEWED and the Talon facts are plain assignments on
# purpose: the environment cannot override them, so a draft cannot be un-drafted by accident.

# ---- the review flag -----------------------------------------------------------------------------------------------
SETTINGS_REVIEWED=yes    # REVIEWED by Jaxson Bugg on 2026-11-12 (settings review with the probe and job 196 values copied in).
                         # Set back to no if a value below is changed without a new review.

# ---- how to reach Talon ----------------------------------------------------------------------------------------------
TALON_SSH_ALIAS="${TALON_SSH_ALIAS-talon}"   # the alias in ~/.ssh/config (host mualhphp01.hpc.miamioh.edu, user buggjm, same account as Redhawk, VPN needed
                                              # off campus: TOLD BY RESEARCH COMPUTING 2026-11-05/06); see recovery/talon_ssh_access.md

# ---- Slurm: how to ask for GPUs (the submit script builds the sbatch options from these; #SBATCH lines cannot hold variables)
TALON_PARTITION="${TALON_PARTITION-talon}"   # TOLD BY RESEARCH COMPUTING 2026-11-05 ("the GPU partition is called talon"); not yet checked by the probe
TALON_NODELIST="${TALON_NODELIST-}"          # OPTIONAL node choice, blank = any node of the partition (the default). TOLD BY RESEARCH COMPUTING
                                              # 2026-11-05: --nodelist=mualhpgp01.mpi lands a job on GPU node 1. That is a confirmed way to CHOOSE
                                              # a node, not a requirement: pin a node only if the nodes differ, only one is usable, or a benchmark
                                              # must run on identical hardware (docs/clusters/talon_setup.md, section "Choosing a node").
TALON_ACCOUNT="${TALON_ACCOUNT-}"            # blank = none. SLURM-REPORTED 2026-11-06 (probe 5e): job accounting is switched off, so there are no accounts to name
TALON_QOS="${TALON_QOS-}"                    # blank = none. SLURM-REPORTED 2026-11-06: no QOS limits are configured
TALON_GPU_STYLE="${TALON_GPU_STYLE-gres}"    # gres (--gres=gpu[:type]:N) or gpus (--gpus[=type:]N). ACCEPTED BY SLURM 2026-11-11 (probe_talon_part2.sh,
                                              # sbatch --test-only, no job created): all four forms were accepted on partition talon (--gres=gpu:1,
                                              # --gres=gpu:nvidia_h100_nvl:1, --gpus=1, --gpus=nvidia_h100_nvl:1), estimated start immediate on
                                              # mualhpgp01.mpi. gres chosen because Research Computing's own example (2026-11-06) uses --gres=gpu:2.
                                              # Acceptance is not delivery: what a job actually receives is shown by the 5-minute probe job (step 2).
TALON_GPU_TYPE="${TALON_GPU_TYPE-nvidia_h100_nvl}"   # SLURM-REPORTED 2026-11-06 (probe 5b): the GPU's name in the scheduler's configuration; blank = untyped
# CPUs and memory, requested IN PROPORTION TO THE GPUs (decided in the settings review, 2026-11-12). OBSERVED 2026-11-12 (job 196): a job
# that does not ask for CPUs gets ONE core, and its memory limit is otherwise unknown. A node has 64 cores, about 503 GB of usable RAM and
# 4 GPUs, shared between users, so a quarter of a node per GPU is a fair share: build_sbatch_opts requests
# --cpus-per-task=CPUS_PER_GPU x GPU_COUNT and --mem=MEM_PER_GPU_GB x GPU_COUNT (a 1-GPU job: 16 cores, 120G; 2 GPUs: 32 cores, 240G).
CPUS_PER_GPU="${CPUS_PER_GPU-16}"
MEM_PER_GPU_GB="${MEM_PER_GPU_GB-120}"
TALON_EXTRA_SBATCH="${TALON_EXTRA_SBATCH-}"  # any OTHER sbatch option, space separated (CPUs and memory are set above). Blank = none.
# Wall-time requests (decided in the settings review, 2026-11-12). A job ends as soon as it finishes, so the limit is an upper bound and
# a safety net, not a cost: short limits for the tests start easily on a busy cluster and surface a hang within the hour; generation
# runs can resume, so a 24-hour job that runs out continues in a new job. TOLD BY RESEARCH COMPUTING 2026-11-06 and SLURM-REPORTED:
# one job may run at most 3 days. Format [D-]HH:MM:SS.
TIME_SMOKE="${TIME_SMOKE-01:00:00}"          # Stage A and Stage B smoke tests
TIME_THROUGHPUT="${TIME_THROUGHPUT-04:00:00}"  # Stage T, one GPU layout per job
TIME_PIPELINE="${TIME_PIPELINE-1-00:00:00}"  # the one-job pipeline (A, B, main)
TIME_MAIN="${TIME_MAIN-1-00:00:00}"          # a main run alone, or its resume
TALON_MIN_MAIN_SECONDS="${TALON_MIN_MAIN_SECONDS-7200}"   # UNVERIFIED guess: the pipeline will not start the main run with less time left

# ---- software ---------------------------------------------------------------------------------------------------------
MOD_PYTHON="${MOD_PYTHON-miniforge3-python3.12}"   # OBSERVED 2026-11-06 (probe 4): this module exists and puts /software/miniforge3-python3.12/bin on PATH.
                                              # The login node's own Python is 3.9, too old for vLLM (needs 3.11+), so Python 3.12 comes from this module.
MOD_CUDA="${MOD_CUDA-}"
MOD_GCC="${MOD_GCC-}"
MOD_EXTRA="${MOD_EXTRA-}"                    # UNVERIFIED: any other module needed, space separated
TALON_ENGINE_MODE="${TALON_ENGINE_MODE-venv}"   # venv = a Python virtual environment with vLLM installed by pip.
                                                # container = Apptainer/Singularity image: NOT IMPLEMENTED in this draft (decide after the probe)
QT_BASE_PYTHON="${QT_BASE_PYTHON-/software/miniforge3-python3.12/bin/python3.12}"   # OBSERVED 2026-11-06: prints "Python 3.12.5" (vLLM needs 3.11+)
VLLM_VERSION="${VLLM_VERSION-0.32.0}"        # DECIDED 2026-11-12 (settings review): one pin for ALL teacher generation. Final release of 2026-10-18 (not an rc);
                                             # supports the model (Qwen3_5ForConditionalGeneration; the card asks >=0.19.0); PyPI wheel built for CUDA 13.0 with
                                             # torch 2.13.0 (driver 610.57.04 is from the R610 branch, CUDA up to about 13.3: inferred, Stage A confirms); Python
                                             # >=3.11,<3.15; requires transformers >=5.16.1,<5.20. 0.33.0 (2026-11-02) not chosen: 10 days old, built from an rc.
                                             # Watch vLLM issue #63505 (garbled output on a model of the same architecture family, 0.31/0.32, not seen on H100):
                                             # Stage A must check that the answers make sense, not only that replies arrive.
SGLANG_NOTE="SGLang (>=0.5.10) is the model card's other engine; it is a fallback if vLLM cannot be installed, not built here."

# ---- the model: BF16 safetensors from Hugging Face, pinned to one commit ---------------------------------------------------
MODEL_REPO="${MODEL_REPO-Qwen/Qwen3.6-27B}"  # from the model card read 2026-11-05
MODEL_REV="${MODEL_REV-6a9e13bd6fc8f0983b9b99948120bc37f49c13e9}"   # CONFIRMED 2026-11-12 (settings review). Commit of 2026-04-24. A COMMIT HASH,
                                             # never a branch name. The head of main moved on 2026-11-07 to 8f33b98937c6031bb49e713dee3e8e185aafd26f, which
                                             # changes only chat_template.jinja and tokenizer_config.json (no weights): KNOWN AND NOT ADOPTED, so the tested
                                             # prompt envelope stays exactly the same.
WEIGHTS_MIB="${WEIGHTS_MIB-53011}"           # OBSERVED 2026-11-06 (probe 8): the 29 files of that commit total 55.6 GB = 53,011 MiB; prep records the real total
SERVED_NAME="${SERVED_NAME-qwen3.6-27b-bf16}"   # must equal BACKENDS["talon"]["model"] in code/generation/open_teacher_test.py
GPU_MIN_TOTAL_MIB="${GPU_MIN_TOTAL_MIB-90000}"  # OBSERVED 2026-11-12 (job 196): each Talon H100 NVL reports 95,830 MiB; a GPU reporting less than
                                                # 90,000 MiB is not one of these cards (wrong node or partition), so the job stops

# ---- GPU layout: NO PREFERRED DEFAULT (the throughput benchmark chooses it; see docs/clusters/talon_setup.md) --------------------------
# GPU_COUNT must equal TENSOR_PARALLEL x REPLICAS. TENSOR_PARALLEL = how many GPUs one copy of the model is split across.
# REPLICAS = how many independent copies run side by side (this draft implements REPLICAS=1 only; more are projected by
# arithmetic from a one-replica measurement and belong to the 200,000-example pipeline, not to this comparison).
GPU_COUNT="${GPU_COUNT-}"
TENSOR_PARALLEL="${TENSOR_PARALLEL-}"
REPLICAS="${REPLICAS-}"
MAX_NUM_SEQS="${MAX_NUM_SEQS-}"              # how many sequences the SERVER decodes at once (vLLM --max-num-seqs)
CLIENT_CONCURRENCY="${CLIENT_CONCURRENCY-}"  # how many requests the CLIENT keeps in flight for the smoke stage B and the main run
# Stage T sweep: the client concurrencies tried inside one server start, space separated. Values above MAX_NUM_SEQS only
# measure queueing and are still recorded.
SWEEP_CONCURRENCY="${SWEEP_CONCURRENCY-1 4 8 16}"
# Per-sequence context. 20,480 = 3,000 input cap + 16,384 output cap + headroom, chosen ONLY so the Talon comparison matches
# the Redhawk run. It is far below Qwen's native 262,144 tokens and below the 128K the model card advises for
# keeping thinking quality: do not read these results as the model's best.
MAX_MODEL_LEN="${MAX_MODEL_LEN-20480}"

# ---- Talon facts that are NOT verified (printed by every script that touches Talon) ---------------------------------------
# Research Computing told Jaxson in a meeting on 2026-11-06 (verbal, NOT yet in writing): the account and user name are the same as
# Redhawk's, using Talon costs nothing, the storage limit is 500 GB (more on request), one job may run at most 3 days, and the
# scheduler may choose the node. Those are TOLD BY RESEARCH COMPUTING, so they are listed below with that caveat until written.
TALON_UNVERIFIED_FACTS=(
  "pricing and charges for GPU time (told in the 2026-11-06 meeting: Talon costs nothing; verbal, not yet in writing)"
  "the total GPU-hours we may use (no figure given) and whether a faculty research credit is involved"
  "per-user GPU limits (none are configured in Slurm; the 3-day job limit and the 500 GB home quota were seen in the scheduler and in the quota display, but are not in writing)"
  "usage and data policies (the meeting said nothing changes without written notice, and our use looked fine; nothing is in writing)"
)
