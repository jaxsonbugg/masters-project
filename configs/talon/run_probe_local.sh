#!/bin/bash
# run_probe_local.sh - run the read-only Talon probe FROM THE PC (Git Bash) and keep a trustworthy record of what happened.
#   cd /c/dev/masters-project && bash configs/talon/run_probe_local.sh
# It sends probe_talon.sh to Talon through ssh's standard input (nothing is copied to the cluster; one password + Duo prompt),
# then decides whether the result may be treated as COMPLETE.
#
# WHY THIS WRAPPER EXISTS (three things that go wrong with a plain `ssh ... < probe | tee out`):
#   1. A pipeline reports the exit status of its LAST command, so `| tee` would hide that ssh failed. Here ssh's own status is captured
#      and preserved: a failure ends this script with that same status (for example 255 = ssh could not connect or was refused).
#   2. A dropped connection can leave a plausible-looking but TRUNCATED output with exit status 0. So the output counts as complete
#      only if it ends with the line "END OF PROBE" AND every expected section header appears (list below).
#   3. Without a record, a failure leaves nothing to look at. Three files are written OUTSIDE the repository, in
#      $TALON_PROBE_DIR (default ~/talon_probe): probe_<UTC>.out (the probe's output), .err (ssh's messages, also shown live) and
#      .diag (UTC time, local ssh version, the settings ssh resolved for the alias, ssh's exit status, size and SHA-256 of the
#      output, which sections were found or missing, whether END OF PROBE appeared, and the verdict).
#
# HOST KEY. ssh runs with StrictHostKeyChecking=yes: it can never silently accept a NEW host key. Before the first run, verify the
# host key's fingerprint with Research Computing and accept it once by hand (recovery/talon_ssh_access.md, "Verify the host key").
#
# Exit status: 0 = COMPLETE; ssh's own non-zero status if ssh failed; 3 = ssh succeeded but the output is incomplete.
# Settings (environment): TALON_SSH_ALIAS (default talon), TALON_PROBE_DIR.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBE="$HERE/probe_talon.sh"
ALIAS="${TALON_SSH_ALIAS:-talon}"
OUTDIR="${TALON_PROBE_DIR:-$HOME/talon_probe}"
EXPECTED_SECTIONS="1 1b 2 3 4 5 5b 5c 5d 5e 6 7 8"
[ -f "$PROBE" ] || { echo "STOP: $PROBE is missing." >&2; exit 2; }
mkdir -p "$OUTDIR" || { echo "STOP: cannot create $OUTDIR" >&2; exit 2; }
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$OUTDIR/probe_$STAMP.out"; ERR="$OUTDIR/probe_$STAMP.err"; DIAG="$OUTDIR/probe_$STAMP.diag"

echo "Running the read-only probe on '$ALIAS' (one password + Duo prompt). Record: $OUTDIR/probe_$STAMP.{out,err,diag}"
START="$(date -u +%FT%TZ)"
# stdout -> file; stderr -> shown live AND saved. The status of ssh itself is read right after it, before anything else can overwrite it.
ssh -o StrictHostKeyChecking=yes -o ConnectTimeout=20 -o ServerAliveInterval=30 -o ServerAliveCountMax=4 "$ALIAS" "bash -l -s" \
  < "$PROBE" > "$OUT" 2> >(tee "$ERR" >&2)
SSH_RC=$?
wait   # let the stderr copy finish writing before the .err file is read
END="$(date -u +%FT%TZ)"

HAS_END=no; grep -q '^END OF PROBE$' "$OUT" && HAS_END=yes
FOUND=""; MISSING=""
for id in $EXPECTED_SECTIONS; do
  if grep -q "^================ $id " "$OUT"; then FOUND="$FOUND $id"; else MISSING="$MISSING $id"; fi
done
LINES="$(wc -l < "$OUT" | tr -d ' ')"
SHA="$(sha256sum "$OUT" | cut -d' ' -f1)"

VERDICT="COMPLETE"; REASON="ssh exited 0, END OF PROBE is present and every expected section appears"; EXIT=0
if [ "$SSH_RC" -ne 0 ]; then
  VERDICT="INCOMPLETE"; EXIT="$SSH_RC"; REASON="ssh exited with status $SSH_RC"
elif [ "$HAS_END" != yes ]; then
  VERDICT="INCOMPLETE"; EXIT=3; REASON="ssh exited 0 but the output does not end with END OF PROBE (a dropped connection or a stopped script)"
elif [ -n "$MISSING" ]; then
  VERDICT="INCOMPLETE"; EXIT=3; REASON="END OF PROBE is present but these sections are missing:$MISSING"
fi

{ echo "UTC_START=$START"; echo "UTC_END=$END"; echo "LOCAL_SSH_VERSION=$(ssh -V 2>&1 | head -n 1)"
  echo "ALIAS=$ALIAS"; ssh -G "$ALIAS" 2>/dev/null | grep -E '^(hostname|user|port|stricthostkeychecking|identityfile) ' | sed 's/^/RESOLVED_/'
  echo "SSH_EXIT_STATUS=$SSH_RC"; echo "OUTPUT_LINES=$LINES"; echo "OUTPUT_SHA256=$SHA"
  echo "END_OF_PROBE_PRESENT=$HAS_END"; echo "SECTIONS_FOUND=$FOUND"; echo "SECTIONS_MISSING=$MISSING"
  echo "VERDICT=$VERDICT"; echo "REASON=$REASON"; } > "$DIAG"

echo
echo "================ VERDICT: $VERDICT ================"
echo "$REASON"
echo "ssh exit status $SSH_RC; $LINES output lines; sections found:$FOUND; missing:${MISSING:- none}"
if [ "$VERDICT" = COMPLETE ]; then
  echo "Record: $OUT  (paste its contents into the chat). Nothing was written on Talon."
else
  echo "Do NOT treat this output as the full picture. Diagnostics: $DIAG and $ERR"
  if grep -qi "Host key verification failed" "$ERR"; then
    echo "  The host key is not accepted yet (or it CHANGED). Verify the fingerprint with Research Computing first (recovery/talon_ssh_access.md); do not bypass this check."
  elif grep -qi "Permission denied" "$ERR"; then
    echo "  Login refused: the Talon account may not be active yet, or the password/Duo step failed. Ask Research Computing."
  elif grep -qiE "timed out|Connection refused|Could not resolve|No route" "$ERR"; then
    echo "  Could not connect: try the Miami VPN, then run Test-NetConnection (see recovery/talon_ssh_access.md)."
  fi
fi
exit "$EXIT"
