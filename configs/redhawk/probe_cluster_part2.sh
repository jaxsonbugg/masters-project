#!/bin/bash
# shellcheck disable=SC2010,SC2012  # a read-only probe: plain ls output is fine here
# probe_cluster_part2.sh - READ-ONLY follow-up to probe_cluster.sh. It changes nothing: no files written, no jobs
# submitted, no weights downloaded (only HTTP HEADERS of the weights URL are requested, never the file itself).
#   ssh redhawk 'bash -l -s' < configs/redhawk/probe_cluster_part2.sh | tee /c/Users/Buggb/redhawk_probe_output3.txt
#
# WHAT THE FIRST PROBE LEFT OPEN, AND WHY EACH ITEM MATTERS
#   1. Which Python can run the client: the first probe showed that loading a Python module does NOT put a new Python on
#      PATH (python stayed 2.7.5, python3 is 3.6.8, too old). The scripts will call a full interpreter path instead.
#   2. How the `module` command is defined: batch jobs start a non-login shell where `module` may not exist, so the
#      scripts need to know how to define it.
#   3. Whether the real download paths work from here: Hugging Face now serves big files from other host names than the
#      one tested before (that one failed DNS), so the actual weights URL is probed with a HEAD request, and git is
#      asked (read-only) whether the pinned llama.cpp tag resolves to the pinned commit with this old git (1.8.3.1).
#   4. How long the gpu queue is likely to be: when the running jobs end and what the waiting jobs asked for (counts and
#      times only, no user names).
# WHY THE WHOLE BODY IS IN main RUN WITH STANDARD INPUT CLOSED: see probe_cluster.sh (a command reading standard input
# must not be able to swallow the rest of this script).
#
# 5. (APPROVED 2026-11-04) PROBE_SBATCH_TEST=yes runs `sbatch --test-only`. That command asks the scheduler to VALIDATE a
#    request and ESTIMATE when it would start; it does NOT create or submit a job. It is asked for exactly what the pipeline
#    job will request (one whole GPU node, 24 hours, excluding the drained node), so it answers two questions at once:
#    does the cluster's per-user policy accept that request, and how long would the wait be? Off unless the variable is set:
#      ssh redhawk 'PROBE_SBATCH_TEST=yes bash -l -s' < configs/redhawk/probe_cluster_part2.sh | tee /c/Users/Buggb/redhawk_probe_output4.txt
#    Section 4b (always on, read-only) also prints Slurm's QOS limits, to find the per-user CPU cap that is holding the
#    21 waiting jobs.

main() {
  set +e
  echo "== who, where, when =="; id -un; hostname; date -u +%FT%TZ

  echo; echo "== 1. Python interpreters by FULL PATH (not through modules) =="
  ls -d /software/python/* 2>&1 | head -n 20
  for p in /software/python/anaconda3-2023-python3.10 /software/python/anaconda3 /software/python/miniforge3-python3.12; do
    echo "- $p"
    if [ -x "$p/bin/python" ]; then
      "$p/bin/python" --version 2>&1
      "$p/bin/python" -c "import sys, ssl, venv, ensurepip, sqlite3; print('venv/ensurepip/ssl ok;', ssl.OPENSSL_VERSION, '; sys.version_info', sys.version_info[:3])" 2>&1 | tail -n 1
      "$p/bin/python" -c "import yaml; print('pyyaml', yaml.__version__)" 2>&1 | tail -n 1
      "$p/bin/python" -m pip --version 2>&1 | head -n 1
    else
      echo "  no $p/bin/python"
    fi
  done
  echo; echo "-- what the Python modules set (names only)"
  module show anaconda-python3.10 2>&1 | head -n 14
  module show miniforge3-python3.12 2>&1 | head -n 14

  echo; echo "== 2. how the module command is defined =="
  echo "MODULESHOME=${MODULESHOME:-unset}"; type module 2>&1 | head -n 3
  declare -f module 2>&1 | head -n 6
  ls /etc/profile.d 2>&1 | grep -iE "module|lmod"
  ls -d /usr/share/Modules /usr/share/lmod /opt/modules /opt/lmod 2>&1 | grep -v "No such"
  module --version 2>&1 | head -n 2

  echo; echo "== 3a. the real weights URL: HTTP HEADERS ONLY (the file is NOT downloaded) =="
  echo "-- Hugging Face resolve URL of the pinned GGUF; expect 200 and content-length 16817244384 at the end of the redirects"
  curl -sIL -m 30 "https://huggingface.co/unsloth/Qwen3.6-27B-GGUF/resolve/82d411acf4a06cfb8d9b073a5211bf410bfc29bf/Qwen3.6-27B-Q4_K_M.gguf" 2>&1 \
    | grep -iE "^(HTTP/|location:|content-length:|x-linked-size:)" | sed -E 's#(location: https?://[^/?]+).*#\1/...(signed path hidden)#I' | head -n 12
  echo "-- the chat template file"
  curl -sIL -m 30 "https://huggingface.co/Qwen/Qwen3.6-27B/resolve/6a9e13bd6fc8f0983b9b99948120bc37f49c13e9/chat_template.jinja" 2>&1 \
    | grep -iE "^(HTTP/|content-length:)" | head -n 6
  echo "-- DNS for the hosts Hugging Face redirects to (an empty address = cannot resolve)"
  for h in cas-bridge.xethub.hf.co transfer.xethub.hf.co cdn-lfs.hf.co cdn-lfs-us-1.hf.co; do
    printf '%-28s' "$h"; getent hosts "$h" | awk '{print $1; exit}'; echo
  done

  echo; echo "== 3b. does this old git (1.8.3.1) reach GitHub, and does the pinned tag give the pinned commit? (read-only) =="
  echo "pinned commit: 8642541b255bfb5dc39cd351a178be09013a55d6"
  timeout 60 git ls-remote https://github.com/ggml-org/llama.cpp "refs/tags/b11960" "refs/tags/b11960^{}" 2>&1 | head -n 4
  echo "-- the same with the newer git module, if it loads"
  ( module load git-2.9.5 2>&1 | head -n 2; git --version; timeout 60 git ls-remote https://github.com/ggml-org/llama.cpp "refs/tags/b11960" "refs/tags/b11960^{}" 2>&1 | head -n 4 )

  echo; echo "== 4. the gpu queue (counts and times only) =="
  echo "-- running jobs: nodes, CPUs, time LEFT, time LIMIT"
  squeue -p gpu -h -t R -o "%D nodes %C cpus left=%L limit=%l" 2>&1 | sort | head -n 12
  echo "-- waiting jobs: nodes, CPUs, time limit asked, reason"
  squeue -p gpu -h -t PD -o "%D nodes %C cpus limit=%l reason=%r" 2>&1 | sort | uniq -c | sort -rn | head -n 12
  echo "-- how many waiting jobs asked for a whole node (exclusive)"
  squeue -p gpu -h -t PD -o "%C" 2>&1 | awk '$1 >= 24 {n++} END {print n+0, "of the waiting jobs ask for 24 or more CPUs"}'

  echo; echo "== 4b. Slurm's own limits that could affect a whole-node request (read-only) =="
  echo "-- QOS definitions (this may fail: job accounting is off on this cluster); look for MaxTRESPU / MaxTRESPerUser = cpu=..."
  scontrol show assoc_mgr flags=qos 2>&1 | head -n 60
  echo "-- scheduler settings"
  scontrol show config 2>&1 | grep -iE "^(PriorityType|SchedulerType|DefMemPerNode|MaxJobCount|MinJobAge)"
  echo "-- your own jobs right now (expected: none)"
  squeue -u "$(id -un)" 2>&1 | head -n 5
  echo "(a whole GPU node is 24 cores, so the per-user CPU cap must be at least 24)"

  if [ "${PROBE_SBATCH_TEST:-}" = "yes" ]; then
    echo; echo "== 5. sbatch --test-only: VALIDATES the request and estimates a start time; NO JOB IS SUBMITTED =="
    echo "-- THE PIPELINE'S REQUEST: one whole GPU node for 24 hours, excluding the drained node"
    sbatch --test-only --partition=gpu --nodes=1 --exclusive --exclude=mualhpcp50.mpi --time=24:00:00 --wrap="hostname" 2>&1 | head -n 4
    echo "-- the same for 12 hours (useful if 24 hours is refused)"
    sbatch --test-only --partition=gpu --nodes=1 --exclusive --exclude=mualhpcp50.mpi --time=12:00:00 --wrap="hostname" 2>&1 | head -n 4
    echo "-- the same for 1 hour (a smoke stage on its own)"
    sbatch --test-only --partition=gpu --nodes=1 --exclusive --exclude=mualhpcp50.mpi --time=01:00:00 --wrap="hostname" 2>&1 | head -n 4
    echo "-- with --gres=gpu:2, as Miami's Slurm page documents (expected to be rejected)"
    sbatch --test-only --partition=gpu --gres=gpu:2 --time=01:00:00 --wrap="hostname" 2>&1 | head -n 4
  fi
  echo; echo "Done. Nothing was changed. Paste this output back."
}
main </dev/null
