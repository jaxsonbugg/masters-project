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
TALON_SSH_ALIAS="${TALON_SSH_ALIAS-talon}"   # UNVERIFIED: the alias goes in ~/.ssh/config; login host and VPN/Duo rules are unknown
                                              # (see recovery/talon_ssh_access.md; the host name is a placeholder until Miami gives it)

# ---- Slurm: how to ask for GPUs (the submit script builds the sbatch options from these; #SBATCH lines cannot hold variables)
TALON_PARTITION="${TALON_PARTITION-}"        # UNVERIFIED: partition name for the H100 nodes; blank = the scheduler's default
TALON_ACCOUNT="${TALON_ACCOUNT-}"            # UNVERIFIED: charge account / allocation name, if one must be given; blank = none
TALON_QOS="${TALON_QOS-}"                    # UNVERIFIED: quality-of-service name, if required; blank = none
TALON_GPU_STYLE="${TALON_GPU_STYLE-}"        # UNVERIFIED: gres (--gres=gpu[:type]:N) or gpus (--gpus[=type:]N); blank = a person must choose
TALON_GPU_TYPE="${TALON_GPU_TYPE-}"          # UNVERIFIED: gpu type name inside the request, for example h100; blank = untyped
TALON_EXTRA_SBATCH="${TALON_EXTRA_SBATCH-}"  # UNVERIFIED: any other required sbatch option, for example --cpus-per-task=16 --mem=200G
TIME_SMOKE="${TIME_SMOKE-}"                  # UNVERIFIED: wall-time requests; the cluster's real maximum is unknown. Format [D-]HH:MM:SS
TIME_THROUGHPUT="${TIME_THROUGHPUT-}"
TIME_PIPELINE="${TIME_PIPELINE-}"
TIME_MAIN="${TIME_MAIN-}"
TALON_MIN_MAIN_SECONDS="${TALON_MIN_MAIN_SECONDS-7200}"   # UNVERIFIED guess: the pipeline will not start the main run with less time left

# ---- software ---------------------------------------------------------------------------------------------------------
MOD_PYTHON="${MOD_PYTHON-}"                  # UNVERIFIED: module names from `module avail`; blank = do not load a module
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
# the Redhawk and Novita runs. It is far below Qwen's native 262,144 tokens and below the 128K the model card advises for
# keeping thinking quality: do not read these results as the model's best.
MAX_MODEL_LEN="${MAX_MODEL_LEN-20480}"

# ---- Talon facts that are NOT verified (printed by every script that touches Talon) ---------------------------------------
TALON_UNVERIFIED_FACTS=(
  "pricing and charges for GPU time"
  "the allocation and whether a sponsored student draws on the faculty sponsor's research credit (a \$1,000 yearly credit per PI was seen only in a search snippet)"
  "GPU quotas, per-user limits and maximum job length"
  "access requirements (sponsorship request, expiry date, usage and data policies, and whether Redhawk and Talon accounts are separate)"
)
