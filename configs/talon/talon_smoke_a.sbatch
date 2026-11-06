#!/bin/bash
#SBATCH --job-name=qt_talon_A
#SBATCH --nodes=1
#SBATCH --output=%x_%j.log
# DRAFT (Talon, written before any Talon login): refuses to run until talon_settings.sh has SETTINGS_REVIEWED=yes.
# Stage A: 2 development questions (BM9001-2), one request at a time: does the model load on the GPUs of the chosen layout, does a full generation work, are the replies saved and tied to the right slots, do the reply fields have the names the code expects?
# SUBMIT WITH THE SUBMIT SCRIPT, NOT WITH A BARE sbatch: #SBATCH lines cannot hold variables, so submit_pipeline.sh builds the
# partition, account, GPU request and wall time from talon_settings.sh and passes the GPU layout:
#   cd <repo copy> && QT_SUBMIT=yes GPU_COUNT=<n> TENSOR_PARALLEL=<n> REPLICAS=1 MAX_NUM_SEQS=<n> CLIENT_CONCURRENCY=<n> bash configs/talon/submit_pipeline.sh smoke_a
# (Without the GPU request the job finds no GPU and stops in its first seconds; without review it stops even earlier.)
set -euo pipefail
SD="${SLURM_SUBMIT_DIR:-$PWD}/configs/talon"
[ -f "$SD/common.sh" ] || { echo "STOP: submit from the repository root (cd <repo>; bash configs/talon/submit_pipeline.sh smoke_a)" >&2; exit 2; }
export QT_STAGE=A QT_PY_TIMEOUT="${QT_PY_TIMEOUT:-35m}"
bash "$SD/serve_and_run.sh"
