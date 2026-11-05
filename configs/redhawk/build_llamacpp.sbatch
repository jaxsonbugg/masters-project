#!/bin/bash
#SBATCH --job-name=qt_build
#SBATCH --partition=batch
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=01:30:00
#SBATCH --output=%x_%j.log
# build_llamacpp.sbatch - compile llama.cpp for the V100 (compute capability 7.0) with a CUDA 12.x toolkit.
# SUBMIT FROM THE REPOSITORY ROOT:   cd <repo copy> && sbatch configs/redhawk/build_llamacpp.sbatch
# It is a batch job (not run on the login node) because compiling needs significant CPU time. It uses NO network:
# the source was fetched on the login node by fetch_source.sh.
# nvcc compiles for sm_70 without a GPU being present. If linking fails for lack of the CUDA driver library on a
# `batch` node, rerun with:  sbatch --partition=gpu --nodes=1 --exclusive --exclude=mualhpcp50.mpi configs/redhawk/build_llamacpp.sbatch
set -euo pipefail
SD="${SLURM_SUBMIT_DIR:-$PWD}/configs/redhawk"
[ -f "$SD/common.sh" ] || { echo "STOP: submit from the repository root (cd <repo>; sbatch configs/redhawk/build_llamacpp.sbatch)" >&2; exit 2; }
source "$SD/common.sh"
trap 'echo "ERROR at line $LINENO: $BASH_COMMAND" >&2' ERR
require_paths
need MOD_CUDA; need MOD_GCC; need MOD_CMAKE
load_modules
echo "== toolchain =="; nvcc --version | tail -2; gcc --version | head -1; cmake --version | head -1
nvcc --version | grep -qE "release 12\." || die "the CUDA toolkit is not 12.x (CUDA 13 dropped the V100). Use a CUDA 12 module."
[ -d "$QT_BUILD/.git" ] || die "$QT_BUILD is missing: run fetch_source.sh on a login node first"
[ -f "$QT_ROOT/llama_cpp_version.txt" ] || die "llama_cpp_version.txt missing: run fetch_source.sh first"
cd "$QT_BUILD"
COMMIT="$(git rev-parse HEAD)"
[ "$COMMIT" = "$LLAMA_EXPECT_COMMIT" ] || die "source is at $COMMIT, not the pinned $LLAMA_EXPECT_COMMIT. Do not build; rerun fetch_source.sh."

# WHICH COMPILERS (found the hard way, job 2510636): CMake looks for a C compiler called `cc`. The gcc-12.2.0 module provides
# `gcc` and `g++` but no `cc`, so CMake silently used the system's /usr/bin/cc, which is gcc 4.8.5 from 2015 and has no
# <stdatomic.h>, and the C part of the build failed. So the compilers are named explicitly, and the build is refused unless
# BOTH report 12.2.x (the version CUDA 12.2 supports as host compiler).
GCC_BIN="$(command -v gcc)"; GXX_BIN="$(command -v g++)"
[ -n "$GCC_BIN" ] && [ -n "$GXX_BIN" ] || die "gcc or g++ is not on PATH after loading $MOD_GCC"
for c in "$GCC_BIN" "$GXX_BIN"; do
  "$c" --version | head -n 1 | grep -qE "[^0-9]12\.2\." || die "$c is not gcc 12.2 ($("$c" --version | head -n 1)); the $MOD_GCC module did not take effect"
done
echo "compilers: C=$GCC_BIN  C++=$GXX_BIN  ($("$GCC_BIN" --version | head -n 1))"

# A fresh build folder every time: a failed or half-finished one remembers the compiler it was configured with (and the
# shared file system's clock skew can make make skip files it thinks are up to date).
rm -rf "$QT_BUILD/build"
echo "== building llama.cpp $LLAMA_TAG ($COMMIT) for sm_70 =="
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=70 -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_C_COMPILER="$GCC_BIN" -DCMAKE_CXX_COMPILER="$GXX_BIN" -DCMAKE_CUDA_HOST_COMPILER="$GXX_BIN"
# Prove CMake kept those compilers instead of substituting its own.
CACHED_C="$(sed -n 's/^CMAKE_C_COMPILER:[A-Z]*=//p' build/CMakeCache.txt | head -n 1)"
[ "$CACHED_C" = "$GCC_BIN" ] || die "CMake configured with C compiler '$CACHED_C', not '$GCC_BIN'. Not building."
echo "CMake C compiler: $CACHED_C"
cmake --build build -j "${SLURM_CPUS_PER_TASK:-8}" --target llama-server
BIN="$QT_BUILD/build/bin/llama-server"
[ -x "$BIN" ] || die "build finished but $BIN is missing"
{ echo "tag $LLAMA_TAG commit $COMMIT"; nvcc --version | tail -1; gcc --version | head -1; cmake --version | head -1; date -u +%FT%TZ; } > "$QT_ROOT/build_info.txt"
echo "== the built binary must list every flag this test uses =="
check_flags "$BIN"
echo "BUILD OK ($BIN). Next: the GPU smoke test, Stage A."
