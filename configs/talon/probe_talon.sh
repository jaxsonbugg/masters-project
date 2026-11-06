#!/bin/bash
# probe_talon.sh - READ-ONLY look at Talon on the FIRST login. It changes nothing, submits nothing, installs nothing, downloads
# nothing big and creates no file on the cluster; it only prints. Its output replaces the guesses in talon_settings.sh.
# Run it from the PC with the local wrapper, which keeps the output, ssh's exit status and a diagnostic record, and checks that
# the output is complete (nothing is copied to Talon: the script is sent through ssh's standard input):
#   cd C:\dev\masters-project  (Git Bash)  and  bash configs/talon/run_probe_local.sh
# Nothing here needs SETTINGS_REVIEWED=yes: this is how the values are found. Partition probed: $TALON_PARTITION, default talon
# (the name Research Computing gave on 2026-11-05).
#
# EVIDENCE LABELS. Every section header carries one, so the output cannot blur what is established and what is only reported:
#   [OBSERVED]        seen directly by a command, independent of the scheduler's configuration (OS, disks, HTTP status ...)
#   [SLURM-REPORTED]  what the scheduler's CONFIGURATION says (partition limits, Gres, billing weights, reservations ...). It
#                     settles "what is configured", NOT "what is accepted", "what works" or "what the policy is".
# Anything this script cannot show stays UNVERIFIED (see the closing note it prints).
#
# WHAT EACH SECTION ANSWERS
#   1  who and where        user, groups, host name, date
#   1b shared-home check    is this the same home folder as Redhawk's (is our Redhawk work visible here)?
#   2  operating system     distribution, kernel, glibc (decides which prebuilt Python wheels can run), bash and coreutils
#   3  tools                Python versions, pip, uv, git, curl, container tools
#   4  modules              the module system and the CUDA, gcc, Python and container modules on offer
#   5  Slurm in general     all partitions, GPU resource types, accounting and scheduler settings
#   5b the talon partition  its limits and billing weights, and EVERY node of it side by side (are the nodes identical?)
#   5c maintenance          down or drained nodes with reasons, and reservations (maintenance windows with end times)
#   5d queue                what is running and waiting on talon, and the scheduler's start estimates for waiting jobs
#   5e limits and billing   your associations (account, QOS), QOS limits and usage factors, accounting reachability
#   6  storage              home, scratch and project folders, mounts, free space, quotas, the login banner
#   7  internet             can THIS login node reach Hugging Face and PyPI (the 54 GB download and pip install need it)?
#   8  pins to choose       the current commit of Qwen/Qwen3.6-27B and the vLLM versions on PyPI (a person picks and pins one)
# GPUs are not looked at: login nodes usually have none, and a GPU node would need a job.
#
# READ-ONLY, ENFORCED BY TESTS (code/tests/talon_deployment_test): every command below is a query (sinfo, scontrol show, squeue,
# sacctmgr show, sshare, sacct, df, findmnt, ls, cat, id, getent, module avail, command -v, curl to /dev/null, python3 -c). A test
# scans this file for anything that submits, allocates, installs, copies, deletes or writes, and another runs it with fake
# versions of those programs that record every call (the record must stay empty).
# Every query has a short time limit and its errors are printed, not hidden. `main </dev/null`: some commands (quota on Redhawk
# was one) read the keyboard and would swallow the rest of a script that arrives through standard input.
set -u
T() { timeout "${2:-20}" bash -c "$1" 2>&1 || echo "  (exit $? from: $1)"; }
sec() { echo; echo "================ $1 $2 [$3] ================"; }

main() {
  P="${TALON_PARTITION:-talon}"; export P
  echo "probe_talon.sh, $(date -u +%FT%TZ). Read-only. Partition probed: $P"
  echo "UNVERIFIED (ask Miami Research Computing, ResComp@MiamiOH.edu) and NOT settled by anything below: pricing and charges, the"
  echo "allocation or PI credit, whether a sponsored student draws on it, access and usage policies, the H100 memory variant."

  sec 1 "who and where" OBSERVED
  T 'id; hostname; hostname -f 2>/dev/null; echo "HOME=$HOME"; echo "SHELL=$SHELL"; date -u +%FT%TZ'

  sec 1b "shared-home check (is Redhawk's home folder visible here?)" OBSERVED
  T 'getent passwd "$(id -un)"'
  T 'df -hP "$HOME" | tail -n 2'
  T 'findmnt -T "$HOME" 2>&1 | head -n 3'
  T 'ls -ld "$HOME/masters_project" /home/buggjm/masters_project 2>&1'
  T 'ls "$HOME/masters_project" 2>&1 | head -n 20'
  echo "(If masters_project from Redhawk is listed just above, home is SHARED with Redhawk: keep Talon folders distinct.)"

  sec 2 "operating system" OBSERVED
  T 'cat /etc/os-release 2>/dev/null | head -n 4; uname -r; getconf GNU_LIBC_VERSION; ldd --version 2>&1 | head -n 1; bash --version | head -n 1; sha256sum --version | head -n 1'

  sec 3 "tools" OBSERVED
  T 'for c in python3 python python3.10 python3.11 python3.12 pip3 uv git curl wget apptainer singularity podman docker nvidia-smi; do p="$(command -v $c 2>/dev/null)"; printf "  %-12s %s\n" "$c" "${p:-MISSING}"; done'
  T 'python3 -c "import sys, ssl; print(\"  python3\", sys.version.split()[0], ssl.OPENSSL_VERSION)"'
  T 'ls -d /software/python/* /opt/python* /usr/local/bin/python3* 2>/dev/null | head -n 20'

  sec 4 "modules" OBSERVED
  # Run in THIS shell, not through T: `module` is usually a shell function of the login shell and a child `bash -c` may lack it.
  { type module 2>&1 | head -n 1; module --version 2>&1 | head -n 2; } || echo "  (no module command in this shell)"
  { module -t avail 2>&1 | grep -iE "cuda|gcc|python|anaconda|conda|apptainer|singularity|vllm|torch|nccl" | sort -u | head -n 60; } || true

  sec 5 "Slurm in general" SLURM-REPORTED
  T 'sinfo -s'
  T 'sinfo -o "%P %a %l %D %G %c %m %f %N"'
  T 'scontrol show config 2>&1 | grep -Ei "^(ClusterName|SlurmVersion|SLURM_VERSION|GresTypes|SelectType|SelectTypeParameters|SchedulerType|PriorityType|TaskPlugin|JobSubmitPlugins|MaxJobCount|DefMemPerNode)"'

  sec 5b "the $P partition and every node of it" SLURM-REPORTED
  T 'sinfo -p "$P" -N -o "%N %T %G %c %m %l %f %E"'
  T 'scontrol show partition "$P" 2>&1 | tr " " "\n" | grep -E "^(PartitionName|State|MaxTime|DefaultTime|MaxNodes|MaxCPUsPerNode|AllowGroups|AllowAccounts|AllowQos|QoS|OverSubscribe|ExclusiveUser|TotalCPUs|TotalNodes|TRES|TRESBillingWeights|Nodes|PriorityTier|DefMemPerNode|DefMemPerCPU|MaxMemPerNode)="'
  T 'for n in $(sinfo -p "$P" -h -N -o %N | sort -u); do echo "--- node $n"; scontrol show node "$n" 2>&1 | tr " " "\n" | grep -E "^(NodeName|State|Gres|CPUTot|RealMemory|CfgTRES|AllocTRES|Features|ActiveFeatures|Reason|OS|Sockets|CoresPerSocket|ThreadsPerCore|Arch)="; done' 40
  echo "(Gres and CfgTRES above are the scheduler's CONFIGURATION. They do not prove that a particular GPU request is accepted or that a GPU works.)"

  sec 5c "maintenance: down or drained nodes, reservations" SLURM-REPORTED
  T 'sinfo -R'
  T 'scontrol show reservation 2>&1 | head -n 40'

  sec 5d "queue on $P" SLURM-REPORTED
  T 'squeue -p "$P" -o "%i %u %P %T %M %l %D %C %b %R" 2>&1 | head -n 40'
  T 'squeue -p "$P" --start 2>&1 | head -n 20'
  T 'squeue -u "$(id -un)" 2>&1 | head -n 5'

  sec 5e "limits, allocation, billing weights (configuration, not policy)" SLURM-REPORTED
  T 'scontrol show config 2>&1 | grep -Ei "^(AccountingStorageType|AccountingStorageTRES|AccountingStorageEnforce|PriorityWeightTRES|PriorityFlags|PriorityWeight|BillingWeights|TRESBillingWeights)"'
  T 'sacctmgr -n -P show assoc user="$(id -un)" format=cluster,account,partition,qos,defaultqos,grptres,grptresmins,maxtres,maxtresmins,maxjobs,maxsubmit,maxwall 2>&1 | head -n 20'
  T 'sacctmgr -n -P show qos format=name,priority,maxwall,maxtrespu,maxtrespj,maxjobspu,maxsubmitpu,usagefactor,grptres,flags 2>&1 | head -n 30'
  T 'sshare -U 2>&1 | head -n 8'
  T 'sacct -u "$(id -un)" -S "$(date +%F)" -n -X 2>&1 | head -n 3; echo "  (no error line above = accounting is reachable)"'
  echo "(Dollar prices, the PI research credit, and whether a sponsored student draws on it are policy, not configuration: UNVERIFIED.)"

  sec 6 "storage" OBSERVED
  T 'df -hP "$HOME" /scratch /projects /project /fs /data /tmp 2>&1 | sort -u'
  T 'findmnt -t nfs,nfs4,lustre,gpfs,beegfs,xfs,ext4 -o TARGET,SOURCE,FSTYPE,SIZE,AVAIL 2>&1 | head -n 30'
  T 'for d in /scratch /scratch/$(id -un) /projects /project /fs /shared /data /work; do [ -e "$d" ] && ls -ld "$d"; done'
  T 'quota -s 2>&1 | head -n 12'
  T 'lfs quota -h -u "$(id -un)" "$HOME" 2>&1 | head -n 8'
  T 'ls /etc/motd 2>/dev/null && head -n 40 /etc/motd'

  sec 7 "internet from this login node" OBSERVED
  T 'curl -sS -o /dev/null -w "  huggingface.co: HTTP %{http_code} in %{time_total}s\n" https://huggingface.co/api/models/Qwen/Qwen3.6-27B'
  T 'curl -sS -o /dev/null -w "  pypi.org:       HTTP %{http_code} in %{time_total}s\n" https://pypi.org/simple/vllm/'
  T 'curl -sS -o /dev/null -w "  download.pytorch.org: HTTP %{http_code} in %{time_total}s\n" https://download.pytorch.org/whl/'

  sec 8 "pins to choose (a person picks and writes them into talon_settings.sh; public API answers)" OBSERVED
  T 'curl -sS https://huggingface.co/api/models/Qwen/Qwen3.6-27B | python3 -c "import json,sys; d=json.load(sys.stdin); print(\"  Qwen/Qwen3.6-27B current commit (MODEL_REV candidate):\", d.get(\"sha\")); print(\"  last modified:\", d.get(\"lastModified\"))"'
  T 'curl -sS "https://huggingface.co/api/models/Qwen/Qwen3.6-27B/tree/main" | python3 -c "import json,sys; f=json.load(sys.stdin); s=sum(x.get(\"size\",0) for x in f); print(\"  files:\", len(f), \" total GB: %.1f\" % (s/1e9), \" (WEIGHTS_MIB about %d)\" % (s/1048576))"'
  T 'curl -sS https://pypi.org/pypi/vllm/json | python3 -c "import json,sys; d=json.load(sys.stdin); v=sorted(d[\"releases\"], key=lambda s:[int(p) if p.isdigit() else 0 for p in s.split(\".\")]); print(\"  newest vLLM:\", d[\"info\"][\"version\"]); print(\"  recent:\", \" \".join(v[-8:])); print(\"  requires python:\", d[\"info\"].get(\"requires_python\"))"'

  echo
  echo "NOTE: nothing above verifies that a GPU request is accepted by the scheduler, that a GPU works, the H100 memory variant,"
  echo "the driver or CUDA version, internet access from compute nodes, dollar pricing, the PI credit, or any policy. Those stay UNVERIFIED."
  echo "END OF PROBE"
}
main </dev/null
