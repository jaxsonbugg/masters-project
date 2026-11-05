#!/bin/bash
#SBATCH --job-name=qt_smokeA
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --exclude=mualhpcp50.mpi
#SBATCH --time=01:00:00
#SBATCH --output=%x_%j.log
# gpu_smoke_a.sbatch - Stage A of the Redhawk GPU smoke test: ONE sequence, 20,480-token context, development
# slots BM9001-BM9002 (never the main slots). It answers: does the model load on the two V100s, does a full
# generation work, are the replies saved and tied to the right slots, and how much GPU memory is free?
# SUBMIT FROM THE REPOSITORY ROOT:   cd <repo copy> && sbatch configs/redhawk/gpu_smoke_a.sbatch
# Prerequisites that this job checks and stops on (see serve_and_run.sh): 2 V100s visible, weights SHA-256, chat
# template hash, pinned llama.cpp commit, every llama-server flag listed; after the load, memory in use on both GPUs.
# WHY A WHOLE NODE: Slurm on Redhawk has no GPU resources defined (GresTypes = null), so --gres=gpu:2 would be rejected
# and a job that does not take the node exclusively could share the two V100s with another user's job. --exclusive gives
# this job the whole node (24 cores, both V100s). mualhpcp38-41 hold the V100s; mualhpcp50 is a different, drained
# node and is excluded. Open question only this job can answer: does flash attention (-fa auto, head size 256) work on
# V100 with this build. If it crashes, rerun with flash attention off:
#   sbatch --export=ALL,QT_FA=off configs/redhawk/gpu_smoke_a.sbatch
set -euo pipefail
SD="${SLURM_SUBMIT_DIR:-$PWD}/configs/redhawk"
[ -f "$SD/common.sh" ] || { echo "STOP: submit from the repository root (cd <repo>; sbatch configs/redhawk/gpu_smoke_a.sbatch)" >&2; exit 2; }
export QT_STAGE=A QT_CTX=20480 QT_PARALLEL=1 QT_FA="${QT_FA:-auto}" QT_PY_TIMEOUT=35m
bash "$SD/serve_and_run.sh"
