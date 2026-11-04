#!/bin/bash
#SBATCH --job-name=qt_smokeB
#SBATCH --partition=gpu
#SBATCH --gres=gpu:2
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=01:00:00
#SBATCH --output=%x_%j.log
# gpu_smoke_b.sbatch - Stage B: TWO sequences at once (context 40,960 = 20,480 per sequence), development slots
# BM9003-BM9004. The job REFUSES to start unless Stage A passed with at least 3 GB free on each GPU, with the same
# flash-attention mode, llama.cpp commit and weights.
# SUBMIT FROM THE REPOSITORY ROOT:   cd <repo copy> && sbatch configs/redhawk/gpu_smoke_b.sbatch
# (pass the same QT_FA that Stage A used if it was not auto: sbatch --export=ALL,QT_FA=off configs/redhawk/gpu_smoke_b.sbatch)
set -euo pipefail
SD="${SLURM_SUBMIT_DIR:-$PWD}/configs/redhawk"
[ -f "$SD/common.sh" ] || { echo "STOP: submit from the repository root (cd <repo>; sbatch configs/redhawk/gpu_smoke_b.sbatch)" >&2; exit 2; }
export QT_STAGE=B QT_CTX=40960 QT_PARALLEL=2 QT_FA="${QT_FA:-auto}" QT_PY_TIMEOUT=35m
bash "$SD/serve_and_run.sh"
