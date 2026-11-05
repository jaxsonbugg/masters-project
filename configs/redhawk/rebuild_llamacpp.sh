#!/bin/bash
# rebuild_llamacpp.sh - submit the compile job AGAIN (for example after fixing build_llamacpp.sbatch) and record the new job
# number, so that submit_pipeline.sh checks the NEW build log and not the failed one. Run on a login node:
#   cd /home/buggjm/masters_project/repo && bash -l configs/redhawk/rebuild_llamacpp.sh
# It only submits the CPU compile job (build_llamacpp.sbatch); it does not touch the weights, the download or the GPU queue.
# The state file is only ever appended to: the last BUILD_JOB line is the current one (submit_pipeline.sh reads the last).
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_paths
STATE="$QT_ROOT/prep_state.txt"
[ -f "$STATE" ] || die "$STATE is missing: run prep_cluster.sh first (this script only repeats the compile step)."
OLD="$(sed -n 's/^BUILD_JOB=//p' "$STATE" | tail -n 1)"
if [ -n "$OLD" ] && [ -n "$(squeue -h -j "$OLD" 2>/dev/null)" ]; then
  die "the previous compile job $OLD is still queued or running. Wait for it, or cancel it with: scancel $OLD"
fi
# The file the compile job runs must itself be intact (no Windows line endings, parses) before it is submitted.
for f in "$QT_SCRIPT_DIR/build_llamacpp.sbatch" "$QT_SCRIPT_DIR/common.sh"; do
  [ "$(tr -cd '\r' < "$f" | wc -c)" -eq 0 ] || die "$f contains carriage returns (Windows line endings): copy it again."
  bash -n "$f" || die "$f has a syntax error: copy it again."
done
cd "$QT_REPO" || die "cannot enter $QT_REPO"
OUT="$(sbatch configs/redhawk/build_llamacpp.sbatch 2>&1)"; echo "  $OUT"
JOB="$(awk '/Submitted batch job/ {print $NF}' <<<"$OUT" | tail -n 1)"
[ -n "$JOB" ] || die "sbatch did not report a job number: the compile job was NOT submitted."
{ echo "BUILD_JOB=$JOB"; echo "REBUILD_SUBMITTED_UTC=$(date -u +%FT%TZ)"; echo "REBUILD_REPLACES=$OLD"; } >> "$STATE"
echo
echo "Compile job $JOB submitted (it replaces $OLD). Watch it:  squeue -u $(id -un)"
echo "When it has left the queue, its log is $QT_REPO/qt_build_${JOB}.log and must end with BUILD OK. Then run submit_pipeline.sh."
