#!/bin/bash
# probe_cluster.sh - a READ-ONLY look at Redhawk. It changes nothing (no files written, no jobs, no downloads).
# Run it on a login node, then paste the whole output back so the storage location, module names and partition
# limits are chosen from facts instead of guesses.
#
# WHAT IT ANSWERS (each is something the other scripts depend on):
#   - which tools exist (git, curl, sbatch, sacct, nvidia-smi, module, quota);
#   - the gpu partition: its time limit, how GPUs are requested (the --gres name), and whether job accounting works
#     (sacct is how queue wait is measured);
#   - which CUDA / gcc / cmake / python modules exist (CUDA must be 12.x);
#   - free space and quota on the home folder and on any scratch or project areas, because the model file is 16.8 GB
#     and the home folder is a shared NFS share that was 81% full on 2026-10-01;
#   - whether the login node can reach the internet (needed for the git clone and the weights download).
# It does NOT test whether compute nodes have internet (that needs a tiny Slurm job; see the command list).
set +e   # keep going if one probe fails: a failure is itself an answer

echo "== who, where, when =="
whoami; id; hostname; date -u +%FT%TZ

echo; echo "== tools =="
for c in git curl python3 sbatch srun sinfo sacct scontrol squeue nvidia-smi module quota df sha256sum timeout awk sed; do
  printf '%-12s' "$c"; command -v "$c" || echo "MISSING"
done
python3 --version 2>&1

echo; echo "== partitions: name, availability, time limit, nodes, GRES (how GPUs are named), CPUs, memory =="
sinfo -o "%P %a %l %D %G %c %m" 2>&1 | head -20
echo; echo "-- gpu partition details"
scontrol show partition gpu 2>&1 | tr ' ' '\n' | grep -E "^(PartitionName|MaxTime|DefaultTime|State|TRES|MaxNodes|AllowAccounts|AllowGroups|QoS)="
echo; echo "-- a GPU node's GRES"
NODE="$(sinfo -p gpu -h -o '%n' 2>/dev/null | head -1)"
[ -n "$NODE" ] && scontrol show node "$NODE" 2>&1 | tr ' ' '\n' | grep -E "^(NodeName|Gres|CPUTot|RealMemory|State)="

echo; echo "== is job accounting available? (sacct measures queue wait) =="
sacct -X -n -S now-1days 2>&1 | head -3
echo "(an error mentioning accounting storage means sacct is off; the job scripts then fall back to scontrol)"

echo; echo "== modules: names only (CUDA must be 12.x) =="
if type module >/dev/null 2>&1; then
  module avail 2>&1 | grep -iE "cuda|gcc|cmake|python|anaconda|git" | head -60
else
  echo "'module' is not defined in this shell (non-interactive?). Run: bash -l -c 'module avail' or do it in your normal login shell."
fi

echo; echo "== storage: free space on candidate locations (the model file needs 16.8 GB plus margin) =="
for d in "$HOME" "${SCRATCH:-}" "/scratch" "/scratch/$(id -un)" "/work" "/work/$(id -un)" "/data" "/projects" "/tmp"; do
  [ -n "$d" ] && [ -d "$d" ] && { echo "-- $d"; df -h "$d" | tail -1; ls -ld "$d"; }
done
echo; echo "-- quota (whichever of these commands exists)"
quota -s 2>&1 | head -8
lfs quota -h -u "$(id -un)" "$HOME" 2>&1 | head -5
echo; echo "-- an existing project folder?"
ls -ld "$HOME/masters_project" 2>&1

echo; echo "== internet from THIS login node (HTTP status; 000 = unreachable) =="
for u in https://huggingface.co https://github.com https://pypi.org; do
  printf '%s ' "$u"; curl -sI -m 8 -o /dev/null -w '%{http_code}\n' "$u" 2>&1 || echo "FAILED"
done
echo; echo "Done. Nothing was changed. Paste this output back."
