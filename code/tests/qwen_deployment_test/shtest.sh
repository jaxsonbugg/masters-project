#!/bin/bash
# Local test of the Redhawk job scripts with FAKE nvidia-smi / module / scontrol / llama-server (see README.md here).
# Usage: bash shtest.sh <work_dir> <part 1|2|3|4>   (parts 1-2: the single stages and gates; 3-4: the one-job pipeline;
#        each part takes a few minutes; the parts may run at the same time)
# Needs bash, GNU coreutils, curl and a python with httpx and pyyaml (OTT_TEST_PYTHON, as a bash-style path, or `python`).
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
S="${1:?give a work folder}"; PART="${2:-1}"; T="$S/shtest$PART"
PYEXE="${OTT_TEST_PYTHON:-$(command -v python)}"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  PASS  $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL  $1   $2"; }
chk() { if eval "$2"; then ok "$1"; else bad "$1" "(condition: $2)"; fi; }

setup() {
  rm -rf "$T"; mkdir -p "$T"/{bin,repo/data,rh/models,rh/teacher_outputs,rh/llama.cpp/build/bin,rh/venv/bin}
  cp -r "$REPO/code" "$REPO/configs" "$T/repo/"; cp -r "$REPO/data/prompts" "$T/repo/data/"
  sed -i "s|^redhawk_root: .*|redhawk_root: $T/rh|; s|^redhawk_repo: .*|redhawk_repo: $T/repo|; s|^redhawk_models: .*|redhawk_models: $T/rh/models|; s|^redhawk_outputs: .*|redhawk_outputs: $T/rh/teacher_outputs|" "$T/repo/configs/paths.yaml"
  echo "export PATH=\"$(dirname "$PYEXE"):\$PATH\"" > "$T/rh/venv/bin/activate"
  # fake programs
  printf '#!/bin/bash\nexit 0\n' > "$T/bin/module"
  cat > "$T/bin/scontrol" <<'EOF'
#!/bin/bash
echo "JobId=$3 JobName=x SubmitTime=2026-11-04T20:00:00 StartTime=2026-11-04T20:10:00 EndTime=Unknown"
EOF
  cat > "$T/bin/squeue" <<'EOF'
#!/bin/bash
echo "${FAKE_TIMELEFT:-23:00:00}"
EOF
  cat > "$T/bin/nvidia-smi" <<'EOF'
#!/bin/bash
args="$*"; n="${FAKE_GPUS:-2}"
if [ "$args" = "-L" ]; then
  [ "$n" -ge 1 ] && echo "GPU 0: Tesla V100-PCIE-16GB (UUID: GPU-aaa)"
  [ "$n" -ge 2 ] && echo "GPU 1: Tesla V100-PCIE-16GB (UUID: GPU-bbb)"; exit 0; fi
case "$args" in
  *"--query-gpu=memory.total"*) for i in $(seq 1 "$n"); do echo 16384; done ;;
  *"--query-gpu=index,name,memory.total,driver_version"*) echo "index, name, memory.total [MiB], driver_version"; echo "0, Tesla V100-PCIE-16GB, 16384 MiB, 535.1"; echo "1, Tesla V100-PCIE-16GB, 16384 MiB, 535.1" ;;
  *"--query-gpu=timestamp,index,memory.used"*) ts="$(date +'%Y/%m/%d %H:%M:%S').000"; used0="${FAKE_USED0:-12000}"
    if [ "${QT_STAGE:-}" = B ] && [ -n "${FAKE_USED0_B:-}" ]; then used0="$FAKE_USED0_B"; fi   # a different level only in Stage B
    echo "$ts, 0, $used0, 16384, 50"; echo "$ts, 1, ${FAKE_USED1:-11000}, 16384, 49" ;;
esac
exit 0
EOF
  cat > "$T/bin/llama-server" <<'EOF'
#!/bin/bash
for a in "$@"; do [ "$a" = "--help" ] && { cat "$FAKE_HELP"; exit 0; }; done
port=""; prev=""; for a in "$@"; do [ "$prev" = "--port" ] && port="$a"; prev="$a"; done
echo "print_info: arch             = qwen35"; echo "load_tensors:      CUDA0 model buffer size =  8000.00 MiB"; echo "load_tensors:      CUDA1 model buffer size =  8000.00 MiB"
echo "args: $*"
FAKE_SERVER_ARGS="$*" exec "$PYEXE" "$FAKE_SERVER" "$port"
EOF
  chmod +x "$T"/bin/*; cp "$T/bin/llama-server" "$T/rh/llama.cpp/build/bin/llama-server"
  cat > "$T/help.txt" <<'EOF'
  -m,    --model FNAME                    model path
  -a,    --alias STRING                   set model name aliases
         --host HOST                      listen on
         --port PORT                      port
  -ngl,  --gpu-layers, --n-gpu-layers N   layers in VRAM
  -sm,   --split-mode {none,layer,row}    split mode
  -ts,   --tensor-split N0,N1,N2,...      fraction per GPU
  -fa,   --flash-attn [on|off|auto]       flash attention
  -c,    --ctx-size N                     context size
  -np,   --parallel N                     server slots
         --jinja, --no-jinja              jinja
         --chat-template-file FILE        template file
         --reasoning-format FORMAT        reasoning format
EOF
  head -c 3000 /dev/urandom > "$T/rh/models/Qwen3.6-27B-Q4_K_M.gguf"
  echo "fake template" > "$T/rh/models/qwen3.6-27b_chat_template.jinja"
  sha256sum "$T/rh/models/qwen3.6-27b_chat_template.jinja" | cut -d' ' -f1 > "$T/rh/models/chat_template.sha256"
  echo "b11960 fakecommit000" > "$T/rh/llama_cpp_version.txt"
  export PATH="$T/bin:$PATH" QT_TEST_MODE=1 TEST_LLAMA_COMMIT=fakecommit000 MOD_CUDA=cuda/12.4 MOD_GCC=gcc MOD_CMAKE=cmake MOD_PYTHON= \
         SLURM_SUBMIT_DIR="$T/repo" FAKE_HELP="$T/help.txt" PYEXE="$PYEXE" FAKE_SERVER="$(cygpath -m "$HERE/fake_server.py" 2>/dev/null || echo "$HERE/fake_server.py")" FAKE_STATE="$T/state"
  export TEST_GGUF_BYTES="$(stat -c %s "$T/rh/models/Qwen3.6-27B-Q4_K_M.gguf")" TEST_GGUF_SHA256="$(sha256sum "$T/rh/models/Qwen3.6-27B-Q4_K_M.gguf" | cut -d' ' -f1)"
}
JOBN=1000
sub() {  # sub <wrapper> [VAR=value ...]  -> runs a wrapper like Slurm would, sets RC and OUT
  local w="$1"; shift; JOBN=$((JOBN+1))
  OUT="$(env SLURM_JOB_ID=$JOBN "$@" bash "$T/repo/configs/redhawk/$w" 2>&1)"; RC=$?
}
RES="$T/rh/teacher_outputs/stage_results"
val() { sed -n "s/^$2=//p" "$1" | tail -n 1; }

if [ "$PART" = 1 ]; then
setup
echo "[S1] Stage A, healthy"
sub gpu_smoke_a.sbatch; echo "$OUT" | tail -n 14
chk "Stage A exits 0 with RESULT: PASS" '[ $RC -eq 0 ] && grep -q "RESULT: PASS (stage A)" <<<"$OUT"'
chk "result file says PASS, Stage B allowed, 4384 MiB free (min over GPUs: 16384-12000)" '[ "$(val $RES/stageA.txt RESULT)" = PASS ] && [ "$(val $RES/stageA.txt STAGE_B_ALLOWED)" = yes ] && [ "$(val $RES/stageA.txt MIN_FREE_MIB)" = 4384 ]'
chk "peak memory per GPU is reported from the correct CSV columns" 'grep -q "gpu 0 peak_used_MiB 12000 total_MiB 16384 min_free_MiB 4384" <<<"$OUT" && grep -q "gpu 1 peak_used_MiB 11000 total_MiB 16384 min_free_MiB 5384" <<<"$OUT"'
chk "queue wait comes from scontrol (600 s), not an assumed variable" 'grep -q "waited 600s" <<<"$OUT"'
chk "validation ran and passed in Stage A" 'grep -q "VALIDATE_RESULT infra=PASS quality_replies=0 replies=2" <<<"$OUT"'
chk "the client received the queue times and llama.cpp commit as metadata" 'grep -q "fakecommit000" $(ls -d $T/rh/teacher_outputs/*smokeA*)/run_log.json && grep -q "queue_wait_seconds" $(ls -d $T/rh/teacher_outputs/*smokeA*)/run_log.json'
chk "Stage A used only development slots BM9001-BM9002" 'grep -q "BM9001" $(ls -d $T/rh/teacher_outputs/*smokeA*)/responses.jsonl && ! grep -q "BM002" $(ls -d $T/rh/teacher_outputs/*smokeA*)/responses.jsonl'
echo "[S2] Stage B, healthy"
sub gpu_smoke_b.sbatch; chk "Stage B passes" '[ $RC -eq 0 ] && grep -q "RESULT: PASS (stage B)" <<<"$OUT"'
echo "[S3] main run 40960/2 after a passing Stage B"
sub qwen_test.sbatch QT_CTX=40960 QT_PARALLEL=2; echo "$OUT" | tail -n 8
MAIN="$(ls -d $T/rh/teacher_outputs/*_test01 2>/dev/null | head -1)"
chk "main run exits 0 and validates (mandatory validation ran)" '[ $RC -eq 0 ] && grep -q "VALIDATE_RESULT infra=PASS quality_replies=0 replies=100" <<<"$OUT"'
chk "main run saved exactly 100 replies, one per slot BM0021-BM0120" '[ "$(wc -l < $MAIN/responses.jsonl)" = 100 ] && [ "$(grep -o "\"item_id\": \"BM[0-9]*\"" $MAIN/responses.jsonl | sort -u | wc -l)" = 100 ] && ! grep -q "BM9" $MAIN/responses.jsonl'
chk "a main summary file was written and no stage file was overwritten" '[ -f $RES/main_job1003.txt ] && [ "$(val $RES/stageB.txt JOB)" = 1002 ]'
echo "[S4] a second main submission without resume is refused by the client, and the job says so"
sub qwen_test.sbatch QT_CTX=40960 QT_PARALLEL=2
chk "refused: exit 1, FAIL_INFRA, nothing validated as a pass" '[ $RC -eq 1 ] && grep -q "RESULT: FAIL_INFRA" <<<"$OUT" && grep -q "main run folder already exists" <<<"$OUT"'
chk "the first main run is untouched (still 100 rows)" '[ "$(wc -l < $MAIN/responses.jsonl)" = 100 ]'
echo "[S5] gates and prerequisites stop the job before anything is sent"
sub qwen_test.sbatch QT_CTX=20480 QT_PARALLEL=1 QT_FA=off; chk "wrong flash-attention mode is refused" '[ $RC -ne 0 ] && grep -q "passed with flash-attn auto, not off" <<<"$OUT"'
sub qwen_test.sbatch QT_CTX=1234 QT_PARALLEL=1; chk "an untested context is refused" '[ $RC -ne 0 ] && grep -q "may only repeat a tested setting" <<<"$OUT"'
sub qwen_test.sbatch; chk "no explicit setting is refused" '[ $RC -ne 0 ] && grep -q "pass the tested setting" <<<"$OUT"'
cp $RES/stageA.txt $RES/stageA.bak; sed -i 's/^RESULT=.*/RESULT=FAIL_INFRA/' $RES/stageA.txt
sub gpu_smoke_b.sbatch; chk "Stage B refuses after a failed Stage A" '[ $RC -ne 0 ] && grep -q "needs a passing Stage A" <<<"$OUT"'
sub qwen_test.sbatch QT_CTX=20480 QT_PARALLEL=1; chk "main 20480/1 refuses after a failed Stage A" '[ $RC -ne 0 ] && grep -q "Stage A did not pass" <<<"$OUT"'
cp $RES/stageA.bak $RES/stageA.txt
sub gpu_smoke_a.sbatch FAKE_GPUS=1; chk "one visible GPU stops the job" '[ $RC -ne 0 ] && grep -q "expected exactly 2 visible GPUs" <<<"$OUT"'
cp "$T/help.txt" "$T/help.bak"; grep -v -- "--chat-template-file" "$T/help.bak" > "$T/help.txt"
sub gpu_smoke_a.sbatch; chk "a llama-server without a required flag stops the job" '[ $RC -ne 0 ] && grep -q "does not list: --chat-template-file" <<<"$OUT"'
cp "$T/help.bak" "$T/help.txt"
cp "$T/rh/models/Qwen3.6-27B-Q4_K_M.gguf" "$T/gguf.bak"; printf 'x' >> "$T/rh/models/Qwen3.6-27B-Q4_K_M.gguf"
sub gpu_smoke_a.sbatch; chk "a weights file of the wrong size stops the job" '[ $RC -ne 0 ] && grep -q "wrong size" <<<"$OUT"'
head -c "$TEST_GGUF_BYTES" /dev/urandom > "$T/rh/models/Qwen3.6-27B-Q4_K_M.gguf"
sub gpu_smoke_a.sbatch; chk "a weights file with the right size but the wrong SHA-256 stops the job" '[ $RC -ne 0 ] && grep -q "SHA-256 mismatch" <<<"$OUT"'
cp "$T/gguf.bak" "$T/rh/models/Qwen3.6-27B-Q4_K_M.gguf"
echo "changed" >> "$T/rh/models/qwen3.6-27b_chat_template.jinja"
sub gpu_smoke_a.sbatch; chk "a changed chat template stops the job" '[ $RC -ne 0 ] && grep -q "chat template hash differs" <<<"$OUT"'
echo "fake template" > "$T/rh/models/qwen3.6-27b_chat_template.jinja"
echo "b11960 deadbeef" > "$T/rh/llama_cpp_version.txt"
sub gpu_smoke_a.sbatch; chk "a different llama.cpp commit stops the job" '[ $RC -ne 0 ] && grep -q "is not the pinned" <<<"$OUT"'
echo "b11960 fakecommit000" > "$T/rh/llama_cpp_version.txt"
sub gpu_smoke_a.sbatch MOD_CUDA=; chk "an empty CUDA module name stops the job" '[ $RC -ne 0 ] && grep -q "MOD_CUDA is empty" <<<"$OUT"'
echo "[S10] the module command is defined when a batch shell lacks it, and the verified module names are the defaults"
mkdir -p "$T/fakemod/init"; printf 'module() { echo "FAKEMODULE $*"; }
' > "$T/fakemod/init/bash"
M="$(env -i PATH=/usr/bin:/bin MODULESHOME="$T/fakemod" bash -c "source $T/repo/configs/redhawk/common.sh; set -u; load_modules; echo loaded" 2>&1)"
chk "module is defined from \$MODULESHOME/init/bash and loads gcc-12.2.0, cmake-3.31.2 and cuda-12.2 by default" 'grep -q "FAKEMODULE load gcc-12.2.0" <<<"$M" && grep -q "FAKEMODULE load cmake-3.31.2" <<<"$M" && grep -q "FAKEMODULE load cuda-12.2" <<<"$M" && grep -q "^loaded" <<<"$M"'
M="$(env -i PATH=/usr/bin:/bin bash -c "source $T/repo/configs/redhawk/common.sh; set -u; load_modules; echo loaded" 2>&1)"
chk "with no module command and no init file the job stops with a clear message" '! grep -q "^loaded" <<<"$M" && grep -q "the .module. command is not available" <<<"$M"'
fi

if [ "$PART" = 2 ]; then
setup
echo "[S6] every smoke reply is a model-quality failure: infrastructure passes, a person must acknowledge"
sub gpu_smoke_a.sbatch FAKE_MODE=badjson; echo "$OUT" | tail -n 6
chk "Stage A: PASS_QUALITY_WARN (a result, not a fault), exit 0" '[ $RC -eq 0 ] && grep -q "RESULT: PASS_QUALITY_WARN" <<<"$OUT" && [ "$(val $RES/stageA.txt INFRA)" = PASS ] && [ "$(val $RES/stageA.txt QUALITY_ALL)" = yes ]'
sub gpu_smoke_b.sbatch FAKE_MODE=badjson; chk "Stage B refuses without QT_ACK_QUALITY" '[ $RC -ne 0 ] && grep -q "had a model-quality finding" <<<"$OUT"'
sub gpu_smoke_b.sbatch FAKE_MODE=badjson QT_ACK_QUALITY=yes; chk "Stage B proceeds once a person acknowledged" '[ $RC -eq 0 ] && grep -q "RESULT: PASS_QUALITY_WARN (stage B)" <<<"$OUT"'
echo "[S7] low GPU memory"
rm -rf "$RES"; sub gpu_smoke_a.sbatch FAKE_USED0=14000
chk "Stage A passes but leaves under 3 GB free: Stage B not allowed" '[ $RC -eq 0 ] && [ "$(val $RES/stageA.txt STAGE_B_ALLOWED)" = no ] && [ "$(val $RES/stageA.txt MIN_FREE_MIB)" = 2384 ]'
sub gpu_smoke_b.sbatch; chk "Stage B refuses" '[ $RC -ne 0 ] && grep -q "left under 3 GB free" <<<"$OUT"'
sed -i 's/^STAGE_B_ALLOWED=.*/STAGE_B_ALLOWED=yes/' $RES/stageA.txt
sub gpu_smoke_b.sbatch FAKE_USED0=15800; chk "Stage B with under 1 GiB free is an INFRASTRUCTURE failure" '[ $RC -eq 1 ] && grep -q "RESULT: FAIL_INFRA" <<<"$OUT" && grep -q "under 1 GiB free" <<<"$OUT"'
echo "[S8] the server dies while loading"
rm -rf "$RES"; sub gpu_smoke_a.sbatch FAKE_DIE=1; chk "reported as an infrastructure failure with a result file" '[ $RC -eq 3 ] && grep -q "llama-server exited while loading" <<<"$OUT" && [ "$(val $RES/stageA.txt RESULT)" = FAIL_INFRA ]'
echo "[S9] an incomplete main run, then a deliberate resume"
rm -rf "$RES" "$T/rh/teacher_outputs"/*_test* "$T/state".*; sub gpu_smoke_a.sbatch >/dev/null; sub gpu_smoke_b.sbatch >/dev/null
sub qwen_test.sbatch QT_CTX=40960 QT_PARALLEL=2 FAKE_FAIL_ITEM=BM0050
MAIN="$(ls -d $T/rh/teacher_outputs/*_test01 | head -1)"
chk "one errored slot makes the run INCOMPLETE: FAIL_INFRA, exit 1, with a resume hint" '[ $RC -eq 1 ] && grep -q "INCOMPLETE" <<<"$OUT" && grep -q "QT_RESUME=" <<<"$OUT" && [ "$(wc -l < $MAIN/responses.jsonl)" = 100 ]'
sub qwen_test.sbatch QT_CTX=40960 QT_PARALLEL=2 QT_RESUME="$(cygpath -m "$MAIN")" FAKE_FAIL_ITEM=BM0050
chk "resume WITHOUT QT_RETRY_ERRORS does not re-send the errored slot" 'grep -q "errored earlier and are NOT" <<<"$OUT" && [ "$RC" -eq 1 ] && [ "$(wc -l < $MAIN/responses.jsonl)" = 100 ]'
sub qwen_test.sbatch QT_CTX=40960 QT_PARALLEL=2 QT_RESUME="$(cygpath -m "$MAIN")" QT_RETRY_ERRORS=yes FAKE_FAIL_ITEM=BM0050
chk "resume WITH QT_RETRY_ERRORS re-sends only that slot (attempt 2); the run then validates clean" '[ $RC -eq 0 ] && [ "$(wc -l < $MAIN/responses.jsonl)" = 101 ] && grep -q "VALIDATE_RESULT infra=PASS quality_replies=0 replies=100" <<<"$OUT" && [ ! -f $MAIN/run.lock ]'
fi

reset_state() { rm -rf "$T/rh/teacher_outputs"/* "$T/state".*; }
LOGS="$T/rh/teacher_outputs/job_logs"
main_dir() { ls -d "$T"/rh/teacher_outputs/*_test01 2>/dev/null | head -n 1; }

if [ "$PART" = 3 ]; then
setup
echo "[P1] pipeline, healthy: A, B, then the main run at 40960/2"
reset_state; sub qwen_pipeline.sbatch; SUMM="$RES/pipeline_job$JOBN.txt"; echo "$OUT" | tail -n 4
chk "exits 0 and the summary says COMPLETE" '[ $RC -eq 0 ] && [ "$(val $SUMM PIPELINE_RESULT)" = COMPLETE ]'
chk "settings recorded: main 40960/2, flash-attn auto, no fallback, B passed" '[ "$(val $SUMM MAIN_SETTING)" = 40960/2 ] && [ "$(val $SUMM FA_MODE)" = auto ] && [ "$(val $SUMM FA_FALLBACK_USED)" = no ] && [ "$(val $SUMM STAGE_B)" = passed ]'
chk "stage A and B passed in this job and the main result is PASS" 'grep -q "^STAGE_A_RESULT=PASS (job $JOBN)" $SUMM && grep -q "^STAGE_B_RESULT=PASS (job $JOBN)" $SUMM && grep -q "^MAIN_RESULT=PASS " $SUMM'
M="$(main_dir)"; chk "the main run folder has exactly 100 replies and no development slots" '[ "$(wc -l < $M/responses.jsonl)" = 100 ] && ! grep -q "BM9" $M/responses.jsonl'
chk "the three stages wrote SEPARATE server logs, memory logs and validation logs" 'for s in A B main; do [ -s $LOGS/llama_server_${JOBN}_$s.log ] && [ -s $LOGS/gpu_memory_${JOBN}_$s.csv ] && [ -s $LOGS/validate_${JOBN}_$s.out ] || exit 1; done'
chk "each stage left its own result file" '[ -f $RES/stageA_job$JOBN.txt ] && [ -f $RES/stageB_job$JOBN.txt ] && [ -f $RES/main_job$JOBN.txt ] && [ "$(val $RES/stageA.txt LOGTAG)" = ${JOBN}_A ]'
echo "[P2] low GPU memory after Stage A: Stage B is skipped, main runs at 20480/1"
reset_state; sub qwen_pipeline.sbatch FAKE_USED0=14000; SUMM="$RES/pipeline_job$JOBN.txt"
chk "COMPLETE, B skipped with the reason, main at 20480/1" '[ $RC -eq 0 ] && [ "$(val $SUMM MAIN_SETTING)" = 20480/1 ] && grep -q "^STAGE_B=skipped" $SUMM && [ ! -f $RES/stageB.txt ]'
M="$(main_dir)"; chk "the main run still has 100 replies" '[ "$(wc -l < $M/responses.jsonl)" = 100 ]'
echo "[P3] Stage B fails on infrastructure: the pipeline falls back to the tested single-sequence setting"
reset_state; sub qwen_pipeline.sbatch FAKE_USED0_B=15800; SUMM="$RES/pipeline_job$JOBN.txt"
chk "B is FAIL_INFRA, main runs at 20480/1, the summary says why, exit 0" '[ $RC -eq 0 ] && [ "$(val $RES/stageB.txt RESULT)" = FAIL_INFRA ] && [ "$(val $SUMM MAIN_SETTING)" = 20480/1 ] && grep -q "^STAGE_B=failed on infrastructure" $SUMM'
echo "[P4] Stage A fails: nothing else runs"
reset_state; sub qwen_pipeline.sbatch FAKE_GPUS=1; SUMM="$RES/pipeline_job$JOBN.txt"
chk "STOPPED_AT_A, non-zero exit, no Stage B file, no main run folder" '[ $RC -ne 0 ] && [ "$(val $SUMM PIPELINE_RESULT)" = STOPPED_AT_A ] && [ ! -f $RES/stageB.txt ] && [ -z "$(main_dir)" ]'
chk "the summary names where to look" 'grep -q "Read " $SUMM || grep -q "Stage A failed" $SUMM'
fi

if [ "$PART" = 4 ]; then
setup
echo "[P5] every smoke reply is a model-quality finding: stops unless a person acknowledged"
reset_state; sub qwen_pipeline.sbatch FAKE_MODE=badjson; SUMM="$RES/pipeline_job$JOBN.txt"
chk "STOPPED_QUALITY after Stage A, non-zero exit, no Stage B, no main run" '[ $RC -ne 0 ] && [ "$(val $SUMM PIPELINE_RESULT)" = STOPPED_QUALITY ] && [ ! -f $RES/stageB.txt ] && [ -z "$(main_dir)" ]'
reset_state; sub qwen_pipeline.sbatch FAKE_MODE=badjson QT_ACK_QUALITY=yes; SUMM="$RES/pipeline_job$JOBN.txt"
chk "with QT_ACK_QUALITY=yes it continues to COMPLETE (the main run's findings are results, not faults)" '[ $RC -eq 0 ] && [ "$(val $SUMM PIPELINE_RESULT)" = COMPLETE ] && grep -q "^MAIN_RESULT=PASS_QUALITY_WARN" $SUMM'
echo "[P6] flash attention crashes with -fa auto: ONE retry with it off, used for B and main"
reset_state; sub qwen_pipeline.sbatch FAKE_FA_CRASH=1; SUMM="$RES/pipeline_job$JOBN.txt"; echo "$OUT" | grep -E "Retrying ONCE|PIPELINE" | head -n 3
chk "COMPLETE with the fallback recorded: FA_MODE off, FA_FALLBACK_USED yes" '[ $RC -eq 0 ] && [ "$(val $SUMM PIPELINE_RESULT)" = COMPLETE ] && [ "$(val $SUMM FA_MODE)" = off ] && [ "$(val $SUMM FA_FALLBACK_USED)" = yes ]'
chk "both Stage A attempts are on record in separate logs and result files" '[ -s $LOGS/llama_server_${JOBN}_A.log ] && [ -s $LOGS/llama_server_${JOBN}_A_2.log ] && grep -q "fattn.cu" $LOGS/llama_server_${JOBN}_A.log && [ -f $RES/stageA_job$JOBN.txt ] && [ -f $RES/stageA_job${JOBN}_2.txt ] && [ "$(val $RES/stageA_job$JOBN.txt RESULT)" = FAIL_INFRA ]'
M="$(main_dir)"; chk "the main run was served with flash attention OFF and says so in its run log" 'grep -q "\"flash_attn\": \"off\"" $M/run_log.json && [ "$(val $RES/stageA.txt FA)" = off ] && [ "$(val $RES/stageB.txt FA)" = off ]'
echo "[P7] the same crash with an EXPLICIT flash-attn setting is never overridden"
reset_state; sub qwen_pipeline.sbatch FAKE_FA_CRASH=1 QT_FA=on; SUMM="$RES/pipeline_job$JOBN.txt"
chk "STOPPED_AT_A, no fallback, no second attempt" '[ $RC -ne 0 ] && [ "$(val $SUMM PIPELINE_RESULT)" = STOPPED_AT_A ] && [ "$(val $SUMM FA_FALLBACK_USED)" = no ] && [ ! -e $LOGS/llama_server_${JOBN}_A_2.log ]'
echo "[P8] too little time left for the main run: it is not started"
reset_state; sub qwen_pipeline.sbatch FAKE_TIMELEFT=02:00:00; SUMM="$RES/pipeline_job$JOBN.txt"
chk "STOPPED_TIME, non-zero exit, no main run folder, and the resume command is printed" '[ $RC -ne 0 ] && [ "$(val $SUMM PIPELINE_RESULT)" = STOPPED_TIME ] && [ -z "$(main_dir)" ] && grep -q "qwen_test.sbatch" <<<"$OUT" && grep -q "QT_CTX=40960,QT_PARALLEL=2" <<<"$OUT"'
chk "stages A and B did pass before the stop" 'grep -q "^STAGE_A_RESULT=PASS" $SUMM && grep -q "^STAGE_B_RESULT=PASS" $SUMM'
echo "[P9] the time-left parser (the formats squeue prints)"
pt() { bash -c "source $T/repo/configs/redhawk/common.sh; parse_slurm_time '$1'"; }
chk "1-02:03:04 is 93784 s, 23:59:59 is 86399, 00:08:09 is 489 (no octal trap), 59:59 is 3599" '[ "$(pt 1-02:03:04)" = 93784 ] && [ "$(pt 23:59:59)" = 86399 ] && [ "$(pt 00:08:09)" = 489 ] && [ "$(pt 59:59)" = 3599 ]'
chk "UNLIMITED, INVALID and empty text give -1 (unknown)" '[ "$(pt UNLIMITED)" = -1 ] && [ "$(pt INVALID)" = -1 ] && [ "$(pt "")" = -1 ]'
fi
rm -rf "$T"
echo "==== part $PART: $PASS passed, $FAIL failed ===="
[ "$FAIL" -eq 0 ]
