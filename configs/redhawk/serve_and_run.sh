#!/bin/bash
# serve_and_run.sh - on one Redhawk GPU node: check everything, start llama-server on the two V100s, wait until the
# model is loaded, run the test client, VALIDATE what was saved (always, in every stage), summarize GPU memory, stop
# the server. Called by gpu_smoke_a.sbatch (Stage A), gpu_smoke_b.sbatch (Stage B) and qwen_test.sbatch (main run).
#
# Environment (set by those wrappers):
#   QT_STAGE     A | B | main
#   QT_CTX       total context tokens shared by all slots   (A: 20480, B: 40960; main must repeat the passing stage)
#   QT_PARALLEL  simultaneous sequences                      (A: 1,     B: 2;     main must repeat the passing stage)
#   QT_FA        flash-attention mode for -fa: auto | on | off   (default auto)
#   QT_RESUME    (main only) an existing run folder to continue; QT_BREAK_LOCK=yes removes a stale lock;
#                QT_RETRY_ERRORS=yes re-sends slots whose earlier call ERRORED (recorded as attempt 2, 3, ...)
#   QT_PY_TIMEOUT optional limit for the client, e.g. 35m (used by the smoke stages)
#   QT_ATTEMPT   optional attempt number (the pipeline sets 2 when it retries Stage A); only changes log file names
#   QT_ACK_QUALITY=yes  needed to go on after a stage in which EVERY smoke reply had a model-quality finding
#
# WHAT MUST PASS BEFORE ANYTHING IS SENT (each stops the job with a plain message):
#   - exactly 2 GPUs are visible, each about 16 GB, and they look like V100s;
#   - the weights file has the pinned size and SHA-256 (re-hashed here, not trusted from the download);
#   - the chat template file matches its recorded hash;
#   - the llama.cpp source commit equals the pinned commit, and the binary lists every flag this test uses;
#   - the stage gate: Stage B needs a passing Stage A with 3 GB free per GPU; the main run needs a passing stage with
#     the SAME context, parallelism, flash-attention mode, llama.cpp commit and weights.
# AFTER THE LOAD it also requires that nvidia-smi shows at least 4096 MiB in use on each of the 2 GPUs (the model is on
# both cards). This replaced an earlier search of the server log for "arch = qwen35" / "CUDA0" / "CUDA1": the pinned
# llama.cpp build does not print those lines, and that search stopped the first job although the model had loaded fine.
#
# TWO KINDS OF FAILURE, KEPT APART (validation is mandatory in every stage, including the main run):
#   INFRASTRUCTURE failure = the plumbing is wrong: missing files, invalid metadata, duplicate slot ids, an
#     incomplete run, GPU errors in the server log, the client crashing, too little GPU memory left. The stage FAILS
#     (RESULT=FAIL_INFRA), the next stage will not start, and the job exits non-zero.
#   MODEL-QUALITY finding = the plumbing worked and the model's reply is poor (invalid JSON, truncated, off-slot
#     fields...). That is a result, not a fault: the stage still passes (RESULT=PASS_QUALITY_WARN) and the findings
#     are printed and recorded. Only if EVERY reply of a smoke stage has a finding does the next stage demand that a
#     person has looked (QT_ACK_QUALITY=yes), because that pattern usually means a settings problem, not a model one.
set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
trap 'echo "ERROR at line $LINENO: $BASH_COMMAND" >&2' ERR
require_paths

STAGE="${QT_STAGE:-}"
case "$STAGE" in A|B|main) ;; *) die "QT_STAGE must be A, B or main" ;; esac
: "${QT_CTX:?QT_CTX must be set explicitly}"; : "${QT_PARALLEL:?QT_PARALLEL must be set explicitly}"
CTX="$QT_CTX"; PAR="$QT_PARALLEL"; FA="${QT_FA:-auto}"
case "$FA" in auto|on|off) ;; *) die "QT_FA must be auto, on or off" ;; esac
if [ "$STAGE" = A ]; then { [ "$CTX" = 20480 ] && [ "$PAR" = 1 ]; } || die "Stage A is defined as context 20480, parallel 1"; fi
if [ "$STAGE" = B ]; then { [ "$CTX" = 40960 ] && [ "$PAR" = 2 ]; } || die "Stage B is defined as context 40960, parallel 2"; fi
if [ "$STAGE" = main ]; then
  { [ "$CTX/$PAR" = "20480/1" ] || [ "$CTX/$PAR" = "40960/2" ]; } || die "the main run may only repeat a tested setting: 20480/1 or 40960/2"
fi

JOB="${SLURM_JOB_ID:-nojob}"
RESULT_DIR="$QT_OUT/stage_results"; LOGDIR="$QT_OUT/job_logs"
mkdir -p "$RESULT_DIR" "$LOGDIR"
# Log files are named by job AND stage (and attempt), because the pipeline job runs several stages inside one Slurm job:
# llama_server_<job>_A.log, llama_server_<job>_B.log, llama_server_<job>_main.log, and ..._A_2.log for a retried Stage A.
TAGID="${JOB}_${STAGE}${QT_ATTEMPT:+_$QT_ATTEMPT}"
SERVER_LOG="$LOGDIR/llama_server_${TAGID}.log"; MEMLOG="$LOGDIR/gpu_memory_${TAGID}.csv"
PYLOG="$LOGDIR/run_${TAGID}.out"; VALLOG="$LOGDIR/validate_${TAGID}.out"

load_modules
need MOD_CUDA

# ---- 1. the GPUs ----------------------------------------------------------------------------------------------------
command -v nvidia-smi >/dev/null || die "nvidia-smi not found: this is not a GPU node"
GPU_LIST="$(nvidia-smi -L)"
N_GPU="$(grep -c '^GPU ' <<<"$GPU_LIST" || true)"
[ "$N_GPU" = 2 ] || die "expected exactly 2 visible GPUs, found $N_GPU. The job must take a whole V100 node (--exclusive). Visible: $GPU_LIST"
grep -qi 'V100' <<<"$GPU_LIST" || warn "GPUs do not look like V100s: $GPU_LIST"
while read -r mib; do
  [ "${mib:-0}" -ge 15000 ] || die "a GPU reports only $mib MiB, expected about 16 GB"
done < <(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits)
echo "=== node $(hostname), job $JOB, stage $STAGE, $(date -u +%FT%TZ) ==="
echo "$GPU_LIST"
nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv

# ---- 2. queue wait, from Slurm itself (not from an assumed variable) -------------------------------------------------
SUBMIT="unknown"; STARTED="unknown"; WAIT="unknown"
if [ "$JOB" != nojob ] && command -v scontrol >/dev/null; then
  J="$(scontrol show job "$JOB" -o 2>/dev/null || true)"
  SUBMIT="$(sed -n 's/.*SubmitTime=\([^ ]*\).*/\1/p' <<<"$J")"; STARTED="$(sed -n 's/.*StartTime=\([^ ]*\).*/\1/p' <<<"$J")"
  if { [ -z "$SUBMIT" ] || [ -z "$STARTED" ]; } && command -v sacct >/dev/null; then
    ROW="$(sacct -j "$JOB" -X -n -P --format=Submit,Start 2>/dev/null | head -n 1 || true)"
    SUBMIT="${ROW%%|*}"; STARTED="${ROW##*|}"
  fi
  [ -n "$SUBMIT" ] || SUBMIT="unknown"
  [ -n "$STARTED" ] || STARTED="unknown"
  if [ "$SUBMIT" != unknown ] && [ "$STARTED" != unknown ]; then
    WAIT="$(( $(date -d "$STARTED" +%s) - $(date -d "$SUBMIT" +%s) ))" || WAIT="unknown"
  fi
fi
echo "queue: submitted $SUBMIT, started $STARTED, waited ${WAIT}s (cluster-local times; confirm later with sacct)"

# ---- 3. weights, template, llama.cpp ------------------------------------------------------------------------------
[ -f "$GGUF_PATH" ] || die "weights not found at $GGUF_PATH (run fetch_weights.sh)"
[ "$(stat -c %s "$GGUF_PATH")" = "$GGUF_BYTES" ] || die "weights file has the wrong size"
echo "Hashing the weights (a minute or two)..."
SHA="$(sha256sum "$GGUF_PATH" | cut -d' ' -f1)"
[ "$SHA" = "$GGUF_SHA256" ] || die "weights SHA-256 mismatch ($SHA)"
{ [ -f "$TEMPLATE_PATH" ] && [ -f "$QT_MODELS/chat_template.sha256" ]; } || die "chat template or its recorded hash is missing (run fetch_weights.sh)"
TSHA="$(sha256sum "$TEMPLATE_PATH" | cut -d' ' -f1)"
[ "$TSHA" = "$(cat "$QT_MODELS/chat_template.sha256")" ] || die "chat template hash differs from the recorded one"
[ -f "$QT_ROOT/llama_cpp_version.txt" ] || die "llama_cpp_version.txt missing (run fetch_source.sh)"
read -r TAG COMMIT < "$QT_ROOT/llama_cpp_version.txt"
[ "$COMMIT" = "$LLAMA_EXPECT_COMMIT" ] || die "built llama.cpp commit $COMMIT is not the pinned $LLAMA_EXPECT_COMMIT"
BIN="$QT_BUILD/build/bin/llama-server"
[ -x "$BIN" ] || die "llama-server not built at $BIN (run build_llamacpp.sbatch)"
check_flags "$BIN" || exit 2
# On the GPU node every library llama-server needs must resolve: gcc's newer libstdc++ and the CUDA libraries come from the
# modules loaded above, and libcuda.so.1 from the node's NVIDIA driver. Anything missing is reported now, with its name.
if [ "${QT_TEST_MODE:-}" != 1 ] && command -v ldd >/dev/null 2>&1; then
  MISSING_LIBS="$(ldd "$BIN" 2>&1 | grep -E "=> not found|version .* not found" | sort -u | head -n 8 || true)"
  [ -z "$MISSING_LIBS" ] || die "llama-server cannot find libraries on this node (module or driver problem):
$MISSING_LIBS"
fi
# shellcheck disable=SC1091
source "$QT_VENV/bin/activate"
python -c 'import httpx, yaml' 2>/dev/null || die "the Python environment lacks httpx/pyyaml (run fetch_weights.sh, which installs them)"
echo "llama.cpp $TAG $COMMIT; ctx $CTX; parallel $PAR; flash-attn $FA; weights sha256 $SHA; template sha256 $TSHA"

# ---- 4. the stage gate -----------------------------------------------------------------------------------------------
res() { if [ -f "$1" ]; then sed -n "s/^$2=//p" "$1" | tail -n 1; fi; }
gate_from() {  # $1 = the stage whose result file must show a pass for exactly this setup
  local f="$RESULT_DIR/stage$1.txt" r
  [ -f "$f" ] || die "no result file $f: run Stage $1 first"
  r="$(res "$f" RESULT)"
  case "$r" in PASS|PASS_QUALITY_WARN) ;; *) die "Stage $1 did not pass (RESULT=$r in $f)" ;; esac
  { [ "$(res "$f" CTX)" = "$CTX" ] && [ "$(res "$f" PARALLEL)" = "$PAR" ]; } || die "Stage $1 passed with a different context or parallelism"
  [ "$(res "$f" FA)" = "$FA" ] || die "Stage $1 passed with flash-attn $(res "$f" FA), not $FA"
  { [ "$(res "$f" LLAMA_COMMIT)" = "$COMMIT" ] && [ "$(res "$f" WEIGHTS_SHA256)" = "$SHA" ]; } || die "Stage $1 passed with a different llama.cpp or weights"
  if [ "$(res "$f" QUALITY_ALL)" = yes ] && [ "${QT_ACK_QUALITY:-}" != yes ]; then
    die "every reply of Stage $1 had a model-quality finding ($f). Read $LOGDIR/validate_$(res "$f" LOGTAG).out; if it is understood, rerun with QT_ACK_QUALITY=yes"
  fi
}
if [ "$STAGE" = B ]; then
  f="$RESULT_DIR/stageA.txt"
  case "$(res "$f" RESULT)" in PASS|PASS_QUALITY_WARN) ;; *) die "Stage B needs a passing Stage A ($f)" ;; esac
  [ "$(res "$f" STAGE_B_ALLOWED)" = yes ] || die "Stage A left under 3 GB free on a GPU, so Stage B is not allowed ($f)"
  [ "$(res "$f" FA)" = "$FA" ] || die "Stage A used flash-attn $(res "$f" FA); Stage B must use the same"
  if [ "$(res "$f" QUALITY_ALL)" = yes ] && [ "${QT_ACK_QUALITY:-}" != yes ]; then
    die "every reply of Stage A had a model-quality finding. Read its validate output, then rerun with QT_ACK_QUALITY=yes"
  fi
fi
if [ "$STAGE" = main ]; then
  if [ "$PAR" = 1 ]; then gate_from A; else gate_from B; fi
fi

# ---- 5. start the server -------------------------------------------------------------------------------------------
PORT="$(python -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
SERVER=""; MON=""; RUN_DIR=""; MINFREE="-1"; B_ALLOWED="no"; QUALITY_REPLIES=0; REPLIES=0; QUALITY_ALL="no"; INFRA_STATE="FAIL"
# shellcheck disable=SC2329  # called through the EXIT trap
cleanup() {
  if [ -n "$MON" ]; then kill "$MON" 2>/dev/null || true; fi
  if [ -n "$SERVER" ]; then kill "$SERVER" 2>/dev/null || true; fi
  wait 2>/dev/null || true
}
trap cleanup EXIT
write_result() {  # $1 = PASS | PASS_QUALITY_WARN | FAIL_INFRA, $2 = reason. Smoke stages leave the gate file; main leaves a summary.
  local f="$RESULT_DIR/stage$STAGE.txt"
  [ "$STAGE" != main ] || f="$RESULT_DIR/main_job${JOB}.txt"
  { echo "RESULT=$1"; echo "REASON=$2"; echo "INFRA=$INFRA_STATE"; echo "QUALITY_REPLIES=$QUALITY_REPLIES"; echo "REPLIES=$REPLIES"
    echo "QUALITY_ALL=$QUALITY_ALL"; echo "CTX=$CTX"; echo "PARALLEL=$PAR"; echo "FA=$FA"; echo "LLAMA_COMMIT=$COMMIT"
    echo "WEIGHTS_SHA256=$SHA"; echo "MIN_FREE_MIB=$MINFREE"; echo "STAGE_B_ALLOWED=$B_ALLOWED"; echo "JOB=$JOB"; echo "LOGTAG=$TAGID"
    echo "NODE=$(hostname)"; echo "UTC=$(date -u +%FT%TZ)"; echo "RUN_DIR=$RUN_DIR"; } > "$f.tmp"
  mv "$f.tmp" "$f"
  [ "$STAGE" = main ] || cp "$f" "$RESULT_DIR/stage${STAGE}_job${JOB}${QT_ATTEMPT:+_$QT_ATTEMPT}.txt"
}
fail() {  # an infrastructure failure before or during loading
  echo "FAIL (infrastructure): $1" >&2; echo "--- last lines of the server log ---" >&2; tail -n 30 "$SERVER_LOG" >&2 || true
  write_result FAIL_INFRA "$1"; exit 3
}

echo "Starting llama-server on 127.0.0.1:$PORT ..."
"$BIN" -m "$GGUF_PATH" --alias qwen3.6-27b-q4_k_m --host 127.0.0.1 --port "$PORT" \
  -ngl 99 -sm layer -ts 1,1 -fa "$FA" -c "$CTX" --parallel "$PAR" \
  --jinja --chat-template-file "$TEMPLATE_PATH" --reasoning-format deepseek > "$SERVER_LOG" 2>&1 &
SERVER=$!
# GPU memory sampled every 2 seconds. llama.cpp reserves the whole context and its work buffers at load, so the level
# right after loading already reflects the full 20,480 (or 40,960) tokens; the monitor catches any growth after it.
echo "timestamp,gpu,mem_used_mib,mem_total_mib,util_pct" > "$MEMLOG"
( while true; do
    nvidia-smi --query-gpu=timestamp,index,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits >> "$MEMLOG" 2>/dev/null || true
    sleep 2
  done ) &
MON=$!

T0="$(date +%s)"; READY=""
for _ in $(seq 1 240); do   # up to 20 minutes: 17 GB from network storage can be slow
  CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/health" || true)"
  if [ "$CODE" = 200 ]; then READY=1; break; fi   # 503 means "Loading model"
  kill -0 "$SERVER" 2>/dev/null || fail "llama-server exited while loading"
  sleep 5
done
[ -n "$READY" ] || fail "server not ready after 20 minutes"
LOAD="$(( $(date +%s) - T0 ))"
echo "Server ready after ${LOAD}s (model load time)"
sleep 6   # lets the monitor take at least two fresh samples after the load
echo "--- GPU memory right after loading ---"; summarize_memory "$MEMLOG" | grep -v '^MINFREE' || true
# Evidence that the model is on BOTH GPUs: measured memory, not log wording (see gpus_hold_model in common.sh). Whether the
# model really is the Qwen3.6 weights is already settled by the SHA-256 re-hash above and by the load itself.
HOLD="$(gpus_hold_model "$MEMLOG" 4096)" || fail "the model is not on both GPUs: $(tr '\n' ';' <<<"$HOLD")"
echo "--- model is on both GPUs (latest nvidia-smi readings) ---"; echo "$HOLD"
# Informational only, never a pass/fail test: any lines this build's log prints about the architecture or the devices.
echo "--- server log lines naming the architecture or devices (if this build prints any) ---"
grep -iE "arch|qwen3|CUDA[0-9]|offload|flash|n_ctx|devices" "$SERVER_LOG" | head -n 12 || true

# ---- 6. run the client -------------------------------------------------------------------------------------------
cd "$QT_REPO/code/generation"
OUT_ARGS=()
if [ "${QT_TEST_MODE:-}" = 1 ]; then OUT_ARGS=(--out-root "$(cygpath -m "$QT_OUT" 2>/dev/null || echo "$QT_OUT")"); fi
ARGS=(run --backend redhawk --base-url "http://127.0.0.1:$PORT/v1" --concurrency "$PAR"
      --meta "llama_cpp_tag=$TAG" --meta "llama_cpp_commit=$COMMIT" --meta "ctx=$CTX" --meta "parallel=$PAR"
      --meta "flash_attn=$FA" --meta "load_seconds=$LOAD" --meta "weights_sha256=$SHA" --meta "chat_template_sha256=$TSHA"
      --meta "slurm_job=$JOB" --meta "node=$(hostname)" --meta "stage=$STAGE"
      --meta "queue_submit_time=$SUBMIT" --meta "queue_start_time=$STARTED" --meta "queue_wait_seconds=$WAIT")
case "$STAGE" in
  A) ARGS+=(--smoke-set A) ;;
  B) ARGS+=(--smoke-set B) ;;
  main)
    if [ -n "${QT_RESUME:-}" ]; then ARGS+=(--resume "$QT_RESUME"); fi
    if [ "${QT_BREAK_LOCK:-}" = yes ]; then ARGS+=(--break-lock); fi
    if [ "${QT_RETRY_ERRORS:-}" = yes ]; then ARGS+=(--retry-errors); fi ;;
esac
trap - ERR   # a non-zero exit of the client is expected and handled below; do not print an ERROR line for it
set +e
if [ -n "${QT_PY_TIMEOUT:-}" ]; then
  timeout "$QT_PY_TIMEOUT" python open_teacher_test.py ${OUT_ARGS[@]+"${OUT_ARGS[@]}"} "${ARGS[@]}" 2>&1 | tee "$PYLOG"
else
  python open_teacher_test.py ${OUT_ARGS[@]+"${OUT_ARGS[@]}"} "${ARGS[@]}" 2>&1 | tee "$PYLOG"
fi
RC="${PIPESTATUS[0]}"
set -e
trap 'echo "ERROR at line $LINENO: $BASH_COMMAND" >&2' ERR
RUN_DIR="$(sed -n 's/^RUN_DIR=//p' "$PYLOG" | tail -n 1)"

# ---- 7. MANDATORY validation (every stage), memory summary, decision -------------------------------------------------
# Exit codes of `validate`: 0 clean, 1 infrastructure failure, 2 infrastructure fine but model-quality findings.
VRC=1
if [ -n "$RUN_DIR" ]; then
  trap - ERR   # validate exits 1 (infrastructure) or 2 (quality findings) on purpose; both are handled below
  set +e
  python open_teacher_test.py ${OUT_ARGS[@]+"${OUT_ARGS[@]}"} validate --run "$RUN_DIR" 2>&1 | tee "$VALLOG"
  VRC="${PIPESTATUS[0]}"
  set -e
  trap 'echo "ERROR at line $LINENO: $BASH_COMMAND" >&2' ERR
else
  echo "INFRASTRUCTURE FAIL: the client never reported a run folder, so there is nothing to validate" | tee "$VALLOG"
fi
VLINE="$(sed -n 's/^VALIDATE_RESULT //p' "$VALLOG" | tail -n 1)"
QUALITY_REPLIES="$(sed -n 's/.*quality_replies=\([0-9]*\).*/\1/p' <<<"$VLINE")"; QUALITY_REPLIES="${QUALITY_REPLIES:-0}"
REPLIES="$(sed -n 's/.*replies=\([0-9]*\)$/\1/p' <<<"$VLINE")"; REPLIES="${REPLIES:-0}"
if [ "$REPLIES" -gt 0 ] && [ "$QUALITY_REPLIES" -eq "$REPLIES" ]; then QUALITY_ALL=yes; fi

MEM="$(summarize_memory "$MEMLOG")"
echo "=== peak GPU memory over the whole job ==="; echo "$MEM" | grep -v '^MINFREE' || true
MINFREE="$(sed -n 's/^MINFREE //p' <<<"$MEM")"; MINFREE="${MINFREE:--1}"
ERRS="$(grep -Eic 'CUDA error|out of memory|GGML_ASSERT|GGML_ABORT|failed to allocate|segmentation fault|illegal memory' "$SERVER_LOG" || true)"
echo "errors in the server log: $ERRS; minimum free GPU memory: ${MINFREE} MiB"
echo "(Throughput, tokens, timings and the queue times read from scontrol at job start are in $RUN_DIR/run_log.json."
echo " sacct does not work on this cluster: its accounting host does not resolve.)"

REASON=""
HINT=""
if [ "$STAGE" = main ]; then HINT=" - if the run is only incomplete, resubmit with QT_RESUME=$RUN_DIR"; fi
[ "$RC" -eq 0 ] || REASON="$REASON client exited with $RC;"
case "$VRC" in 0|2) INFRA_STATE=PASS ;; *) REASON="$REASON INFRASTRUCTURE validation failed (see $VALLOG)$HINT;" ;; esac
[ "$ERRS" -eq 0 ] || REASON="$REASON errors in the server log;"
[ "$MINFREE" -ge 0 ] || REASON="$REASON no GPU memory samples;"
if [ "$STAGE" = B ] && [ "$MINFREE" -ge 0 ] && [ "$MINFREE" -lt 1024 ]; then REASON="$REASON under 1 GiB free on a GPU;"; fi
if [ -n "$REASON" ]; then
  INFRA_STATE=FAIL
  write_result FAIL_INFRA "$REASON"
  echo "RESULT: FAIL_INFRA (stage $STAGE):$REASON"
  exit 1
fi
[ "$STAGE" != A ] || [ "$MINFREE" -lt 3072 ] || B_ALLOWED=yes
if [ "$QUALITY_REPLIES" -gt 0 ]; then
  write_result PASS_QUALITY_WARN "$QUALITY_REPLIES of $REPLIES repl(ies) have model-quality findings"
  echo "RESULT: PASS_QUALITY_WARN (stage $STAGE): infrastructure is fine; $QUALITY_REPLIES of $REPLIES repl(ies) have model-quality findings (listed above; these are results, not faults)"
else
  write_result PASS "ok"
  echo "RESULT: PASS (stage $STAGE)"
fi
[ "$STAGE" != A ] || echo "Stage B allowed: $B_ALLOWED (needs at least 3072 MiB free on each GPU; minimum seen: $MINFREE MiB)"
exit 0
