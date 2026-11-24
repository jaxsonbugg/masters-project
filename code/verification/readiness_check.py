"""
readiness_check.py - the automatic gate before the 150-question audit and the freeze (plan "resolve the Codex flags", 2026-11-21).

WHAT IT CHECKS, for the assembled benchmark positions file:
  1. complete: exactly 1,000 positions, numbered 1..1000, each holding one usable question;
  2. matches the plan: every question's category, subtopic, area, difficulty, answer type, setting and preferred letter equal
     the slot dealt for that position (data/slots/benchmark_slots.jsonl), so the planned mix holds exactly;
  3. screened: every question's LATEST Codex screen verdict is "pass", or the owner kept it with a logged override
     (screen_overrides.json); a question edited after its screen counts only if it was screened again after the edit;
  4. R clean: R verify (keys and checks, R sandbox) passes for every question, re-run here, not taken from earlier records;
     and the v8 format checks pass;
  5. no reserved question: none of the calibration spares (benchmark_excluded_spares.json) is used;
  6. no duplicates: no item id and no question text appears twice.
It also tabulates the Codex alignment verdicts that exist (subtopic and difficulty), for the report.
The result is a JSON report and a PASS/FAIL line; it changes nothing.
"""
import argparse
import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "code" / "generation"))
import generate_benchmark as gb  # noqa: E402
import generate_set as gs  # noqa: E402
import set_prompts as sp  # noqa: E402
import variety  # noqa: E402


def latest_results(root, name):
    """{item_id: result} keeping the latest verdict per item. Batches are ordered by the time Codex finished them
    (run.json `finished_utc`), not by folder name: two batches of one date would otherwise sort alphabetically by label
    (fixed 2026-11-24, after "assembly-edited" sorted before an older "loop" batch of the same day)."""
    def finished(f):
        rj = f.parent / "run.json"
        return json.loads(rj.read_text(encoding="utf-8")).get("finished_utc", "") if rj.exists() else ""
    out = {}
    files = list(Path(root).glob(f"*_codex_*/*/{name}"))
    missing = [str(f) for f in files if not finished(f)]
    if missing:
        sys.exit(f"cannot order Codex results without run.json finished_utc: {missing[:3]}")
    for f in sorted(files, key=finished):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["item_id"]] = {**r, "source": f"{f.parent.parent.name}/{f.parent.name}"}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--positions", required=True)
    ap.add_argument("--manifest", default=str(REPO / "data" / "slots" / "benchmark_slots.manifest.json"))
    ap.add_argument("--overrides", default=None)
    ap.add_argument("--logs", default=str(REPO / "data" / "verification_logs"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    pos = [json.loads(l) for l in Path(a.positions).read_text(encoding="utf-8").splitlines() if l.strip()]
    man = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    dealt = {s["item_id"]: s for s in variety.read_slots(Path(a.manifest).parent / man["slots_file"])}
    excluded = gs.excluded_spares(a.manifest)
    overrides = {o["item_id"]: o for o in json.loads(Path(a.overrides).read_text(encoding="utf-8"))} if a.overrides else {}
    screen, align = latest_results(a.logs, "screen_results.jsonl"), latest_results(a.logs, "align_results.jsonl")
    problems = collections.defaultdict(list)

    # 1. complete
    if [p["position"] for p in pos] != list(range(1, 1001)):
        problems["complete"].append("positions are not exactly 1..1000")
    for p in pos:
        if p.get("status") != "usable":
            problems["complete"].append(f"position {p['position']}: status {p.get('status')}")
    # 2. matches the plan
    for p in pos:
        d = dealt[f"BM{p['position']:04d}"]
        diff = [k for k in gs.SAME_SLOT_KEYS if p["slot"].get(k) != d.get(k)]
        if diff:
            problems["plan"].append(f"position {p['position']} ({p['item_id']}): {diff} differ from the dealt slot")
    # 3. screened (latest verdict; an edit must be followed by a screen)
    for p in pos:
        iid = p["item_id"]
        s = screen.get(iid)
        if iid in overrides:
            continue
        if s is None:
            problems["screen"].append(f"position {p['position']} ({iid}): never screened")
        elif s["verdict"] != "pass":
            problems["screen"].append(f"position {p['position']} ({iid}): latest screen flags it ({s['issue_type']}, {s['source']})")
        elif p.get("owner_fixed") and not s["source"].split("_codex_")[1].startswith(("assembly", "loop")):
            problems["screen"].append(f"position {p['position']} ({iid}): edited, but its latest screen predates the edit")
    # 4. R verify and format, re-run now
    rscript = gb.rscript_path()
    for p in pos:
        status, issues, _ = gb.verify_item(p["item"], rscript)
        if status == "FLAGGED":
            problems["r_verify"].append(f"position {p['position']} ({p['item_id']}): {issues}")
        fmt = sp.check_benchmark_item(p["item"], p["slot"], version="benchmark-v8")
        if fmt:
            problems["format"].append(f"position {p['position']} ({p['item_id']}): {fmt}")
    # 5. reserved, 6. duplicates
    for p in pos:
        if p["item_id"] in excluded:
            problems["reserved"].append(f"position {p['position']}: {p['item_id']} is a calibration spare")
    ids = collections.Counter(p["item_id"] for p in pos)
    texts = collections.Counter(p["item"]["question"].strip() for p in pos)
    problems["duplicates"] += [f"item {i} appears {n} times" for i, n in ids.items() if n > 1]
    problems["duplicates"] += [f"a question text appears {n} times" for t, n in texts.items() if n > 1]

    mix = collections.Counter((p["slot"]["category"], p["slot"]["difficulty"]) for p in pos)
    al = [align[p["item_id"]] for p in pos if p["item_id"] in align]
    report = {"positions": len(pos), "problems": {k: v for k, v in problems.items() if v},
              "overrides": sorted(overrides), "mix": {f"{c}/{d}": n for (c, d), n in sorted(mix.items())},
              "alignment_available": len(al),
              "alignment_subtopic": dict(collections.Counter(r["subtopic_verdict"] for r in al)),
              "alignment_difficulty": dict(collections.Counter(r["difficulty_verdict"] for r in al)),
              "screen_sources": dict(collections.Counter(screen[p["item_id"]]["source"].split("/")[0]
                                                         for p in pos if p["item_id"] in screen))}
    report["result"] = "PASS" if not report["problems"] else "FAIL"
    Path(a.out).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"READINESS {report['result']}: {sum(len(v) for v in report['problems'].values())} problem(s) -> {a.out}")
    for k, v in report["problems"].items():
        print(f"  {k}: {len(v)}")
        for x in v[:8]:
            print("    ", x)


if __name__ == "__main__":
    main()
