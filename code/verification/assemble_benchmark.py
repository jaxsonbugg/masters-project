"""
assemble_benchmark.py - put the owner's decisions into the benchmark positions in one auditable step (2026-11-22).

WHAT AND WHY. After the replacement loops, three kinds of owner decision are still outside the positions file:
  1. the 14 positions on the open-16 fix sheet hold no question yet: each gets its chosen candidate (column `candidate`);
  2. the owner's typed edits: the rounding-fix sheet (rows keyed by `item_id`) and the open-16 fix sheet (keyed by `candidate`);
  3. the revised R checks (r2) the owner approved (`decisions_r2.json`), for items still in the benchmark.
This tool applies all of them at once. Edits are all or nothing (rounding_fixes.apply_fixes: every `new_text` filled, every
current text found exactly once); a sheet row whose item is no longer in the benchmark (replaced by the loop) is skipped and
listed, never applied elsewhere. Every changed question is re-checked: the format checks of prompt v8, the printout checker
(output_check) and R verify (keys and checks, R sandbox). The output is a new positions file plus a report and the list of
edited item ids, which then go to the Codex screen and alignment check. Nothing is overwritten.

EXAMPLE. Position 30 holds no question; its sheet row names candidate BM1160 and replaces "p-value = 0.0978" with
"p-value = 0.0981". The tool puts BM1160 into position 30, applies the edit, records old and new text in `owner_fixes`, and
re-runs the checks on BM1160.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "code" / "generation"))
sys.path.insert(0, str(REPO / "code" / "verification"))
import generate_benchmark as gb  # noqa: E402
import output_check  # noqa: E402
import rounding_fixes as rf  # noqa: E402
import set_prompts as sp  # noqa: E402


def read_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def read_csv(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--positions", required=True, help="current positions (after the loops)")
    ap.add_argument("--candidates", nargs="+", required=True, help="collected candidate files of all loops")
    ap.add_argument("--open-sheet", required=True, help="open16_fix_sheet.csv (keyed by candidate)")
    ap.add_argument("--rounding-sheet", required=True, help="rounding_fixes.csv (keyed by item_id)")
    ap.add_argument("--r2", required=True, help="decisions_r2.json")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out_dir)
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} is not empty; assemblies are never overwritten")
    out.mkdir(parents=True, exist_ok=True)
    pos = read_jsonl(a.positions)
    cands = {c["item_id"]: c for f in a.candidates for c in read_jsonl(f)}
    open_rows, round_rows = read_csv(a.open_sheet), read_csv(a.rounding_sheet)
    report = {"filled_from_sheet": [], "skipped_rows": [], "edited": [], "r2_applied": [], "r2_skipped": [], "checks": {}}

    # 1. the chosen candidates go into their positions
    for k, cid in sorted({(int(r["position"]), r["candidate"]) for r in open_rows}):
        if pos[k - 1].get("status") != "needs_candidate":
            sys.exit(f"position {k} is not open; nothing written")
        c = cands[cid]
        if c["status"] != "usable" or c["slot"].get("replaces") != f"BM{k:04d}":
            sys.exit(f"{cid} is not a usable candidate for position {k}; nothing written")
        pos[k - 1] = {"position": k, **c, "replaces": c["slot"]["replaces"], "previous_item": pos[k - 1]["item_id"],
                      "owner_selected": True}
        report["filled_from_sheet"].append((k, cid))
    if any(p.get("status") == "needs_candidate" for p in pos):
        sys.exit("positions are still open after the fix sheet; nothing written")

    # 2. the owner's edits, all or nothing
    by_id = {p["item_id"]: p for p in pos}
    rows = []
    for r in open_rows:
        rows.append({**r, "item_id": r["candidate"], "field": "question", "kind": r["group"][:1].lower() + "_open16"})
    for r in round_rows:
        if r["item_id"] in by_id:
            rows.append(r)
        else:
            report["skipped_rows"].append({"item_id": r["item_id"], "why": "no longer in the benchmark (position replaced)"})
    changed, problems = rf.apply_fixes(by_id, rows)
    if problems:
        print("NOTHING WRITTEN:\n  " + "\n  ".join(problems))
        sys.exit(2)
    report["edited"] = changed

    # 3. the approved revised checks (r2) for items still in the benchmark
    rscript = gb.rscript_path()
    for d in json.loads(Path(a.r2).read_text(encoding="utf-8")):
        p = by_id.get(d["item_id"])
        if p is None:
            report["r2_skipped"].append(d["item_id"])
            continue
        it = p["item"]
        it.setdefault("r_check_history", []).append(it["r_check"])
        it["r_check"] = d["new_r_check"]
        p["r2_applied"] = d["reason"]
        report["r2_applied"].append(d["item_id"])

    # 4. checks on everything that changed
    bad = {}
    for iid in sorted(set(changed) | set(report["r2_applied"]) | {c for _, c in report["filled_from_sheet"]}):
        p = by_id[iid]
        fmt = sp.check_benchmark_item(p["item"], p["slot"], version="benchmark-v8")
        pc = output_check.check(p["item"]["question"])
        status, issues, _ = gb.verify_item(p["item"], rscript)
        report["checks"][iid] = {"format": fmt, "printout": pc, "verify": status, "verify_issues": issues}
        if fmt or pc or status == "FLAGGED":
            bad[iid] = report["checks"][iid]
    (out / "positions.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pos),
                                         encoding="utf-8", newline="\n")
    edited = sorted(set(changed) | {c for _, c in report["filled_from_sheet"]})
    (out / "edited_ids.txt").write_text("".join(i + "\n" for i in edited), encoding="utf-8", newline="\n")
    (out / "assembly_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"{len(pos)} positions; {len(report['filled_from_sheet'])} filled from the sheet; {len(changed)} questions edited; "
          f"{len(report['r2_applied'])} revised checks applied ({len(report['r2_skipped'])} skipped: not in the benchmark); "
          f"{len(report['skipped_rows'])} sheet rows skipped; {len(bad)} with a check finding -> {out}")
    for iid, v in bad.items():
        print("  CHECK:", iid, v)


if __name__ == "__main__":
    main()
