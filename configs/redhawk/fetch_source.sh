#!/bin/bash
# fetch_source.sh - download the llama.cpp source at the pinned release and check the commit.
# RUN ON A LOGIN NODE BY HAND. It only needs the network and a little disk (the source is under 100 MB); it is not a
# computation. The compile itself happens later in a batch job (build_llamacpp.sbatch), because compiling needs
# significant CPU time and Miami asks that heavy work not run on the login node.
# Compute nodes may have no internet, which is why the clone happens here and the build job never uses the network.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_paths
command -v git >/dev/null || die "git is not available on this node"
mkdir -p "$QT_ROOT"
if [ ! -d "$QT_BUILD/.git" ]; then
  git clone https://github.com/ggml-org/llama.cpp "$QT_BUILD"
fi
cd "$QT_BUILD"
git fetch --tags --quiet
git checkout --quiet "$LLAMA_TAG"
COMMIT="$(git rev-parse HEAD)"
echo "tag $LLAMA_TAG resolves to commit $COMMIT"
echo "expected                      $LLAMA_EXPECT_COMMIT"
if [ "$COMMIT" != "$LLAMA_EXPECT_COMMIT" ]; then
  die "the tag does not point at the commit recorded in common.sh. Do not build. Check https://github.com/ggml-org/llama.cpp/releases/tag/$LLAMA_TAG and update LLAMA_EXPECT_COMMIT deliberately (and log the change)."
fi
printf '%s %s\n' "$LLAMA_TAG" "$COMMIT" > "$QT_ROOT/llama_cpp_version.txt"
echo "OK: source is at the pinned commit. Next: sbatch configs/redhawk/build_llamacpp.sbatch (from the repository root)."
