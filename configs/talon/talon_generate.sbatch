#!/bin/bash
#SBATCH --nodes=1
#SBATCH --output=%x_%j.log
# Stage G: generation (added 2026-11-20). One SHARD of a frozen slot file is sent to the teacher with the benchmark prompt v7 or
# the training prompt v1, through code/generation/generate_set.py (up to 3 attempts per slot, every attempt saved), on one
# server start, then validated. The client stops GEN_MARGIN_SECONDS before the job's end; an unfinished shard resumes when the
# SAME shard is submitted again. Needs a passing Stage A with the same engine and weights. Collected later on the PC.
# The job name is set by the submit script (qt_talon_G_<set>-<prompt>-p<first>n<count>-<k>of<K>), so the 4 shards of one
# slot file can run side by side while a second job for the SAME shard is refused.
# Refuses to run until talon_settings.sh has SETTINGS_REVIEWED=yes.
# SUBMIT WITH THE SUBMIT SCRIPT, NOT WITH A BARE sbatch:
#   cd <repo copy> && QT_SUBMIT=yes GPU_COUNT=1 TENSOR_PARALLEL=1 REPLICAS=1 MAX_NUM_SEQS=16 CLIENT_CONCURRENCY=16 \
#     GEN_SLOTS=data/slots/smoke_slots.jsonl GEN_PROMPT=benchmark GEN_SHARD=1/1 GEN_FIRST=1 GEN_COUNT=20 bash configs/talon/submit_pipeline.sh generate
set -euo pipefail
SD="${SLURM_SUBMIT_DIR:-$PWD}/configs/talon"
[ -f "$SD/common.sh" ] || { echo "STOP: submit from the repository root (cd <repo>; bash configs/talon/submit_pipeline.sh generate)" >&2; exit 2; }
export QT_STAGE=G
bash "$SD/serve_and_run.sh"
