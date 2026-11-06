#!/bin/bash
#SBATCH --job-name=qt_talon_main
#SBATCH --nodes=1
#SBATCH --output=%x_%j.log
# DRAFT (Talon, written before any Talon login): refuses to run until talon_settings.sh has SETTINGS_REVIEWED=yes.
# The MAIN run alone: BM0021-BM0120, one attempt per slot, with the layout that passed Stage B. Use it to resume or repeat the
# main run after the pipeline stopped (talon_pipeline.sbatch runs A, B and main in one job). A resume sends only the slots that
# have no saved reply: finished slots are never re-sent. The gate demands a passing Stage B with the SAME layout, engine and weights.
# SUBMIT WITH THE SUBMIT SCRIPT (it builds the partition, account, GPU request and wall time from talon_settings.sh):
#   cd <repo copy> && QT_SUBMIT=yes GPU_COUNT=<n> TENSOR_PARALLEL=<n> REPLICAS=1 MAX_NUM_SEQS=<n> CLIENT_CONCURRENCY=<n> bash configs/talon/submit_pipeline.sh main
# To resume:  ... QT_RESUME=<the run folder named in the failed job's summary> bash configs/talon/submit_pipeline.sh main
set -euo pipefail
SD="${SLURM_SUBMIT_DIR:-$PWD}/configs/talon"
[ -f "$SD/common.sh" ] || { echo "STOP: submit from the repository root (cd <repo>; bash configs/talon/submit_pipeline.sh main)" >&2; exit 2; }
export QT_STAGE=main
bash "$SD/serve_and_run.sh"
