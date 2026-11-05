#!/bin/bash
# submit_pipeline.sh - check that the preparation really finished, then submit qwen_pipeline.sbatch. Run on a login node:
#   cd /home/buggjm/masters_project/repo && QT_SUBMIT=yes bash -l configs/redhawk/submit_pipeline.sh
# Without QT_SUBMIT=yes it only does the checks and the scheduler's start estimate (sbatch --test-only: no job is created).
#
# WHY CHECK FIRST: under first-come-first-served scheduling the job's place in the queue is worth keeping, so a job that
# starts days from now and then dies in its first minute (no weights, no binary) would waste it. Everything the job needs
# is therefore verified here, before it is submitted:
#   1. the preparation was started and this repository copy is the one that was prepared;
#   2. the compile job has left the queue and the build finished with BUILD OK: binary present, version file present;
#   3. the weights download finished with "OK: weights verified" and the file has the pinned size;
#   4. no pipeline job of yours is already waiting (a second one would just compete with the first);
#   5. the scheduler accepts the request (sbatch --test-only), and its estimated start is shown.
# Optional settings are passed through to the job: QT_ACK_QUALITY=yes, QT_FA=<auto|on|off>, QT_MIN_MAIN_SECONDS=<n>.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_paths
STATE="$QT_ROOT/prep_state.txt"
ok() { echo "  OK   $1"; }

echo "== 1. preparation state =="
[ -f "$STATE" ] || die "$STATE is missing: run prep_cluster.sh first."
BUILD_JOB="$(sed -n 's/^BUILD_JOB=//p' "$STATE" | tail -n 1)"
[ "$(sed -n 's/^REPO=//p' "$STATE" | tail -n 1)" = "$QT_REPO" ] || die "this repository copy ($QT_REPO) is not the one that was prepared."
ok "preparation was started (build job $BUILD_JOB)"

echo "== 2. the compile job and the binary =="
load_modules   # gcc's libstdc++ and the CUDA libraries are needed just to run llama-server --help
if [ -n "$(squeue -h -j "$BUILD_JOB" 2>/dev/null)" ]; then die "the compile job $BUILD_JOB is still in the queue or running. Wait for it to leave 'squeue -u $(id -un)'."; fi
BIN="$QT_BUILD/build/bin/llama-server"
[ -x "$BIN" ] || die "llama-server is missing at $BIN."
# The build counts as good if its own log ends with BUILD OK, OR if verify_build.sh has recorded a verification of THIS very
# binary (same commit, same SHA-256). The second route exists because the first compile's own check ran on a CPU node
# without a GPU driver and failed although the binary was fine (see docs/cluster_selection.md).
BLOG="$QT_REPO/qt_build_${BUILD_JOB}.log"; VER="$QT_ROOT/build_verified.txt"
if [ -f "$BLOG" ] && grep -q "BUILD OK" "$BLOG"; then
  ok "the build log ends with BUILD OK"
elif [ -f "$VER" ] && [ "$(sed -n 's/^COMMIT=//p' "$VER" | tail -n 1)" = "$LLAMA_EXPECT_COMMIT" ] \
     && [ "$(sed -n 's/^BIN_SHA256=//p' "$VER" | tail -n 1)" = "$(sha256sum "$BIN" | cut -d' ' -f1)" ]; then
  ok "verify_build.sh verified this exact binary on $(sed -n 's/^VERIFIED_UTC=//p' "$VER" | tail -n 1)"
elif [ ! -f "$BLOG" ]; then
  die "no build log $BLOG: the compile job did not run. Look at 'squeue' and the job's output file."
else
  die "the build log does not end with BUILD OK ($BLOG) and there is no verification of the current binary. Read the log; if the build itself succeeded run: bash -l configs/redhawk/verify_build.sh"
fi
[ -f "$QT_ROOT/llama_cpp_version.txt" ] || die "llama_cpp_version.txt is missing."
read -r TAG COMMIT < "$QT_ROOT/llama_cpp_version.txt"
[ "$COMMIT" = "$LLAMA_EXPECT_COMMIT" ] || die "the built commit $COMMIT is not the pinned $LLAMA_EXPECT_COMMIT."
check_flags "$QT_BUILD/build/bin/llama-server" || die "the built llama-server lacks a flag the test needs."
ok "llama-server $TAG ($COMMIT) is built and lists every required flag"

echo "== 3. the weights =="
WLOG="$QT_ROOT/fetch_weights.log"
[ -f "$WLOG" ] || die "no download log $WLOG: the download never started."
grep -q "OK: weights verified" "$WLOG" || die "the download has not finished or failed (last lines below). Wait, or read the log.
$(tail -n 4 "$WLOG")"
[ "$(stat -c %s "$GGUF_PATH")" = "$GGUF_BYTES" ] || die "the weights file has the wrong size."
[ -f "$QT_MODELS/chat_template.sha256" ] || die "the chat template hash file is missing."
ok "weights verified by the download script and the file has the pinned size"

echo "== 4. no pipeline job of yours already waiting =="
if [ -n "$(squeue -h -u "$(id -un)" -n qt_pipeline 2>/dev/null)" ]; then die "a qt_pipeline job of yours is already in the queue. A second one would only compete with it."; fi
ok "none"

echo "== 5. the scheduler's verdict (sbatch --test-only: no job is created) =="
cd "$QT_REPO" || die "cannot enter $QT_REPO"
TEST="$(sbatch --test-only configs/redhawk/qwen_pipeline.sbatch 2>&1)"; echo "  $TEST"
grep -q "to start at" <<<"$TEST" || die "the scheduler did not accept the request (see above)."
ok "accepted"

if [ "${QT_SUBMIT:-}" != yes ]; then
  echo; echo "All checks passed. Nothing was submitted (QT_SUBMIT=yes was not set). To submit:"
  echo "  cd $QT_REPO && QT_SUBMIT=yes bash -l configs/redhawk/submit_pipeline.sh"
  exit 0
fi

echo "== 6. submitting the pipeline job =="
EXPORTS="ALL"
for v in QT_ACK_QUALITY QT_FA QT_MIN_MAIN_SECONDS; do
  if [ -n "${!v:-}" ]; then EXPORTS="$EXPORTS,$v=${!v}"; fi
done
OUT="$(sbatch --export="$EXPORTS" configs/redhawk/qwen_pipeline.sbatch 2>&1)"; echo "  $OUT"
JOB="$(awk '/Submitted batch job/ {print $NF}' <<<"$OUT" | tail -n 1)"
[ -n "$JOB" ] || die "sbatch did not report a job number: the pipeline was NOT submitted."
{ echo "PIPELINE_JOB=$JOB"; echo "SUBMITTED_UTC=$(date -u +%FT%TZ)"; echo "EXPORTS=$EXPORTS"; } >> "$STATE"
echo
echo "Submitted pipeline job $JOB. It is now in line; the PC can be off and the VPN can be disconnected."
echo "  Where it stands:     squeue -j $JOB -o '%i %T %r %S'        (STATE, REASON, estimated start)"
echo "  Full details:        scontrol show job $JOB"
echo "  Cancel (if needed):  scancel $JOB"
echo "  When it runs, its log is $QT_REPO/qt_pipeline_$JOB.log and its summary is $QT_OUT/stage_results/pipeline_job$JOB.txt"
