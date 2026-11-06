#!/bin/bash
#SBATCH --job-name=qt_talon_pipeline
#SBATCH --nodes=1
#SBATCH --output=%x_%j.log
# talon_pipeline.sbatch - ONE Slurm job that runs the Talon side of the Qwen3.6-27B test in one go: Stage A, then Stage B, then the
# main run (BM0021-BM0120, one attempt per slot), with the same automatic gates between them as the Redhawk pipeline.
# DRAFT (written before any Talon login): refuses to run until talon_settings.sh has SETTINGS_REVIEWED=yes.
# SUBMIT WITH THE SUBMIT SCRIPT (it builds the partition, account, GPU request and wall time from talon_settings.sh):
#   cd <repo copy> && QT_SUBMIT=yes GPU_COUNT=<n> TENSOR_PARALLEL=<n> REPLICAS=1 MAX_NUM_SEQS=<n> CLIENT_CONCURRENCY=<n> bash configs/talon/submit_pipeline.sh pipeline
#
# WHY ONE JOB. A job waits in the queue once and then keeps its GPUs. Whether Talon's queue is long is UNKNOWN; if it is short,
# separate jobs (talon_smoke_a, talon_smoke_b, talon_test) let a person read each result before the next one.
# THE LAYOUT IS THE SAME IN EVERY STAGE. Unlike the Redhawk pipeline there is no fallback setting: the layout (GPU count, tensor
# parallelism, sequences, concurrency) is chosen BEFORE this job, from the throughput benchmark (stage T), and a stage that fails
# stops the pipeline.
#
# WHAT IT DOES, IN ORDER (each stage is serve_and_run.sh with its own checks and its own mandatory validation):
#   1. Stage A (one request at a time). Failure on INFRASTRUCTURE ends the pipeline.
#   2. If every Stage A reply had a model-quality finding, the pipeline stops unless QT_ACK_QUALITY=yes was given at submission
#      (that pattern usually means a settings problem, so a person must look).
#   3. Stage B (the concurrency the main run will use). Same rules.
#   4. Before the main run the job checks its remaining time (squeue). Under TALON_MIN_MAIN_SECONDS it does not start the main run
#      (a run cut off by the time limit leaves only a partial result); the main run can be started later with talon_test.sbatch.
#   5. The main run. Model-quality findings are RESULTS and do not fail the job; infrastructure problems do.
#   6. A summary file, stage_results/pipeline_job<ID>.txt, with every stage's result. It is also written if the job is stopped.
# Exit code 0 only if the main run finished with its infrastructure validation passed.
set -uo pipefail   # no -e on purpose: a failing stage is handled explicitly below, with its own message
SD="${SLURM_SUBMIT_DIR:-$PWD}/configs/talon"
[ -f "$SD/common.sh" ] || { echo "STOP: submit from the repository root (cd <repo>; bash configs/talon/submit_pipeline.sh pipeline)" >&2; exit 2; }
# shellcheck disable=SC1091
source "$SD/common.sh"
require_reviewed
require_paths
check_layout
check_concurrency

JOB="${SLURM_JOB_ID:-nojob}"
RESULT_DIR="$QT_OUT/stage_results"; LOGDIR="$QT_OUT/job_logs"
mkdir -p "$RESULT_DIR" "$LOGDIR"
SUMMARY="$RESULT_DIR/pipeline_job${JOB}.txt"
T0="$(date +%s)"
MIN_MAIN="${QT_MIN_MAIN_SECONDS:-$TALON_MIN_MAIN_SECONDS}"

PIPE_RESULT="STARTED"; PIPE_REASON=""; B_STATUS="not reached"; MAIN_STATUS="not started"
res() { if [ -f "$1" ]; then sed -n "s/^$2=//p" "$1" | tail -n 1; fi; }
# shellcheck disable=SC2329  # called through the EXIT trap
write_summary() {
  { echo "PIPELINE_RESULT=$PIPE_RESULT"; echo "REASON=$PIPE_REASON"; echo "JOB=$JOB"; echo "NODE=$(hostname)"
    echo "LAYOUT=$GPU_COUNT GPU(s), tensor parallel $TENSOR_PARALLEL, replicas $REPLICAS, max sequences $MAX_NUM_SEQS, client concurrency $CLIENT_CONCURRENCY, max length $MAX_MODEL_LEN"
    echo "STAGE_B=$B_STATUS"; echo "MAIN=$MAIN_STATUS"
    echo "STAGE_A_RESULT=$(res "$RESULT_DIR/stageA.txt" RESULT) (job $(res "$RESULT_DIR/stageA.txt" JOB))"
    echo "STAGE_B_RESULT=$(res "$RESULT_DIR/stageB.txt" RESULT) (job $(res "$RESULT_DIR/stageB.txt" JOB))"
    echo "MAIN_RESULT=$(res "$RESULT_DIR/main_job${JOB}.txt" RESULT) RUN_DIR=$(res "$RESULT_DIR/main_job${JOB}.txt" RUN_DIR)"
    echo "SECONDS_USED=$(( $(date +%s) - T0 ))"; echo "UTC=$(date -u +%FT%TZ)"; } > "$SUMMARY.tmp" && mv "$SUMMARY.tmp" "$SUMMARY"
}
stop_with() {  # $1 = result word, $2 = reason; ends the job with a non-zero code
  PIPE_RESULT="$1"; PIPE_REASON="$2"
  echo; echo "PIPELINE STOPPED ($1): $2"; echo "Summary: $SUMMARY"
  exit 1
}
trap write_summary EXIT
trap 'PIPE_RESULT="TERMINATED"; PIPE_REASON="the job received SIGTERM (time limit or scancel); a main run in progress can be resumed with talon_test.sbatch and QT_RESUME"; exit 143' TERM

run_stage() {  # $1 stage, $2 client timeout (may be empty)
  QT_STAGE="$1" QT_ATTEMPT="" QT_PY_TIMEOUT="${2:-}" bash "$SD/serve_and_run.sh"
}
passed() {  # $1 = stage result file: PASS or PASS_QUALITY_WARN
  case "$(res "$1" RESULT)" in PASS|PASS_QUALITY_WARN) return 0 ;; *) return 1 ;; esac
}

echo "=== Talon pipeline job $JOB on $(hostname), $(date -u +%FT%TZ): minimum time left for the main run ${MIN_MAIN}s ==="
talon_facts_banner

echo; echo "######## STAGE A ########"
run_stage A 35m; RC_A=$?
if [ "$RC_A" -ne 0 ] || ! passed "$RESULT_DIR/stageA.txt"; then
  stop_with "STOPPED_AT_A" "Stage A failed (exit $RC_A, result '$(res "$RESULT_DIR/stageA.txt" REASON)'). Read $LOGDIR/validate_${JOB}_A*.out and $LOGDIR/vllm_server_${JOB}_A*.log. Nothing else was run."
fi
if [ "$(res "$RESULT_DIR/stageA.txt" QUALITY_ALL)" = yes ] && [ "${QT_ACK_QUALITY:-}" != yes ]; then
  stop_with "STOPPED_QUALITY" "every Stage A reply had a model-quality finding. Read $LOGDIR/validate_${JOB}_A*.out; if it is understood, resubmit with QT_ACK_QUALITY=yes"
fi

echo; echo "######## STAGE B ########"
run_stage B 35m; RC_B=$?
if [ "$RC_B" -ne 0 ] || ! passed "$RESULT_DIR/stageB.txt"; then
  B_STATUS="failed (exit $RC_B, '$(res "$RESULT_DIR/stageB.txt" REASON)')"
  stop_with "STOPPED_AT_B" "Stage B failed (exit $RC_B, result '$(res "$RESULT_DIR/stageB.txt" REASON)'). Read $LOGDIR/validate_${JOB}_B*.out and $LOGDIR/vllm_server_${JOB}_B*.log. The main run was not started."
fi
B_STATUS="passed"
if [ "$(res "$RESULT_DIR/stageB.txt" QUALITY_ALL)" = yes ] && [ "${QT_ACK_QUALITY:-}" != yes ]; then
  stop_with "STOPPED_QUALITY" "every Stage B reply had a model-quality finding. Read $LOGDIR/validate_${JOB}_B*.out; resubmit with QT_ACK_QUALITY=yes if it is understood"
fi

LEFT="$(slurm_seconds_left)"
echo; echo "time left in this job: ${LEFT}s (the main run needs at least ${MIN_MAIN}s to be worth starting; -1 = unknown)"
if [ "$LEFT" -ge 0 ] && [ "$LEFT" -lt "$MIN_MAIN" ]; then
  stop_with "STOPPED_TIME" "only ${LEFT}s left, under the ${MIN_MAIN}s minimum. Both smoke stages passed. Start the main run with: QT_SUBMIT=yes bash configs/talon/submit_pipeline.sh main (same layout settings)"
fi
[ "$LEFT" -ge 0 ] || echo "WARNING: the time left could not be read; starting the main run anyway."

echo; echo "######## MAIN RUN ########"
MAIN_STATUS="started"
run_stage main ""; RC_M=$?
MAIN_STATUS="exit $RC_M, result $(res "$RESULT_DIR/main_job${JOB}.txt" RESULT)"
if [ "$RC_M" -ne 0 ]; then
  stop_with "MAIN_FAILED" "the main run ended with exit $RC_M ($(res "$RESULT_DIR/main_job${JOB}.txt" REASON)). If it is only incomplete, resume it with talon_test.sbatch and QT_RESUME=$(res "$RESULT_DIR/main_job${JOB}.txt" RUN_DIR)"
fi
PIPE_RESULT="COMPLETE"; PIPE_REASON="all stages ran with one layout"
echo; echo "PIPELINE COMPLETE. Summary: $SUMMARY"
exit 0
