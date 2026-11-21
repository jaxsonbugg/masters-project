"""
calibration_reserve.py - reserve unused benchmark spares for calibrating the Codex grader, before the replacement loop starts.

WHAT AND WHY (approved plan "resolve the Codex flags", revision 2, item 5; docs/methodology/workflow.md Section 2.3)
The Codex grader is calibrated on answers written for benchmark-style questions that are NOT in the benchmark. Those questions
must be chosen independently of everything that later fills the benchmark, so they are drawn now, by a seeded random draw,
and written to data/slots/benchmark_excluded_spares.json. Every tool that fills or screens the benchmark reads that file and
refuses those ids (generate_set.excluded_spares, codex_batch.benchmark_rows), so they can never enter the benchmark.

HOW
  1. Unused spares: BM1001-BM1150 that hold no benchmark position and were not rejected by the owner.
  2. Clean only: status usable and an R verify result that is not FLAGGED ("ok" where R could check the key; a question R
     cannot check, for example a conceptual multiple-choice one, is "not_machine_checkable" and allowed).
  3. Stratified by category in the benchmark's own mix (30/20/20/15/15 percent): of 40, 12 numerical, 8 conceptual,
     8 R generation, 6 output interpretation, 6 R interpretation.
  4. Within each category the clean spares are shuffled with a seeded random generator (seed recorded) and taken in that order.
     An unclean spare is never in the pool, so "swap a failed one for the next draw" happens automatically; skipped ones
     are listed in the output.
EXAMPLE: 41 clean numerical spares are shuffled with seed calibration-2026-11-21 and the first 12 are reserved.
"""
import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

QUOTA = {"numerical": 12, "conceptual": 8, "r_generation": 8, "output_interpretation": 6, "r_interpretation": 6}


def draw(items, positions, rejected, seed, quota=QUOTA):
    used = {p["item_id"] for p in positions}
    spares = [r for r in items if int(r["item_id"][2:]) > 1000 and r["item_id"] not in used and r["item_id"] not in rejected]
    rng = random.Random(seed)
    picked, skipped, strata = [], [], {}
    for cat, n in quota.items():
        pool = sorted((r for r in spares if r["slot"]["category"] == cat), key=lambda r: r["item_id"])
        rng.shuffle(pool)
        take = []
        for r in pool:
            if len(take) == n:
                break
            if r["status"] == "usable" and r.get("verify_status") != "FLAGGED":
                take.append(r["item_id"])
            else:
                skipped.append({"item_id": r["item_id"], "status": r["status"], "verify": r.get("verify_status")})
        strata[cat] = {"wanted": n, "drawn": len(take), "pool": len(pool)}
        picked += take
    return picked, skipped, strata


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", required=True, help="all collected benchmark rows (after repairs), with verify results")
    ap.add_argument("--positions", required=True, help="the current benchmark positions")
    ap.add_argument("--rejected", required=True, help="owner_rejections.json")
    ap.add_argument("--seed", required=True)
    ap.add_argument("--out", required=True, help="data/slots/benchmark_excluded_spares.json")
    a = ap.parse_args(argv)
    if Path(a.out).exists():
        sys.exit(f"{a.out} exists; the reserve is drawn once and never redrawn")
    rd = lambda p: [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
    rej = {d["item_id"] for d in json.loads(Path(a.rejected).read_text(encoding="utf-8"))}
    picked, skipped, strata = draw(rd(a.items), rd(a.positions), rej, a.seed)
    out = {"ids": sorted(picked), "reason": "Codex calibration reserve (plan revision 2, item 5): permanently excluded from "
           "the benchmark", "seed": a.seed, "strata": strata, "skipped_unclean": skipped,
           "source_items": Path(a.items).name, "source_positions": Path(a.positions).name,
           "drawn_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: out[k] for k in ("seed", "strata")}, indent=1), f"\n{len(picked)} reserved -> {a.out}")


if __name__ == "__main__":
    main()
