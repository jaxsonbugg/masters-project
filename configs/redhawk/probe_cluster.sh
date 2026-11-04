#!/bin/bash
# probe_cluster.sh - a READ-ONLY look at Redhawk. It changes nothing (no files written, no jobs submitted, no downloads).
# Run it on a login node and paste the whole output back, so the storage location, module names and Slurm options are
# chosen from facts instead of guesses:
#   ssh redhawk 'bash -l -s' < configs/redhawk/probe_cluster.sh | tee /c/Users/Buggb/redhawk_probe_output.txt
#
# WHY EVERYTHING IS INSIDE main AND RUN WITH STANDARD INPUT CLOSED: this script reaches the cluster on its standard input
# (`bash -s`), so any command that reads standard input would swallow the rest of the script. That happened in the first
# probe run (the output stopped after the quota heading). Bash reads the whole function and the last line before it runs
# anything, and `main </dev/null` gives every command inside an empty input, so nothing can eat the script.
#
# WHAT IT ANSWERS: which GPU nodes exist and how Slurm exposes their GPUs (the --gres question), which module names
# work together (CUDA must be 12.x), which Python is new enough, free space and quota where the 16.8 GB file could go,
# whether the login node can reach the internet, and whether job accounting (sacct) works.
# It does NOT test whether compute nodes have internet (that needs a tiny Slurm job; it is not needed by the plan).
#
# OPTIONAL: PROBE_SBATCH_TEST=yes runs `sbatch --test-only`, which VALIDATES a GPU request and estimates a start time
# without submitting anything. It is off by default; see the section near the end.

main() {
  set +e   # keep going if one probe fails: a failure is itself an answer

  echo "== who, where, when =="
  whoami; id -un; hostname; date -u +%FT%TZ
  { grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release; ldd --version | head -n 1; git --version; nproc; } 2>&1

  echo; echo "== tools =="
  for c in git curl python3 sbatch srun sinfo sacct scontrol squeue nvidia-smi module quota df sha256sum timeout awk sed; do
    printf '%-12s' "$c"; command -v "$c" || echo "MISSING"
  done
  python3 --version 2>&1

  echo; echo "== partitions: name, availability, time limit, nodes, GRES (how GPUs are named), CPUs, memory =="
  sinfo -o "%P %a %l %D %G %c %m" 2>&1 | head -n 20
  echo; echo "-- gpu partition settings"
  scontrol show partition gpu 2>&1 | tr ' ' '\n' | grep -E "^(PartitionName|MaxTime|DefaultTime|State|TRES|MaxNodes|AllowAccounts|AllowGroups|QoS|OverSubscribe|Nodes)="

  echo; echo "== the nodes of the gpu partition, one line each: name, CPUs, memory MB, GRES, state =="
  sinfo -p gpu -N -h -o "%N %c %m %G %T" 2>&1 | head -n 12
  echo; echo "-- details per node (GPUs show up as Gres/CfgTRES only if Slurm tracks them)"
  for n in $(sinfo -p gpu -N -h -o "%N" 2>/dev/null | sort -u | head -n 6); do
    echo "- $n"
    scontrol show node "$n" 2>&1 | tr ' ' '\n' | grep -E "^(Gres|GresUsed|CfgTRES|AllocTRES|State|Features|CPUTot|RealMemory)="
  done
  echo; echo "-- Slurm's own GRES settings (no output means none configured)"
  scontrol show config 2>&1 | grep -iE "^(GresTypes|AccountingStorageType|AccountingStorageHost|SelectType|TaskPlugin|ProctrackType|JobAcctGatherType)"
  echo; echo "-- how busy the gpu partition is (counts only): running jobs, pending jobs"
  printf 'running '; squeue -p gpu -h -t R 2>/dev/null | wc -l
  printf 'pending '; squeue -p gpu -h -t PD 2>/dev/null | wc -l

  echo; echo "== is job accounting available? (sacct measures queue wait; the scripts fall back to scontrol if not) =="
  sacct -X -n -S now-1days 2>&1 | head -n 3

  echo; echo "== modules: names only (CUDA must be 12.x) =="
  if type module >/dev/null 2>&1; then
    module avail 2>&1 | grep -iE "cuda|gcc|cmake|python|anaconda|miniforge|git" | head -n 80
    echo; echo "-- do the candidate modules load TOGETHER, and what do they provide? (each in a throwaway sub-shell)"
    ( module load gcc-12.2.0 cuda-12.2 cmake-3.31.2 2>&1; echo "nvcc:"; nvcc --version 2>&1 | tail -n 2; echo "gcc:"; gcc --version 2>&1 | head -n 1; echo "cmake:"; cmake --version 2>&1 | head -n 1 )
    echo; echo "-- Python candidates: version, executable, and whether pyyaml and venv are present"
    for m in anaconda-python3 anaconda-python3.10 python-3.10.0 miniforge3-python3.12; do
      echo "- $m"
      ( module load "$m" 2>&1 | head -n 2; python --version 2>&1; command -v python; python -c "import yaml; print('pyyaml', yaml.__version__)" 2>&1 | tail -n 1; python -c "import venv; print('venv ok')" 2>&1 | tail -n 1 )
    done
  else
    echo "'module' is not defined in this shell. Run: bash -l -c 'module avail' or do it in your normal login shell."
  fi

  echo; echo "== storage: free space on candidate locations (the model file needs 16.8 GB plus margin) =="
  for d in "$HOME" "${SCRATCH:-}" "/scratch" "/scratch/$(id -un)" "/work" "/data" "/projects" "/tmp"; do
    [ -n "$d" ] && [ -d "$d" ] && { echo "-- $d"; df -h "$d" | tail -n 1; ls -ld "$d"; }
  done
  echo; echo "-- how /home and /scratch are mounted"
  mount 2>/dev/null | grep -E " on /(home|scratch) " | sed 's/(.*//'
  echo; echo "-- quota, asked per file system (a plain 'quota' fails here on an unrelated mount)"
  quota -s -f /home 2>&1 | head -n 6
  quota -s -f /scratch 2>&1 | head -n 6
  echo; echo "-- how much YOU already use in your home folder (can take up to a minute)"
  timeout 90 du -sh "$HOME" 2>&1 | tail -n 1
  echo; echo "-- an existing project folder?"
  ls -ld "$HOME/masters_project" "/scratch/$(id -un)" 2>&1

  echo; echo "== internet from THIS login node (HTTP status; 000 = unreachable) =="
  for h in huggingface.co github.com pypi.org files.pythonhosted.org cdn-lfs.huggingface.co; do
    printf '%-26s dns:' "$h"; getent hosts "$h" | awk '{print $1; exit}' | tr -d '\n'; [ -n "$(getent hosts "$h")" ] || printf 'FAILED'
    printf '  http:'; curl -sI -m 8 -o /dev/null -w '%{http_code}\n' "https://$h" 2>&1 || echo "FAILED"
  done

  if [ "${PROBE_SBATCH_TEST:-}" = "yes" ]; then
    echo; echo "== sbatch --test-only: validates a GPU request WITHOUT submitting a job =="
    echo "-- with --gres=gpu:2 (what Miami's Slurm page documents)"
    sbatch --test-only --partition=gpu --gres=gpu:2 --time=00:10:00 --wrap="hostname" 2>&1 | head -n 3
    echo "-- with --exclusive instead (a whole node, no gres)"
    sbatch --test-only --partition=gpu --nodes=1 --exclusive --time=00:10:00 --wrap="hostname" 2>&1 | head -n 3
  fi
  echo; echo "Done. Nothing was changed. Paste this output back."
}
main </dev/null
