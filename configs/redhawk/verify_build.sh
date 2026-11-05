#!/bin/bash
# verify_build.sh - check an EXISTING llama-server build and record the result, WITHOUT recompiling. Run on a login node:
#   cd /home/buggjm/masters_project/repo && bash -l configs/redhawk/verify_build.sh
#
# WHY IT EXISTS. The first successful compile (job 2510641) ended with its own flag check failing, because that check ran
# on a CPU node with no NVIDIA driver, where llama-server cannot even start (see run_llama in common.sh). The binary itself
# was fine. Rebuilding would cost another half hour and gain nothing, so this script repeats the check correctly (with the
# gcc and CUDA modules loaded, and the CUDA toolkit's stub driver library standing in for the missing driver) and writes
# $QT_ROOT/build_verified.txt. submit_pipeline.sh accepts that file for THIS binary only: it records the pinned commit and
# the SHA-256 of the binary, so rebuilding or changing the binary invalidates it.
#
# WHAT IT CHECKS: the source commit is the pinned one; llama-server starts and lists every flag the test uses; its own
# version line; and it records the SHA-256 of llama-server and of the GPU library (provenance for the report). It does NOT
# prove the model runs on a V100 (only the GPU smoke test can): it proves the program is the pinned build and has the flags.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_paths
need MOD_CUDA; need MOD_GCC; need MOD_CMAKE
load_modules
BIN="$QT_BUILD/build/bin/llama-server"
[ -x "$BIN" ] || die "llama-server is missing at $BIN: nothing to verify (build it first)."
[ -f "$QT_ROOT/llama_cpp_version.txt" ] || die "llama_cpp_version.txt is missing."
read -r TAG COMMIT < "$QT_ROOT/llama_cpp_version.txt"
[ "$COMMIT" = "$LLAMA_EXPECT_COMMIT" ] || die "the source is at $COMMIT, not the pinned $LLAMA_EXPECT_COMMIT."
echo "== llama-server starts and lists every required flag =="
check_flags "$BIN" || die "verification failed (see above); nothing was recorded."
echo "== its own version line =="
VERSION_LINE="$(run_llama "$BIN" --version | grep -iE "version|build" | head -n 2 | tr '\n' ' ')"
echo "  ${VERSION_LINE:-<none printed>}"
BIN_SHA="$(sha256sum "$BIN" | cut -d' ' -f1)"
CUDA_LIB=""
for f in "$QT_BUILD"/build/bin/libggml-cuda.so.*; do [ -f "$f" ] && { CUDA_LIB="$f"; break; }; done
CUDA_SHA="$([ -n "$CUDA_LIB" ] && sha256sum "$CUDA_LIB" | cut -d' ' -f1)"
{ echo "TAG=$TAG"; echo "COMMIT=$COMMIT"; echo "BIN_SHA256=$BIN_SHA"; echo "CUDA_LIB_SHA256=${CUDA_SHA:-none}"
  echo "FLAGS_OK=yes"; echo "VERSION_LINE=$VERSION_LINE"; echo "MODULES=$MOD_GCC $MOD_CMAKE $MOD_CUDA"
  echo "VERIFIED_UTC=$(date -u +%FT%TZ)"; echo "HOST=$(hostname)"; } > "$QT_ROOT/build_verified.txt"
echo
echo "OK: recorded in $QT_ROOT/build_verified.txt (binary sha256 ${BIN_SHA:0:16}..., GPU library sha256 ${CUDA_SHA:0:16}...)."
echo "Next: cd $QT_REPO && QT_SUBMIT=yes bash -l configs/redhawk/submit_pipeline.sh"
