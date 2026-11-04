#!/bin/bash
#SBATCH --job-name=qt_pipeline
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --exclude=mualhpcp50.mpi
#SBATCH --time=24:00:00
#SBATCH --output=%x_%j.log
# qwen_pipeline.sbatch - ONE Slurm job that runs the whole Redhawk side of the Qwen3.6-27B test: smoke Stage A, then
# smoke Stage B, then the main run (BM0021-BM0120, one attempt per slot), with the same automatic gates between them.
# SUBMIT FROM THE REPOSITORY ROOT:   cd <repo copy> && sbatch configs/redhawk/qwen_pipeline.sbatch
#
# WHY ONE JOB. On Redhawk the four V100 nodes were all busy (about 22 hours until the first whole node frees, with a
# backlog behind it). Three separate jobs would each wait in that queue again. One job waits once and then keeps the node.
# The price: nobody reviews the smoke results by hand before the main run. The automatic gates replace that review, and
# they are strict (see below); anything unclear stops the pipeline instead of pressing on.
#
# WHY 24 HOURS. Both smoke stages take under an hour together (weights are re-checked and the model reloaded for each
# stage). The main run is the long part: 100 questions of up to 16,384 tokens each. At about 25 tokens per second (an
# unmeasured estimate) that is at most about 18 hours if every reply hit the cap, usually far less. 24 hours covers that
# with margin and is well inside the partition's 3-day limit.
#
# WHAT IT DOES, IN ORDER (each stage is `serve_and_run.sh`, which does its own checks and its own mandatory validation):
#   1. Stage A: context 20,480, one sequence, development slots BM9001-BM9002. If it fails on INFRASTRUCTURE and the flash-
#      attention setting is "auto" and the server log shows a flash-attention crash, it is retried ONCE with flash attention
#      OFF, and Stages B and main then use "off" too (the gates demand the same setting everywhere). An explicit
#      QT_FA=on or QT_FA=off is never overridden. Any other failure ends the pipeline.
#   2. If every Stage A reply had a model-quality finding, the pipeline stops unless QT_ACK_QUALITY=yes was given when the
#      job was submitted (that pattern usually means a settings problem, so a person must look).
#   3. Stage B: context 40,960, two sequences, slots BM9003-BM9004, only if Stage A left at least 3 GB free on each GPU.
#      If B is not allowed, or fails on infrastructure, the main run uses the tested 20,480 / one-sequence setting instead.
#   4. Before the main run the job checks its remaining time (squeue). Under 6 hours (QT_MIN_MAIN_SECONDS) it does not
#      start the main run: a main run cut off by the time limit would just leave a partial result. It says so, and the main
#      run can be started later with qwen_test.sbatch (which can also RESUME: finished slots are never re-sent).
#   5. The main run, with the setting that passed. Model-quality findings are RESULTS and do not fail the job;
#      infrastructure problems (an incomplete run, bad files, GPU errors) do.
#   6. A summary file, stage_results/pipeline_job<ID>.txt, says which stages ran, which flash-attention mode and which
#      parallelism were used and why, and every stage's result. It is also written if the job is stopped at the limit.
# Exit code 0 only if the main run finished with its infrastructure validation passed.
#
# Optional settings, passed when submitting:  sbatch --export=ALL,QT_ACK_QUALITY=yes,QT_FA=off configs/redhawk/qwen_pipeline.sbatch
set -uo pipefail   # no -e on purpose: a failing stage is handled explicitly below, with its own message
SD="${SLURM_SUBMIT_DIR:-$PWD}/configs/redhawk"
[ -f "$SD/common.sh" ] || { echo "STOP: submit from the repository root (cd <repo>; sbatch configs/redhawk/qwen_pipeline.sbatch)" >&2; exit 2; }
# shellcheck disable=SC1091
source "$SD/common.sh"
require_paths

JOB="${SLURM_JOB_ID:-nojob}"
RESULT_DIR="$QT_OUT/stage_results"; LOGDIR="$QT_OUT/job_logs"
mkdir -p "$RESULT_DIR" "$LOGDIR"
SUMMARY="$RESULT_DIR/pipeline_job${JOB}.txt"
T0="$(date +%s)"
FA="${QT_FA:-auto}"
MIN_MAIN="${QT_MIN_MAIN_SECONDS:-21600}"

PIPE_RESULT="STARTED"; PIPE_REASON=""; FA_FALLBACK="no"; B_STATUS="not reached"; MAIN_SETTING="not decided"; MAIN_STATUS="not started"
res() { if [ -f "$1" ]; then sed -n "s/^$2=//p" "$1" | tail -n 1; fi; }
# shellcheck disable=SC2329  # called through the EXIT trap
write_summary() {
  { echo "PIPELINE_RESULT=$PIPE_RESULT"; echo "REASON=$PIPE_REASON"; echo "JOB=$JOB"; echo "NODE=$(hostname)"
    echo "FA_MODE=$FA"; echo "FA_FALLBACK_USED=$FA_FALLBACK"; echo "MAIN_SETTING=$MAIN_SETTING"; echo "STAGE_B=$B_STATUS"; echo "MAIN=$MAIN_STATUS"
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
trap 'PIPE_RESULT="TERMINATED"; PIPE_REASON="the job received SIGTERM (time limit or scancel); a main run in progress can be resumed with qwen_test.sbatch and QT_RESUME"; exit 143' TERM

run_stage() {  # $1 stage, $2 context, $3 parallel, $4 flash-attention mode, $5 attempt number (may be empty), $6 client timeout (may be empty)
  QT_STAGE="$1" QT_CTX="$2" QT_PARALLEL="$3" QT_FA="$4" QT_ATTEMPT="${5:-}" QT_PY_TIMEOUT="${6:-}" bash "$SD/serve_and_run.sh"
}
passed() {  # $1 = stage result file: PASS or PASS_QUALITY_WARN
  case "$(res "$1" RESULT)" in PASS|PASS_QUALITY_WARN) return 0 ;; *) return 1 ;; esac
}
fa_crash_in_log() {  # a crash that names flash attention (a normal start-up line that merely mentions it does not count)
  [ -f "$1" ] || return 1
  grep -Eiq "GGML_ASSERT|GGML_ABORT|CUDA error|illegal memory" "$1" || return 1
  grep -Eiq "fattn[-a-z0-9_.]*:[0-9]+|in function [a-z_0-9]*(flash_attn|fattn)" "$1"
}

echo "=== pipeline job $JOB on $(hostname), $(date -u +%FT%TZ): flash-attn $FA, minimum time left for the main run ${MIN_MAIN}s ==="

# ---- 1. Stage A (with the single flash-attention retry) -------------------------------------------------------------
echo; echo "######## STAGE A ########"
run_stage A 20480 1 "$FA" "" 35m; RC_A=$?
if [ "$RC_A" -ne 0 ] && [ "$FA" = auto ] && fa_crash_in_log "$LOGDIR/llama_server_${JOB}_A.log"; then
  echo; echo "Stage A crashed in flash attention with -fa auto. Retrying ONCE with flash attention OFF; Stages B and main will use OFF too."
  FA="off"; FA_FALLBACK="yes"
  run_stage A 20480 1 "$FA" 2 35m; RC_A=$?
fi
if [ "$RC_A" -ne 0 ] || ! passed "$RESULT_DIR/stageA.txt"; then
  stop_with "STOPPED_AT_A" "Stage A failed (exit $RC_A, result '$(res "$RESULT_DIR/stageA.txt" REASON)'). Read $LOGDIR/validate_${JOB}_A*.out and $LOGDIR/llama_server_${JOB}_A*.log. Nothing else was run."
fi

# ---- 2. the quality gate ----------------------------------------------------------------------------------------------
if [ "$(res "$RESULT_DIR/stageA.txt" QUALITY_ALL)" = yes ] && [ "${QT_ACK_QUALITY:-}" != yes ]; then
  stop_with "STOPPED_QUALITY" "every Stage A reply had a model-quality finding. Read $LOGDIR/validate_${JOB}_A*.out; if it is understood, resubmit with --export=ALL,QT_ACK_QUALITY=yes"
fi

# ---- 3. Stage B, or the single-sequence fallback ------------------------------------------------------------------------
MAIN_CTX=20480; MAIN_PAR=1
if [ "$(res "$RESULT_DIR/stageA.txt" STAGE_B_ALLOWED)" = yes ]; then
  echo; echo "######## STAGE B ########"
  run_stage B 40960 2 "$FA" "" 35m; RC_B=$?
  if [ "$RC_B" -eq 0 ] && passed "$RESULT_DIR/stageB.txt"; then
    if [ "$(res "$RESULT_DIR/stageB.txt" QUALITY_ALL)" = yes ] && [ "${QT_ACK_QUALITY:-}" != yes ]; then
      stop_with "STOPPED_QUALITY" "every Stage B reply had a model-quality finding. Read $LOGDIR/validate_${JOB}_B.out; resubmit with --export=ALL,QT_ACK_QUALITY=yes if it is understood"
    fi
    MAIN_CTX=40960; MAIN_PAR=2; B_STATUS="passed"
  else
    B_STATUS="failed on infrastructure (exit $RC_B, '$(res "$RESULT_DIR/stageB.txt" REASON)'): falling back to the tested single-sequence setting"
    echo; echo "Stage B did not pass: $B_STATUS"
  fi
else
  B_STATUS="skipped: Stage A left under 3 GB free on a GPU, so two sequences are not allowed"
  echo; echo "$B_STATUS"
fi
MAIN_SETTING="$MAIN_CTX/$MAIN_PAR"

# ---- 4. is there enough time left for the main run? ---------------------------------------------------------------------
LEFT="$(slurm_seconds_left)"
echo; echo "time left in this job: ${LEFT}s (the main run needs at least ${MIN_MAIN}s to be worth starting; -1 = unknown)"
if [ "$LEFT" -ge 0 ] && [ "$LEFT" -lt "$MIN_MAIN" ]; then
  stop_with "STOPPED_TIME" "only ${LEFT}s left, under the ${MIN_MAIN}s minimum. The smoke stages passed (setting $MAIN_SETTING). Start the main run with: sbatch --export=ALL,QT_CTX=$MAIN_CTX,QT_PARALLEL=$MAIN_PAR,QT_FA=$FA configs/redhawk/qwen_test.sbatch"
fi
[ "$LEFT" -ge 0 ] || echo "WARNING: the time left could not be read; starting the main run anyway."

# ---- 5. the main run -----------------------------------------------------------------------------------------------------
echo; echo "######## MAIN RUN ($MAIN_SETTING, flash-attn $FA) ########"
MAIN_STATUS="started"
run_stage main "$MAIN_CTX" "$MAIN_PAR" "$FA" "" ""; RC_M=$?
MAIN_STATUS="exit $RC_M, result $(res "$RESULT_DIR/main_job${JOB}.txt" RESULT)"
if [ "$RC_M" -ne 0 ]; then
  stop_with "MAIN_FAILED" "the main run ended with exit $RC_M ($(res "$RESULT_DIR/main_job${JOB}.txt" REASON)). If it is only incomplete, resume it with qwen_test.sbatch and QT_RESUME=$(res "$RESULT_DIR/main_job${JOB}.txt" RUN_DIR)"
fi
PIPE_RESULT="COMPLETE"; PIPE_REASON="all stages ran; main setting $MAIN_SETTING, flash-attn $FA"
echo; echo "PIPELINE COMPLETE. Summary: $SUMMARY"
exit 0
