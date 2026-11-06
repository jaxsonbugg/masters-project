#!/bin/bash
# Local test of the Talon scripts (configs/talon) with FAKE nvidia-smi / module / scontrol / squeue / sbatch / vllm (see README.md).
# Usage: bash shtest_talon.sh <work_dir> <part 1|2|3>
#   part 1: guards, layout checks, single stages and gates;  part 2: throughput stage, report, pipeline, main;
#   part 3: submit, probe, prep and download scripts, file hygiene. The parts may run at the same time.
# Needs bash, GNU coreutils, curl and a python with httpx and pyyaml (OTT_TEST_PYTHON, as a bash-style path such as /c/...).
# Give the work folder as a bash-style path (/tmp/x or /c/...), never C:/...: a colon in PATH hides every fake command.
#
# THE FAKES ARE PLACEHOLDERS. No real vLLM or Talon output was available when these tests were written. The scripts were written
# so that nothing passes because of log WORDING; the fakes only answer HTTP requests and print nvidia-smi numbers.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
S="${1:?give a work folder}"; PART="${2:-1}"; T="$S/talon$PART"
PYEXE="${OTT_TEST_PYTHON:-$(command -v python)}"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  PASS  $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL  $1   $2"; }
chk() { if eval "$2"; then ok "$1"; else bad "$1" "(condition: $2)"; [ -z "${SHOW_OUT_ON_FAIL:-}" ] || { echo "    --- captured output of the last command:"; echo "$OUT" | tail -n 14 | sed 's/^/    | /'; }; fi; }
REV="0123456789abcdef0123456789abcdef01234567"

setup() {
  rm -rf "$T"; mkdir -p "$T"/{bin,repo/data,tl/models/Qwen3.6-27B,tl/teacher_outputs,tl/venv/bin}
  cp -r "$REPO/code" "$REPO/configs" "$T/repo/"; cp -r "$REPO/data/prompts" "$T/repo/data/"
  sed -i "s|^talon_root: .*|talon_root: $T/tl|; s|^talon_repo: .*|talon_repo: $T/repo|; s|^talon_models: .*|talon_models: $T/tl/models|; s|^talon_outputs: .*|talon_outputs: $T/tl/teacher_outputs|" "$T/repo/configs/paths.yaml"
  SETF="$T/repo/configs/talon/talon_settings.sh"
  cp "$SETF" "$T/settings_draft.sh"
  sed -i 's/^SETTINGS_REVIEWED=no/SETTINGS_REVIEWED=yes/' "$SETF"     # a person "reviewed" the test copy; the draft copy is kept for the guard tests
  echo "export PATH=\"$(dirname "$PYEXE"):\$PATH\"" > "$T/tl/venv/bin/activate"
  printf '#!/bin/bash\nexit 0\n' > "$T/bin/module"
  cat > "$T/bin/scontrol" <<'EOF'
#!/bin/bash
echo "JobId=$3 JobName=x SubmitTime=2026-11-05T20:00:00 StartTime=2026-11-05T20:05:00 EndTime=Unknown"
EOF
  cat > "$T/bin/squeue" <<'EOF'
#!/bin/bash
case "$*" in
  *"%L"*) echo "${FAKE_TIMELEFT:-23:00:00}" ;;
  *"-n "*) [ -n "${FAKE_QUEUED:-}" ] && echo "9999 PD" ;;
  *"-j"*) [ -n "${FAKE_JOB_RUNNING:-}" ] && echo "7777 R" ;;
esac
exit 0
EOF
  cat > "$T/bin/sbatch" <<'EOF'
#!/bin/bash
echo "$*" >> "${FAKE_SBATCH_LOG:-/dev/null}"
if [[ "$*" == *"--test-only"* ]]; then
  if [ -n "${FAKE_REFUSE_RE:-}" ] && [[ "$*" =~ $FAKE_REFUSE_RE ]]; then echo "sbatch: error: Invalid generic resource (gres) specification"; exit 1; fi
  echo "sbatch: Job 99 to start at 2026-11-20T10:00:00 using 16 processors on nodes tlgpu01 in partition gpu-h100"; exit 0
fi
echo "Submitted batch job ${FAKE_JOBID:-4444}"
EOF
  cat > "$T/bin/nvidia-smi" <<'EOF'
#!/bin/bash
n="${FAKE_GPUS:-2}"; tot="${FAKE_TOTAL:-81559}"; args="$*"
if [ "$args" = "-L" ]; then for i in $(seq 0 $((n-1))); do echo "GPU $i: NVIDIA H100 80GB HBM3 (UUID: GPU-$i)"; done; exit 0; fi
case "$args" in
  *"--query-gpu=memory.total"*) for i in $(seq 1 "$n"); do echo "$tot"; done ;;
  *"--query-gpu=index,name,memory.total,driver_version"*) echo "index, name, memory.total [MiB], driver_version"; for i in $(seq 0 $((n-1))); do echo "$i, NVIDIA H100 80GB HBM3, $tot MiB, 560.35"; done ;;
  *"--query-gpu=timestamp,index,memory.used"*) ts="$(date +'%Y/%m/%d %H:%M:%S').000"
    for i in $(seq 0 $((n-1))); do u="${FAKE_USED:-70000}"; [ "$i" -eq $((n-1)) ] && [ -n "${FAKE_USED_LAST:-}" ] && u="$FAKE_USED_LAST"; echo "$ts, $i, $u, $tot, 50"; done ;;
esac
exit 0
EOF
  cat > "$T/tl/venv/bin/vllm" <<'EOF'
#!/bin/bash
if [ "${1:-}" = "--version" ]; then echo "${FAKE_VLLM_VERSION:-0.19.1}"; exit 0; fi
if [ "${1:-}" = serve ]; then
  for a in "$@"; do if [ "$a" = "--help=all" ] || [ "$a" = "--help" ]; then cat "$FAKE_VHELP"; exit 0; fi; done
  port=""; prev=""; for a in "$@"; do [ "$prev" = "--port" ] && port="$a"; prev="$a"; done
  echo "PLACEHOLDER fake vLLM log line (the real vLLM log on Talon is unknown until the first real run)"
  [ -z "${FAKE_ERRLOG:-}" ] || echo "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB"
  echo "args: $*"
  FAKE_SERVER_ARGS="$*" exec "$PYEXE" "$FAKE_VLLM_SERVER" "$port"
fi
echo "fake vllm: unknown command $*"; exit 1
EOF
  chmod +x "$T"/bin/* "$T/tl/venv/bin/vllm"
  cat > "$T/vhelp.txt" <<'EOF'
  --served-model-name SERVED_MODEL_NAME
  --host HOST
  --port PORT
  --tensor-parallel-size, -tp TENSOR_PARALLEL_SIZE
  --max-model-len MAX_MODEL_LEN
  --max-num-seqs MAX_NUM_SEQS
  --reasoning-parser {deepseek_r1,qwen3,...}
  --dtype {auto,bfloat16,float16,...}
EOF
  echo '{"architectures": ["Qwen3_5ForConditionalGeneration"]}' > "$T/tl/models/Qwen3.6-27B/config.json"
  head -c 4000 /dev/urandom > "$T/tl/models/Qwen3.6-27B/model-00001-of-00001.safetensors"
  ( cd "$T/tl/models/Qwen3.6-27B" && sha256sum config.json model-00001-of-00001.safetensors ) > "$T/tl/models/weights_manifest.sha256"
  echo "$REV" > "$T/tl/models/model_revision.txt"
  export PATH="$T/bin:$PATH" QT_TEST_MODE=1 PYEXE="$PYEXE" FAKE_VHELP="$T/vhelp.txt" FAKE_STATE="$T/state" \
         FAKE_VLLM_SERVER="$(cygpath -m "$HERE/fake_vllm_server.py" 2>/dev/null || echo "$HERE/fake_vllm_server.py")" \
         VLLM_VERSION=0.19.1 MODEL_REV="$REV" QT_BASE_PYTHON="$PYEXE" \
         GPU_COUNT=2 TENSOR_PARALLEL=2 REPLICAS=1 MAX_NUM_SEQS=8 CLIENT_CONCURRENCY=4 SWEEP_CONCURRENCY="1 4" \
         TALON_PARTITION=gpu-h100 TALON_GPU_STYLE=gres TALON_GPU_TYPE=h100 TIME_SMOKE=00:45:00 TIME_THROUGHPUT=02:00:00 TIME_PIPELINE=12:00:00 TIME_MAIN=10:00:00 \
         QT_LOAD_POLLS=30 SLURM_SUBMIT_DIR="$T/repo"
}
JOBN=2000
sub() {  # sub <wrapper> [VAR=value ...]  -> runs a wrapper like Slurm would, sets RC and OUT
  local w="$1"; shift; JOBN=$((JOBN+1))
  OUT="$(env SLURM_JOB_ID=$JOBN "$@" bash "$T/repo/configs/talon/$w" 2>&1)"; RC=$?
}
RES="$T/tl/teacher_outputs/stage_results"
val() { sed -n "s/^$2=//p" "$1" | tail -n 1; }
draft() { cp "$T/settings_draft.sh" "$T/repo/configs/talon/talon_settings.sh"; }
reviewed() { sed 's/^SETTINGS_REVIEWED=no/SETTINGS_REVIEWED=yes/' "$T/settings_draft.sh" > "$T/repo/configs/talon/talon_settings.sh"; }

if [ "$PART" = 1 ]; then
setup
echo "[D1] the drafts refuse to run until a person sets SETTINGS_REVIEWED=yes in the FILE (the environment cannot override it)"
draft
sub talon_smoke_a.sbatch; chk "Stage A refuses as a DRAFT" '[ $RC -ne 0 ] && grep -q "DRAFT: these Talon scripts were written before any Talon login" <<<"$OUT"'
sub talon_smoke_a.sbatch SETTINGS_REVIEWED=yes; chk "SETTINGS_REVIEWED=yes in the environment does not un-draft it" '[ $RC -ne 0 ] && grep -q "DRAFT" <<<"$OUT"'
sub talon_pipeline.sbatch; chk "the pipeline refuses as a DRAFT" '[ $RC -ne 0 ] && grep -q "DRAFT" <<<"$OUT"'
chk "the shipped settings file really says SETTINGS_REVIEWED=no" 'grep -q "^SETTINGS_REVIEWED=no" "$REPO/configs/talon/talon_settings.sh"'
reviewed
echo "[D2] paths: UNSET talon keys stop the job; Talon may never share a folder with Redhawk"
cp "$T/repo/configs/paths.yaml" "$T/paths.bak"
sed -i "s|^talon_outputs: .*|talon_outputs: UNSET|" "$T/repo/configs/paths.yaml"
sub talon_smoke_a.sbatch; chk "talon_outputs UNSET: stops with the UNSET message" '[ $RC -ne 0 ] && grep -q "QT_OUT is UNSET" <<<"$OUT" && grep -q "first Talon login" <<<"$OUT"'
RH_OUT="$(sed -n 's/^redhawk_outputs: //p' "$T/repo/configs/paths.yaml")"
sed -i "s|^talon_outputs: .*|talon_outputs: $RH_OUT|" "$T/repo/configs/paths.yaml"
sub talon_smoke_a.sbatch; chk "talon_outputs equal to redhawk_outputs is refused" '[ $RC -ne 0 ] && grep -q "same folder as redhawk_outputs" <<<"$OUT"'
cp "$T/paths.bak" "$T/repo/configs/paths.yaml"
echo "[L1] the GPU layout has no preferred default and must be consistent"
sub talon_smoke_a.sbatch GPU_COUNT=; chk "blank GPU_COUNT stops with 'no preferred default'" '[ $RC -ne 0 ] && grep -q "no preferred default" <<<"$OUT"'
sub talon_smoke_a.sbatch GPU_COUNT=4 TENSOR_PARALLEL=2 REPLICAS=1; chk "GPU_COUNT 4 with TP 2 x replicas 1 is refused" '[ $RC -ne 0 ] && grep -q "must equal TENSOR_PARALLEL" <<<"$OUT"'
sub talon_smoke_a.sbatch GPU_COUNT=4 TENSOR_PARALLEL=2 REPLICAS=2; chk "REPLICAS 2 is refused as not implemented (it belongs to the 200k pipeline)" '[ $RC -ne 0 ] && grep -q "not implemented in this draft" <<<"$OUT"'
sub talon_smoke_a.sbatch MAX_MODEL_LEN=8192; chk "a context below 19,384 tokens is refused" '[ $RC -ne 0 ] && grep -q "below 19,384" <<<"$OUT"'
sub talon_smoke_b.sbatch CLIENT_CONCURRENCY=; chk "Stage B needs CLIENT_CONCURRENCY (no default)" '[ $RC -ne 0 ] && grep -q "CLIENT_CONCURRENCY is" <<<"$OUT"'
echo "[A1] Stage A, healthy, 2 GPUs (TP 2)"
sub talon_smoke_a.sbatch; echo "$OUT" | tail -n 6
chk "Stage A exits 0 with RESULT: PASS" '[ $RC -eq 0 ] && grep -q "RESULT: PASS (stage A)" <<<"$OUT"'
chk "the UNVERIFIED Talon facts are printed" 'grep -q "UNVERIFIED (ask Miami Research Computing" <<<"$OUT" && grep -q "pricing and charges" <<<"$OUT"'
chk "the 20,480-token context note is printed" 'grep -q "far below Qwen" <<<"$OUT" && grep -q "128K" <<<"$OUT"'
chk "result file records the layout and the fingerprints" '[ "$(val $RES/stageA.txt RESULT)" = PASS ] && [ "$(val $RES/stageA.txt GPU_COUNT)" = 2 ] && [ "$(val $RES/stageA.txt TENSOR_PARALLEL)" = 2 ] && grep -q "^LAYOUT_FP=2/2/1/8/0.19.1/$REV/" $RES/stageA.txt'
chk "the model-on-every-GPU check ran on measured memory (needs 51500/2/2 = 12875 MiB per GPU)" 'grep -q "model is on all 2 GPU(s)" <<<"$OUT" && grep -q "gpu 1 in_use_MiB 70000 (needs at least 12875)" <<<"$OUT"'
chk "vLLM was started with the layout and BF16 (args reached the server)" 'grep -q -- "--tensor-parallel-size 2 --max-model-len 20480 --max-num-seqs 8 --reasoning-parser qwen3 --dtype bfloat16" $T/tl/teacher_outputs/job_logs/vllm_server_2*_A.log'
SA="$(ls -d $T/tl/teacher_outputs/*talon-bf16_smokeA* 2>/dev/null | head -n 1)"
chk "the run folder is under talon_outputs and named talon-bf16" '[ -n "$SA" ] && [ -f "$SA/responses.jsonl" ]'
chk "validation passed and saw the reasoning under the NEWER field name 'reasoning'" 'grep -q "VALIDATE_RESULT infra=PASS quality_replies=0 replies=2" <<<"$OUT" && grep -q "2 with separate reasoning" <<<"$OUT"'
chk "the run log records the layout as metadata for the throughput report" 'grep -q "\"gpu_count\": \"2\"" $SA/run_log.json && grep -q "\"tensor_parallel\": \"2\"" $SA/run_log.json && grep -q "\"max_model_len\": \"20480\"" $SA/run_log.json'
chk "nothing was written under the Redhawk outputs folder name" '! ls -d $T/tl/teacher_outputs/*redhawk* >/dev/null 2>&1'
cp $RES/stageA.txt $RES/stageA.keep
echo "[A2] GPU and memory checks for 1, 2 and 4 GPUs"
sub talon_smoke_a.sbatch FAKE_GPUS=1; chk "1 visible GPU for a 2-GPU layout stops the job" '[ $RC -ne 0 ] && grep -q "expected exactly 2 visible GPU(s)" <<<"$OUT"'
sub talon_smoke_a.sbatch FAKE_USED_LAST=200; chk "model missing from the last GPU (200 MiB): FAIL_INFRA, exit 3" '[ $RC -eq 3 ] && grep -q "the model is not on all 2 GPU(s)" <<<"$OUT" && [ "$(val $RES/stageA.txt RESULT)" = FAIL_INFRA ]'
sub talon_smoke_a.sbatch FAKE_GPUS=1 GPU_COUNT=1 TENSOR_PARALLEL=1; chk "a 1-GPU layout (TP 1) passes; needs 25750 MiB on the GPU" '[ $RC -eq 0 ] && grep -q "needs at least 25750" <<<"$OUT" && [ "$(val $RES/stageA.txt GPU_COUNT)" = 1 ]'
sub talon_smoke_a.sbatch FAKE_GPUS=4 GPU_COUNT=4 TENSOR_PARALLEL=4; chk "a 4-GPU layout (TP 4) passes and checks all 4 GPUs" '[ $RC -eq 0 ] && grep -q "model is on all 4 GPU(s)" <<<"$OUT" && grep -q "gpu 3 in_use_MiB" <<<"$OUT"'
sub talon_smoke_a.sbatch FAKE_TOTAL=40000; chk "a GPU with only 40000 MiB stops the job" '[ $RC -ne 0 ] && grep -q "reports only 40000 MiB" <<<"$OUT"'
echo "[A3] weights, engine and server checks stop the job before anything is sent"
cp "$T/tl/models/Qwen3.6-27B/model-00001-of-00001.safetensors" "$T/w.bak"; printf 'x' >> "$T/tl/models/Qwen3.6-27B/model-00001-of-00001.safetensors"
sub talon_smoke_a.sbatch; chk "a changed weight file fails the manifest check" '[ $RC -ne 0 ] && grep -q "does not match the manifest" <<<"$OUT"'
cp "$T/w.bak" "$T/tl/models/Qwen3.6-27B/model-00001-of-00001.safetensors"
sub talon_smoke_a.sbatch MODEL_REV=ffffffffffffffffffffffffffffffffffffffff; chk "a different pinned revision is refused" '[ $RC -ne 0 ] && grep -q "is not the pinned MODEL_REV" <<<"$OUT"'
sub talon_smoke_a.sbatch FAKE_VLLM_VERSION=0.20.0; chk "a different vLLM version is refused" '[ $RC -ne 0 ] && grep -q "vLLM is 0.20.0, not the pinned 0.19.1" <<<"$OUT"'
cp "$T/vhelp.txt" "$T/vhelp.bak"; grep -v -- "--max-num-seqs" "$T/vhelp.bak" > "$T/vhelp.txt"
sub talon_smoke_a.sbatch; chk "a vllm without a required flag stops the job" '[ $RC -ne 0 ] && grep -q "does not list: --max-num-seqs" <<<"$OUT"'
cp "$T/vhelp.bak" "$T/vhelp.txt"
sub talon_smoke_a.sbatch FAKE_WRONG_NAME=1; chk "a server that does not list the served name: FAIL_INFRA exit 3" '[ $RC -eq 3 ] && grep -q "does not list the served model name" <<<"$OUT"'
sub talon_smoke_a.sbatch FAKE_DIE=1; chk "a server that dies while loading: FAIL_INFRA exit 3" '[ $RC -eq 3 ] && grep -q "exited while loading" <<<"$OUT"'
sub talon_smoke_a.sbatch FAKE_ERRLOG=1; chk "CUDA out-of-memory words in the server log: FAIL_INFRA (error words can only fail)" '[ $RC -eq 1 ] && grep -q "error words in the server log" <<<"$OUT" && grep -q "CUDA out of memory" <<<"$OUT"'
sub talon_smoke_a.sbatch FAKE_REASONING_FIELD=reasoning_content; chk "the older field name reasoning_content works too" '[ $RC -eq 0 ] && grep -q "2 with separate reasoning" <<<"$OUT"'
cp $RES/stageA.keep $RES/stageA.txt
echo "[B1] Stage B gates"
sub talon_smoke_b.sbatch; chk "Stage B passes after a Stage A with the same layout" '[ $RC -eq 0 ] && grep -q "RESULT: PASS (stage B)" <<<"$OUT" && [ "$(val $RES/stageB.txt CLIENT_CONCURRENCY)" = 4 ]'
sub talon_smoke_b.sbatch FAKE_GPUS=1 GPU_COUNT=1 TENSOR_PARALLEL=1; chk "Stage B with another layout than Stage A is refused" '[ $RC -ne 0 ] && grep -q "different LAYOUT_FP" <<<"$OUT"'
echo "[Q1] model-quality findings are results, not faults; all-bad replies need a person"
sub talon_smoke_a.sbatch FAKE_MODE=badjson; chk "Stage A with bad JSON: PASS_QUALITY_WARN, QUALITY_ALL yes, exit 0" '[ $RC -eq 0 ] && grep -q "RESULT: PASS_QUALITY_WARN" <<<"$OUT" && [ "$(val $RES/stageA.txt QUALITY_ALL)" = yes ]'
sub talon_smoke_b.sbatch; chk "Stage B refuses without QT_ACK_QUALITY" '[ $RC -ne 0 ] && grep -q "had a model-quality finding" <<<"$OUT"'
sub talon_smoke_b.sbatch QT_ACK_QUALITY=yes; chk "Stage B proceeds once a person acknowledged" '[ $RC -eq 0 ]'
echo "[R1] truncation and reasoning exhaustion are detected and reported"
sub talon_smoke_a.sbatch FAKE_MODE=truncate; chk "cut-off replies with reasoning only are named as findings" '[ $RC -eq 0 ] && grep -q "reply cut off at max_tokens" <<<"$OUT" && grep -q "the whole budget went to reasoning" <<<"$OUT"'
sub talon_smoke_a.sbatch FAKE_MODE=reasoning_only; chk "reasoning without an answer (stopped normally) is a finding" '[ $RC -eq 0 ] && grep -q "content is empty" <<<"$OUT"'
cp $RES/stageA.keep $RES/stageA.txt
fi

if [ "$PART" = 2 ]; then
setup
sub talon_smoke_a.sbatch; chk "(setup) Stage A passes" '[ $RC -eq 0 ]'
echo "[T1] the throughput stage: one server start, one run per concurrency, then the report"
sub talon_throughput.sbatch; echo "$OUT" | tail -n 4 | cut -c1-200
chk "Stage T passes and lists its runs" '[ $RC -eq 0 ] && grep -q "RESULT: PASS (stage T)" <<<"$OUT" && grep -q "throughput_report.py --run" <<<"$OUT"'
chk "only ONE server start for the whole sweep" '[ "$(grep -c "Starting vllm serve" <<<"$OUT")" = 1 ]'
RUNS="$(val $RES/stageT.txt RUN_DIRS)"
chk "two run folders (concurrency 1 and 4), 32 replies each, BM9101-BM9132 only" 'set -- $RUNS; [ $# -eq 2 ] && [ "$(wc -l < $1/responses.jsonl)" = 32 ] && [ "$(wc -l < $2/responses.jsonl)" = 32 ] && grep -q BM9101 $1/responses.jsonl && grep -q BM9132 $2/responses.jsonl && ! grep -q "BM00" $1/responses.jsonl'
chk "each run recorded its concurrency and has gpu_peak.txt" 'set -- $RUNS; grep -q "\"concurrency\": 1" $1/run_log.json && grep -q "\"concurrency\": 4" $2/run_log.json && [ -s $1/gpu_peak.txt ]'
RARGS=""; for d in $RUNS; do RARGS="$RARGS --run $(cygpath -m "$d" 2>/dev/null || echo "$d")"; done
OUT="$("$PYEXE" "$T/repo/code/generation/throughput_report.py" $RARGS --failed "1gpu-tp1=not tried in this test" 2>&1)"; RC=$?
chk "throughput_report reads the real stage-T folders: 32 successes each, GPU-hours per 1,000, projection, exit 0" '[ $RC -eq 0 ] && [ "$(grep -c "successful examples 32" <<<"$OUT")" = 2 ] && grep -q "GPU-hours per 1,000 successful examples" <<<"$OUT" && grep -q "PROJECTION for 200,000" <<<"$OUT" && grep -q "NO THROUGHPUT" <<<"$OUT"'
echo "[T2] truncation in the sweep is a finding the report cannot hide"
sub talon_throughput.sbatch FAKE_MODE=mixed SWEEP_CONCURRENCY=8; RUNS="$(val $RES/stageT.txt RUN_DIRS)"
chk "Stage T still passes on infrastructure (cut-offs are model results)" '[ $RC -eq 0 ] && grep -q "PASS_QUALITY_WARN (stage T)" <<<"$OUT"'
OUT="$("$PYEXE" "$T/repo/code/generation/throughput_report.py" --run "$(cygpath -m "$RUNS" 2>/dev/null || echo "$RUNS")" 2>&1)"; RC=$?
chk "8 of 32 cut off = 25% > 5%: report exit 2 with FINDINGS" '[ $RC -eq 2 ] && grep -q "FINDINGS" <<<"$OUT" && grep -q "25.0%" <<<"$OUT"'
echo "[T3] Stage T needs a Stage A with the same engine and weights (any layout)"
sub talon_throughput.sbatch FAKE_GPUS=1 GPU_COUNT=1 TENSOR_PARALLEL=1; chk "a different layout is allowed for T (same engine)" '[ $RC -eq 0 ] && [ "$(val $RES/stageT.txt GPU_COUNT)" = 1 ]'
sub talon_throughput.sbatch FAKE_VLLM_VERSION=0.19.2 VLLM_VERSION=0.19.2; chk "another vLLM version than Stage A is refused" '[ $RC -ne 0 ] && grep -q "different ENGINE_FP" <<<"$OUT"'
echo "[P1] the one-job pipeline: A, B, main with one layout"
rm -f $RES/stageA.txt $RES/stageB.txt
sub talon_pipeline.sbatch; PJ=$JOBN; SUMM="$RES/pipeline_job$PJ.txt"
chk "exits 0 and the summary says COMPLETE with the layout" '[ $RC -eq 0 ] && [ "$(val $SUMM PIPELINE_RESULT)" = COMPLETE ] && grep -q "^LAYOUT=2 GPU(s), tensor parallel 2" $SUMM'
M="$(val $RES/main_job$PJ.txt RUN_DIR)"
chk "the main run has exactly 100 replies BM0021-BM0120 and no development slot" '[ -n "$M" ] && [ "$(wc -l < $M/responses.jsonl)" = 100 ] && grep -q BM0021 $M/responses.jsonl && grep -q BM0120 $M/responses.jsonl && ! grep -q "BM9" $M/responses.jsonl'
MU="$(cygpath -u "$M" 2>/dev/null || echo "$M")"   # Git Bash hands Windows Python a C:\ path; compare in one form
chk "the main run folder is named talon-bf16_test01 under talon_outputs" '[[ "$MU" == *talon-bf16_test01 ]] && [[ "$MU" == $T/tl/teacher_outputs/* ]]'
echo "[M1] a second main run without resume is refused (one attempt per slot)"
sub talon_test.sbatch; chk "refused: FAIL_INFRA and 'main run folder already exists'" '[ $RC -ne 0 ] && grep -q "main run folder already exists" <<<"$OUT"'
chk "the first main run is untouched (still 100 rows)" '[ "$(wc -l < $M/responses.jsonl)" = 100 ]'
sub talon_test.sbatch FAKE_GPUS=1 GPU_COUNT=1 TENSOR_PARALLEL=1; chk "the main run refuses a layout that Stage B did not pass" '[ $RC -ne 0 ] && grep -q "different LAYOUT_FP" <<<"$OUT"'
echo "[P2] the pipeline stops at the first failure"
sub talon_pipeline.sbatch FAKE_DIE=1; SUMM="$RES/pipeline_job$JOBN.txt"
chk "a server that dies in Stage A: STOPPED_AT_A, non-zero, main not started" '[ $RC -ne 0 ] && [ "$(val $SUMM PIPELINE_RESULT)" = STOPPED_AT_A ] && [ "$(val $SUMM MAIN)" = "not started" ]'
sub talon_pipeline.sbatch FAKE_TIMELEFT=00:30:00; SUMM="$RES/pipeline_job$JOBN.txt"
chk "too little time left: STOPPED_TIME after both smoke stages" '[ $RC -ne 0 ] && [ "$(val $SUMM PIPELINE_RESULT)" = STOPPED_TIME ] && [ "$(val $SUMM STAGE_B)" = passed ]'
sub talon_pipeline.sbatch FAKE_MODE=badjson; SUMM="$RES/pipeline_job$JOBN.txt"
chk "all-bad Stage A replies: STOPPED_QUALITY unless acknowledged" '[ $RC -ne 0 ] && [ "$(val $SUMM PIPELINE_RESULT)" = STOPPED_QUALITY ]'
fi

if [ "$PART" = 3 ]; then
setup
export FAKE_SBATCH_LOG="$T/sbatch.log"
VER="$T/repo/talon_verified.txt"; STATE="$T/tl/prep_state.txt"; FLOG="$T/tl/fetch_talon.log"
subm() { OUT="$(env "$@" bash "$T/repo/configs/talon/submit_pipeline.sh" "${KIND:-pipeline}" 2>&1)"; RC=$?; }
ready() { echo "REPO=$T/repo" > "$STATE"; echo "OK: weights verified" > "$FLOG"; printf 'PART2_OK=yes\nGPU_STYLES_ACCEPTED=gres\n' > "$VER"; }
echo "[S1] submit_pipeline.sh refuses until everything is ready"
draft; ready; subm; chk "refused as a DRAFT" '[ $RC -ne 0 ] && grep -q "DRAFT" <<<"$OUT"'
reviewed
rm -f "$STATE"; subm; chk "refused without prep_state.txt" '[ $RC -ne 0 ] && grep -q "run prep_talon.sh first" <<<"$OUT"'
ready; echo "downloading..." > "$FLOG"; subm; chk "refused while the download has not ended with OK" '[ $RC -ne 0 ] && grep -q "has not finished or failed" <<<"$OUT"'
ready; rm -f "$VER"; subm; chk "refused without the probe record talon_verified.txt" '[ $RC -ne 0 ] && grep -q "talon_verified.txt is missing" <<<"$OUT"'
ready; subm TALON_GPU_STYLE=gpus; chk "refused when the GPU style was not accepted by the probe" '[ $RC -ne 0 ] && grep -q "probe recorded these accepted styles" <<<"$OUT"'
ready; subm TIME_PIPELINE=; chk "refused when the wall-time setting is blank" '[ $RC -ne 0 ] && grep -q "wall-time setting for .pipeline. jobs" <<<"$OUT"'
ready; subm FAKE_QUEUED=1; chk "refused when a job of the same kind is already waiting" '[ $RC -ne 0 ] && grep -q "already in the queue" <<<"$OUT"'
ready; subm CLIENT_CONCURRENCY=; chk "the pipeline kind needs CLIENT_CONCURRENCY" '[ $RC -ne 0 ] && grep -q "CLIENT_CONCURRENCY is" <<<"$OUT"'
echo "[S2] with everything ready: the checks pass, the options are built from the settings, nothing is submitted without QT_SUBMIT"
ready; : > "$FAKE_SBATCH_LOG"; subm
chk "all checks pass; options include partition, typed gres for 2 GPUs and the wall time" '[ $RC -eq 0 ] && grep -q "All checks passed" <<<"$OUT" && grep -q -- "--partition=gpu-h100 --gres=gpu:h100:2 --time=12:00:00" <<<"$OUT"'
chk "only a --test-only call reached sbatch" '[ "$(grep -c . "$FAKE_SBATCH_LOG")" = 1 ] && grep -q -- "--test-only" "$FAKE_SBATCH_LOG"'
chk "the UNVERIFIED facts are printed by the submit script too" 'grep -q "UNVERIFIED (ask Miami Research Computing" <<<"$OUT"'
: > "$FAKE_SBATCH_LOG"; subm QT_SUBMIT=yes TALON_GPU_STYLE=gres TALON_GPU_TYPE=
chk "QT_SUBMIT=yes submits the pipeline wrapper with untyped gres and records the job" '[ $RC -eq 0 ] && grep -q "Submitted pipeline job 4444" <<<"$OUT" && grep -v -- "--test-only" "$FAKE_SBATCH_LOG" | grep -q -- "--gres=gpu:2 --time=12:00:00 configs/talon/talon_pipeline.sbatch" && grep -q "JOB=4444 KIND=pipeline" "$T/tl/submit_log.txt"'
: > "$FAKE_SBATCH_LOG"; KIND=throughput subm QT_SUBMIT=yes GPU_COUNT=1 TENSOR_PARALLEL=1 CLIENT_CONCURRENCY=
chk "the throughput kind uses its own wall time and GPU count, and needs no CLIENT_CONCURRENCY" '[ $RC -eq 0 ] && grep -q -- "--gres=gpu:h100:1 --time=02:00:00 configs/talon/talon_throughput.sbatch" "$FAKE_SBATCH_LOG"'
KIND=bogus subm; chk "an unknown kind is refused" '[ $RC -ne 0 ] && grep -q "unknown kind" <<<"$OUT"'
echo "[PR1] probe_talon_part2.sh: which GPU request forms are accepted, one probe job, then the record"
cd "$T/repo" || exit 1
OUT="$(env FAKE_REFUSE_RE='--gpus' bash configs/talon/probe_talon_part2.sh 2>&1)"; RC=$?
chk "checks only: gres forms accepted, gpus forms refused, nothing submitted" '[ $RC -eq 0 ] && grep -q "accepted styles: gres " <<<"$OUT" && grep -q "refused   --gpus=1" <<<"$OUT" && grep -q "Nothing was submitted" <<<"$OUT" && [ ! -f talon_probe_job.txt ]'
draft; OUT="$(env FAKE_REFUSE_RE='--gpus' bash configs/talon/probe_talon_part2.sh 2>&1)"; RC=$?
chk "the probe works on the DRAFT settings (it is how the values are found)" '[ $RC -eq 0 ] && grep -q "accepted styles" <<<"$OUT"'
reviewed
OUT="$(env FAKE_REFUSE_RE='--gpus' FAKE_JOBID=5151 QT_SUBMIT=yes bash configs/talon/probe_talon_part2.sh 2>&1)"; RC=$?
chk "QT_SUBMIT=yes submits one probe job with the first accepted form" '[ $RC -eq 0 ] && grep -q "^JOB=5151" talon_probe_job.txt && grep -q "^SPEC_USED=--gres=gpu:1" talon_probe_job.txt'
printf 'PROBE_START x\nPROBE_GPU GPU 0: NVIDIA H100 80GB HBM3 (UUID: GPU-0)\n' > qt_talon_probe_5151.log
OUT="$(bash configs/talon/probe_talon_part2.sh record 2>&1)"; RC=$?
chk "record refuses a probe log without PROBE_END" '[ $RC -ne 0 ] && grep -q "did not finish" <<<"$OUT"'
printf 'PROBE_DRIVER_LINE | NVIDIA-SMI 560.35  Driver Version: 560.35  CUDA Version: 12.6 |\nPROBE_NET huggingface 200\nPROBE_NET pypi 200\nPROBE_WHEEL vllm-0.19.1-cp38-abi3-manylinux1_x86_64.whl\nPROBE_END y\n' >> qt_talon_probe_5151.log
OUT="$(env FAKE_JOB_RUNNING=1 bash configs/talon/probe_talon_part2.sh record 2>&1)"; RC=$?
chk "record refuses while the probe job is still in the queue" '[ $RC -ne 0 ] && grep -q "still in the queue" <<<"$OUT"'
OUT="$(bash configs/talon/probe_talon_part2.sh record 2>&1)"; RC=$?
chk "record writes talon_verified.txt with PART2_OK, accepted styles, GPU name and network facts" '[ $RC -eq 0 ] && grep -q "^PART2_OK=yes" talon_verified.txt && grep -q "^GPU_STYLES_ACCEPTED=gres$" talon_verified.txt && grep -q "^GPU_NAME=NVIDIA H100 80GB HBM3$" talon_verified.txt && grep -q "^COMPUTE_NODE_PYPI=200" talon_verified.txt'
echo "[PR2] probe_talon.sh is read-only and finishes even when every cluster command is missing"
mkdir -p "$T/nonet"; printf '#!/bin/bash\necho "fake curl: no network in tests" >&2; exit 7\n' > "$T/nonet/curl"; chmod +x "$T/nonet/curl"
BEFORE="$(find "$T" -type f | wc -l)"
OUT="$(PATH="$T/nonet:$PATH" bash configs/talon/probe_talon.sh 2>&1)"; RC=$?
chk "probe_talon.sh exits 0, reaches its end and names the UNVERIFIED facts" '[ $RC -eq 0 ] && grep -q "END OF PROBE" <<<"$OUT" && grep -q "UNVERIFIED" <<<"$OUT"'
chk "it created no file" '[ "$(find "$T" -type f | wc -l)" = "$BEFORE" ]'
cd - >/dev/null || exit 1
echo "[PR3] prep_talon.sh and fetch_talon.sh guards (no network is used)"
rm -f "$STATE"
printf '#!/bin/bash\necho "stub fetch ran"; echo "OK: weights verified"\n' > "$T/stub_fetch.sh"
draft; OUT="$(env QT_CONFIRM_STORAGE=yes PREP_FETCH="$T/stub_fetch.sh" bash "$T/repo/configs/talon/prep_talon.sh" 2>&1)"; RC=$?
chk "prep refuses as a DRAFT" '[ $RC -ne 0 ] && grep -q "DRAFT" <<<"$OUT" && [ ! -f "$STATE" ]'
reviewed
OUT="$(env PREP_FETCH="$T/stub_fetch.sh" bash "$T/repo/configs/talon/prep_talon.sh" 2>&1)"; RC=$?
chk "prep refuses without QT_CONFIRM_STORAGE=yes (Talon storage rules are UNVERIFIED)" '[ $RC -ne 0 ] && grep -q "QT_CONFIRM_STORAGE=yes" <<<"$OUT" && [ ! -f "$STATE" ]'
OUT="$(env QT_CONFIRM_STORAGE=yes PREP_FETCH="$T/stub_fetch.sh" bash "$T/repo/configs/talon/prep_talon.sh" 2>&1)"; RC=$?; sleep 2
chk "prep checks the files, starts the download in the background and writes prep_state.txt" '[ $RC -eq 0 ] && grep -q "all scripts parse, no carriage returns" <<<"$OUT" && grep -q "^MODEL_REV=$REV" "$STATE" && grep -q "OK: weights verified" "$FLOG"'
OUT="$(env QT_CONFIRM_STORAGE=yes PREP_FETCH="$T/stub_fetch.sh" bash "$T/repo/configs/talon/prep_talon.sh" 2>&1)"; RC=$?
chk "a second prep is refused" '[ $RC -ne 0 ] && grep -q "already started" <<<"$OUT"'
OUT="$(env MODEL_REV=main bash "$T/repo/configs/talon/fetch_talon.sh" 2>&1)"; RC=$?
chk "fetch refuses a branch name instead of a commit hash" '[ $RC -ne 0 ] && grep -q "not a 40-character commit hash" <<<"$OUT"'
cp "$T/repo/configs/paths.yaml" "$T/paths.bak"; sed -i "s|^talon_models: .*|talon_models: $HOME/talon_models_test_never_created|" "$T/repo/configs/paths.yaml"
OUT="$(bash "$T/repo/configs/talon/fetch_talon.sh" 2>&1)"; RC=$?
chk "fetch refuses a models folder in the home directory without QT_ALLOW_HOME=yes" '[ $RC -ne 0 ] && grep -q "inside your home folder" <<<"$OUT" && [ ! -e "$HOME/talon_models_test_never_created" ]'
cp "$T/paths.bak" "$T/repo/configs/paths.yaml"
echo "[H1] file hygiene of the real repository's Talon folder"
BAD=""; for f in "$REPO"/configs/talon/*.sh "$REPO"/configs/talon/*.sbatch; do [ "$(tr -cd '\r' < "$f" | wc -c)" = 0 ] || BAD="$BAD $f"; bash -n "$f" || BAD="$BAD $f(syntax)"; done
chk "every Talon script has no carriage return and parses" '[ -z "$BAD" ]'
chk "no Redhawk script mentions talon (Redhawk is untouched)" '! grep -qil talon "$REPO"/configs/redhawk/*'
fi

echo "==== talon part $PART: $PASS passed, $FAIL failed ===="
[ "$FAIL" -eq 0 ]
