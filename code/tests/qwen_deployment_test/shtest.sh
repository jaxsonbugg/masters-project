#!/bin/bash
# Local test of the Redhawk job scripts with FAKE nvidia-smi / module / scontrol / llama-server (see README.md here).
# Usage: bash shtest.sh <work_dir> <part 1|2|3|4|5>   (parts 1-2: the single stages and gates; 3-4: the one-job pipeline; 5: prep and submit scripts;
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
chk() { if eval "$2"; then ok "$1"; else bad "$1" "(condition: $2)"; [ -z "${SHOW_OUT_ON_FAIL:-}" ] || { echo "    --- captured output of the last command:"; echo "$OUT" | tail -n 14 | sed 's/^/    | /'; }; fi; }

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
case "$*" in
  *"%L"*) echo "${FAKE_TIMELEFT:-23:00:00}" ;;
  *"-n qt_pipeline"*) [ -n "${FAKE_PIPE_QUEUED:-}" ] && echo "9999 qt_pipeline PD" ;;
  *"-j"*) [ -n "${FAKE_BUILD_QUEUED:-}" ] && echo "5555 R" ;;
esac
exit 0
EOF
  cat > "$T/bin/sbatch" <<'EOF'
#!/bin/bash
if [[ "$*" == *"--test-only"* ]]; then
  if [ "${FAKE_TESTONLY_FAIL:-}" = 1 ]; then echo "sbatch: error: Batch job submission failed: Invalid generic resource (gres) specification"; exit 1; fi
  echo "sbatch: Job 99 to start at 2026-11-17T15:33:21 using 24 processors on nodes mualhpcp38.mpi in partition gpu"; exit 0
fi
if [ "${FAKE_SBATCH_FAIL:-}" = 1 ]; then echo "sbatch: error: Batch job submission failed"; exit 1; fi
echo "$*" >> "${FAKE_SBATCH_LOG:-/dev/null}"
echo "Submitted batch job ${FAKE_JOBID:-5555}"
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
if [ "${FAKE_NEEDS_DRIVER:-}" = 1 ]; then
  have=no; IFS=: read -ra D <<<"${LD_LIBRARY_PATH:-}"
  for d in "${D[@]}"; do [ -e "$d/libcuda.so.1" ] && have=yes; done
  if [ "$have" = no ]; then echo "./llama-server: error while loading shared libraries: libcuda.so.1: cannot open shared object file: No such file or directory"; exit 127; fi
fi
for a in "$@"; do [ "$a" = "--version" ] && { echo "version: 1 (fakecommit000)"; exit 0; }; done
for a in "$@"; do [ "$a" = "--help" ] && { cat "$FAKE_HELP"; exit 0; }; done
port=""; prev=""; for a in "$@"; do [ "$prev" = "--port" ] && port="$a"; prev="$a"; done
echo "0.01.562.689 I srv  llama_server: initializing ..."; echo "0.09.817.908 I srv  server_run_i: model loaded"   # the REAL b11960 log has no architecture or CUDA0/CUDA1 lines
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
echo "[S11] the both-GPUs check rests on measured memory, not on log wording (job 2510690 died on a log-wording check)"
cp $RES/stageA.txt $RES/stageA.keep
sub gpu_smoke_a.sbatch FAKE_USED1=200; chk "model on only one GPU (GPU 1 holds 200 MiB): FAIL_INFRA, exit 3, nothing sent" '[ $RC -eq 3 ] && grep -q "the model is not on both GPUs" <<<"$OUT" && grep -q "gpu 1 in_use_MiB 200" <<<"$OUT" && [ "$(val $RES/stageA.txt RESULT)" = FAIL_INFRA ]'
sub gpu_smoke_a.sbatch; chk "the fake server log has no arch/CUDA0/CUDA1 lines (like the real build) and Stage A still passes" '[ $RC -eq 0 ] && grep -q "RESULT: PASS (stage A)" <<<"$OUT" && grep -q "model is on both GPUs" <<<"$OUT" && grep -q "gpu 0 in_use_MiB 12000" <<<"$OUT"'
printf 'timestamp,gpu,mem_used_mib,mem_total_mib,util_pct\n2026/11/05 09:35:11.178, 0, 7698, 16384, 0\n2026/11/05 09:35:11.180, 1, 8270, 16384, 38\n2026/11/05 09:35:13.223, 0, 8790, 16384, 1\n2026/11/05 09:35:13.224, 1, 9226, 16384, 0\n' > "$T/real_mem.csv"
OUT="$(bash -c "source $T/repo/configs/redhawk/common.sh; gpus_hold_model $T/real_mem.csv 4096; echo rc=\$?" 2>&1)"
chk "the real readings of job 2510690 (8790 and 9226 MiB) pass the check" 'grep -q "gpu 0 in_use_MiB 8790" <<<"$OUT" && grep -q "gpu 1 in_use_MiB 9226" <<<"$OUT" && grep -q "rc=0" <<<"$OUT"'
printf 'timestamp,gpu,mem_used_mib,mem_total_mib,util_pct\n2026/11/05 09:35:11.178, 0, 9000, 16384, 0\n' > "$T/one_gpu.csv"
OUT="$(bash -c "source $T/repo/configs/redhawk/common.sh; gpus_hold_model $T/one_gpu.csv 4096; echo rc=\$?" 2>&1)"
chk "a CSV with samples from only one GPU fails the check" 'grep -q "rc=1" <<<"$OUT"'
cp $RES/stageA.keep $RES/stageA.txt
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

if [ "$PART" = 5 ]; then
setup
STATE_F="$T/rh/prep_state.txt"; WLOG_F="$T/rh/fetch_weights.log"; BLOG_F="$T/repo/qt_build_5555.log"
printf '#!/bin/bash\necho "stub fetch_source ran"\nexit 0\n' > "$T/stub_fs.sh"
printf '#!/bin/bash\necho "stub download"\necho "OK: weights verified"\n' > "$T/stub_fw.sh"
prep() { env QT_PREP_AGAIN="${QT_PREP_AGAIN:-}" PREP_FETCH_SOURCE="$T/stub_fs.sh" PREP_FETCH_WEIGHTS="$T/stub_fw.sh" "$@" bash "$T/repo/configs/redhawk/prep_cluster.sh" 2>&1; }
fresh() { rm -f "$STATE_F" "$WLOG_F" "$BLOG_F" "$T/rh/pipeline.log"; }

echo "[Q1] prep_cluster.sh: the first run"
fresh; OUT="$(prep)"; RC=$?; echo "$OUT" | tail -n 6 | cut -c1-150
for i in 1 2 3 4 5 6; do grep -q "OK: weights verified" "$WLOG_F" 2>/dev/null && break; sleep 1; done
chk "exits 0, checks the files, runs fetch_source, submits the build job and reports its number" '[ $RC -eq 0 ] && grep -q "prompt file hash matches" <<<"$OUT" && grep -q "stub fetch_source ran" <<<"$OUT" && grep -q "Submitted batch job 5555" <<<"$OUT"'
chk "the download was started in the background and wrote its own log" 'grep -q "OK: weights verified" "$WLOG_F"'
chk "the state file records the build job and the log path" 'grep -q "^BUILD_JOB=5555" "$STATE_F" && grep -q "^WEIGHTS_LOG=" "$STATE_F"'
chk "it tells the user what to run next" 'grep -q "submit_pipeline.sh" <<<"$OUT" && grep -q "qt_build_5555.log" <<<"$OUT"'
echo "[Q2] a second run is refused so nothing is submitted twice"
OUT="$(prep)"; RC=$?; chk "refused, and no second build job number appears" '[ $RC -ne 0 ] && grep -q "already started" <<<"$OUT" && ! grep -q "Submitted batch job" <<<"$OUT"'
QT_PREP_AGAIN=yes OUT="$(QT_PREP_AGAIN=yes prep)"; RC=$?; chk "QT_PREP_AGAIN=yes allows a deliberate repeat" '[ $RC -eq 0 ] && grep -q "Submitted batch job" <<<"$OUT"'
echo "[Q3] damaged copies stop everything before anything is started"
fresh; cp "$T/repo/configs/redhawk/common.sh" "$T/common.bak"; printf 'echo hi\r\n' >> "$T/repo/configs/redhawk/common.sh"
OUT="$(prep)"; RC=$?; chk "a Windows line ending in a script is refused, nothing submitted, no state file" '[ $RC -ne 0 ] && grep -q "carriage return" <<<"$OUT" && ! grep -q "Submitted batch job" <<<"$OUT" && [ ! -f "$STATE_F" ]'
cp "$T/common.bak" "$T/repo/configs/redhawk/common.sh"
cp "$T/repo/data/prompts/benchmark_generation_v6.md" "$T/prompt.bak"; echo "x" >> "$T/repo/data/prompts/benchmark_generation_v6.md"
fresh; OUT="$(prep)"; RC=$?; chk "a prompt file that differs from the pinned v6 hash is refused" '[ $RC -ne 0 ] && grep -q "pinned SHA-256" <<<"$OUT" && [ ! -f "$STATE_F" ]'
cp "$T/prompt.bak" "$T/repo/data/prompts/benchmark_generation_v6.md"
fresh; OUT="$(prep FAKE_SBATCH_FAIL=1)"; RC=$?; chk "if sbatch gives no job number, the download is NOT started and there is no state file" '[ $RC -ne 0 ] && [ ! -f "$WLOG_F" ] && [ ! -f "$STATE_F" ]'
printf '#!/bin/bash\necho "git clone failed"\nexit 1\n' > "$T/stub_fs_fail.sh"
fresh; OUT="$(env PREP_FETCH_SOURCE="$T/stub_fs_fail.sh" PREP_FETCH_WEIGHTS="$T/stub_fw.sh" bash "$T/repo/configs/redhawk/prep_cluster.sh" 2>&1)"; RC=$?
chk "if fetch_source fails nothing else starts (no build job, no download)" '[ $RC -ne 0 ] && ! grep -q "Submitted batch job" <<<"$OUT" && [ ! -f "$WLOG_F" ]'

echo "[Q4] submit_pipeline.sh: checks first, submits only when everything is ready"
sp() { env QT_SUBMIT="${QT_SUBMIT:-}" "$@" bash "$T/repo/configs/redhawk/submit_pipeline.sh" 2>&1; }
ready() { rm -f "$STATE_F"; echo "BUILD_JOB=5555" > "$STATE_F"; echo "REPO=$T/repo" >> "$STATE_F"; echo "BUILD OK" > "$BLOG_F"; printf 'download\nOK: weights verified\n' > "$WLOG_F"; }
ready; OUT="$(sp)"; RC=$?; echo "$OUT" | tail -n 5 | cut -c1-140
chk "everything ready, no QT_SUBMIT: the checks pass, the scheduler's estimate is shown, NOTHING is submitted" '[ $RC -eq 0 ] && grep -q "All checks passed" <<<"$OUT" && grep -q "to start at 2026-11-17" <<<"$OUT" && ! grep -q "PIPELINE_JOB" "$STATE_F"'
ready; : > "$T/sbatch.log"; OUT="$(QT_SUBMIT=yes sp FAKE_JOBID=7777 FAKE_SBATCH_LOG="$T/sbatch.log")"; RC=$?
chk "with QT_SUBMIT=yes it submits once, records the job and prints the monitoring commands" '[ $RC -eq 0 ] && grep -q "^PIPELINE_JOB=7777" "$STATE_F" && grep -q "scancel 7777" <<<"$OUT" && [ "$(grep -c "qwen_pipeline.sbatch" "$T/sbatch.log")" = 1 ]'
ready; : > "$T/sbatch.log"; OUT="$(QT_SUBMIT=yes sp QT_ACK_QUALITY=yes QT_FA=off FAKE_SBATCH_LOG="$T/sbatch.log")"
chk "QT_ACK_QUALITY and QT_FA are passed through to the job" 'grep -q "\-\-export=ALL,QT_ACK_QUALITY=yes,QT_FA=off" "$T/sbatch.log"'
ready; OUT="$(sp FAKE_BUILD_QUEUED=1)"; RC=$?; chk "refused while the compile job is still queued or running" '[ $RC -ne 0 ] && grep -q "still in the queue" <<<"$OUT"'
ready; rm -f "$BLOG_F"; OUT="$(QT_SUBMIT=yes sp)"; RC=$?; chk "refused when the build log is missing; nothing submitted" '[ $RC -ne 0 ] && grep -q "no build log" <<<"$OUT" && ! grep -q "PIPELINE_JOB" "$STATE_F"'
ready; echo "error: link failed" > "$BLOG_F"; OUT="$(QT_SUBMIT=yes sp)"; RC=$?; chk "refused when the build did not end with BUILD OK" '[ $RC -ne 0 ] && grep -q "BUILD OK" <<<"$OUT" && ! grep -q "PIPELINE_JOB" "$STATE_F"'
ready; echo "still downloading" > "$WLOG_F"; OUT="$(QT_SUBMIT=yes sp)"; RC=$?; chk "refused while the weights download has not verified" '[ $RC -ne 0 ] && grep -q "has not finished or failed" <<<"$OUT" && ! grep -q "PIPELINE_JOB" "$STATE_F"'
ready; cp "$T/rh/models/Qwen3.6-27B-Q4_K_M.gguf" "$T/gguf.bak"; printf "x" >> "$T/rh/models/Qwen3.6-27B-Q4_K_M.gguf"; OUT="$(QT_SUBMIT=yes sp)"; RC=$?; chk "refused when the weights file has the wrong size" '[ $RC -ne 0 ] && grep -q "wrong size" <<<"$OUT"'
cp "$T/gguf.bak" "$T/rh/models/Qwen3.6-27B-Q4_K_M.gguf"
ready; OUT="$(QT_SUBMIT=yes sp FAKE_PIPE_QUEUED=1)"; RC=$?; chk "refused when a qt_pipeline job of yours is already waiting" '[ $RC -ne 0 ] && grep -q "already in the queue" <<<"$OUT"'
ready; OUT="$(QT_SUBMIT=yes sp FAKE_TESTONLY_FAIL=1)"; RC=$?; chk "refused when the scheduler rejects the request" '[ $RC -ne 0 ] && grep -q "did not accept" <<<"$OUT" && ! grep -q "PIPELINE_JOB" "$STATE_F"'
rm -f "$STATE_F"; OUT="$(QT_SUBMIT=yes sp)"; RC=$?; chk "refused when preparation was never started" '[ $RC -ne 0 ] && grep -q "run prep_cluster.sh first" <<<"$OUT"'

echo "[Q5] build_llamacpp.sbatch: the compiler fix (the failure seen in job 2510636)"
printf '#!/bin/bash\n[ "$1" = rev-parse ] && echo fakecommit000\nexit 0\n' > "$T/bin/git"
printf '#!/bin/bash\necho "Cuda compilation tools, release 12.2, V12.2.140"\necho "Build cuda_12.2.r12.2/compiler.33191640_0"\n' > "$T/bin/nvcc"
for c in gcc g++; do printf '#!/bin/bash\necho "%s (GCC) ${FAKE_GCC_VERSION:-12.2.0}"\n' "$c" > "$T/bin/$c"; done
cat > "$T/bin/cmake" <<'EOF'
#!/bin/bash
if [ "${1:-}" = "--version" ]; then echo "cmake version 3.31.2"; exit 0; fi
echo "cmake $*" >> "$T_CMAKE_LOG"
if [ "${1:-}" = "--build" ]; then mkdir -p build/bin && cp "$FAKE_LLAMA_SERVER_BIN" build/bin/llama-server && exit 0; fi
cc=""; for a in "$@"; do case "$a" in -DCMAKE_C_COMPILER=*) cc="${a#-DCMAKE_C_COMPILER=}";; esac; done
[ "${FAKE_CMAKE_USES_CC:-}" = 1 ] && cc=/usr/bin/cc          # simulate CMake ignoring the request and using the old system cc
mkdir -p build && echo "CMAKE_C_COMPILER:FILEPATH=$cc" > build/CMakeCache.txt
exit 0
EOF
chmod +x "$T/bin/git" "$T/bin/nvcc" "$T/bin/gcc" "$T/bin/g++" "$T/bin/cmake"
mkdir -p "$T/rh/llama.cpp/.git" "$T/rh/llama.cpp/build"; : > "$T/rh/llama.cpp/build/STALE_FROM_A_FAILED_BUILD"
cp "$T/bin/llama-server" "$T/fake_llama_server_bin"; CML="$T/cmake.log"; : > "$CML"
bld() { env T_CMAKE_LOG="$CML" FAKE_LLAMA_SERVER_BIN="$T/fake_llama_server_bin" SLURM_SUBMIT_DIR="$T/repo" "$@" bash "$T/repo/configs/redhawk/build_llamacpp.sbatch" 2>&1; }
OUT="$(bld)"; RC=$?; echo "$OUT" | tail -n 5 | cut -c1-150
chk "with gcc 12.2: BUILD OK, and CMake was told the exact compilers (gcc, g++ and the CUDA host compiler)" '[ $RC -eq 0 ] && grep -q "BUILD OK" <<<"$OUT" && grep -q "DCMAKE_C_COMPILER=$T/bin/gcc" "$CML" && grep -q "DCMAKE_CXX_COMPILER=$T/bin/g++" "$CML" && grep -q "DCMAKE_CUDA_HOST_COMPILER=$T/bin/g++" "$CML"'
chk "the stale build folder from the failed attempt was wiped first" '[ ! -e "$T/rh/llama.cpp/build/STALE_FROM_A_FAILED_BUILD" ] && [ -x "$T/rh/llama.cpp/build/bin/llama-server" ]'
chk "the log names the compilers it used" 'grep -q "compilers: C=$T/bin/gcc" <<<"$OUT" && grep -q "CMake C compiler: $T/bin/gcc" <<<"$OUT"'
: > "$CML"; OUT="$(bld FAKE_GCC_VERSION=4.8.5)"; RC=$?
chk "a compiler that is not 12.2 (the old 4.8.5) is refused BEFORE CMake runs" '[ $RC -ne 0 ] && grep -q "is not gcc 12.2" <<<"$OUT" && [ ! -s "$CML" ]'
: > "$CML"; OUT="$(bld FAKE_CMAKE_USES_CC=1)"; RC=$?
chk "if CMake substitutes the old system cc anyway, the build is refused before compiling" '[ $RC -ne 0 ] && grep -q "CMake configured with C compiler" <<<"$OUT" && ! grep -q -- "--build" "$CML"'

echo "[Q6] rebuild_llamacpp.sh: resubmit the compile job and make submit_pipeline.sh follow the NEW job"
bld > /dev/null   # one good build first, so a binary exists (the refused build just above wiped the folder)
printf 'PREP_STARTED_UTC=x\nBUILD_JOB=5555\nREPO=%s\n' "$T/repo" > "$STATE_F"; echo "error: stdatomic.h" > "$BLOG_F"; printf 'download\nOK: weights verified\n' > "$WLOG_F"
rb() { env "$@" bash "$T/repo/configs/redhawk/rebuild_llamacpp.sh" 2>&1; }
OUT="$(rb FAKE_JOBID=6666)"; RC=$?; echo "$OUT" | tail -n 3 | cut -c1-150
chk "submits the compile job again and appends the new job number (old lines are kept)" '[ $RC -eq 0 ] && [ "$(sed -n "s/^BUILD_JOB=//p" "$STATE_F" | tail -n 1)" = 6666 ] && grep -q "^BUILD_JOB=5555" "$STATE_F" && grep -q "^REBUILD_REPLACES=5555" "$STATE_F"'
echo "BUILD OK" > "$T/repo/qt_build_6666.log"
OUT="$(env QT_SUBMIT= bash "$T/repo/configs/redhawk/submit_pipeline.sh" 2>&1)"; RC=$?
chk "submit_pipeline.sh now checks the NEW build log (the old failed log is ignored)" '[ $RC -eq 0 ] && grep -q "build job 6666" <<<"$OUT" && grep -q "All checks passed" <<<"$OUT"'
OUT="$(rb FAKE_BUILD_QUEUED=1 FAKE_JOBID=7777)"; RC=$?; chk "refused while the previous compile job is still queued or running" '[ $RC -ne 0 ] && grep -q "still queued or running" <<<"$OUT" && [ "$(sed -n "s/^BUILD_JOB=//p" "$STATE_F" | tail -n 1)" = 6666 ]'
cp "$T/repo/configs/redhawk/build_llamacpp.sbatch" "$T/bld.bak"; printf 'echo x\r\n' >> "$T/repo/configs/redhawk/build_llamacpp.sbatch"
OUT="$(rb FAKE_JOBID=8888)"; RC=$?; chk "refused if the compile script has Windows line endings" '[ $RC -ne 0 ] && grep -q "carriage returns" <<<"$OUT" && [ "$(sed -n "s/^BUILD_JOB=//p" "$STATE_F" | tail -n 1)" = 6666 ]'
cp "$T/bld.bak" "$T/repo/configs/redhawk/build_llamacpp.sbatch"
rm -f "$STATE_F"; OUT="$(rb)"; RC=$?; chk "refused when preparation was never started" '[ $RC -ne 0 ] && grep -q "run prep_cluster.sh first" <<<"$OUT"'

echo "[Q7] llama-server cannot start without the NVIDIA driver (the real failure of job 2510641): the check borrows the CUDA stub library"
mkdir -p "$T/lib64/stubs"; echo stub > "$T/lib64/stubs/libcuda.so"
LSB="$T/rh/llama.cpp/build/bin/llama-server"; mkdir -p "$T/rh/llama.cpp/build/bin"; cp "$T/bin/llama-server" "$LSB"
runfn() { env FAKE_NEEDS_DRIVER=1 bash -c "source $T/repo/configs/redhawk/common.sh; $1" 2>&1; }
OUT="$(runfn "run_llama $LSB --help | head -n 3")"
chk "run_llama: the first try fails without the driver, the stub retry prints the help" 'grep -q -- "--model" <<<"$OUT" && ! grep -q "error while loading" <<<"$OUT"'
OUT="$(runfn "check_flags $LSB")"; RC=$?
chk "check_flags passes on a node that has no driver" '[ $RC -eq 0 ] && grep -q "lists all required flags" <<<"$OUT"'
mv "$T/lib64/stubs/libcuda.so" "$T/stub.bak"
OUT="$(runfn "check_flags $LSB")"; RC=$?
chk "with no stub available it fails AND shows the loader error, not just a list of 'missing flags'" '[ $RC -ne 0 ] && grep -q "error while loading shared libraries" <<<"$OUT"'
mv "$T/stub.bak" "$T/lib64/stubs/libcuda.so"
echo "[Q8] verify_build.sh records a verification of the existing binary without recompiling; submit_pipeline.sh accepts it"
vb() { env FAKE_NEEDS_DRIVER=1 bash "$T/repo/configs/redhawk/verify_build.sh" 2>&1; }
rm -f "$T/rh/build_verified.txt"; BEFORE="$(sha256sum "$LSB" | cut -d' ' -f1)"
OUT="$(vb)"; RC=$?; echo "$OUT" | tail -n 3 | cut -c1-150
chk "verify_build.sh passes and writes the record (pinned commit, binary hash, flags ok)" '[ $RC -eq 0 ] && grep -q "^COMMIT=fakecommit000" "$T/rh/build_verified.txt" && grep -q "^BIN_SHA256=[0-9a-f]\{64\}" "$T/rh/build_verified.txt" && grep -q "^FLAGS_OK=yes" "$T/rh/build_verified.txt"'
chk "it did not modify the binary (no rebuild happened)" '[ "$(sha256sum "$LSB" | cut -d" " -f1)" = "$BEFORE" ] && grep -q "^BIN_SHA256=$BEFORE" "$T/rh/build_verified.txt"'
ready; echo "error: flag check failed on a CPU node" > "$BLOG_F"
OUT="$(env FAKE_NEEDS_DRIVER=1 QT_SUBMIT= bash "$T/repo/configs/redhawk/submit_pipeline.sh" 2>&1)"; RC=$?
chk "submit_pipeline.sh accepts the verified binary although the build log has no BUILD OK" '[ $RC -eq 0 ] && grep -q "verify_build.sh verified this exact binary" <<<"$OUT" && grep -q "All checks passed" <<<"$OUT"'
printf '\n# changed after verification\n' >> "$LSB"
OUT="$(env FAKE_NEEDS_DRIVER=1 QT_SUBMIT= bash "$T/repo/configs/redhawk/submit_pipeline.sh" 2>&1)"; RC=$?
chk "once the binary changes, the old verification no longer counts" '[ $RC -ne 0 ] && grep -q "no verification of the current binary" <<<"$OUT"'
rm -f "$T/rh/build_verified.txt"; ready; echo "error" > "$BLOG_F"
OUT="$(env FAKE_NEEDS_DRIVER=1 QT_SUBMIT= bash "$T/repo/configs/redhawk/submit_pipeline.sh" 2>&1)"; RC=$?
chk "with a failed build log and no verification at all it refuses and points to verify_build.sh" '[ $RC -ne 0 ] && grep -q "verify_build.sh" <<<"$OUT"'
fi
[ -n "${KEEP_WORK:-}" ] || rm -rf "$T"
echo "==== part $PART: $PASS passed, $FAIL failed ===="
[ "$FAIL" -eq 0 ]
