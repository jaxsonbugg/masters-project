#!/bin/bash
# fetch_talon.sh - install the pinned vLLM into a Python environment and download the pinned BF16 weights, then VERIFY them.
# Normally started in the background by prep_talon.sh (it writes $QT_ROOT/fetch_talon.log). DRAFT: refuses to run until
# talon_settings.sh has SETTINGS_REVIEWED=yes. Network-bound, about 54 GB, done once. Whether the login node may download this
# much, and whether it has internet at all, is UNVERIFIED (probe_talon.sh section 6 checks the internet; ask Research Computing
# about large downloads). If only compute nodes have internet, run this inside a short CPU batch job instead.
#
# WHAT IT DOES
#   1. Storage first: refuses to run while talon_models is UNSET, refuses a folder under $HOME unless QT_ALLOW_HOME=yes, needs
#      about 80 GB free (54 GB of weights plus margin), prints the quota and stops until QT_CONFIRM_STORAGE=yes says a person read it.
#   2. Creates $QT_VENV from QT_BASE_PYTHON (3.10 or newer) and installs vllm==VLLM_VERSION plus the test client's needs.
#   3. Downloads MODEL_REPO at the pinned COMMIT MODEL_REV into $QT_MODEL_DIR.
#   4. Verifies every large file against the SHA-256 that Hugging Face itself publishes for that commit (and every small file
#      against its published size). Any mismatch or missing file stops it.
#   5. Writes the manifest (sha256 of every file; the job re-checks it before every stage), model_revision.txt and the real
#      total size, then prints "OK: weights verified" (submit_pipeline.sh looks for exactly that line).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_reviewed
require_paths
talon_facts_banner
need QT_BASE_PYTHON; need VLLM_VERSION; need MODEL_REV
[[ "$MODEL_REV" =~ ^[0-9a-f]{40}$ ]] || die "MODEL_REV '$MODEL_REV' is not a 40-character commit hash. Pin a commit, never a branch name such as main."

case "$QT_MODELS" in
  "$HOME"|"$HOME"/*) [ "${QT_ALLOW_HOME:-}" = "yes" ] || die "talon_models ($QT_MODELS) is inside your home folder. Pick a project or scratch area, or set QT_ALLOW_HOME=yes if Research Computing approved it." ;;
esac
mkdir -p "$QT_MODELS"
NEED_GB="${QT_NEED_GB:-80}"
FREE_KB="$(df -Pk "$QT_MODELS" | awk 'NR==2 {print $4}')"
echo "Target: $QT_MODELS"
df -hP "$QT_MODELS" | tail -1
echo "Free: $((FREE_KB / 1024 / 1024)) GB; needed: $NEED_GB GB (about 54 GB of BF16 weights plus margin)"
[ "$FREE_KB" -ge $((NEED_GB * 1024 * 1024)) ] || die "not enough free space on that file system"
echo "--- quota: the 500 GB limit applies to the home file system (OBSERVED 2026-11-06 with: quota -s -v -f /home) ---"
MNT="$(df -P "$QT_MODELS" | awk 'NR==2 {print $6}')"
if [ "$MNT" = /home ]; then
  timeout 60 quota -s -v -f /home 2>&1 | head -12 || true
  Q="$(home_quota_mib /home)"
  if [ "$Q" = UNKNOWN ]; then
    warn "could not read the home quota, so the 500 GB limit cannot be checked here (the file system still enforces it)"
  else
    read -r Q_USED Q_SOFT Q_HARD <<<"$Q"
    NEED_MIB=$((WEIGHTS_MIB + ${QT_ENV_MIB:-25000}))   # the weights plus about 25 GB for the Python environment and caches
    echo "home quota: used $Q_USED MiB, soft limit $Q_SOFT MiB, hard limit $Q_HARD MiB; this setup needs about $NEED_MIB MiB more"
    [ $((Q_USED + NEED_MIB)) -le "$Q_SOFT" ] || die "this download would pass the soft quota of the home folder ($Q_SOFT MiB; $Q_USED MiB used). Free space or ask Research Computing for more. Nothing was downloaded."
  fi
else
  echo "(the target is on $MNT, not /home: the home quota does not apply; no quota command is known for it)"
fi
[ "${QT_CONFIRM_STORAGE:-}" = "yes" ] || die "read the free space and quota above, then run again with QT_CONFIRM_STORAGE=yes. Nothing was downloaded."

echo "== Python environment with vllm==$VLLM_VERSION =="
[ -x "$QT_BASE_PYTHON" ] || die "no Python at $QT_BASE_PYTHON (QT_BASE_PYTHON in talon_settings.sh, from probe_talon.sh)"
"$QT_BASE_PYTHON" -c 'import sys, ssl, venv; assert sys.version_info >= (3, 10), sys.version' || die "$QT_BASE_PYTHON is not a Python 3.10+ with venv and ssl"
[ -d "$QT_VENV" ] || "$QT_BASE_PYTHON" -m venv "$QT_VENV"
# shellcheck disable=SC1091
source "$QT_VENV/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet "vllm==$VLLM_VERSION" huggingface_hub httpx pyyaml
GOT="$(installed_vllm_version || true)"   # package records: `vllm --version` crashes on a login node without a GPU (2026-11-12)
[ "$GOT" = "$VLLM_VERSION" ] || die "pip installed vLLM '$GOT', not the pinned $VLLM_VERSION"
# Record EVERY installed package version (decided 2026-11-12). vLLM is pinned, but pip chooses the versions of what it pulls in
# (PyTorch, transformers, CUDA libraries, ...); this list puts the exact environment on record for the whole project.
FREEZE="$QT_ROOT/venv_pip_freeze.txt"
{ echo "# recorded $(date -u +%FT%TZ); $("$QT_VENV/bin/python" -V 2>&1); vllm $GOT"; pip freeze --all; } > "$FREEZE"
echo "installed packages: $(grep -vc '^#' "$FREEZE") recorded in $FREEZE (sha256 $(sha256sum "$FREEZE" | cut -d' ' -f1))"
grep -iE '^(torch|transformers|vllm)==' "$FREEZE" | sed 's/^/  /' || true
HF="$(command -v hf || command -v huggingface-cli || true)"
[ -n "$HF" ] || die "neither 'hf' nor 'huggingface-cli' was installed by pip"

echo "== downloading $MODEL_REPO @ $MODEL_REV into $QT_MODEL_DIR =="
"$HF" download "$MODEL_REPO" --revision "$MODEL_REV" --local-dir "$QT_MODEL_DIR"

echo "== verifying against the hashes Hugging Face publishes for this commit =="
python - "$MODEL_REPO" "$MODEL_REV" "$QT_MODEL_DIR" <<'PY'
import hashlib, os, sys
from huggingface_hub import HfApi
repo, rev, root = sys.argv[1:4]
info = HfApi().model_info(repo, revision=rev, files_metadata=True)
if info.sha != rev:
    sys.exit(f"STOP: Hugging Face reports commit {info.sha}, not the pinned {rev}")
bad, checked = [], 0
for s in info.siblings:
    path = os.path.join(root, s.rfilename)
    if not os.path.isfile(path):
        bad.append(f"missing: {s.rfilename}")
        continue
    size = os.path.getsize(path)
    if s.size is not None and size != s.size:
        bad.append(f"size {size} != published {s.size}: {s.rfilename}")
        continue
    if s.lfs is not None:                       # large files: compare the full SHA-256 that Hugging Face publishes
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 24), b""):
                h.update(block)
        if h.hexdigest() != s.lfs.sha256:
            bad.append(f"sha256 mismatch: {s.rfilename}")
    checked += 1
if bad:
    print("\n".join(bad))
    sys.exit("STOP: the download does not match the pinned commit. Do not use this folder; delete it and download again.")
print(f"{checked} files match the published sizes; every large file matches its published SHA-256")
PY

( cd "$QT_MODEL_DIR" && find . -type f ! -path './.cache/*' | sed 's|^\./||' | LC_ALL=C sort | xargs -d '\n' sha256sum ) > "$QT_MANIFEST.tmp"
mv "$QT_MANIFEST.tmp" "$QT_MANIFEST"
echo "$MODEL_REV" > "$QT_MODELS/model_revision.txt"
TOTAL_MIB="$(du -sm --exclude=.cache "$QT_MODEL_DIR" | cut -f1)"
echo "$TOTAL_MIB" > "$QT_MODELS/weights_total_mib.txt"
echo "manifest: $QT_MANIFEST ($(wc -l < "$QT_MANIFEST") files, sha256 $(sha256sum "$QT_MANIFEST" | cut -d' ' -f1)); total $TOTAL_MIB MiB"
echo "If $TOTAL_MIB differs much from WEIGHTS_MIB ($WEIGHTS_MIB) in talon_settings.sh, update WEIGHTS_MIB there."
echo "OK: weights verified"
