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
# the contingency ladder is: (1) QT_FA=off, (2) that commit with the patch (docs/progress_update.md, 2026-11-04, "The one-job pipeline built").

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

# Module names, VERIFIED by probe_cluster.sh on 2026-11-04 (they load together: nvcc 12.2.140, gcc 12.2.0, cmake 3.31.2).
# CUDA must be a 12.x module (CUDA 13 dropped the V100); CUDA 12.2 supports host compilers up to gcc 12, hence gcc-12.2.0.
# `${VAR-default}` (no colon) means: use the default only if the variable is UNSET, so an explicit empty value stays empty
# and makes the scripts stop (that is what the tests rely on).
export MOD_CUDA="${MOD_CUDA-cuda-12.2}"
export MOD_GCC="${MOD_GCC-gcc-12.2.0}"
export MOD_CMAKE="${MOD_CMAKE-cmake-3.31.2}"
# PYTHON: loading a Python module on Redhawk does NOT put a new Python on PATH (python stays 2.7.5 and python3 is 3.6.8,
# too old for the client). So a full interpreter is called by path. Verified by probe_cluster_part2.sh before use.
export QT_BASE_PYTHON="${QT_BASE_PYTHON-/software/python/anaconda3-2023-python3.10/bin/python}"

# Make sure the `module` command exists. A batch script starts a NON-login shell, where `module` may be undefined, so the
# usual init files are tried. `set +u` is needed because those init files use variables that may be unset.
ensure_module_cmd() {
  type module >/dev/null 2>&1 && return 0
  local f
  for f in /etc/profile.d/modules.sh "${MODULESHOME:-/nonexistent}/init/bash" /usr/share/Modules/init/bash /usr/share/lmod/lmod/init/bash; do
    if [ -f "$f" ]; then
      set +u; # shellcheck disable=SC1090
      . "$f"; set -u
      type module >/dev/null 2>&1 && return 0
    fi
  done
  die "the 'module' command is not available in this shell and no init file was found (see probe_cluster_part2.sh section 2)"
}

load_modules() {
  ensure_module_cmd
  local m
  for m in "$MOD_GCC" "$MOD_CMAKE" "$MOD_CUDA"; do
    if [ -n "$m" ]; then
      set +u
      module load "$m" || { set -u; die "module load $m failed (see: module avail)"; }
      set -u
    fi
  done
  return 0
}
need() { [ -n "${!1:-}" ] || die "$1 is empty. Export it before running (see probe_cluster.sh output), e.g. export $1=<module name>."; }

# --- the llama-server flags this test depends on. Each must appear in `llama-server --help` of the built binary. ----
# (Verified in the b11960 server README on 2026-11-04. Re-checked on the real binary by serve_and_run.sh.)
REQUIRED_FLAGS=(-m --alias --host --port -ngl -sm -ts -fa -c --parallel --jinja --chat-template-file --reasoning-format)

# run_llama BIN ARGS...: run llama-server and print its output. llama-server is linked to the NVIDIA driver library
# (libcuda.so.1), which exists only on GPU nodes. On the login node or a CPU node the program cannot even start
# ("error while loading shared libraries: libcuda.so.1"), so its --help prints nothing. Found on Redhawk 2026-11-04 (job
# 2510641): every flag looked "missing". So if that exact error appears, the call is repeated ONCE with the CUDA toolkit's
# stub libcuda on the library path for that single call (the toolkit ships stubs/libcuda.so for exactly this purpose: it
# lets a program load and print help without a GPU). It is never used to run a model.
run_llama() {
  local bin="$1" out rc nvcc stubs tmp
  shift
  out="$("$bin" "$@" 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ] && grep -q "error while loading shared libraries: libcuda" <<<"$out"; then
    nvcc="$(command -v nvcc 2>/dev/null || true)"
    if [ -n "$nvcc" ]; then
      stubs="$(dirname "$(dirname "$nvcc")")/lib64/stubs/libcuda.so"
      if [ -f "$stubs" ]; then
        tmp="$(mktemp -d)"; ln -s "$stubs" "$tmp/libcuda.so.1"
        out="$(LD_LIBRARY_PATH="$tmp:${LD_LIBRARY_PATH:-}" "$bin" "$@" 2>&1)"; rc=$?
        rm -rf "$tmp"
      fi
    fi
  fi
  printf '%s\n' "$out"
  return "$rc"
}

check_flags() {  # $1 = llama-server binary
  local help missing=() f
  help="$(run_llama "$1" --help || true)"
  for f in "${REQUIRED_FLAGS[@]}"; do
    grep -qE "(^|[[:space:],])${f}([[:space:],=]|\$)" <<<"$help" || missing+=("$f")
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    echo "STOP: this llama-server does not list: ${missing[*]}" >&2
    echo "What it printed for --help (first 3 lines; an error here usually means a missing library, not missing flags):" >&2
    head -n 3 <<<"$help" | sed 's/^/    /' >&2
    echo "The test cannot run as designed. Do not improvise flags; report this and re-pin llama.cpp." >&2
    return 1
  fi
  echo "llama-server lists all required flags: ${REQUIRED_FLAGS[*]}"
}

# --- Slurm time-left text -> seconds. `squeue -h -j <job> -o %L` prints [days-]hours:minutes:seconds, minutes:seconds,
# or words such as UNLIMITED / INVALID. Prints whole seconds, or -1 when the text is not a countdown. `10#` stops numbers
# with a leading zero (08, 09) from being read as octal.
parse_slurm_time() {
  local t="$1" d h m s
  t="${t// /}"
  case "$t" in
    [0-9]*-[0-9]*:[0-9]*:[0-9]*) d="${t%%-*}"; t="${t#*-}"; IFS=: read -r h m s <<<"$t"; echo $(( 10#$d * 86400 + 10#$h * 3600 + 10#$m * 60 + 10#$s )) ;;
    [0-9]*:[0-9]*:[0-9]*) IFS=: read -r h m s <<<"$t"; echo $(( 10#$h * 3600 + 10#$m * 60 + 10#$s )) ;;
    [0-9]*:[0-9]*) IFS=: read -r m s <<<"$t"; echo $(( 10#$m * 60 + 10#$s )) ;;
    *) echo -1 ;;
  esac
}
slurm_seconds_left() {  # seconds left in this job, or -1 if unknown
  parse_slurm_time "$(squeue -h -j "${SLURM_JOB_ID:-0}" -o %L 2>/dev/null | head -n 1)"
}

# --- Is the model really spread over both GPUs? Evidence = what nvidia-smi measured, NOT the wording of the server log. -----
# The first pipeline job (2510690) stopped at Stage A because it searched the log for "arch = qwen35" and "CUDA0"/"CUDA1".
# That llama.cpp build (b11960) prints a short, timestamped log without those lines, so the search could never succeed although
# the model had loaded (about 8.8 GB on GPU 0 and 9.2 GB on GPU 1). Memory readings do not depend on log wording.
# gpus_hold_model CSV MIN_MIB: uses the LATEST sample of each GPU in the monitor's CSV (columns timestamp,gpu,used,total,util).
# Prints one line per GPU. Returns 0 only if exactly 2 GPUs were sampled and each has at least MIN_MIB in use. The weights file
# is 16.8 GB, so a GPU holding its half has about 8 GB; 4096 MiB per GPU is far below that and far above an idle card (0-300 MiB).
gpus_hold_model() {
  local out
  out="$(awk -F', *' -v min="$2" '
    NR == 1 { next }
    NF >= 4 && $3 ~ /^[0-9]+$/ { used[$2] = $3 + 0 }          # later rows overwrite earlier ones: the latest sample wins
    END {
      n = 0; ok = 1
      for (g in used) { n++; printf "gpu %s in_use_MiB %d (needs at least %d)\n", g, used[g], min; if (used[g] < min) ok = 0 }
      if (n != 2) ok = 0
      print "GPUS_SEEN " n; print "HOLD_OK " ok
    }' "$1")"
  grep -v '^HOLD_OK\|^GPUS_SEEN' <<<"$out"
  [ "$(sed -n 's/^HOLD_OK //p' <<<"$out")" = 1 ]
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
