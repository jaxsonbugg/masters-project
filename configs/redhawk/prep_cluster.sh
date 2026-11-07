#!/bin/bash
# prep_cluster.sh - ALL the login-node preparation for the Qwen3.6-27B test, in one command. Run it ONCE, on a login node,
# from the repository copy, right after the files were copied there:
#   cd /home/buggjm/masters_project/repo && bash -l configs/redhawk/prep_cluster.sh
# (the one-line command that copies the files and then runs this is in docs/clusters/cluster_selection.md and the chat; it needs
# only ONE password + Duo login.)
#
# WHAT IT DOES, IN ORDER (any failure stops it with a plain message; nothing later runs):
#   1. Checks the copied files are intact: no Windows carriage returns, every shell script parses, and the prompt file has
#      the pinned SHA-256 (so the question prompt that reaches the cluster is exactly the one that was tested).
#   2. fetch_source.sh: clones llama.cpp and checks that the pinned tag points at the pinned commit.
#   3. Submits build_llamacpp.sbatch: a CPU batch job (not the GPU queue) that compiles llama.cpp for the V100s.
#   4. Starts fetch_weights.sh in the BACKGROUND (about 17 GB; it survives this login ending): it downloads the pinned
#      GGUF file and Qwen's chat template and verifies the SHA-256. It is given the two confirmations it asks for because
#      the probes already showed what they check: your home quota is 480 GB with 60 KB used (QT_CONFIRM_STORAGE), and the
#      project folder is in your home folder on purpose (QT_ALLOW_HOME).
#   5. Writes $QT_ROOT/prep_state.txt and prints how to watch progress and the next command (submit_pipeline.sh).
# Running it a second time is refused (it would submit a second build job and start a second download) unless
# QT_PREP_AGAIN=yes is set.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_paths

# In the local tests (QT_TEST_MODE=1) the two heavy steps can be replaced by stubs; in real use they are never overridden.
FETCH_SOURCE="$QT_SCRIPT_DIR/fetch_source.sh"; FETCH_WEIGHTS="$QT_SCRIPT_DIR/fetch_weights.sh"
if [ "${QT_TEST_MODE:-}" = "1" ]; then FETCH_SOURCE="${PREP_FETCH_SOURCE:-$FETCH_SOURCE}"; FETCH_WEIGHTS="${PREP_FETCH_WEIGHTS:-$FETCH_WEIGHTS}"; fi
PROMPT_SHA256="348db6ff84da29d22b2fcdeec9c13191df9d828b6af64b61146f2794b1888cc4"   # data/prompts/benchmark_generation_v6.md
STATE="$QT_ROOT/prep_state.txt"

echo "== 0. is this the first run? =="
if [ -f "$STATE" ] && [ "${QT_PREP_AGAIN:-}" != yes ]; then
  die "preparation was already started (see $STATE). A second run would submit a second build job and start a second download. Check progress instead, or set QT_PREP_AGAIN=yes if you really mean to repeat it."
fi

echo "== 1. are the copied files intact? =="
# Only SHELL scripts matter for carriage returns (bash breaks on them; Python does not, and one older Python file in this
# project has Windows line endings). The count uses `tr`, which counts the bytes themselves; `grep` was found to MISS
# carriage returns in some shells (Git Bash) and must not be used for this.
bad=0
for f in "$QT_SCRIPT_DIR"/*.sh "$QT_SCRIPT_DIR"/*.sbatch; do
  if [ "$(tr -cd '\r' < "$f" | wc -c)" -gt 0 ]; then echo "  carriage return (Windows line ending) in $f"; bad=1; fi
  bash -n "$f" || { echo "  syntax error in $f"; bad=1; }
done
[ "$bad" -eq 0 ] || die "some copied files are damaged (see above). Copy them again; nothing was started."
PF="$QT_REPO/data/prompts/benchmark_generation_v6.md"
[ -f "$PF" ] || die "the prompt file $PF is missing; copy data/prompts again. Nothing was started."
[ "$(sha256sum "$PF" | cut -d' ' -f1)" = "$PROMPT_SHA256" ] || die "the prompt file does not have the pinned SHA-256 (it changed in transit?). Nothing was started."
echo "  all scripts parse, no carriage returns, prompt file hash matches the pinned v6 prompt."

echo "== 2. llama.cpp source at the pinned commit =="
bash "$FETCH_SOURCE" || die "fetch_source.sh failed (see above). Nothing else was started."

echo "== 3. submitting the compile job (CPU batch job) =="
cd "$QT_REPO" || die "cannot enter $QT_REPO"
OUT="$(sbatch configs/redhawk/build_llamacpp.sbatch 2>&1)"; echo "  $OUT"
BUILD_JOB="$(awk '/Submitted batch job/ {print $NF}' <<<"$OUT" | tail -n 1)"
[ -n "$BUILD_JOB" ] || die "sbatch did not report a job number, so the compile job was not submitted. The weights download was NOT started either."

echo "== 4. starting the 17 GB weights download in the background =="
START_UTC="$(date -u +%FT%TZ)"
# `setsid` (when present) puts the download in its own session so it survives this login ending; nohup alone also does.
if command -v setsid >/dev/null 2>&1; then
  QT_ALLOW_HOME=yes QT_CONFIRM_STORAGE=yes setsid nohup bash "$FETCH_WEIGHTS" > "$QT_ROOT/fetch_weights.log" 2>&1 < /dev/null &
else
  QT_ALLOW_HOME=yes QT_CONFIRM_STORAGE=yes nohup bash "$FETCH_WEIGHTS" > "$QT_ROOT/fetch_weights.log" 2>&1 < /dev/null &
fi
echo "  started; it writes to $QT_ROOT/fetch_weights.log"

{ echo "PREP_STARTED_UTC=$START_UTC"; echo "BUILD_JOB=$BUILD_JOB"; echo "REPO=$QT_REPO"; echo "WEIGHTS_LOG=$QT_ROOT/fetch_weights.log"; } > "$STATE"

echo
echo "== 5. what to do now =="
echo "  Watch the compile job:   squeue -u $(id -un)            (gone from the list = finished; then read qt_build_${BUILD_JOB}.log, it must end with BUILD OK)"
echo "  Watch the download:      tail -n 5 $QT_ROOT/fetch_weights.log      (it must end with: OK: weights verified)"
echo "  When BOTH are done:      cd $QT_REPO && QT_SUBMIT=yes bash configs/redhawk/submit_pipeline.sh"
echo "                           (it re-checks everything first and refuses to submit if anything is wrong)"
