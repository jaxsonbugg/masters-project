#!/bin/bash
# probe_talon.sh - READ-ONLY look at Talon on the FIRST login. It changes nothing, submits nothing and downloads nothing big;
# it only prints. Its output replaces the guesses in talon_settings.sh (partition, GPU request, modules, Python, storage paths,
# vLLM version, model revision). Run it from the PC in ONE command (one password and Duo prompt), keeping a copy of the output:
#   scp configs/talon/probe_talon.sh talon:~/  &&  ssh talon 'bash -l ~/probe_talon.sh' | tee /c/Users/Buggb/talon_probe_output.txt
# (`talon` is the SSH alias from recovery/talon_ssh_access.md; the real login host is UNVERIFIED until Miami gives it.)
# Then paste the output into the chat. Nothing here needs SETTINGS_REVIEWED=yes: this is how the values are found.
#
# WHAT EACH SECTION ANSWERS
#   1 who and where     user, groups (an allocation is often a group), host name, date
#   2 operating system  distribution, kernel, glibc (decides which prebuilt Python wheels can run), bash and coreutils versions
#   3 tools             Python versions, pip, uv, git, curl, and container tools (Apptainer/Singularity/Podman)
#   4 modules           module system and the CUDA, gcc, Python and container modules on offer
#   5 Slurm             partitions, time limits, GPU resources (GRES) per node, accounts and QOS, whether sacct works
#   6 storage           home, scratch and project folders, free space, quotas
#   7 internet          can THIS login node reach Hugging Face and PyPI (the 54 GB download and the pip install need it)?
#   8 pins to choose    the current commit of Qwen/Qwen3.6-27B and the vLLM versions on PyPI (a person picks and pins one)
# GPUs are not looked at here: login nodes usually have none. probe_talon_part2.sh asks for one small GPU job.
#
# Every command has a short time limit and its errors are printed, not hidden; a missing command is reported as missing.
# `main </dev/null`: some commands (quota on Redhawk was one) read the keyboard and would swallow the rest of this script.
set -u
T() { timeout "${2:-20}" bash -c "$1" 2>&1 || echo "  (exit $? from: $1)"; }
sec() { echo; echo "================ $1 ================"; }

main() {
  echo "probe_talon.sh, $(date -u +%FT%TZ). Read-only. Talon facts below are measurements; anything about pricing, allocation,"
  echo "GPU quotas or access rules is UNVERIFIED (ask Miami Research Computing, ResComp@MiamiOH.edu) and cannot be probed."

  sec "1 who and where"
  T 'id; hostname; hostname -f 2>/dev/null; echo "HOME=$HOME"; echo "SHELL=$SHELL"'

  sec "2 operating system"
  T 'cat /etc/os-release 2>/dev/null | head -n 4; uname -r; ldd --version 2>&1 | head -n 1; bash --version | head -n 1; sha256sum --version | head -n 1'

  sec "3 tools"
  T 'for c in python3 python python3.10 python3.11 python3.12 pip3 uv git curl wget apptainer singularity podman docker nvidia-smi; do p="$(command -v $c 2>/dev/null)"; printf "  %-12s %s\n" "$c" "${p:-MISSING}"; done'
  T 'python3 -c "import sys, ssl; print(\"  python3\", sys.version.split()[0], ssl.OPENSSL_VERSION)"'
  T 'ls -d /software/python/* /opt/python* /usr/local/bin/python3* 2>/dev/null | head -n 20'

  sec "4 modules"
  # Run in THIS shell, not through T: `module` is usually a shell function of the login shell and a child `bash -c` may lack it.
  { type module 2>&1 | head -n 1; module --version 2>&1 | head -n 2; } || echo "  (no module command in this shell)"
  { module -t avail 2>&1 | grep -iE "cuda|gcc|python|anaconda|conda|apptainer|singularity|vllm|torch|nccl" | sort -u | head -n 60; } || true

  sec "5 Slurm"
  T 'sinfo -s'
  T 'sinfo -o "%P %a %l %D %G %c %m %f %N"'
  T 'scontrol show partition 2>&1 | grep -E "PartitionName|MaxTime|DefaultTime|AllowAccounts|AllowQos|QoS|TRES|OverSubscribe|ExclusiveUser" | head -n 60'
  T 'scontrol show config 2>&1 | grep -Ei "GresTypes|SelectType|AccountingStorageType|AccountingStorageHost|PriorityType|DefMemPer|MaxJobCount|JobSubmitPlugins"'
  T 'scontrol show node 2>&1 | grep -E "NodeName|Gres=|CfgTRES|RealMemory|ActiveFeatures" | head -n 40'
  T 'sacctmgr -n show assoc user="$(id -un)" format=cluster,account,partition,qos,grptres,maxtres 2>&1 | head -n 20'
  T 'sacctmgr -n show qos format=name,maxwall,maxtrespu,maxjobspu,maxsubmitpu 2>&1 | head -n 20'
  T 'sacct -u "$(id -un)" -S "$(date +%F)" -n -X 2>&1 | head -n 3; echo "  (no error above = sacct works)"'
  T 'sshare -U 2>&1 | head -n 5'

  sec "6 storage"
  T 'df -hP "$HOME" /scratch /scratch/$(id -un) /projects /fs/scratch /tmp 2>&1 | sort -u'
  T 'for d in /scratch /scratch/$(id -un) /projects /fs /shared /data; do [ -e "$d" ] && ls -ld "$d"; done'
  T 'quota -s 2>&1 | head -n 12'
  T 'lfs quota -h -u "$(id -un)" "$HOME" 2>&1 | head -n 8'
  T 'ls /etc/motd 2>/dev/null && head -n 40 /etc/motd'

  sec "7 internet from this login node"
  T 'curl -sS -o /dev/null -w "  huggingface.co: HTTP %{http_code} in %{time_total}s\n" https://huggingface.co/api/models/Qwen/Qwen3.6-27B'
  T 'curl -sS -o /dev/null -w "  pypi.org:       HTTP %{http_code} in %{time_total}s\n" https://pypi.org/simple/vllm/'
  T 'curl -sS -o /dev/null -w "  download.pytorch.org: HTTP %{http_code} in %{time_total}s\n" https://download.pytorch.org/whl/'

  sec "8 pins to choose (a person picks and writes them into talon_settings.sh)"
  T 'curl -sS https://huggingface.co/api/models/Qwen/Qwen3.6-27B | python3 -c "import json,sys; d=json.load(sys.stdin); print(\"  Qwen/Qwen3.6-27B current commit (MODEL_REV candidate):\", d.get(\"sha\")); print(\"  last modified:\", d.get(\"lastModified\"))"'
  T 'curl -sS "https://huggingface.co/api/models/Qwen/Qwen3.6-27B/tree/main" | python3 -c "import json,sys; f=json.load(sys.stdin); s=sum(x.get(\"size\",0) for x in f); print(\"  files:\", len(f), \" total GB: %.1f\" % (s/1e9), \" (WEIGHTS_MIB about %d)\" % (s/1048576))"'
  T 'curl -sS https://pypi.org/pypi/vllm/json | python3 -c "import json,sys; d=json.load(sys.stdin); v=sorted(d[\"releases\"], key=lambda s:[int(p) if p.isdigit() else 0 for p in s.split(\".\")]); print(\"  newest vLLM:\", d[\"info\"][\"version\"]); print(\"  recent:\", \" \".join(v[-8:])); print(\"  requires python:\", d[\"info\"].get(\"requires_python\"))"'

  echo; echo "END OF PROBE. Paste everything above into the chat. Nothing was changed."
}
main </dev/null
