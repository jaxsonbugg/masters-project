#!/bin/bash
# fetch_weights.sh - download the pinned 4-bit file and Qwen's chat template, then verify the SHA-256.
# RUN ON A LOGIN NODE BY HAND (network-bound, about 17 GB, done once; it is not a computation). If the probe showed
# that only compute nodes have internet, run it inside a short batch job instead.
#
# STORAGE FIRST. The file is 16.8 GB and the home folder is a shared NFS share that was 81% full. So this script:
#   1. refuses to run until redhawk_models in configs/paths.yaml points at an approved location (not UNSET);
#   2. refuses to put the file under $HOME unless you pass QT_ALLOW_HOME=yes (home is the wrong place by default);
#   3. checks free space on that file system (needs at least 25 GB free: file plus margin);
#   4. prints your quota and stops until you confirm you have read it, with QT_CONFIRM_STORAGE=yes.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_paths

case "$QT_MODELS" in
  "$HOME"|"$HOME"/*) [ "${QT_ALLOW_HOME:-}" = "yes" ] || die "redhawk_models ($QT_MODELS) is inside your home folder. Pick a project or scratch area, or set QT_ALLOW_HOME=yes if Research Computing approved it." ;;
esac
mkdir -p "$QT_MODELS"
NEED_KB=$((25 * 1024 * 1024))
FREE_KB="$(df -Pk "$QT_MODELS" | awk 'NR==2 {print $4}')"
echo "Target: $QT_MODELS"
df -hP "$QT_MODELS" | tail -1
echo "Free: $((FREE_KB / 1024 / 1024)) GB; needed: 25 GB (16.8 GB file plus margin)"
[ "$FREE_KB" -ge "$NEED_KB" ] || die "not enough free space on that file system"
echo "--- quota (whichever command exists) ---"
{ quota -s 2>&1 || true; lfs quota -h -u "$(id -un)" "$QT_MODELS" 2>&1 || true; } | head -12
[ "${QT_CONFIRM_STORAGE:-}" = "yes" ] || die "read the free space and quota above, then run again with QT_CONFIRM_STORAGE=yes. Nothing was downloaded."

[ -x "$QT_BASE_PYTHON" ] || die "no Python at $QT_BASE_PYTHON (see probe_cluster_part2.sh section 1; set QT_BASE_PYTHON to a Python 3.8+ interpreter)"
"$QT_BASE_PYTHON" -c 'import sys, ssl, venv; assert sys.version_info >= (3, 8), sys.version' || die "$QT_BASE_PYTHON is not a Python 3.8+ with venv and ssl"
[ -d "$QT_VENV" ] || "$QT_BASE_PYTHON" -m venv "$QT_VENV"
# shellcheck disable=SC1091
source "$QT_VENV/bin/activate"
pip install --quiet --upgrade pip huggingface_hub httpx pyyaml
HF="$(command -v hf || command -v huggingface-cli || true)"
[ -n "$HF" ] || die "neither 'hf' nor 'huggingface-cli' was installed by pip"

echo "Downloading $GGUF_REPO @ $GGUF_REV : $GGUF_FILE"
"$HF" download "$GGUF_REPO" "$GGUF_FILE" --revision "$GGUF_REV" --local-dir "$QT_MODELS"
echo "Downloading the official chat template ($TEMPLATE_REPO @ $TEMPLATE_REV)"
"$HF" download "$TEMPLATE_REPO" chat_template.jinja --revision "$TEMPLATE_REV" --local-dir "$QT_MODELS/_template_src"
cp "$QT_MODELS/_template_src/chat_template.jinja" "$TEMPLATE_PATH"

ACTUAL_BYTES="$(stat -c %s "$GGUF_PATH")"
ACTUAL_SHA="$(sha256sum "$GGUF_PATH" | cut -d' ' -f1)"
TEMPLATE_SHA="$(sha256sum "$TEMPLATE_PATH" | cut -d' ' -f1)"
echo "bytes    $ACTUAL_BYTES (expected $GGUF_BYTES)"
echo "sha256   $ACTUAL_SHA"
echo "expected $GGUF_SHA256"
echo "chat template sha256 $TEMPLATE_SHA"
if [ "$ACTUAL_BYTES" != "$GGUF_BYTES" ] || [ "$ACTUAL_SHA" != "$GGUF_SHA256" ]; then
  die "CHECKSUM MISMATCH. Do not use this file. Delete it and download again."
fi
echo "$TEMPLATE_SHA" > "$QT_MODELS/chat_template.sha256"
echo "OK: weights verified. Record the template hash above in the run notes."
