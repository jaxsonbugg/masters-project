"""
r_sandbox.py - run model-written R code inside a sealed box, and prove that the box holds.

WHAT THIS IS AND WHY
The teacher (Qwen) writes R code: an r_solution that recomputes a number key, and an r_check that tests an answer.
Later the students' R answers are run too. All of that code was written by a model, so it is UNTRUSTED: by mistake or
otherwise it could delete files, read personal files or reach the internet. A list of forbidden function names
(UNSAFE_R in generate_benchmark.py) is kept as an extra layer, but a pattern list can always be bypassed, so the real
protection is this sandbox (docs/methodology/workflow.md Section 4, safeguard 10).

HOW IT WORKS (one R run)
1. Windows starts the Linux system WSL2 (Ubuntu 24.04) and passes the R code in as text on standard input.
   The Linux system itself is already cut off from Windows: /etc/wsl.conf turns off the C: drive (automount) and
   the launching of Windows programs (interop). recovery/r_sandbox.md has the setup.
2. Inside Linux, `timeout` and `prlimit` set hard limits, then `bubblewrap` (bwrap) opens a fresh sealed box:
     - no network (its own empty network namespace), no other processes visible, a new session;
     - a read-only view of the system programs (/usr, /etc) and of R (/opt/R), and nothing else: no home folder,
       no /mnt, no Windows files;
     - one empty, size-limited temporary folder (/tmp), where the code is written and run;
     - a cleared environment (no inherited variables).
3. R 4.3.1 (the same version as the Windows R used before, so keys come out identical) runs the code with
   `Rscript --vanilla`. Its printed output comes back on standard output, its messages on standard error, both cut
   off at a size limit. When R ends, the box and everything in it are thrown away.
4. Limits (configs/paths.yaml, r_sandbox): memory (address space), CPU seconds, wall-clock seconds, size of any file
   written, number of processes, and output size. A run that hits one fails with a clear message.

SELF-TEST (python r_sandbox.py selftest)
Runs R code inside the box that tries every forbidden thing (open a URL, open a socket, read a planted "canary"
file in the Linux home folder, see the Windows drive, write outside /tmp, use too much memory, loop forever, leave a
background process running, print too much) and checks that each one FAILS, plus positive controls (the BM9001
calculation gives 0.2304; the R version is the pinned one). require() runs it once per process before the first R
run, and nothing runs if any check fails (fail closed).

Example: the r_solution `cat(dbinom(2, size = 5, prob = 0.6))` prints 0.2304 inside the box. A reply that instead
tried `readLines(url("http://example.com"))` gets "cannot open the connection", because the box has no network.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]

# Inside Linux: limits first (timeout, prlimit), then the sealed box (bwrap), then R. Arguments come in as $1..$8 so
# nothing is pasted into the script text. Standard output and standard error are each cut at OUT+1 bytes, so the
# caller can tell "too much output" apart from normal output. The exit status of bwrap is kept (pipefail).
WSL_SCRIPT = r'''
set -o pipefail
WALL="$1"; AS="$2"; CPU="$3"; FS="$4"; NP="$5"; OUT="$6"; RBIN="$7"; TMPSIZE="$8"
LIM=$((OUT + 1))
timeout -s KILL "$WALL" prlimit --as="$AS" --cpu="$CPU" --fsize="$FS" --nproc="$NP" -- \
  bwrap --unshare-all --die-with-parent --new-session --clearenv \
    --setenv PATH /usr/bin:/bin --setenv HOME /tmp --setenv TMPDIR /tmp --setenv LANG C.UTF-8 \
    --ro-bind /usr /usr --ro-bind /opt/R /opt/R --ro-bind /etc /etc \
    --symlink usr/bin /bin --symlink usr/sbin /sbin --symlink usr/lib /lib --symlink usr/lib64 /lib64 \
    --proc /proc --dev /dev --size "$TMPSIZE" --tmpfs /tmp --remount-ro / --chdir /tmp \
    /bin/sh -c 'cat > /tmp/code.R && exec "$0" --vanilla /tmp/code.R' "$RBIN" \
  2> >(head -c "$LIM" >&2) | head -c "$LIM"
rc=$?
wait $! 2>/dev/null
exit $rc
'''

DISTRO_OVERRIDE = "MP_R_SANDBOX_DISTRO"  # tests only: point at a missing distribution to prove that R then refuses


class SandboxError(Exception):
    pass


class Sandbox:
    def __init__(self, cfg):
        need = ("wsl_distro", "r_bin", "r_version", "memory_mb", "cpu_seconds", "wall_seconds", "output_bytes",
                "file_size_mb", "max_processes", "tmp_size_mb")
        missing = [k for k in need if k not in (cfg or {})]
        if missing:
            raise SandboxError(f"r_sandbox settings missing in configs/paths.yaml: {', '.join(missing)}")
        self.cfg = dict(cfg)
        if os.environ.get(DISTRO_OVERRIDE):
            self.cfg["wsl_distro"] = os.environ[DISTRO_OVERRIDE]

    def describe(self):
        c = self.cfg
        return (f"WSL {c['wsl_distro']}, bubblewrap, R {c['r_version']}; limits: {c['memory_mb']} MB memory, "
                f"{c['cpu_seconds']} s CPU, {c['wall_seconds']} s wall, {c['output_bytes']} bytes output, "
                f"{c['file_size_mb']} MB per file, {c['tmp_size_mb']} MB /tmp, {c['max_processes']} processes")

    def wsl(self, args, stdin=b"", timeout=60):
        """Run a command in the WSL distribution (outside the sandbox). Used for the self-test's setup only."""
        return subprocess.run(["wsl.exe", "-d", self.cfg["wsl_distro"], "--exec", *args], input=stdin,
                              capture_output=True, timeout=timeout)

    def run(self, code):
        """Run R code in the sandbox. Returns (ok, stdout_or_error_text), like the old direct run."""
        c = self.cfg
        out_cap = int(c["output_bytes"])
        args = [str(c["wall_seconds"]), str(int(c["memory_mb"]) * 1024 * 1024), str(c["cpu_seconds"]),
                str(int(c["file_size_mb"]) * 1024 * 1024), str(c["max_processes"]), str(out_cap), c["r_bin"],
                str(int(c["tmp_size_mb"]) * 1024 * 1024)]
        try:
            r = subprocess.run(["wsl.exe", "-d", c["wsl_distro"], "--exec", "bash", "-c", WSL_SCRIPT, "bash", *args],
                               input=code.encode("utf-8"), capture_output=True,
                               timeout=int(c["wall_seconds"]) + 30)
        except subprocess.TimeoutExpired:
            return False, f"R timed out after {c['wall_seconds']} s"
        except OSError as e:
            return False, f"sandbox could not start: {e}"
        stdout = r.stdout.decode("utf-8", errors="replace")
        stderr = r.stderr.decode("utf-8", errors="replace")
        if len(r.stdout) > out_cap or len(r.stderr) > out_cap:
            return False, f"refused: output larger than {out_cap} bytes"
        if r.returncode == 137:  # killed by `timeout -s KILL`
            return False, f"R timed out after {c['wall_seconds']} s"
        if r.returncode == 152:  # 128 + SIGXCPU: the CPU-seconds limit
            return False, f"R stopped at the CPU limit of {c['cpu_seconds']} s"
        if r.returncode != 0:
            return False, "R error: " + (stderr.strip().splitlines() or ["?"])[-1]
        return True, stdout


def load():
    paths = yaml.safe_load((REPO / "configs" / "paths.yaml").read_text())
    return Sandbox(paths.get("r_sandbox"))


# ---------------------------------------------------------------------------------------------------------- self-test
def selftest(sb, verbose=True):
    """Try every forbidden action inside the sandbox; each must fail. Returns (all_passed, lines)."""
    lines, ok_all = [], True

    def check(name, cond, detail=""):
        nonlocal ok_all
        ok_all &= bool(cond)
        lines.append(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"  [{detail[:200]}]"))
        if verbose:
            print(lines[-1], flush=True)

    # The canary: a file planted in the Linux home folder, OUTSIDE the box. It must exist out there (so the test means
    # something) and be invisible inside.
    try:
        probe = sb.wsl(["printenv", "HOME"])
        home = probe.stdout.decode("utf-8", errors="replace").strip()
        # A missing distribution makes wsl.exe fail with an error message (in UTF-16), so check the exit status and
        # that the answer looks like a folder, before anything is built from it.
        if probe.returncode != 0 or not home.startswith("/") or "\x00" in home:
            check("the WSL distribution starts", False, f"wsl.exe exit status {probe.returncode}")
            return False, lines
        canary = f"{home}/r_sandbox_canary.txt"
        sb.wsl(["sh", "-c", f"echo canary > '{canary}'"])
        planted = sb.wsl(["test", "-f", canary]).returncode == 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        check("the WSL distribution starts", False, str(e))
        return False, lines
    check("the WSL distribution starts and the canary file is planted outside the box", planted)

    ok, out = sb.run("cat(dbinom(2, size = 5, prob = 0.6))")
    check("positive control: BM9001's calculation prints 0.2304", ok and out.strip() == "0.2304", out)
    ok, out = sb.run('cat(R.version$major, R.version$minor, sep = ".")')
    check(f"R is the pinned version {sb.cfg['r_version']}", ok and out.strip() == str(sb.cfg["r_version"]), out)
    ok, out = sb.run('tryCatch({x <- readLines(url("http://example.com"), n = 1); cat("NETWORK_OPEN")}, '
                     'error = function(e) cat("BLOCKED"), warning = function(w) cat("BLOCKED"))')
    check("no network: opening a URL fails", "NETWORK_OPEN" not in out and (not ok or "BLOCKED" in out), out)
    ok, out = sb.run('tryCatch({s <- socketConnection("1.1.1.1", 53, timeout = 3); cat("SOCKET_OPEN")}, '
                     'error = function(e) cat("BLOCKED"), warning = function(w) cat("BLOCKED"))')
    check("no network: opening a socket fails", "SOCKET_OPEN" not in out and (not ok or "BLOCKED" in out), out)
    ok, out = sb.run(f'cat(file.exists("{canary}"), file.exists("{home}"))')
    check("the canary file and the home folder are invisible inside the box", ok and out.split() == ["FALSE", "FALSE"], out)
    ok, out = sb.run('cat(file.exists("/mnt/c"), file.exists("/mnt"))')
    check("the Windows drive is invisible", ok and out.split() == ["FALSE", "FALSE"], out)
    ok, out = sb.run('r <- sapply(c("/usr/sandbox_probe", "/opt/R/sandbox_probe", "/etc/sandbox_probe", "/sandbox_probe"), '
                     'function(p) tryCatch({writeLines("x", p); "WROTE"}, error = function(e) "BLOCKED", '
                     'warning = function(w) "BLOCKED")); cat(r)')
    check("writing outside /tmp fails", ok and "WROTE" not in out and out.split().count("BLOCKED") == 4, out)
    ok, out = sb.run('x <- numeric(6e8); cat("ALLOCATED")')
    check("using more memory than the limit fails", not ok and "ALLOCATED" not in out, out)
    ok, out = sb.run("repeat {}")
    check("an endless loop is stopped", not ok and ("CPU limit" in out or "timed out" in out), out)
    ok, out = sb.run('system("sleep 600 &"); cat("STARTED")')
    left = sb.wsl(["pgrep", "-f", "sleep 600"]).returncode == 0
    check("a background process does not outlive the run", not left, "a 'sleep 600' process is still running")
    if left:
        sb.wsl(["pkill", "-f", "sleep 600"])
    ok, out = sb.run('cat(strrep("x", 3e6))')
    check("too much output is refused", not ok and "output larger" in out, out)
    ok, out = sb.run('cat(nchar(Sys.getenv("WSL_DISTRO_NAME")), Sys.getenv("HOME"))')
    check("the environment is cleared", ok and out.split() == ["0", "/tmp"], out)
    sb.wsl(["rm", "-f", canary])
    return ok_all, lines


_CHECKED = {}


def require():
    """Return a sandbox whose self-test has passed (checked once per process); stop the program otherwise."""
    if "sb" in _CHECKED:
        return _CHECKED["sb"]
    try:
        sb = load()
    except SandboxError as e:
        sys.exit(f"Refusing to run R: {e} (docs/methodology/workflow.md Section 4, safeguard 10).")
    passed, lines = selftest(sb, verbose=False)
    if not passed:
        sys.exit("Refusing to run R: the R sandbox self-test failed, so model-written R cannot be run safely "
                 "(docs/methodology/workflow.md Section 4, safeguard 10):\n" + "\n".join(lines))
    _CHECKED["sb"] = sb
    return sb


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest", help="try every forbidden action inside the sandbox; each must fail")
    p = sub.add_parser("run", help="run an R file in the sandbox and print its output")
    p.add_argument("file")
    args = ap.parse_args()
    sb = load()
    if args.cmd == "selftest":
        print(f"R sandbox self-test ({sb.describe()})")
        passed, lines = selftest(sb)
        n_fail = sum(l.lstrip().startswith("FAIL") for l in lines)
        print(f"==== {len(lines) - n_fail} passed, {n_fail} failed ====")
        sys.exit(0 if passed else 1)
    sb = require()
    ok, out = sb.run(Path(args.file).read_text(encoding="utf-8"))
    print(out, end="" if out.endswith("\n") else "\n")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
