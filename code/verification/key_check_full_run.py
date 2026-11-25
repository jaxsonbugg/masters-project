"""
key_check_full_run.py - the unattended full run of the five-solver key check (Jaxson's approval of 2026-11-25: "pilot then
full", after the pilot passed its six pre-set checks; docs/methodology/workflow.md Section 4, safeguard 6e).

WHAT IT DOES, in order (every step through the existing, tested tools; nothing new decides anything):
  1. builds the batches for every benchmark question not in the pilot: Claude C1, C2, C3 and the variants agent
     (key_check.py build, build-variants) and Codex X1, X2 (codex_batch.py build-solve-*);
  2. runs them: Claude 4 at a time (subscription login only, never the API), Codex 2 at a time; each accepted run is
     imported at once (format validation included);
  3. a rejected run or a failed import is set aside (its outputs moved to _rejected_attempts/, so the evidence is kept and
     the folder is clean again) and retried ONCE; a second failure is recorded and the batch left for the owner;
  4. a usage-limit message from the Claude CLI (exit code 3) stops every further Claude run (Jaxson's rule: no waiting, no
     retrying); Codex continues on its own allowance;
  5. then compare (all 1,000), adjudicator briefs for the contested questions (Claude), and the owner's review sheet.
Progress goes to run_log.txt in the run folder; the final state to full_run_summary.json.

It never changes a question, a key or an instruction, never touches Talon, and stops (it does not improvise) on anything it
does not expect.
"""
import argparse
import concurrent.futures
import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "code" / "verification"))
import codex_batch as cb  # noqa: E402
import key_check as kc  # noqa: E402

PY = sys.executable
KC = str(REPO / "code" / "verification" / "key_check.py")
CBT = str(REPO / "code" / "verification" / "codex_batch.py")
MAN = str(REPO / "data" / "slots" / "benchmark_slots.manifest.json")
LOCK = threading.Lock()
STOP_CLAUDE = threading.Event()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Log:
    def __init__(self, path):
        self.path = path

    def __call__(self, msg):
        line = f"{now()} {msg}"
        with LOCK:
            print(line, flush=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


def sh(args, timeout=None):
    r = subprocess.run([PY, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                       cwd=str(REPO))
    return r.returncode, (r.stdout + r.stderr).strip()


def set_aside(folder, why):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    keep = folder.parent / "_rejected_attempts" / f"{folder.name}_{stamp}"
    keep.mkdir(parents=True)
    for f in cb.OUTPUT_FILES:
        if (folder / f).exists():
            (folder / f).rename(keep / f)
    (keep / "why.txt").write_text(why, encoding="utf-8")


def run_one(job, log, results):
    family, folder = job["family"], Path(job["folder"])
    for attempt in (1, 2):
        if family == "claude" and STOP_CLAUDE.is_set():
            results[folder.name] = "skipped: usage limit reached earlier"
            log(f"SKIP {folder.name} (usage limit)")
            return
        if family == "claude":
            rc, out = sh([KC, "run-claude", "--batch", str(folder), "--real"], timeout=4000)
        else:
            rc, out = sh([CBT, "run", "--batch", str(folder), "--real", "--model", job["model"], "--effort", job["effort"]],
                         timeout=4000)
        if family == "claude" and rc == 3:
            STOP_CLAUDE.set()
            results[folder.name] = "usage limit: Claude side stopped"
            log(f"USAGE LIMIT at {folder.name}: no further Claude runs. {out[-300:]}")
            return
        if rc == 0:
            irc, iout = sh([KC if family == "claude" else CBT, "import", "--batch", str(folder)])
            if irc == 0:
                results[folder.name] = "imported"
                log(f"OK {folder.name} (attempt {attempt}) {out.splitlines()[-1][:220] if out else ''}")
                return
            why = f"import failed: {iout[-800:]}"
        else:
            why = f"run rejected (exit {rc}): {out[-800:]}"
        log(f"REJECTED {folder.name} attempt {attempt}: {why[:300]}")
        set_aside(folder, why)
    results[folder.name] = "failed twice; left for the owner"
    log(f"FAILED {folder.name} after 2 attempts")


def built_folders(out):
    return [l.split("built ", 1)[1].split(" (")[0] for l in out.splitlines() if l.startswith("built ")]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--positions", required=True)
    ap.add_argument("--pilot-ids", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--claude-workers", type=int, default=4)
    ap.add_argument("--codex-workers", type=int, default=2)
    ap.add_argument("--compare-workers", type=int, default=4)
    a = ap.parse_args(argv)
    work = kc.kc_paths()[3] / f"{a.date}_key_check" / "full_run"
    work.mkdir(parents=True, exist_ok=True)
    log = Log(work / "run_log.txt")
    log(f"FULL RUN START (positions {a.positions})")
    pilot = {l.strip() for l in Path(a.pilot_ids).read_text(encoding="utf-8").splitlines() if l.strip()}
    pos = kc.read_jsonl(a.positions)
    rest = [p["item_id"] for p in pos if p["item_id"] not in pilot]
    rest_file = work / "remaining_ids.txt"
    rest_file.write_text("".join(i + "\n" for i in rest), encoding="utf-8", newline="\n")
    log(f"{len(rest)} questions outside the pilot")

    # 1. build
    jobs = []
    for role in ("C1", "C2", "C3"):
        rc, out = sh([KC, "build", "--role", role, "--positions", a.positions, "--only", str(rest_file), "--date", a.date])
        if rc != 0:
            log(f"STOP: build {role} failed: {out[-500:]}")
            return 2
        jobs += [{"family": "claude", "folder": f} for f in built_folders(out)]
    rc, out = sh([KC, "build-variants", "--positions", a.positions, "--only", str(rest_file), "--date", a.date])
    if rc != 0:
        log(f"STOP: build-variants failed: {out[-500:]}")
        return 2
    jobs += [{"family": "claude", "folder": f} for f in built_folders(out)]
    for kind, label in (("build-solve-analytic", "kc-x1"), ("build-solve-compute", "kc-x2")):
        rc, out = sh([CBT, kind, "--items", a.positions, "--manifest", MAN, "--only", str(rest_file), "--label", label,
                      "--date", a.date, "--batch-size", str(kc.CFG["codex_batch_size"])])
        if rc != 0:
            log(f"STOP: {kind} failed: {out[-500:]}")
            return 2
        jobs += [{"family": "codex", "folder": f, "model": kc.CFG["codex_model"], "effort": kc.CFG["codex_effort"]}
                 for f in built_folders(out)]
    log(f"built {sum(j['family'] == 'claude' for j in jobs)} Claude and {sum(j['family'] == 'codex' for j in jobs)} "
        f"Codex batches")

    # 2-4. run, import, retry once, stop Claude on a usage limit
    results = {}
    with concurrent.futures.ThreadPoolExecutor(a.claude_workers) as cpool, \
            concurrent.futures.ThreadPoolExecutor(a.codex_workers) as xpool:
        futs = [(cpool if j["family"] == "claude" else xpool).submit(run_one, j, log, results) for j in jobs]
        for f in futs:
            f.result()
    bad = {k: v for k, v in results.items() if v != "imported"}
    log(f"runs done: {sum(v == 'imported' for v in results.values())} imported, {len(bad)} not: {bad}")

    # 5. compare, briefs, review
    rc, out = sh([KC, "compare", "--positions", a.positions, "--date", a.date, "--workers", str(a.compare_workers),
                  "--allow-incomplete"])
    log(f"compare (exit {rc}): {out[-1500:]}")
    if rc != 0:
        log("STOP: compare failed")
        return 2
    compare_dir = out.strip().splitlines()[-1].replace("-> ", "").strip()
    briefs = "not run"
    if not STOP_CLAUDE.is_set():
        rc, out = sh([KC, "build-briefs", "--positions", a.positions, "--date", a.date, "--compare", compare_dir])
        bjobs = [{"family": "claude", "folder": f} for f in built_folders(out)] if rc == 0 else []
        log(f"briefs: {len(bjobs)} batches (build exit {rc})")
        with concurrent.futures.ThreadPoolExecutor(a.claude_workers) as cpool:
            for f in [cpool.submit(run_one, j, log, results) for j in bjobs]:
                f.result()
        briefs = f"{sum(results.get(Path(j['folder']).name) == 'imported' for j in bjobs)} of {len(bjobs)} brief batches"
    rc, out = sh([KC, "review", "--positions", a.positions, "--date", a.date, "--compare", compare_dir])
    log(f"review (exit {rc}): {out[-400:]}")
    summary = {"finished_utc": now(), "batches": results, "compare": compare_dir, "briefs": briefs,
               "claude_stopped_by_usage_limit": STOP_CLAUDE.is_set()}
    (work / "full_run_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")
    log("FULL RUN DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
