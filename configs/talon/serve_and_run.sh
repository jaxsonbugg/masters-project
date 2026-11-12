#!/bin/bash
# serve_and_run.sh (Talon) - runs ONE stage inside a GPU job: check everything, start the vLLM server, send the questions
# through code/generation/open_teacher_test.py, validate the replies, decide PASS or FAIL. Called by the talon_*.sbatch wrappers.
# THIS IS A DRAFT, written before any Talon login (see talon_settings.sh): it refuses to run until a person has set
# SETTINGS_REVIEWED=yes there. Every part that depends on how Talon or vLLM really behave is marked UNVERIFIED.
#
# It is the Talon twin of configs/redhawk/serve_and_run.sh. What stayed the same: the stage idea, the two kinds of failure,
# mandatory validation, the result files and gates, "evidence by measurement, not by log wording". What changed: the engine is
# vLLM serving BF16 safetensors, the GPU count and layout are settings (no assumed 2 GPUs), the context is per sequence, and
# there is a throughput stage T.
#
# STAGES (QT_STAGE):
#   A     2 development questions (BM9001-2), ONE request at a time: do the plumbing and the reply fields work?
#   B     2 development questions (BM9003-4) at the client concurrency (CLIENT_CONCURRENCY) the main run will use.
#   T     the throughput benchmark: 32 development questions (BM9101-9132) once per client concurrency in SWEEP_CONCURRENCY, on
#         ONE server start. Run it once per GPU layout (see talon_throughput.sbatch), then read all runs with
#         code/generation/throughput_report.py.
#   main  the comparison run, BM0021-BM0120, one attempt per slot, with the layout that passed B.
# Settings (talon_settings.sh or the job's environment): GPU_COUNT, TENSOR_PARALLEL, REPLICAS, MAX_NUM_SEQS, CLIENT_CONCURRENCY,
# MAX_MODEL_LEN (no preferred defaults). Optional: QT_ACK_QUALITY=yes (go on after a stage in which EVERY reply had a
# model-quality finding), QT_RESUME=<run folder> and QT_RETRY_ERRORS=yes and QT_BREAK_LOCK=yes (main only), QT_PY_TIMEOUT.
#
# WHAT MUST PASS BEFORE ANYTHING IS SENT (each stops the job with a plain message):
#   - the settings were reviewed by a person; the layout values are present and agree (GPU_COUNT = TP x REPLICAS);
#   - Slurm assigned exactly GPU_COUNT GPUs (CUDA_VISIBLE_DEVICES; on Talon nvidia-smi alone lists every GPU of the node) and
#     each assigned GPU reports at least GPU_MIN_TOTAL_MIB; a 2-GPU job records whether it got an NVLink pair (not required);
#   - every weight file matches the recorded SHA-256 manifest (re-hashed here, not trusted from the download) and the model
#     folder is the pinned revision;
#   - vLLM is the pinned version and `vllm serve --help` lists every flag this stage uses;
#   - the stage gate (A needs nothing; B needs a passing A with the same layout; T needs a passing A with the same engine and
#     weights; main needs a passing B with the same layout).
# AFTER THE LOAD: nvidia-smi must show at least half of one GPU's share of the weights in use on each of the GPU_COUNT ASSIGNED GPUs, and
# the server must list the served model name. No pass/fail rests on the wording of the server log (only error WORDS can fail).
#
# TWO KINDS OF FAILURE, KEPT APART (validation is mandatory in every stage):
#   INFRASTRUCTURE failure = the plumbing is wrong (missing files, GPU errors, incomplete run...): RESULT=FAIL_INFRA, exit non-zero.
#   MODEL-QUALITY finding  = the plumbing worked and a reply is poor (invalid JSON, cut off...): RESULT=PASS_QUALITY_WARN, a
#     result and not a fault. Only if EVERY reply of a smoke stage has a finding must a person acknowledge before the next stage.
set -Eeuo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
trap 'echo "ERROR at line $LINENO: $BASH_COMMAND" >&2' ERR
require_reviewed
require_paths
talon_facts_banner

STAGE="${QT_STAGE:-}"
case "$STAGE" in A|B|T|main) ;; *) die "QT_STAGE must be A, B, T or main" ;; esac
check_layout
case "$STAGE" in B|main) check_concurrency ;; esac
[ "$TALON_ENGINE_MODE" = venv ] || die "TALON_ENGINE_MODE=$TALON_ENGINE_MODE is not implemented in this draft (only venv). Decide after the probe, then extend this script."
need VLLM_VERSION; need MODEL_REV; need GPU_MIN_TOTAL_MIB; need SERVED_NAME

JOB="${SLURM_JOB_ID:-nojob}"
RESULT_DIR="$QT_OUT/stage_results"; LOGDIR="$QT_OUT/job_logs"
mkdir -p "$RESULT_DIR" "$LOGDIR"
TAGID="${JOB}_${STAGE}${QT_ATTEMPT:+_$QT_ATTEMPT}"
SERVER_LOG="$LOGDIR/vllm_server_${TAGID}.log"; MEMLOG="$LOGDIR/gpu_memory_${TAGID}.csv"

load_modules

# ---- 1. the GPUs ----------------------------------------------------------------------------------------------------
command -v nvidia-smi >/dev/null || die "nvidia-smi not found: this is not a GPU node"
# Only the GPUs Slurm ASSIGNED to this job count. On Talon `nvidia-smi` on its own lists all four GPUs of the node, including GPUs
# that other people's jobs are using (OBSERVED 2026-11-12, job 196), so every query here is limited with -i to the assigned ids.
GPU_IDS="$(assigned_gpu_ids)"
N_ASSIGNED="$(count_ids "$GPU_IDS")"
[ "$N_ASSIGNED" = "$GPU_COUNT" ] || die "expected exactly $GPU_COUNT assigned GPU(s) (GPU_COUNT), but CUDA_VISIBLE_DEVICES='$GPU_IDS' lists $N_ASSIGNED. Check the GPU request the job was submitted with (submit_pipeline.sh builds it from the settings)."
GPU_LIST="$(nvidia-smi -i "$GPU_IDS" --query-gpu=index,name,uuid --format=csv,noheader)" || die "nvidia-smi could not query the assigned GPU(s) '$GPU_IDS'."
N_GPU="$(grep -c . <<<"$GPU_LIST" || true)"
[ "$N_GPU" = "$GPU_COUNT" ] || die "nvidia-smi reports $N_GPU of the assigned GPU(s) '$GPU_IDS', expected $GPU_COUNT: $GPU_LIST"
grep -qi 'H100' <<<"$GPU_LIST" || warn "the assigned GPUs do not look like H100s: $GPU_LIST"
while read -r mib; do
  [ "${mib:-0}" -ge "$GPU_MIN_TOTAL_MIB" ] || die "a GPU reports only $mib MiB, expected at least $GPU_MIN_TOTAL_MIB (GPU_MIN_TOTAL_MIB; each Talon H100 NVL reports 95,830 MiB, observed in job 196)"
done < <(nvidia-smi -i "$GPU_IDS" --query-gpu=memory.total --format=csv,noheader,nounits)
GPU_INDEXES="$(cut -d, -f1 <<<"$GPU_LIST" | tr -d ' ' | paste -sd, -)"
# NVLink pairing for 2-GPU jobs: recorded, not required (decided in the settings review, 2026-11-12). Slurm does not promise a
# linked pair; tensor parallelism across a PCIe path still works, only slower, so this is a measured fact next to the timings.
NVLINK_PAIR="not applicable ($GPU_COUNT GPU(s))"
if [ "$GPU_COUNT" = 2 ]; then
  LINK="$(gpu_pair_link "${GPU_INDEXES%%,*}" "${GPU_INDEXES##*,}")"
  case "$LINK" in
    NV*) NVLINK_PAIR="yes ($LINK)" ;;
    unknown) NVLINK_PAIR="unknown (nvidia-smi topo -m could not be read)" ;;
    *) NVLINK_PAIR="no ($LINK)"; warn "the two assigned GPUs ($GPU_INDEXES) are not an NVLink pair (link: $LINK). The job continues; timings from it are recorded with NVLINK_PAIR=no." ;;
  esac
fi
echo "=== node $(hostname), job $JOB, stage $STAGE, $(date -u +%FT%TZ) ==="
echo "assigned GPU(s): CUDA_VISIBLE_DEVICES=$GPU_IDS (indexes $GPU_INDEXES); NVLink pair: $NVLINK_PAIR"
echo "$GPU_LIST"
nvidia-smi -i "$GPU_IDS" --query-gpu=index,name,memory.total,driver_version --format=csv
nvidia-smi 2>/dev/null | head -n 4 || true   # the header line shows the CUDA version the driver supports (not yet recorded for Talon)
echo "layout: $GPU_COUNT GPU(s), tensor parallel $TENSOR_PARALLEL, replicas $REPLICAS, max sequences $MAX_NUM_SEQS, max length per sequence $MAX_MODEL_LEN"
echo "NOTE: $MAX_MODEL_LEN tokens per sequence is far below Qwen's native 262,144 and below the 128K its model card advises; used only to match the Redhawk run."

# ---- 2. queue wait, from Slurm itself (not from an assumed variable) -------------------------------------------------
SUBMIT="unknown"; STARTED="unknown"; WAIT="unknown"
if [ "$JOB" != nojob ] && command -v scontrol >/dev/null; then
  J="$(scontrol show job "$JOB" -o 2>/dev/null || true)"
  SUBMIT="$(sed -n 's/.*SubmitTime=\([^ ]*\).*/\1/p' <<<"$J")"; STARTED="$(sed -n 's/.*StartTime=\([^ ]*\).*/\1/p' <<<"$J")"
  if { [ -z "$SUBMIT" ] || [ -z "$STARTED" ]; } && command -v sacct >/dev/null; then   # UNVERIFIED: whether sacct works on Talon
    ROW="$(sacct -j "$JOB" -X -n -P --format=Submit,Start 2>/dev/null | head -n 1 || true)"
    SUBMIT="${ROW%%|*}"; STARTED="${ROW##*|}"
  fi
  [ -n "$SUBMIT" ] || SUBMIT="unknown"
  [ -n "$STARTED" ] || STARTED="unknown"
  if [ "$SUBMIT" != unknown ] && [ "$STARTED" != unknown ]; then
    WAIT="$(( $(date -d "$STARTED" +%s) - $(date -d "$SUBMIT" +%s) ))" || WAIT="unknown"
  fi
fi
echo "queue: submitted $SUBMIT, started $STARTED, waited ${WAIT}s (cluster-local times)"

# ---- 3. weights and engine ----------------------------------------------------------------------------------------------
[ -d "$QT_MODEL_DIR" ] || die "model folder not found at $QT_MODEL_DIR (run prep_talon.sh)"
[ -f "$QT_MODEL_DIR/config.json" ] || die "$QT_MODEL_DIR has no config.json: the download is incomplete"
[ -f "$QT_MANIFEST" ] || die "the weights manifest $QT_MANIFEST is missing (fetch_talon.sh writes it after the download is verified)"
[ "$(cat "$QT_MODELS/model_revision.txt" 2>/dev/null || true)" = "$MODEL_REV" ] || die "the downloaded revision ($(cat "$QT_MODELS/model_revision.txt" 2>/dev/null || echo none)) is not the pinned MODEL_REV ($MODEL_REV)"
echo "Hashing the weights (a few minutes)..."
( cd "$QT_MODEL_DIR" && sha256sum --quiet -c "$QT_MANIFEST" ) || die "a weight file does not match the manifest. Do not use this folder; delete it and download again."
MANIFEST_SHA="$(sha256sum "$QT_MANIFEST" | cut -d' ' -f1)"
VLLM_BIN="$QT_VENV/bin/vllm"
[ -x "$VLLM_BIN" ] || die "vllm not installed at $VLLM_BIN (run prep_talon.sh)"
ACTUAL_VERSION="$(installed_vllm_version || true)"   # package records, not `vllm --version` (it prints warnings first; see common.sh)
[ -n "$ACTUAL_VERSION" ] || die "could not read the installed vLLM version from Python's package records in $QT_VENV"
[ "$ACTUAL_VERSION" = "$VLLM_VERSION" ] || die "vLLM is $ACTUAL_VERSION, not the pinned $VLLM_VERSION"
# UNVERIFIED list: confirmed against the real `vllm serve --help` by probe_talon_part2.sh before this file may be marked reviewed.
REQUIRED_VLLM_FLAGS=(--served-model-name --host --port --tensor-parallel-size --max-model-len --max-num-seqs --reasoning-parser --dtype)
VHELP="$("$VLLM_BIN" serve --help=all 2>&1)" || VHELP="$("$VLLM_BIN" serve --help 2>&1)" || true
MISSING=()
for f in "${REQUIRED_VLLM_FLAGS[@]}"; do grep -q -- "$f" <<<"$VHELP" || MISSING+=("$f"); done
[ "${#MISSING[@]}" -eq 0 ] || die "this vllm does not list: ${MISSING[*]}. The test cannot run as designed. Do not improvise flags; report this and re-pin vLLM."
# shellcheck disable=SC1091
source "$QT_VENV/bin/activate"
python -c 'import httpx, yaml' 2>/dev/null || die "the Python environment lacks httpx/pyyaml (fetch_talon.sh installs them)"
ENGINE_FP="$ACTUAL_VERSION/$MODEL_REV/$MANIFEST_SHA/$MAX_MODEL_LEN"
LAYOUT_FP="$GPU_COUNT/$TENSOR_PARALLEL/$REPLICAS/$MAX_NUM_SEQS/$ENGINE_FP"
echo "vLLM $ACTUAL_VERSION; model $MODEL_REPO @ $MODEL_REV; manifest sha256 ${MANIFEST_SHA:0:16}...; dtype bfloat16"

# ---- 4. the stage gate -----------------------------------------------------------------------------------------------
res() { if [ -f "$1" ]; then sed -n "s/^$2=//p" "$1" | tail -n 1; fi; }
gate_from() {  # $1 = the stage whose result file must show a pass; $2 = LAYOUT_FP (same layout) or ENGINE_FP (same engine and weights)
  local f="$RESULT_DIR/stage$1.txt" r key="$2" have
  [ -f "$f" ] || die "no result file $f: run Stage $1 first"
  r="$(res "$f" RESULT)"
  case "$r" in PASS|PASS_QUALITY_WARN) ;; *) die "Stage $1 did not pass (RESULT=$r in $f)" ;; esac
  have="$(res "$f" "$key")"
  [ "$have" = "${!key}" ] || die "Stage $1 passed with a different $key ($have), this job has ${!key}. Re-run Stage $1 with this layout / engine / weights."
  if [ "$(res "$f" QUALITY_ALL)" = yes ] && [ "${QT_ACK_QUALITY:-}" != yes ]; then
    die "every reply of Stage $1 had a model-quality finding ($f). Read $LOGDIR/validate_$(res "$f" LOGTAG).out; if it is understood, rerun with QT_ACK_QUALITY=yes"
  fi
}
case "$STAGE" in
  B) gate_from A LAYOUT_FP ;;
  T) gate_from A ENGINE_FP ;;
  main) gate_from B LAYOUT_FP ;;
esac

# ---- 5. start the server -------------------------------------------------------------------------------------------
PORT="$(python -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
SERVER=""; MON=""; RUN_DIR=""; RUN_DIRS=""; QUALITY_REPLIES=0; REPLIES=0; QUALITY_ALL="no"; INFRA_STATE="FAIL"; MINFREE="-1"
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
    echo "QUALITY_ALL=$QUALITY_ALL"; echo "GPU_COUNT=$GPU_COUNT"; echo "TENSOR_PARALLEL=$TENSOR_PARALLEL"; echo "REPLICAS=$REPLICAS"
    echo "GPU_IDS=$GPU_IDS"; echo "GPU_INDEXES=$GPU_INDEXES"; echo "NVLINK_PAIR=$NVLINK_PAIR"; echo "MAX_NUM_SEQS=$MAX_NUM_SEQS"; echo "CLIENT_CONCURRENCY=${CLIENT_CONCURRENCY:-sweep: $SWEEP_CONCURRENCY}"; echo "MAX_MODEL_LEN=$MAX_MODEL_LEN"
    echo "VLLM_VERSION=$ACTUAL_VERSION"; echo "MODEL_REV=$MODEL_REV"; echo "WEIGHTS_MANIFEST_SHA256=$MANIFEST_SHA"
    echo "ENGINE_FP=$ENGINE_FP"; echo "LAYOUT_FP=$LAYOUT_FP"; echo "MIN_FREE_MIB=$MINFREE"; echo "JOB=$JOB"; echo "LOGTAG=$TAGID"
    echo "NODE=$(hostname)"; echo "UTC=$(date -u +%FT%TZ)"; echo "RUN_DIR=$RUN_DIR"; echo "RUN_DIRS=$RUN_DIRS"; } > "$f.tmp"
  mv "$f.tmp" "$f"
  [ "$STAGE" = main ] || cp "$f" "$RESULT_DIR/stage${STAGE}_job${JOB}${QT_ATTEMPT:+_$QT_ATTEMPT}.txt"
}
fail() {  # an infrastructure failure before or during loading
  echo "FAIL (infrastructure): $1" >&2; echo "--- last lines of the server log ---" >&2; tail -n 30 "$SERVER_LOG" >&2 || true
  write_result FAIL_INFRA "$1"; exit 3
}

echo "Starting vllm serve on 127.0.0.1:$PORT ..."
"$VLLM_BIN" serve "$QT_MODEL_DIR" --served-model-name "$SERVED_NAME" --host 127.0.0.1 --port "$PORT" \
  --tensor-parallel-size "$TENSOR_PARALLEL" --max-model-len "$MAX_MODEL_LEN" --max-num-seqs "$MAX_NUM_SEQS" \
  --reasoning-parser qwen3 --dtype bfloat16 > "$SERVER_LOG" 2>&1 &
SERVER=$!
# GPU memory of the ASSIGNED GPUs only, sampled every 2 seconds, for the report and for the "is the model on every GPU" check below.
echo "timestamp,gpu,mem_used_mib,mem_total_mib,util_pct" > "$MEMLOG"
( while true; do
    nvidia-smi -i "$GPU_IDS" --query-gpu=timestamp,index,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits >> "$MEMLOG" 2>/dev/null || true
    sleep 2
  done ) &
MON=$!

T0="$(date +%s)"; READY=""
for _ in $(seq 1 "${QT_LOAD_POLLS:-480}"); do   # default 480 x 5 s = 40 minutes: UNVERIFIED guess; 54 GB of weights plus start-up work
  CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/health" || true)"
  if [ "$CODE" = 200 ]; then READY=1; break; fi
  kill -0 "$SERVER" 2>/dev/null || fail "vllm serve exited while loading"
  sleep 5
done
[ -n "$READY" ] || fail "the server was not ready after $(( ${QT_LOAD_POLLS:-480} * 5 / 60 )) minutes"
LOAD="$(( $(date +%s) - T0 ))"
echo "Server ready after ${LOAD}s (model load time)"
MODELS_JSON="$(curl -s "http://127.0.0.1:$PORT/v1/models" || true)"   # not piped straight into grep -q: with pipefail an early grep exit would look like a failure
grep -q "$SERVED_NAME" <<<"$MODELS_JSON" || fail "the server does not list the served model name '$SERVED_NAME' at /v1/models"
sleep 6   # lets the monitor take at least two fresh samples after the load
echo "--- GPU memory right after loading ---"; summarize_memory "$MEMLOG" | grep -v '^MINFREE' || true
# Evidence that the model is on EVERY GPU of the layout: measured memory, not log wording. Each GPU must hold at least half of its
# share of the weights (WEIGHTS_MIB / TENSOR_PARALLEL / 2); an idle GPU shows 0 to a few hundred MiB.
HOLD_MIN="$(( WEIGHTS_MIB / TENSOR_PARALLEL / 2 ))"
HOLD="$(gpus_hold_model "$MEMLOG" "$HOLD_MIN" "$GPU_COUNT")" || fail "the model is not on all $GPU_COUNT GPU(s): $(tr '\n' ';' <<<"$HOLD")"
echo "--- model is on all $GPU_COUNT GPU(s) (latest nvidia-smi readings) ---"; echo "$HOLD"

# ---- 6. run the client (once per concurrency in stage T) -------------------------------------------------------------------
cd "$QT_REPO/code/generation"
case "$STAGE" in
  A) CONC_LIST="1" ;;
  B|main) CONC_LIST="$CLIENT_CONCURRENCY" ;;
  T) CONC_LIST="$SWEEP_CONCURRENCY" ;;
esac
RC=0; VRC=0; SMEM=""
trap - ERR   # a non-zero exit of the client or of validate is expected and handled below; do not print an ERROR line for it
set +e
for C in $CONC_LIST; do
  SUF=""; [ "$STAGE" != T ] || SUF="_c$C"
  PYLOG="$LOGDIR/run_${TAGID}${SUF}.out"; VALLOG="$LOGDIR/validate_${TAGID}${SUF}.out"
  ARGS=(--out-root "$QT_OUT" run --backend talon --base-url "http://127.0.0.1:$PORT/v1" --concurrency "$C"
        --meta "engine=vllm" --meta "vllm_version=$ACTUAL_VERSION" --meta "model_repo=$MODEL_REPO" --meta "model_rev=$MODEL_REV"
        --meta "gpu_count=$GPU_COUNT" --meta "tensor_parallel=$TENSOR_PARALLEL" --meta "replicas=$REPLICAS"
        --meta "max_num_seqs=$MAX_NUM_SEQS" --meta "max_model_len=$MAX_MODEL_LEN" --meta "load_seconds=$LOAD"
        --meta "weights_manifest_sha256=$MANIFEST_SHA" --meta "slurm_job=$JOB" --meta "node=$(hostname)" --meta "stage=$STAGE"
        --meta "queue_submit_time=$SUBMIT" --meta "queue_start_time=$STARTED" --meta "queue_wait_seconds=$WAIT")
  case "$STAGE" in
    A) ARGS+=(--smoke-set A) ;;
    B) ARGS+=(--smoke-set B) ;;
    T) ARGS+=(--smoke-set T) ;;
    main)
      if [ -n "${QT_RESUME:-}" ]; then ARGS+=(--resume "$QT_RESUME"); fi
      if [ "${QT_BREAK_LOCK:-}" = yes ]; then ARGS+=(--break-lock); fi
      if [ "${QT_RETRY_ERRORS:-}" = yes ]; then ARGS+=(--retry-errors); fi ;;
  esac
  echo; echo "--- client: stage $STAGE, concurrency $C ---"
  if [ -n "${QT_PY_TIMEOUT:-}" ]; then
    timeout "$QT_PY_TIMEOUT" python open_teacher_test.py "${ARGS[@]}" 2>&1 | tee "$PYLOG"
  else
    python open_teacher_test.py "${ARGS[@]}" 2>&1 | tee "$PYLOG"
  fi
  RC_ONE="${PIPESTATUS[0]}"; [ "$RC_ONE" -eq 0 ] || RC="$RC_ONE"
  RUN_DIR="$(sed -n 's/^RUN_DIR=//p' "$PYLOG" | tail -n 1)"
  # ---- MANDATORY validation. Exit codes of `validate`: 0 clean, 1 infrastructure failure, 2 infrastructure fine but quality findings.
  if [ -n "$RUN_DIR" ]; then
    RUN_DIRS="${RUN_DIRS:+$RUN_DIRS }$RUN_DIR"
    python open_teacher_test.py --out-root "$QT_OUT" validate --run "$RUN_DIR" 2>&1 | tee "$VALLOG"
    V_ONE="${PIPESTATUS[0]}"
  else
    echo "INFRASTRUCTURE FAIL: the client never reported a run folder, so there is nothing to validate" | tee "$VALLOG"
    V_ONE=1
  fi
  case "$V_ONE" in 0) ;; 2) [ "$VRC" -eq 1 ] || VRC=2 ;; *) VRC=1 ;; esac
  VLINE="$(sed -n 's/^VALIDATE_RESULT //p' "$VALLOG" | tail -n 1)"
  Q_ONE="$(sed -n 's/.*quality_replies=\([0-9]*\).*/\1/p' <<<"$VLINE")"; REP_ONE="$(sed -n 's/.*replies=\([0-9]*\)$/\1/p' <<<"$VLINE")"
  QUALITY_REPLIES=$(( QUALITY_REPLIES + ${Q_ONE:-0} )); REPLIES=$(( REPLIES + ${REP_ONE:-0} ))
  # peak memory so far, saved next to the replies so throughput_report.py can show it
  if [ -n "$RUN_DIR" ] && [ -d "$RUN_DIR" ]; then summarize_memory "$MEMLOG" | grep '^gpu' > "$RUN_DIR/gpu_peak.txt" || true; fi
done
set -e
trap 'echo "ERROR at line $LINENO: $BASH_COMMAND" >&2' ERR
if [ "$REPLIES" -gt 0 ] && [ "$QUALITY_REPLIES" -eq "$REPLIES" ]; then QUALITY_ALL=yes; fi

# ---- 7. memory summary and decision ----------------------------------------------------------------------------------
MEM="$(summarize_memory "$MEMLOG")"
echo "=== peak GPU memory over the whole job ==="; echo "$MEM" | grep -v '^MINFREE' || true
MINFREE="$(sed -n 's/^MINFREE //p' <<<"$MEM")"; MINFREE="${MINFREE:--1}"
# Error WORDS can only FAIL a stage, never pass one. UNVERIFIED word list: the first real vLLM log decides whether it needs changing.
ERR_RE='CUDA out of memory|OutOfMemoryError|NCCL error|Engine core initialization failed|CUDA error|Traceback \(most recent call last\)'
ERRS="$(grep -Eic "$ERR_RE" "$SERVER_LOG" || true)"
echo "error words in the server log: $ERRS; minimum free GPU memory: ${MINFREE} MiB"
if [ "$ERRS" -gt 0 ]; then echo "first matching lines:"; grep -Ei "$ERR_RE" "$SERVER_LOG" | head -n 5 | cut -c1-200 | sed 's/^/    /'; fi
echo "(Throughput numbers, tokens and timings are in each run folder's run_log.json; read them with code/generation/throughput_report.py.)"

REASON=""
HINT=""
if [ "$STAGE" = main ]; then HINT=" - if the run is only incomplete, resubmit with QT_RESUME=$RUN_DIR"; fi
[ "$RC" -eq 0 ] || REASON="$REASON client exited with $RC;"
case "$VRC" in 0|2) INFRA_STATE=PASS ;; *) REASON="$REASON INFRASTRUCTURE validation failed (see $LOGDIR/validate_${TAGID}*.out)$HINT;" ;; esac
[ "$ERRS" -eq 0 ] || REASON="$REASON error words in the server log;"
[ "$MINFREE" -ge 0 ] || REASON="$REASON no GPU memory samples;"
if [ -n "$REASON" ]; then
  INFRA_STATE=FAIL
  write_result FAIL_INFRA "$REASON"
  echo "RESULT: FAIL_INFRA (stage $STAGE):$REASON"
  exit 1
fi
if [ "$QUALITY_REPLIES" -gt 0 ]; then
  write_result PASS_QUALITY_WARN "$QUALITY_REPLIES of $REPLIES repl(ies) have model-quality findings"
  echo "RESULT: PASS_QUALITY_WARN (stage $STAGE): infrastructure is fine; $QUALITY_REPLIES of $REPLIES repl(ies) have model-quality findings (listed above; these are results, not faults)"
else
  write_result PASS "ok"
  echo "RESULT: PASS (stage $STAGE)"
fi
if [ "$STAGE" = T ]; then
  echo "Throughput runs of this layout: $RUN_DIRS"
  echo "Read them (and the runs of other layouts) with:  python code/generation/throughput_report.py $(for d in $RUN_DIRS; do printf -- '--run %s ' "$d"; done)"
fi
exit 0
