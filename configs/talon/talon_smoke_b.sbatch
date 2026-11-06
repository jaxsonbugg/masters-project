#!/bin/bash
#SBATCH --job-name=qt_talon_B
#SBATCH --nodes=1
#SBATCH --output=%x_%j.log
# DRAFT (Talon, written before any Talon login): refuses to run until talon_settings.sh has SETTINGS_REVIEWED=yes.
# Stage B: 2 development questions (BM9003-4) at the client concurrency the main run will use. Needs a passing Stage A with the same layout, engine and weights.
# SUBMIT WITH THE SUBMIT SCRIPT, NOT WITH A BARE sbatch: #SBATCH lines cannot hold variables, so submit_pipeline.sh builds the
# partition, account, GPU request and wall time from talon_settings.sh and passes the GPU layout:
#   cd <repo copy> && QT_SUBMIT=yes GPU_COUNT=<n> TENSOR_PARALLEL=<n> REPLICAS=1 MAX_NUM_SEQS=<n> CLIENT_CONCURRENCY=<n> bash configs/talon/submit_pipeline.sh smoke_b
# (Without the GPU request the job finds no GPU and stops in its first seconds; without review it stops even earlier.)
set -euo pipefail
SD="${SLURM_SUBMIT_DIR:-$PWD}/configs/talon"
[ -f "$SD/common.sh" ] || { echo "STOP: submit from the repository root (cd <repo>; bash configs/talon/submit_pipeline.sh smoke_b)" >&2; exit 2; }
export QT_STAGE=B QT_PY_TIMEOUT="${QT_PY_TIMEOUT:-35m}"
bash "$SD/serve_and_run.sh"
