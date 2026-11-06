#!/bin/bash
#SBATCH --job-name=qt_talon_T
#SBATCH --nodes=1
#SBATCH --output=%x_%j.log
# DRAFT (Talon, written before any Talon login): refuses to run until talon_settings.sh has SETTINGS_REVIEWED=yes.
# Stage T: the throughput benchmark. 32 development questions (BM9101-9132) once per client concurrency in SWEEP_CONCURRENCY, on one server start, for the layout given in the environment. Run it once per layout (for example 1 GPU, then 2 GPUs), then read all runs with code/generation/throughput_report.py. Needs a passing Stage A with the same engine and weights.
# SUBMIT WITH THE SUBMIT SCRIPT, NOT WITH A BARE sbatch: #SBATCH lines cannot hold variables, so submit_pipeline.sh builds the
# partition, account, GPU request and wall time from talon_settings.sh and passes the GPU layout:
#   cd <repo copy> && QT_SUBMIT=yes GPU_COUNT=<n> TENSOR_PARALLEL=<n> REPLICAS=1 MAX_NUM_SEQS=<n> CLIENT_CONCURRENCY=<n> bash configs/talon/submit_pipeline.sh throughput
# (Without the GPU request the job finds no GPU and stops in its first seconds; without review it stops even earlier.)
set -euo pipefail
SD="${SLURM_SUBMIT_DIR:-$PWD}/configs/talon"
[ -f "$SD/common.sh" ] || { echo "STOP: submit from the repository root (cd <repo>; bash configs/talon/submit_pipeline.sh throughput)" >&2; exit 2; }
export QT_STAGE=T QT_PY_TIMEOUT="${QT_PY_TIMEOUT:-90m}"
bash "$SD/serve_and_run.sh"
