#!/bin/bash
# submit_pipeline.sh (Talon) - check that everything is ready, then submit ONE Talon job. Run it on a login node:
#   cd <repo copy> && GPU_COUNT=2 TENSOR_PARALLEL=2 REPLICAS=1 MAX_NUM_SEQS=8 CLIENT_CONCURRENCY=8 QT_SUBMIT=yes bash configs/talon/submit_pipeline.sh <kind>
# (the numbers are placeholders for the layout you chose; there is no preferred default)
# <kind> is one of: smoke_a | smoke_b | throughput | pipeline | main   (default: pipeline)
# Without QT_SUBMIT=yes it only does the checks and the scheduler's start estimate (sbatch --test-only: no job is created).
#
# WHY THIS SCRIPT EXISTS. #SBATCH lines in a script cannot hold variables, and nothing about Talon's partition, account, GPU
# request syntax or time limits is known yet. So this script builds the sbatch options from talon_settings.sh (build_sbatch_opts in
# common.sh) and passes the GPU layout through the environment. Everything the job needs is verified BEFORE the job is queued,
# so a job that starts and dies in its first minute does not waste a queue wait:
#   0. the settings were reviewed by a person (SETTINGS_REVIEWED=yes in talon_settings.sh) and the layout values agree;
#   1. the preparation (prep_talon.sh) was started from this repository copy and the download ended with "OK: weights verified";
#   2. the first-login probe recorded its result ($QT_REPO/talon_verified.txt: written by probe_talon_part2.sh) and the GPU
#      request style in the settings is one the scheduler accepted there;
#   3. the weights folder, the pinned revision and the vLLM install exist;
#   4. no job of the same kind of yours is already waiting (a second one would only compete with the first);
#   5. the scheduler accepts the request (sbatch --test-only) and its estimated start is shown.
# Optional settings are passed through the environment to the job: QT_ACK_QUALITY=yes, QT_RESUME=<run folder>, QT_RETRY_ERRORS=yes,
# QT_BREAK_LOCK=yes, QT_MIN_MAIN_SECONDS=<n>, SWEEP_CONCURRENCY="1 4 8 16", MAX_MODEL_LEN=<n>.
# DRAFT: written before any Talon login. Whether `sbatch --test-only` prints "to start at" on Talon is UNVERIFIED.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
KIND="${1:-pipeline}"
ok() { echo "  OK   $1"; }
case "$KIND" in
  smoke_a)    WRAPPER=talon_smoke_a.sbatch;    JOBNAME=qt_talon_A;        TKIND=smoke ;;
  smoke_b)    WRAPPER=talon_smoke_b.sbatch;    JOBNAME=qt_talon_B;        TKIND=smoke ;;
  throughput) WRAPPER=talon_throughput.sbatch; JOBNAME=qt_talon_T;        TKIND=throughput ;;
  pipeline)   WRAPPER=talon_pipeline.sbatch;   JOBNAME=qt_talon_pipeline; TKIND=pipeline ;;
  main)       WRAPPER=talon_test.sbatch;       JOBNAME=qt_talon_main;     TKIND=main ;;
  *) die "unknown kind '$KIND' (use smoke_a, smoke_b, throughput, pipeline or main)" ;;
esac

echo "== 0. settings reviewed, paths, layout =="
require_reviewed
require_paths
talon_facts_banner
check_layout
case "$KIND" in smoke_b|pipeline|main) check_concurrency ;; esac
need VLLM_VERSION; need MODEL_REV
ok "settings reviewed by a person; layout: $GPU_COUNT GPU(s) = tensor parallel $TENSOR_PARALLEL x replicas $REPLICAS; max length $MAX_MODEL_LEN"

echo "== 1. preparation state =="
STATE="$QT_ROOT/prep_state.txt"
[ -f "$STATE" ] || die "$STATE is missing: run prep_talon.sh first."
[ "$(sed -n 's/^REPO=//p' "$STATE" | tail -n 1)" = "$QT_REPO" ] || die "this repository copy ($QT_REPO) is not the one that was prepared."
FLOG="$QT_ROOT/fetch_talon.log"
[ -f "$FLOG" ] || die "no download log $FLOG: the download never started."
grep -q "OK: weights verified" "$FLOG" || die "the download has not finished or failed (last lines below). Wait, or read the log.
$(tail -n 4 "$FLOG")"
ok "preparation started from this copy; the download log ends with OK: weights verified"

echo "== 2. the first-login probe =="
VER="$QT_REPO/talon_verified.txt"
[ -f "$VER" ] || die "$VER is missing: probe_talon_part2.sh has not recorded a successful probe job (it proves the GPU request syntax)."
grep -q '^PART2_OK=yes' "$VER" || die "$VER does not say PART2_OK=yes."
ACCEPTED="$(sed -n 's/^GPU_STYLES_ACCEPTED=//p' "$VER" | tail -n 1)"
case " $ACCEPTED " in *" $TALON_GPU_STYLE "*) ok "the scheduler accepted the GPU request style '$TALON_GPU_STYLE' (accepted: $ACCEPTED)" ;;
  *) die "TALON_GPU_STYLE is '$TALON_GPU_STYLE' but the probe recorded these accepted styles: '$ACCEPTED'." ;; esac

echo "== 3. weights and engine on disk =="
[ -f "$QT_MODEL_DIR/config.json" ] || die "$QT_MODEL_DIR/config.json is missing."
[ "$(cat "$QT_MODELS/model_revision.txt" 2>/dev/null || true)" = "$MODEL_REV" ] || die "the downloaded revision is not the pinned MODEL_REV ($MODEL_REV)."
[ -f "$QT_MANIFEST" ] || die "the weights manifest $QT_MANIFEST is missing."
[ -x "$QT_VENV/bin/vllm" ] || die "vllm is not installed at $QT_VENV/bin/vllm."
ok "model folder, pinned revision, manifest and vllm are present (the job itself re-hashes the weights and checks the vLLM version)"

echo "== 4. no job of the same kind already waiting =="
if [ -n "$(squeue -h -u "$(id -un)" -n "$JOBNAME" 2>/dev/null)" ]; then die "a $JOBNAME job of yours is already in the queue. A second one would only compete with it."; fi
ok "none"

echo "== 5. the scheduler's verdict (sbatch --test-only: no job is created) =="
cd "$QT_REPO" || die "cannot enter $QT_REPO"
build_sbatch_opts "$TKIND"
echo "  sbatch options built from the settings: ${SB_OPTS[*]}"
TEST="$(sbatch --test-only "${SB_OPTS[@]}" "configs/talon/$WRAPPER" 2>&1)"; echo "  $TEST"
grep -q "to start at" <<<"$TEST" || die "the scheduler did not accept the request (see above)."
ok "accepted"

if [ "${QT_SUBMIT:-}" != yes ]; then
  echo; echo "All checks passed. Nothing was submitted (QT_SUBMIT=yes was not set). To submit, run the same command with QT_SUBMIT=yes."
  exit 0
fi

echo "== 6. submitting the $KIND job =="
OUT="$(sbatch "${SB_OPTS[@]}" "configs/talon/$WRAPPER" 2>&1)"; echo "  $OUT"
JOB="$(awk '/Submitted batch job/ {print $NF}' <<<"$OUT" | tail -n 1)"
[ -n "$JOB" ] || die "sbatch did not report a job number: the $KIND job was NOT submitted."
{ echo "JOB=$JOB KIND=$KIND SUBMITTED_UTC=$(date -u +%FT%TZ) LAYOUT=$GPU_COUNT/$TENSOR_PARALLEL/$REPLICAS/$MAX_NUM_SEQS/${CLIENT_CONCURRENCY:-none}/$MAX_MODEL_LEN"; } >> "$QT_ROOT/submit_log.txt"
echo
echo "Submitted $KIND job $JOB. It is now in line; the PC can be off and the VPN can be disconnected."
echo "  Where it stands:     squeue -j $JOB -o '%i %T %r %S'        (STATE, REASON, estimated start)"
echo "  Full details:        scontrol show job $JOB"
echo "  Cancel (if needed):  scancel $JOB"
echo "  When it runs, its log is $QT_REPO/${JOBNAME}_$JOB.log and its result files are in $QT_OUT/stage_results"
