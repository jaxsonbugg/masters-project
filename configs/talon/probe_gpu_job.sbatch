#!/bin/bash
#SBATCH --job-name=qt_talon_probe
#SBATCH --nodes=1
#SBATCH --output=%x_%j.log
# probe_gpu_job.sbatch - the ONE small GPU job of the first-login probe (about 5 minutes, one GPU). It is submitted only by
# probe_talon_part2.sh with QT_SUBMIT=yes, which adds the partition, account and the GPU request style the scheduler accepted.
# It loads no model and writes nothing outside its own log. It prints what only a GPU node can show:
#   the GPUs Slurm gave the job (name, memory, driver, the CUDA version the driver supports, how the GPUs are connected),
#   the node's CPUs, memory and local disk, its glibc, whether THIS node reaches Hugging Face and PyPI, and whether pip can fetch
#   the pinned vLLM wheel for this platform (only the wheel itself, deleted again; nothing is installed).
# The markers PROBE_START / PROBE_GPU / PROBE_END are what probe_talon_part2.sh record looks for.
set -u
SD="${SLURM_SUBMIT_DIR:-$PWD}/configs/talon"
# shellcheck disable=SC1091
[ -f "$SD/common.sh" ] && source "$SD/common.sh"   # settings only (VLLM_VERSION, QT_BASE_PYTHON); no paths are needed
echo "PROBE_START $(date -u +%FT%TZ) on $(hostname), job ${SLURM_JOB_ID:-none}"
echo "--- GPUs given to this job ---"
nvidia-smi -L 2>&1 | sed 's/^/PROBE_GPU /'
nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv 2>&1
nvidia-smi 2>&1 | grep -m1 "CUDA Version" | sed 's/^/PROBE_DRIVER_LINE /'
nvidia-smi topo -m 2>&1 | head -n 12
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
echo "--- node ---"
nproc; free -g | head -n 2; df -hP /tmp "${TMPDIR:-/tmp}" 2>&1 | sort -u; ldd --version 2>&1 | head -n 1
echo "--- internet from the compute node ---"
curl -sS -m 20 -o /dev/null -w "PROBE_NET huggingface %{http_code}\n" https://huggingface.co/api/models/Qwen/Qwen3.6-27B 2>&1 || echo "PROBE_NET huggingface FAILED"
curl -sS -m 20 -o /dev/null -w "PROBE_NET pypi %{http_code}\n" https://pypi.org/simple/vllm/ 2>&1 || echo "PROBE_NET pypi FAILED"
echo "--- can pip fetch the pinned vLLM wheel for this platform? (downloaded to a temporary folder, then deleted) ---"
PY="${QT_BASE_PYTHON:-}"; [ -n "$PY" ] || PY="$(command -v python3 || true)"
if [ -n "${VLLM_VERSION:-}" ] && [ -n "$PY" ]; then
  TMPW="$(mktemp -d)"
  if timeout 300 "$PY" -m pip download --no-deps --quiet -d "$TMPW" "vllm==$VLLM_VERSION" 2>&1 | tail -n 3; then :; fi
  W="$(ls "$TMPW" 2>/dev/null | head -n 1)"; echo "PROBE_WHEEL ${W:-NONE}"
  rm -rf "$TMPW"
else
  echo "PROBE_WHEEL SKIPPED (VLLM_VERSION or a Python 3 is not set yet)"
fi
echo "PROBE_END $(date -u +%FT%TZ)"
