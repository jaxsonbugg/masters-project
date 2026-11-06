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
SETTINGS_REVIEWED=no     # change to yes ONLY after the probe output has been copied in below and a person has read this file

# ---- how to reach Talon ----------------------------------------------------------------------------------------------
TALON_SSH_ALIAS="${TALON_SSH_ALIAS-talon}"   # the alias in ~/.ssh/config (host mualhphp01.hpc.miamioh.edu, user buggjm, same account as Redhawk, VPN needed
                                              # off campus: TOLD BY RESEARCH COMPUTING 2026-11-05/06); see recovery/talon_ssh_access.md

# ---- Slurm: how to ask for GPUs (the submit script builds the sbatch options from these; #SBATCH lines cannot hold variables)
TALON_PARTITION="${TALON_PARTITION-talon}"   # TOLD BY RESEARCH COMPUTING 2026-11-05 ("the GPU partition is called talon"); not yet checked by the probe
TALON_NODELIST="${TALON_NODELIST-}"          # OPTIONAL node choice, blank = any node of the partition (the default). TOLD BY RESEARCH COMPUTING
                                              # 2026-11-05: --nodelist=mualhpgp01.mpi lands a job on GPU node 1. That is a confirmed way to CHOOSE
                                              # a node, not a requirement: pin a node only if the nodes differ, only one is usable, or a benchmark
                                              # must run on identical hardware (docs/talon_setup.md, section "Choosing a node").
TALON_ACCOUNT="${TALON_ACCOUNT-}"            # UNVERIFIED: charge account / allocation name, if one must be given; blank = none
TALON_QOS="${TALON_QOS-}"                    # UNVERIFIED: quality-of-service name, if required; blank = none
TALON_GPU_STYLE="${TALON_GPU_STYLE-}"        # UNVERIFIED: gres (--gres=gpu[:type]:N) or gpus (--gpus[=type:]N); blank = a person must choose.
                                              # Research Computing's own example (2026-11-06) uses --gres=gpu:2, so gres is the likely answer, but
                                              # nothing has been tested yet: probe_talon_part2.sh (sbatch --test-only) checks it, with approval.
TALON_GPU_TYPE="${TALON_GPU_TYPE-}"          # UNVERIFIED: gpu type name inside the request, for example h100; blank = untyped
TALON_EXTRA_SBATCH="${TALON_EXTRA_SBATCH-}"  # UNVERIFIED: any other required sbatch option, for example --cpus-per-task=16 --mem=200G
TIME_SMOKE="${TIME_SMOKE-}"                  # wall-time requests. TOLD BY RESEARCH COMPUTING 2026-11-06: one job may run at most 3 days (72:00:00);
                                              # the probe shows the scheduler's MaxTime for comparison. Format [D-]HH:MM:SS
TIME_THROUGHPUT="${TIME_THROUGHPUT-}"
TIME_PIPELINE="${TIME_PIPELINE-}"
TIME_MAIN="${TIME_MAIN-}"
TALON_MIN_MAIN_SECONDS="${TALON_MIN_MAIN_SECONDS-7200}"   # UNVERIFIED guess: the pipeline will not start the main run with less time left

# ---- software ---------------------------------------------------------------------------------------------------------
MOD_PYTHON="${MOD_PYTHON-}"                  # UNVERIFIED: module names from `module avail`; blank = do not load a module. Research Computing's example
                                              # (2026-11-06) loads miniforge3-python3.12 (conda); the probe checks that the module exists
MOD_CUDA="${MOD_CUDA-}"
MOD_GCC="${MOD_GCC-}"
MOD_EXTRA="${MOD_EXTRA-}"                    # UNVERIFIED: any other module needed, space separated
TALON_ENGINE_MODE="${TALON_ENGINE_MODE-venv}"   # venv = a Python virtual environment with vLLM installed by pip.
                                                # container = Apptainer/Singularity image: NOT IMPLEMENTED in this draft (decide after the probe)
QT_BASE_PYTHON="${QT_BASE_PYTHON-}"          # UNVERIFIED: full path of a Python 3.10+ interpreter (blank = a person must choose)
VLLM_VERSION="${VLLM_VERSION-}"              # UNVERIFIED: exact pin; the model card requires vllm>=0.19.0. Blank = a person must choose
SGLANG_NOTE="SGLang (>=0.5.10) is the model card's other engine; it is a fallback if vLLM cannot be installed, not built here."

# ---- the model: BF16 safetensors from Hugging Face, pinned to one commit ---------------------------------------------------
MODEL_REPO="${MODEL_REPO-Qwen/Qwen3.6-27B}"  # from the model card read 2026-11-05
MODEL_REV="${MODEL_REV-}"                    # UNVERIFIED: a COMMIT HASH, never a branch name; resolved at probe time from the Hugging Face page
WEIGHTS_MIB="${WEIGHTS_MIB-51500}"           # UNVERIFIED ARITHMETIC: 27B parameters x 2 bytes = about 54 GB = about 51,500 MiB; prep records the real total
SERVED_NAME="${SERVED_NAME-qwen3.6-27b-bf16}"   # must equal BACKENDS["talon"]["model"] in code/generation/open_teacher_test.py
GPU_MIN_TOTAL_MIB="${GPU_MIN_TOTAL_MIB-70000}"  # UNVERIFIED: an 80 GB-class H100 reports about 81,500 MiB; the 94 GB variant about 95,800

# ---- GPU layout: NO PREFERRED DEFAULT (the throughput benchmark chooses it; see docs/talon_setup.md) --------------------------
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
  "the 500 GB storage limit and the 3-day job limit (told in the meeting; the scheduler's own limits are shown by the probe), and any per-user GPU limits"
  "usage and data policies (the meeting said nothing changes without written notice, and our use looked fine; nothing is in writing)"
)
