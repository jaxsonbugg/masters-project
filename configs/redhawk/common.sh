# shellcheck shell=bash
# common.sh - settings and helpers shared by the Redhawk scripts for the Qwen3.6-27B test. It is SOURCED, not run.
#
# WHERE PATHS COME FROM: configs/paths.yaml is the single source of truth (redhawk_root, redhawk_models, redhawk_outputs).
# They are UNSET until you have run probe_cluster.sh, read the free-space and quota output, and chosen an approved
# project or scratch location. Every script stops with a clear message while a path is UNSET.
#
# EVERYTHING PINNED BELOW IS ALSO WRITTEN INTO THE RUN LOGS, so a result can always be traced to exact files.

# This file's own folder, and the repository copy it belongs to (works under Slurm, where the batch script itself is
# copied to a spool folder but this file is sourced from its real place).
QT_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QT_REPO="$(cd "$QT_SCRIPT_DIR/../.." && pwd)"
QT_CONF="$QT_REPO/configs/paths.yaml"
export QT_SCRIPT_DIR QT_REPO QT_CONF

die() { echo "STOP: $*" >&2; exit 2; }
warn() { echo "WARNING: $*" >&2; }

yaml_get() {  # value of a top-level "key: value" line of paths.yaml, without trailing spaces
  sed -n "s/^$1: *//p" "$QT_CONF" | head -n 1 | sed 's/[[:space:]]*$//'
}

require_paths() {
  [ -f "$QT_CONF" ] || die "$QT_CONF not found (is this the repository copy?)"
  QT_ROOT="$(yaml_get redhawk_root)"
  QT_MODELS="$(yaml_get redhawk_models)"
  QT_OUT="$(yaml_get redhawk_outputs)"
  for v in QT_ROOT QT_MODELS QT_OUT; do
    val="${!v}"
    if [ -z "$val" ] || [ "$(echo "$val" | tr '[:lower:]' '[:upper:]')" = "UNSET" ]; then
      die "$v is UNSET in $QT_CONF. Run probe_cluster.sh, pick an approved project or scratch folder, and set redhawk_root, redhawk_repo, redhawk_models and redhawk_outputs there."
    fi
  done
  export QT_ROOT QT_MODELS QT_OUT
  export QT_BUILD="$QT_ROOT/llama.cpp"      # llama.cpp source and build
  export QT_VENV="$QT_ROOT/venv"            # Python environment for the test client
  export GGUF_PATH="$QT_MODELS/$GGUF_FILE"
  export TEMPLATE_PATH="$QT_MODELS/qwen3.6-27b_chat_template.jinja"
}

# --- llama.cpp: a release TAG plus the commit it must resolve to (GitHub release API, read 2026-11-04) -------------
export LLAMA_TAG="b11960"                                            # released 2026-10-28
export LLAMA_EXPECT_COMMIT="8642541b255bfb5dc39cd351a178be09013a55d6"
# The only V100 evidence found (Atlas3D, 2026-10-20) used commit f74e2fa6a31cc33ab4ee4ae516641cfe62df3924 plus a patch
# for a flash-attention dispatch crash that was NOT confirmed upstream. If the smoke test crashes in flash attention,
# the contingency ladder in recovery/redhawk_qwen_test.md is: (1) QT_FA=off, (2) that commit with the patch.

# --- the 4-bit weights: pinned commit and SHA-256 (Hugging Face API, read 2026-11-04) -----------------------------
export GGUF_REPO="unsloth/Qwen3.6-27B-GGUF"
export GGUF_REV="82d411acf4a06cfb8d9b073a5211bf410bfc29bf"
export GGUF_FILE="Qwen3.6-27B-Q4_K_M.gguf"
export GGUF_BYTES="16817244384"
export GGUF_SHA256="5ed60d0af4650a854b1755bd392f9aef4872643dc25a254bc68043fa638392a0"
# --- Qwen's own chat template, so the template does not come from the third-party GGUF -----------------------------
export TEMPLATE_REPO="Qwen/Qwen3.6-27B"
export TEMPLATE_REV="6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"

# TEST MODE (used only by the local dry-run tests with fake programs): lets the pins be overridden by the environment.
if [ "${QT_TEST_MODE:-}" = "1" ]; then
  export GGUF_SHA256="${TEST_GGUF_SHA256:-$GGUF_SHA256}" GGUF_BYTES="${TEST_GGUF_BYTES:-$GGUF_BYTES}"
  export LLAMA_EXPECT_COMMIT="${TEST_LLAMA_COMMIT:-$LLAMA_EXPECT_COMMIT}"
fi

# Module names are NOT known yet. After probe_cluster.sh, export them (or edit here). CUDA must be a 12.x module:
# CUDA 13 dropped the V100. Scripts stop with a clear message if a needed one is empty.
export MOD_CUDA="${MOD_CUDA:-}"
export MOD_GCC="${MOD_GCC:-}"
export MOD_CMAKE="${MOD_CMAKE:-}"
export MOD_PYTHON="${MOD_PYTHON:-anaconda-python3}"   # the one module name the Redhawk pages show

load_modules() {
  for m in "$MOD_GCC" "$MOD_CMAKE" "$MOD_CUDA" "$MOD_PYTHON"; do
    [ -n "$m" ] && { module load "$m" || die "module load $m failed (see: module avail)"; }
  done
  return 0
}
need() { [ -n "${!1:-}" ] || die "$1 is empty. Export it before running (see probe_cluster.sh output), e.g. export $1=<module name>."; }

# --- the llama-server flags this test depends on. Each must appear in `llama-server --help` of the built binary. ----
# (Verified in the b11960 server README on 2026-11-04. Re-checked on the real binary by serve_and_run.sh.)
REQUIRED_FLAGS=(-m --alias --host --port -ngl -sm -ts -fa -c --parallel --jinja --chat-template-file --reasoning-format)

check_flags() {  # $1 = llama-server binary
  local help missing=() f
  help="$("$1" --help 2>&1 || true)"
  for f in "${REQUIRED_FLAGS[@]}"; do
    grep -qE "(^|[[:space:],])${f}([[:space:],=]|\$)" <<<"$help" || missing+=("$f")
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    echo "STOP: this llama-server does not list: ${missing[*]}" >&2
    echo "The test cannot run as designed. Do not improvise flags; report this and re-pin llama.cpp." >&2
    return 1
  fi
  echo "llama-server lists all required flags: ${REQUIRED_FLAGS[*]}"
}

# --- GPU memory summary. Input: the CSV written by the monitor in serve_and_run.sh ------------------------------
# Columns: timestamp,gpu,mem_used_mib,mem_total_mib,util_pct  ($1..$5 below, split on a comma plus optional spaces).
# Prints one line per GPU (peak used, total, minimum free = total - peak) and a last line MINFREE <n>.
summarize_memory() {
  awk -F', *' '
    NR == 1 { next }                                   # header row
    NF >= 4 && $3 ~ /^[0-9]+$/ && $4 ~ /^[0-9]+$/ {
      g = $2; used = $3 + 0; total = $4 + 0
      if (!(g in peak) || used > peak[g]) peak[g] = used
      tot[g] = total; seen = 1
    }
    END {
      if (!seen) { print "NODATA"; print "MINFREE -1"; exit }
      minfree = -1
      for (g in peak) {
        free = tot[g] - peak[g]
        printf "gpu %s peak_used_MiB %d total_MiB %d min_free_MiB %d\n", g, peak[g], tot[g], free
        if (minfree < 0 || free < minfree) minfree = free
      }
      print "MINFREE " minfree
    }' "$1"
}
