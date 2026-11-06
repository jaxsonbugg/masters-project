#!/bin/bash
# prep_talon.sh - ALL the login-node preparation for the Talon side of the Qwen3.6-27B test, in one command. Run it ONCE, on a
# login node, from the repository copy, right after the files were copied there:
#   cd <repo copy> && QT_CONFIRM_STORAGE=yes bash -l configs/talon/prep_talon.sh
# DRAFT: refuses to run until talon_settings.sh has SETTINGS_REVIEWED=yes (the probe values must be in first).
#
# WHAT IT DOES, IN ORDER (any failure stops it with a plain message; nothing later runs):
#   1. Checks the copied files are intact: no Windows carriage returns, every Talon shell script parses, and the prompt file has
#      the pinned SHA-256 (so the question prompt that reaches the cluster is exactly the one that was tested).
#   2. Starts fetch_talon.sh in the BACKGROUND (it survives this login ending): it installs the pinned vLLM, downloads the pinned
#      BF16 weights (about 54 GB) and verifies them. Unlike the Redhawk prep, the storage confirmations are NOT given
#      automatically: Talon's storage rules are UNVERIFIED, so you pass QT_CONFIRM_STORAGE=yes yourself (and QT_ALLOW_HOME=yes only
#      if Research Computing approved using your home folder) after reading the probe's storage section.
#   3. Writes $QT_ROOT/prep_state.txt and prints how to watch progress and the next command.
# There is no compile step: vLLM is installed by pip (or later from a container), not built from source.
# Running it a second time is refused (it would start a second download) unless QT_PREP_AGAIN=yes is set.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_reviewed
require_paths
talon_facts_banner
need QT_BASE_PYTHON; need VLLM_VERSION; need MODEL_REV

# In the local tests (QT_TEST_MODE=1) the download can be replaced by a stub; in real use it is never overridden.
FETCH="$QT_SCRIPT_DIR/fetch_talon.sh"
if [ "${QT_TEST_MODE:-}" = "1" ]; then FETCH="${PREP_FETCH:-$FETCH}"; fi
PROMPT_SHA256="348db6ff84da29d22b2fcdeec9c13191df9d828b6af64b61146f2794b1888cc4"   # data/prompts/benchmark_generation_v6.md
STATE="$QT_ROOT/prep_state.txt"

echo "== 0. is this the first run? =="
mkdir -p "$QT_ROOT" || die "cannot create $QT_ROOT"
if [ -f "$STATE" ] && [ "${QT_PREP_AGAIN:-}" != yes ]; then
  die "preparation was already started (see $STATE). A second run would start a second download. Check progress instead, or set QT_PREP_AGAIN=yes if you really mean to repeat it."
fi

echo "== 1. are the copied files intact? =="
# The count uses `tr`, which counts the bytes themselves; `grep` was found to MISS carriage returns in some shells (Git Bash).
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
[ "${QT_CONFIRM_STORAGE:-}" = yes ] || die "Talon's storage rules are UNVERIFIED: read the storage section of the probe output, then run again with QT_CONFIRM_STORAGE=yes. Nothing was started."

echo "== 2. starting the vLLM install and the 54 GB weights download in the background =="
START_UTC="$(date -u +%FT%TZ)"
# `setsid` (when present) puts the download in its own session so it survives this login ending; nohup alone also does.
if command -v setsid >/dev/null 2>&1; then
  QT_CONFIRM_STORAGE=yes setsid nohup bash "$FETCH" > "$QT_ROOT/fetch_talon.log" 2>&1 < /dev/null &
else
  QT_CONFIRM_STORAGE=yes nohup bash "$FETCH" > "$QT_ROOT/fetch_talon.log" 2>&1 < /dev/null &
fi
echo "  started; it writes to $QT_ROOT/fetch_talon.log"
{ echo "PREP_STARTED_UTC=$START_UTC"; echo "REPO=$QT_REPO"; echo "FETCH_LOG=$QT_ROOT/fetch_talon.log"
  echo "VLLM_VERSION=$VLLM_VERSION"; echo "MODEL_REPO=$MODEL_REPO"; echo "MODEL_REV=$MODEL_REV"; } > "$STATE"

echo
echo "== 3. what to do now =="
echo "  Watch the download:  tail -n 5 $QT_ROOT/fetch_talon.log      (it must end with: OK: weights verified)"
echo "  When it is done:     cd $QT_REPO && <layout settings> bash configs/talon/submit_pipeline.sh smoke_a"
echo "                       (it re-checks everything first and refuses to submit if anything is wrong; add QT_SUBMIT=yes to submit)"
