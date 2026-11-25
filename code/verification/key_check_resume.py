"""
key_check_resume.py - finish the full run of the key check after the 2026-11-25 interruption (Jaxson's approval of
2026-11-25: "import valid, redo the rest" and "yes, run it now").

WHAT HAPPENED. The full run (key_check_full_run.py) completed C1, C2 and X1 for all 975 non-pilot questions, but:
  - at 06:00 UTC the subscription's five-hour window was full; the usage-limit detector missed the CLI's wording, so the
    remaining 20 C3 and 8 variants batches failed in seconds (no tokens used) instead of stopping cleanly (fixed);
  - 7 Codex X2 batches were rejected twice because one to three r_expression answers lacked test inputs;
  - the laptop slept from 06:46 to 21:47 UTC, 2 X2 batches were cut off, and a VS Code update moved the Codex CLI (fixed).
Every rejected attempt was set aside in _rejected_attempts/ with its outputs, so nothing is lost.

WHAT IT DOES
  1. X2, the 7 batches with slips: the attempt with the fewest malformed answers is copied back (the original stays set
     aside) and imported with --partial: the valid answers are imported and the malformed ones listed for a redo;
  2. X2, the 3 interrupted batches: run, then imported with --partial;
  3. X2 redo: the set-aside questions are built into one small new batch (or more), run and imported, twice at most;
  4. Claude, 20 C3 and 8 variants batches: run 2 at a time and imported; a usage limit stops the Claude side cleanly;
  5. compare all 1,000, briefs for the contested questions, the owner's review sheet.
"""
import argparse
import concurrent.futures
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "code" / "verification"))
import codex_batch as cb  # noqa: E402
import key_check as kc  # noqa: E402
import key_check_full_run as fr  # noqa: E402
import key_check_schemas as kcs  # noqa: E402

CBT, KC, MAN = fr.CBT, fr.KC, fr.MAN


def best_attempt(folder):
    """The set-aside attempt of `folder` with an accepted run and the fewest malformed answers."""
    key = json.loads((cb.paths()[1] / f"{folder.name}_key.json").read_text(encoding="utf-8"))
    shown = {r["id"]: r for r in map(json.loads, (folder / "batch.jsonl").read_text(encoding="utf-8").splitlines()) if r}
    best = None
    for att in sorted((folder.parent / "_rejected_attempts").glob(f"{folder.name}_*")):
        rj, vj = att / "run.json", att / "verdicts.json"
        if not (rj.exists() and vj.exists()) or not json.loads(rj.read_text(encoding="utf-8")).get("accepted_run"):
            continue
        _, redo, bp = kcs.validate_partial(key["kind"], vj.read_text(encoding="utf-8"), list(key["ids"]), shown)
        if not bp and (best is None or len(redo) < best[1]):
            best = (att, len(redo))
    return best


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--positions", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--slip-batches", nargs="+", required=True, help="X2 batch numbers rejected for malformed answers")
    ap.add_argument("--rerun-batches", nargs="+", required=True, help="X2 batch numbers interrupted (run again)")
    ap.add_argument("--claude-workers", type=int, default=2)
    a = ap.parse_args(argv)
    work = kc.kc_paths()[3] / f"{a.date}_key_check" / "full_run"
    log = fr.Log(work / "run_log.txt")
    log("RESUME START (key_check_resume.py)")
    cws = cb.paths()[0]
    out_root = REPO / "data" / "verification_logs" / f"{a.date}_codex_kc-x2"
    redo_ids = []

    # 1. the slip batches: copy back the best attempt, import the valid answers
    for n in a.slip_batches:
        folder = cws / f"{a.date}_kc-x2_{int(n):02d}"
        best = best_attempt(folder)
        if best is None:
            log(f"STOP: no usable attempt for {folder.name}")
            return 2
        for f in cb.OUTPUT_FILES:
            if (best[0] / f).exists():
                shutil.copy2(best[0] / f, folder / f)
        rc, out = fr.sh([CBT, "import", "--batch", str(folder), "--partial"])
        log(f"partial import {folder.name} from {best[0].name} (exit {rc}): {out[-300:]}")
        if rc != 0:
            log("STOP: partial import failed")
            return 2
        rf = out_root / folder.name / "redo_item_ids.txt"
        if rf.exists():
            redo_ids += [l.strip() for l in rf.read_text(encoding="utf-8").splitlines() if l.strip()]

    # 2. the interrupted batches: run, import (partial)
    for n in a.rerun_batches:
        folder = cws / f"{a.date}_kc-x2_{int(n):02d}"
        for attempt in (1, 2):
            rc, out = fr.sh([CBT, "run", "--batch", str(folder), "--real", "--model", kc.CFG["codex_model"], "--effort",
                             kc.CFG["codex_effort"]], timeout=4000)
            if rc == 0:
                irc, iout = fr.sh([CBT, "import", "--batch", str(folder), "--partial"])
                log(f"run + partial import {folder.name} (exit {irc}): {iout[-300:]}")
                if irc == 0:
                    rf = out_root / folder.name / "redo_item_ids.txt"
                    if rf.exists():
                        redo_ids += [l.strip() for l in rf.read_text(encoding="utf-8").splitlines() if l.strip()]
                    break
                out = iout
            log(f"REJECTED {folder.name} attempt {attempt}: {out[-300:]}")
            fr.set_aside(folder, out)
        else:
            log(f"FAILED {folder.name} after 2 attempts")

    # 3. the redo batches for the set-aside questions (at most two rounds)
    for rnd in (1, 2):
        if not redo_ids:
            break
        f = work / f"x2_redo_round{rnd}_ids.txt"
        f.write_text("".join(i + "\n" for i in redo_ids), encoding="utf-8", newline="\n")
        log(f"X2 redo round {rnd}: {len(redo_ids)} questions")
        rc, out = fr.sh([CBT, "build-solve-compute", "--items", a.positions, "--manifest", MAN, "--only", str(f),
                         "--label", "kc-x2", "--date", a.date, "--batch-size", "25"])
        if rc != 0:
            log(f"STOP: redo build failed: {out[-300:]}")
            return 2
        redo_ids = []
        for folder in map(Path, fr.built_folders(out)):
            rc, out = fr.sh([CBT, "run", "--batch", str(folder), "--real", "--model", kc.CFG["codex_model"], "--effort",
                             kc.CFG["codex_effort"]], timeout=4000)
            if rc != 0:
                log(f"REJECTED redo {folder.name}: {out[-300:]}")
                continue
            irc, iout = fr.sh([CBT, "import", "--batch", str(folder), "--partial"])
            log(f"redo import {folder.name} (exit {irc}): {iout[-300:]}")
            rf = out_root / folder.name / "redo_item_ids.txt"
            if irc == 0 and rf.exists():
                redo_ids += [l.strip() for l in rf.read_text(encoding="utf-8").splitlines() if l.strip()]
    if redo_ids:
        log(f"X2: {len(redo_ids)} questions still without a valid answer after two redo rounds (incomplete): {redo_ids}")

    # 4. Claude: the 20 C3 and 8 variants batches cut off by the usage limit
    kws = kc.kc_paths()[0]
    imported = {p.name for p in (REPO / "data" / "verification_logs" / f"{a.date}_key_check_with_codex").glob("*/*")}
    jobs = [{"family": "claude", "folder": str(p)} for lab in ("kc-c3", "kc-variants")
            for p in sorted(kws.glob(f"{a.date}_{lab}_*")) if p.name not in imported]
    log(f"Claude: {len(jobs)} batches to run, {a.claude_workers} at a time")
    results = {}
    with concurrent.futures.ThreadPoolExecutor(a.claude_workers) as pool:
        for fut in [pool.submit(fr.run_one, j, log, results) for j in jobs]:
            fut.result()
    log(f"Claude done: {sum(v == 'imported' for v in results.values())} imported; "
        f"{ {k: v for k, v in results.items() if v != 'imported'} }")

    # 5. compare, briefs, review
    rc, out = fr.sh([KC, "compare", "--positions", a.positions, "--date", a.date, "--workers", "4", "--allow-incomplete"])
    log(f"compare (exit {rc}): {out[-1500:]}")
    if rc != 0:
        return 2
    compare_dir = out.strip().splitlines()[-1].replace("-> ", "").strip()
    if not fr.STOP_CLAUDE.is_set():
        rc, out = fr.sh([KC, "build-briefs", "--positions", a.positions, "--date", a.date, "--compare", compare_dir])
        bjobs = [{"family": "claude", "folder": f} for f in fr.built_folders(out)] if rc == 0 else []
        log(f"briefs: {len(bjobs)} batches")
        with concurrent.futures.ThreadPoolExecutor(a.claude_workers) as pool:
            for fut in [pool.submit(fr.run_one, j, log, results) for j in bjobs]:
                fut.result()
    rc, out = fr.sh([KC, "review", "--positions", a.positions, "--date", a.date, "--compare", compare_dir])
    log(f"review (exit {rc}): {out[-400:]}")
    log("RESUME DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
