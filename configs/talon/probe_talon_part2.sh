#!/bin/bash
# probe_talon_part2.sh - the second part of the first-login probe: HOW does Talon want GPUs to be requested? Run on a login node
# from the repository copy, after probe_talon.sh, in three steps:
#   cd <repo copy> && bash configs/talon/probe_talon_part2.sh                 (1) checks only: sbatch --test-only, NO job is created
#   cd <repo copy> && QT_SUBMIT=yes bash configs/talon/probe_talon_part2.sh   (2) submits ONE small GPU job (about 5 minutes)
#   cd <repo copy> && bash configs/talon/probe_talon_part2.sh record          (3) after that job has finished: reads its log and
#                                                                                 writes talon_verified.txt
# Step (2) uses GPU time and may count against an allocation (UNVERIFIED), so it needs a separate approval before it is run.
# It does NOT need SETTINGS_REVIEWED=yes or the talon_* paths: it is part of finding the values. It reads only the partition,
# account and QOS from talon_settings.sh (set them from probe_talon.sh first, or pass them in the environment).
#
# WHY. Slurm sites differ in how a job asks for GPUs. Redhawk defines no GPU resource at all (a whole node had to be taken);
# Talon very likely does, but the exact form is unknown. Four common forms are tried with `sbatch --test-only`, which asks the
# scheduler "would you accept this, and when could it start?" without creating a job:
#   --gres=gpu:1    --gres=gpu:<type>:1    --gpus=1    --gpus=<type>:1      (<type> = TALON_GPU_TYPE, or h100 if blank)
# The styles that are accepted are recorded; TALON_GPU_STYLE in talon_settings.sh must be one of them (submit_pipeline.sh checks).
# Then one real 5-minute job (probe_gpu_job.sbatch) shows what the job really receives: GPU model, memory, driver, links between
# GPUs, CPUs and memory, and whether a compute node can reach Hugging Face and PyPI.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"   # settings only; no require_paths, no require_reviewed (see above)
MODE="${1:-check}"
JOBFILE="$QT_REPO/talon_probe_job.txt"; VER="$QT_REPO/talon_verified.txt"
talon_facts_banner

if [ "$MODE" = record ]; then
  [ -f "$JOBFILE" ] || die "$JOBFILE is missing: the probe job was never submitted (step 2)."
  JOB="$(sed -n 's/^JOB=//p' "$JOBFILE" | tail -n 1)"; STYLES="$(sed -n 's/^STYLES_ACCEPTED=//p' "$JOBFILE" | tail -n 1)"
  SPEC="$(sed -n 's/^SPEC_USED=//p' "$JOBFILE" | tail -n 1)"
  if [ -n "$(squeue -h -j "$JOB" 2>/dev/null)" ]; then die "probe job $JOB is still in the queue or running. Wait until 'squeue -u $(id -un)' no longer lists it."; fi
  LOG="$QT_REPO/qt_talon_probe_${JOB}.log"
  [ -f "$LOG" ] || die "the probe job's log $LOG is missing."
  grep -q '^PROBE_END' "$LOG" || die "the probe job did not finish (no PROBE_END in $LOG). Read the log."
  NGPU="$(grep -c '^PROBE_GPU GPU [0-9]' "$LOG" || true)"
  [ "$NGPU" -ge 1 ] || die "the probe job saw no GPU (no 'GPU 0:' line in $LOG): the request was accepted but gave no GPU. Read the log; ask Research Computing."
  GPU_NAME="$(sed -n 's/^PROBE_GPU GPU 0: \(.*\) (UUID.*/\1/p' "$LOG" | head -n 1)"
  DRIVER="$(sed -n 's/^PROBE_DRIVER_LINE //p' "$LOG" | head -n 1 | tr -s ' ')"
  NET_HF="$(sed -n 's/^PROBE_NET huggingface //p' "$LOG" | head -n 1)"; NET_PYPI="$(sed -n 's/^PROBE_NET pypi //p' "$LOG" | head -n 1)"
  WHEEL="$(sed -n 's/^PROBE_WHEEL //p' "$LOG" | head -n 1)"
  { echo "PART2_OK=yes"; echo "JOB=$JOB"; echo "GPU_STYLES_ACCEPTED=$STYLES"; echo "SPEC_USED=$SPEC"; echo "GPUS_SEEN=$NGPU"
    echo "GPU_NAME=$GPU_NAME"; echo "DRIVER_LINE=$DRIVER"; echo "COMPUTE_NODE_HUGGINGFACE=$NET_HF"; echo "COMPUTE_NODE_PYPI=$NET_PYPI"
    echo "VLLM_WHEEL=$WHEEL"; echo "RECORDED_UTC=$(date -u +%FT%TZ)"; } > "$VER"
  echo "Recorded in $VER:"; sed 's/^/  /' "$VER"
  grep -qi H100 <<<"$GPU_NAME" || warn "the GPU is '$GPU_NAME', not an H100: check the partition before going on."
  echo "Next: copy these facts into talon_settings.sh (TALON_GPU_STYLE must be one of: $STYLES), then review the file."
  exit 0
fi

[ "$MODE" = check ] || die "unknown mode '$MODE' (use no argument, or 'record')"
cd "$QT_REPO" || die "cannot enter $QT_REPO"
BASE=(--nodes=1 --time=00:10:00)
[ -z "$TALON_PARTITION" ] || BASE+=(--partition="$TALON_PARTITION")
[ -z "$TALON_ACCOUNT" ] || BASE+=(--account="$TALON_ACCOUNT")
[ -z "$TALON_QOS" ] || BASE+=(--qos="$TALON_QOS")
[ -z "$TALON_NODELIST" ] || BASE+=(--nodelist="$TALON_NODELIST")   # optional node choice; blank = any node of the partition
TYPE="${TALON_GPU_TYPE:-h100}"
echo "== which GPU request forms does the scheduler accept? (sbatch --test-only: no job is created) =="
echo "   base options: ${BASE[*]}"
STYLES=""; FIRST=""
for spec in "--gres=gpu:1" "--gres=gpu:$TYPE:1" "--gpus=1" "--gpus=$TYPE:1"; do
  OUT="$(sbatch --test-only "${BASE[@]}" "$spec" configs/talon/probe_gpu_job.sbatch 2>&1)"
  if grep -q "to start at" <<<"$OUT"; then
    echo "  ACCEPTED  $spec   ($OUT)"
    fam="${spec%%=*}"; fam="${fam#--}"; [ "$fam" = gres ] || fam=gpus
    case " $STYLES " in *" $fam "*) ;; *) STYLES="${STYLES:+$STYLES }$fam" ;; esac
    [ -n "$FIRST" ] || FIRST="$spec"
  else
    echo "  refused   $spec   ($(head -n 1 <<<"$OUT"))"
  fi
done
[ -n "$FIRST" ] || die "the scheduler refused every GPU request form. Check the partition/account in talon_settings.sh (probe_talon.sh section 5) or ask Research Computing which form to use."
echo "accepted styles: $STYLES (first accepted form: $FIRST)"

if [ "${QT_SUBMIT:-}" != yes ]; then
  echo; echo "Nothing was submitted. To run the one 5-minute GPU probe job (uses GPU time; approve it first):"
  echo "  cd $QT_REPO && QT_SUBMIT=yes bash configs/talon/probe_talon_part2.sh"
  exit 0
fi
OUT="$(sbatch "${BASE[@]}" "$FIRST" configs/talon/probe_gpu_job.sbatch 2>&1)"; echo "  $OUT"
JOB="$(awk '/Submitted batch job/ {print $NF}' <<<"$OUT" | tail -n 1)"
[ -n "$JOB" ] || die "sbatch did not report a job number: the probe job was NOT submitted."
{ echo "JOB=$JOB"; echo "STYLES_ACCEPTED=$STYLES"; echo "SPEC_USED=$FIRST"; echo "SUBMITTED_UTC=$(date -u +%FT%TZ)"; } > "$JOBFILE"
echo "Submitted probe job $JOB. When 'squeue -u $(id -un)' no longer lists it:  bash configs/talon/probe_talon_part2.sh record"
