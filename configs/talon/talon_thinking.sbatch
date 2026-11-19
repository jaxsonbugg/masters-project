#!/bin/bash
#SBATCH --job-name=qt_talon_K
#SBATCH --nodes=1
#SBATCH --output=%x_%j.log
# Stage K: the thinking on/off check (docs/methodology/workflow.md Section 2.1), on one server start. Set K (BM8001-BM8060:
# 40 primary development slots plus a 20-slot reserve) is written with thinking on and with thinking off; the fixed shared
# question set is built from both (answer-set); then each mode answers it K_SAMPLES (default 3) times per question. Every run
# is validated. Needs a passing Stage A with the same engine and weights. Graded later on the PC (answer_check.py).
# Refuses to run until talon_settings.sh has SETTINGS_REVIEWED=yes.
# SUBMIT WITH THE SUBMIT SCRIPT, NOT WITH A BARE sbatch (it builds the partition, GPU request and wall time from the settings):
#   cd <repo copy> && QT_SUBMIT=yes GPU_COUNT=1 TENSOR_PARALLEL=1 REPLICAS=1 MAX_NUM_SEQS=16 CLIENT_CONCURRENCY=16 bash configs/talon/submit_pipeline.sh thinking
set -euo pipefail
SD="${SLURM_SUBMIT_DIR:-$PWD}/configs/talon"
[ -f "$SD/common.sh" ] || { echo "STOP: submit from the repository root (cd <repo>; bash configs/talon/submit_pipeline.sh thinking)" >&2; exit 2; }
export QT_STAGE=K QT_PY_TIMEOUT="${QT_PY_TIMEOUT:-120m}"
bash "$SD/serve_and_run.sh"
