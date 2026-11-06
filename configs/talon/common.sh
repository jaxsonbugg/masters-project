# shellcheck shell=bash
# common.sh - helpers shared by the Talon scripts for the Qwen3.6-27B test. It is SOURCED, not run.
#
# This is the Talon twin of configs/redhawk/common.sh. It was copied and adapted, NOT shared, so that nothing here can break the
# working Redhawk scripts. What was kept unchanged: die/warn/need, the module loader, the Slurm time parser, the GPU memory
# summary. What changed: paths come from the talon_* keys of configs/paths.yaml (UNSET until the first login), there are no
# llama.cpp or GGUF pins (the engine is vLLM and the weights are BF16 safetensors), and the GPU count is a parameter, not 2.
# EVERY guess about Talon is in talon_settings.sh, which this file sources; nothing about Talon is hard-coded here.

# This file's own folder, and the repository copy it belongs to (works under Slurm, where the batch script itself is copied to a
# spool folder but this file is sourced from its real place).
QT_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QT_REPO="$(cd "$QT_SCRIPT_DIR/../.." && pwd)"
QT_CONF="$QT_REPO/configs/paths.yaml"
QT_SETTINGS_FILE="$QT_SCRIPT_DIR/talon_settings.sh"
export QT_SCRIPT_DIR QT_REPO QT_CONF QT_SETTINGS_FILE

die() { echo "STOP: $*" >&2; exit 2; }
warn() { echo "WARNING: $*" >&2; }

# Talon's login shell sets http_proxy and https_proxy to the university web proxy (OBSERVED 2026-11-06, /etc/profile.d/httpproxy.sh).
# Our client and health checks talk to vllm on 127.0.0.1 inside the job: that traffic must never go through a proxy, so these two
# addresses are added to no_proxy here, whatever the environment already holds. Downloads (Hugging Face, PyPI) keep using the proxy.
export no_proxy="${no_proxy:+$no_proxy,}127.0.0.1,localhost"
export NO_PROXY="$no_proxy"

[ -f "$QT_SETTINGS_FILE" ] || die "$QT_SETTINGS_FILE is missing (is this the repository copy?)"
# shellcheck disable=SC1090
source "$QT_SETTINGS_FILE"

# home_quota_mib [FILESYSTEM]: prints "USED SOFT HARD" in MiB for the home file system, or UNKNOWN if the output cannot be read.
# Built on the REAL output of `quota -s -v -f /home` seen on Talon on 2026-11-06 (the file-system name sits on its own line and the
# numbers on the next one; sizes carry a K, M, G or T suffix; a "*" after the used size means a limit was passed):
#   muanasp05-4001.mcs.miamioh.edu:p05_nfs_oel_rh3_home
#                    17336M    480G    500G           10541   4295m   4295m
# An unreadable answer is UNKNOWN, never a guess: the caller warns and the file system itself still enforces the limit.
home_quota_mib() {
  local out
  out="$(timeout 60 quota -s -v -f "${1:-/home}" 2>/dev/null)" || { echo UNKNOWN; return 0; }
  awk '
    function mib(s,   u, n) { gsub(/\*/, "", s); u = substr(s, length(s)); n = s + 0
      if (u == "K") return n / 1024; if (u == "M") return n; if (u == "G") return n * 1024; if (u == "T") return n * 1048576
      return n / 1024 }
    /^[^ ].*:/ && !/^Disk quotas/ { if (NF >= 4) { print int(mib($2)), int(mib($3)), int(mib($4)); found = 1; exit } want = 1; next }
    want && NF >= 3 { print int(mib($1)), int(mib($2)), int(mib($3)); found = 1; exit }
    END { if (!found) print "UNKNOWN" }' <<<"$out"
}

yaml_get() {  # value of a top-level "key: value" line of paths.yaml, without trailing spaces
  sed -n "s/^$1: *//p" "$QT_CONF" | head -n 1 | sed 's/[[:space:]]*$//'
}

require_paths() {
  [ -f "$QT_CONF" ] || die "$QT_CONF not found (is this the repository copy?)"
  QT_ROOT="$(yaml_get talon_root)"
  QT_MODELS="$(yaml_get talon_models)"
  QT_OUT="$(yaml_get talon_outputs)"
  local v val
  for v in QT_ROOT QT_MODELS QT_OUT; do
    val="${!v}"
    if [ -z "$val" ] || [ "$(echo "$val" | tr '[:lower:]' '[:upper:]')" = "UNSET" ]; then
      die "$v is UNSET in $QT_CONF (the talon_* keys stay UNSET until the first Talon login: run probe_talon.sh, read the storage section, choose an approved folder, and set talon_root, talon_repo, talon_models and talon_outputs together)."
    fi
  done
  # Talon results must never land in the Redhawk folders (and the reverse): refuse a Talon path that equals a Redhawk path.
  local rh_root rh_out
  rh_root="$(yaml_get redhawk_root)"; rh_out="$(yaml_get redhawk_outputs)"
  { [ -z "$rh_out" ] || [ "$QT_OUT" != "$rh_out" ]; } || die "talon_outputs is the same folder as redhawk_outputs ($QT_OUT). Talon and Redhawk results must be kept apart."
  { [ -z "$rh_root" ] || [ "$QT_ROOT" != "$rh_root" ]; } || die "talon_root is the same folder as redhawk_root ($QT_ROOT). Talon and Redhawk must be kept apart."
  export QT_ROOT QT_MODELS QT_OUT
  export QT_VENV="$QT_ROOT/venv"                       # Python environment (vLLM and the test client)
  export QT_MODEL_DIR="$QT_MODELS/$(basename "$MODEL_REPO")"   # the downloaded BF16 safetensors folder
  export QT_MANIFEST="$QT_MODELS/weights_manifest.sha256"      # sha256 of every weight file, written by fetch_talon.sh
}

# --- the Talon facts that nobody has verified. Printed by every script that touches Talon so they cannot be forgotten. ---
talon_facts_banner() {
  local f
  echo "UNVERIFIED (ask Miami Research Computing, ResComp@MiamiOH.edu) until confirmed in writing:"
  for f in "${TALON_UNVERIFIED_FACTS[@]}"; do echo "  - $f"; done
}

# --- the review flag is read from the FILE, never from the environment, so a draft cannot be un-drafted by accident -----------
settings_reviewed_value() { sed -n 's/^SETTINGS_REVIEWED=\([A-Za-z]*\).*/\1/p' "$QT_SETTINGS_FILE" | head -n 1; }
require_reviewed() {
  [ "$(settings_reviewed_value)" = yes ] && return 0
  die "DRAFT: these Talon scripts were written before any Talon login and cannot run yet. Run probe_talon.sh and probe_talon_part2.sh, copy the real values into $QT_SETTINGS_FILE, read the file, and only then change SETTINGS_REVIEWED=no to yes there."
}

need() { [ -n "${!1:-}" ] || die "$1 is empty. It has no default on purpose: set it in $QT_SETTINGS_FILE (from the probe output) or in the environment for this job."; }

# --- modules: blank names are skipped. A batch script starts a NON-login shell, where `module` may be undefined. -----------------
ensure_module_cmd() {
  type module >/dev/null 2>&1 && return 0
  local f
  for f in /etc/profile.d/modules.sh /etc/profile.d/lmod.sh "${MODULESHOME:-/nonexistent}/init/bash" /usr/share/Modules/init/bash /usr/share/lmod/lmod/init/bash; do
    if [ -f "$f" ]; then
      set +u; # shellcheck disable=SC1090
      . "$f"; set -u
      type module >/dev/null 2>&1 && return 0
    fi
  done
  die "the 'module' command is not available in this shell and no init file was found (see probe_talon.sh, the modules section)"
}
load_modules() {
  local m any=""
  for m in "$MOD_GCC" "$MOD_PYTHON" "$MOD_CUDA" $MOD_EXTRA; do [ -n "$m" ] && any=1; done
  [ -n "$any" ] || return 0
  ensure_module_cmd
  for m in "$MOD_GCC" "$MOD_PYTHON" "$MOD_CUDA" $MOD_EXTRA; do
    if [ -n "$m" ]; then
      set +u
      module load "$m" || { set -u; die "module load $m failed (see: module avail)"; }
      set -u
    fi
  done
  return 0
}

# --- the GPU layout: no preferred default, so every value is checked and the three that must agree are compared ---------------
check_layout() {
  local v
  for v in GPU_COUNT TENSOR_PARALLEL REPLICAS MAX_NUM_SEQS MAX_MODEL_LEN; do
    [[ "${!v:-}" =~ ^[1-9][0-9]*$ ]] || die "$v is '${!v:-}', not a positive whole number. The GPU layout has no preferred default on purpose (the throughput benchmark chooses it): set $v in $QT_SETTINGS_FILE or in the environment for this job."
  done
  [ "$((TENSOR_PARALLEL * REPLICAS))" -eq "$GPU_COUNT" ] || die "GPU_COUNT ($GPU_COUNT) must equal TENSOR_PARALLEL ($TENSOR_PARALLEL) x REPLICAS ($REPLICAS) = $((TENSOR_PARALLEL * REPLICAS))."
  [ "$REPLICAS" -eq 1 ] || die "REPLICAS=$REPLICAS is not implemented in this draft: several side-by-side servers belong to the 200,000-example pipeline (docs/talon_setup.md). Project them by arithmetic from a one-replica measurement."
  [ "$MAX_MODEL_LEN" -ge 19384 ] || die "MAX_MODEL_LEN $MAX_MODEL_LEN is below 19,384 (3,000 input cap + 16,384 output cap): replies would be cut off by the server."
}
check_concurrency() {
  [[ "${CLIENT_CONCURRENCY:-}" =~ ^[1-9][0-9]*$ ]] || die "CLIENT_CONCURRENCY is '${CLIENT_CONCURRENCY:-}', not a positive whole number (no preferred default): set it in $QT_SETTINGS_FILE or in the environment for this job."
}

# --- sbatch options built from the settings (#SBATCH lines in a script cannot hold variables). $1 = smoke | throughput | pipeline | main
# Fills the array SB_OPTS; stops with a plain message if a required value is still blank.
build_sbatch_opts() {
  local kind="$1" t extra
  SB_OPTS=(--nodes=1)
  [ -z "$TALON_PARTITION" ] || SB_OPTS+=(--partition="$TALON_PARTITION")
  [ -z "$TALON_ACCOUNT" ] || SB_OPTS+=(--account="$TALON_ACCOUNT")
  [ -z "$TALON_QOS" ] || SB_OPTS+=(--qos="$TALON_QOS")
  [ -z "$TALON_NODELIST" ] || SB_OPTS+=(--nodelist="$TALON_NODELIST")   # optional; blank = the scheduler may use any node of the partition
  case "$TALON_GPU_STYLE" in
    gres) SB_OPTS+=(--gres="gpu${TALON_GPU_TYPE:+:$TALON_GPU_TYPE}:$GPU_COUNT") ;;
    gpus) SB_OPTS+=(--gpus="${TALON_GPU_TYPE:+$TALON_GPU_TYPE:}$GPU_COUNT") ;;
    *) die "TALON_GPU_STYLE is '$TALON_GPU_STYLE': choose gres or gpus in $QT_SETTINGS_FILE (probe_talon_part2.sh shows which one the scheduler accepts)." ;;
  esac
  case "$kind" in smoke) t="$TIME_SMOKE" ;; throughput) t="$TIME_THROUGHPUT" ;; pipeline) t="$TIME_PIPELINE" ;; main) t="$TIME_MAIN" ;; *) die "unknown job kind '$kind'" ;; esac
  [ -n "$t" ] || die "the wall-time setting for '$kind' jobs (TIME_*) is blank in $QT_SETTINGS_FILE: set it from the partition's real limit (probe_talon.sh)."
  SB_OPTS+=(--time="$t")
  if [ -n "$TALON_EXTRA_SBATCH" ]; then read -r -a extra <<<"$TALON_EXTRA_SBATCH"; SB_OPTS+=("${extra[@]}"); fi
  return 0
}

# --- Slurm time-left text -> seconds. `squeue -h -j <job> -o %L` prints [days-]hours:minutes:seconds, minutes:seconds, or words
# such as UNLIMITED / INVALID. Prints whole seconds, or -1 when the text is not a countdown. `10#` stops numbers with a leading
# zero (08, 09) from being read as octal.
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

# --- Is the model really on the GPUs? Evidence = what nvidia-smi MEASURED, never the wording of the server log. -----------------
# gpus_hold_model CSV MIN_MIB WANT: uses the LATEST sample of each GPU in the monitor's CSV (columns timestamp,gpu,used,total,util).
# Prints one line per GPU. Returns 0 only if exactly WANT GPUs were sampled and each has at least MIN_MIB in use.
gpus_hold_model() {
  local out
  out="$(awk -F', *' -v min="$2" -v want="$3" '
    NR == 1 { next }
    NF >= 4 && $3 ~ /^[0-9]+$/ { used[$2] = $3 + 0 }          # later rows overwrite earlier ones: the latest sample wins
    END {
      n = 0; ok = 1
      for (g in used) { n++; printf "gpu %s in_use_MiB %d (needs at least %d)\n", g, used[g], min; if (used[g] < min) ok = 0 }
      if (n != want) ok = 0
      print "GPUS_SEEN " n; print "HOLD_OK " ok
    }' "$1")"
  grep -v '^HOLD_OK\|^GPUS_SEEN' <<<"$out"
  [ "$(sed -n 's/^HOLD_OK //p' <<<"$out")" = 1 ]
}

# --- GPU memory summary. Input: the CSV written by the monitor in serve_and_run.sh ------------------------------------------
# Columns: timestamp,gpu,mem_used_mib,mem_total_mib,util_pct. Prints one line per GPU (peak used, total, minimum free) and a
# last line MINFREE <n>. (Unlike the Redhawk scripts nothing is gated on free memory: vLLM reserves a fixed share of each GPU
# at start, so "free memory" is nearly constant and says little. The numbers are recorded for the report only.)
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
