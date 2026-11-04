#!/bin/bash
#SBATCH --job-name=qt_main
#SBATCH --partition=gpu
#SBATCH --gres=gpu:2
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=12:00:00
#SBATCH --output=%x_%j.log
# qwen_test.sbatch - the overnight run: the main slots BM0021-BM0120, ONE attempt per slot.
# It REFUSES to start unless the matching smoke stage passed with exactly the same context, parallelism,
# flash-attention mode, llama.cpp commit and weights. The setting must be given explicitly (no default):
#   cd <repo copy>
#   sbatch --export=ALL,QT_CTX=20480,QT_PARALLEL=1 configs/redhawk/qwen_test.sbatch     (Stage A passed)
#   sbatch --export=ALL,QT_CTX=40960,QT_PARALLEL=2 configs/redhawk/qwen_test.sbatch     (Stage B also passed)
# (add QT_FA=<mode> to --export if the passing stage used something other than auto)
# VALIDATION is mandatory: when the run ends the job validates the run folder and reports INFRASTRUCTURE problems
# (missing files, duplicate or missing slots, an incomplete run) separately from MODEL-QUALITY findings (invalid
# JSON, truncation, wrong fields), which are results and do not fail the job.
# RESUMING after a time limit or a stop: add QT_RESUME=<the run folder>. Finished slots are never re-sent, errored
# slots are re-sent only with QT_RETRY_ERRORS=yes, the settings must match the original run, and a stale lock needs QT_BREAK_LOCK=yes
# (only after checking with squeue that no job is still running). Starting a SECOND main folder is refused by the
# client. If sbatch says 12 hours exceeds the gpu partition's limit, lower --time (probe_cluster.sh shows MaxTime).
set -euo pipefail
SD="${SLURM_SUBMIT_DIR:-$PWD}/configs/redhawk"
[ -f "$SD/common.sh" ] || { echo "STOP: submit from the repository root (cd <repo>; sbatch configs/redhawk/qwen_test.sbatch)" >&2; exit 2; }
[ -n "${QT_CTX:-}" ] && [ -n "${QT_PARALLEL:-}" ] || { echo "STOP: pass the tested setting with --export=ALL,QT_CTX=...,QT_PARALLEL=... (see the header of this file)" >&2; exit 2; }
export QT_STAGE=main QT_FA="${QT_FA:-auto}"
bash "$SD/serve_and_run.sh"
