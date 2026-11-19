"""
answer_check.py - grade the thinking on/off check and apply its pre-set rule (runs on this PC; R only inside the sandbox).

WHAT THIS IS AND WHY
About 95% of the teacher's output is "thinking". Switching thinking off could make generation much cheaper, but a teacher
that gets much worse would undermine the experiment (students learn from its worked answers). This script reads the
four Talon runs of the check (docs/methodology/workflow.md Section 2.1) and reports two SEPARATE outcomes plus the cost:
  1. USABILITY: of the 40 primary slots each mode wrote (BM8001-BM8040), how many replies passed every automatic check
     on the first attempt. Every failure is listed with its reason; the 20 reserve slots are reported separately.
  2. ANSWER CORRECTNESS: both modes answered the same fixed set of up to 40 questions (positions 1-20 written with
     thinking on, 21-40 with thinking off), 3 times each. Each answer's "Final answer:" line is graded against the key.
  3. COST: GPU-hours per usable WRITTEN question (the generation cost, including the GPU time spent on failed attempts);
     answering throughput separately; model start-up time separately (never inside either).
It then applies the rule fixed BEFORE the results (a descriptive engineering criterion, not a statistical test):
  thinking off is adopted only if (a) its mean answer accuracy is no more than 5 points below thinking on, (b) its
  first-attempt usable rate is no more than 5 points below, and (c) question generation costs at least 2x fewer GPU-hours
  per usable question; and no category of numerical or R-generation questions is 10+ points worse without your review.

HOW AN ANSWER IS GRADED (key = the origin writing run's key after `open_teacher_test.py score`, R in the sandbox)
  number           correct if |answer - key| <= the item's answer_tolerance (0.230 vs 0.23 is the same number: correct)
  multiple choice  correct if the letter matches ("C", "C.", "(C)" all count as C)
  R expression     correct if the item's r_check accepts it as `candidate` (run in the R sandbox)
  short text       correct if equal after lower-casing and removing spaces and punctuation; always put on your sheet
  no "Final answer:" line = wrong, counted separately as a format failure.

YOUR LOOK (check_sheet.csv). Questions where the two modes' most common answers differ, short-text questions, and questions
whose key R could not confirm go on a sheet. For each you fill in key_correct (yes/no), corrected_key if no, and optionally
accept_also (more answers that are also right, separated by |). Run again with --sheet to regrade.

USAGE
  python answer_check.py --write-on <run> --write-off <run> --answers-on <run> --answers-off <run> --set-dir <folder>
                         --out <results folder> [--sheet <filled check_sheet.csv>]
The writing runs must already be scored (`open_teacher_test.py score --run <run>` writes items.jsonl).
"""

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import open_teacher_test as ott  # noqa: E402  (reuses reply parsing, the usable test, final-answer extraction)
import generate_benchmark as gb  # noqa: E402

ACC_MARGIN, USABLE_MARGIN, SPEEDUP_MIN, CATEGORY_FLAG = 5.0, 5.0, 2.0, 10.0   # the pre-set rule (points, points, ratio, points)
BLOCKING_CATEGORIES = ("numerical", "r_generation")
PROJECTED_GENERATIONS = 232_000   # nested 1k...200k training sets + spares + benchmark + dev set (workflow.md Section 2.1)
BOOT = 10_000


def norm(s):
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


def as_number(s):
    if s is None:
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?|-?\.\d+", s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def mc_letter(s):
    m = re.match(r"^\W*([A-Da-d])\b", (s or "").strip())
    return m.group(1).upper() if m else None


def grade(answer, key_item, sandbox, extra_ok=()):
    """(correct: bool, how: str) for one final answer against one key item."""
    if answer is None:
        return False, "format failure: no 'Final answer:' line"
    if norm(answer) and any(norm(answer) == norm(x) for x in extra_ok):
        return True, "accepted on the owner's sheet"
    t = key_item["answer_type"]
    key = key_item["canonical_answer"]
    if t == "number":
        a, k = as_number(answer), as_number(key)
        if a is None or k is None:
            return False, "not a number"
        tol = float(key_item.get("answer_tolerance") or 0)
        return abs(a - k) <= tol + 1e-9, f"|{a:g} - {k:g}| vs tolerance {tol:g}"
    if t == "multiple_choice":
        return mc_letter(answer) == mc_letter(key), "letter"
    if t == "r_expression":
        if norm(answer) == norm(key):
            return True, "same text as the key"
        if not (key_item.get("r_check") or "").strip():
            return False, "no r_check to run"
        res = gb.r_check_result(key_item, answer, sandbox)
        if isinstance(res, str):  # refused by the pattern screen
            return False, res
        return bool(res), "r_check in the sandbox"
    return norm(answer) == norm(key), "normalized text match"


def load_items(run_dir):
    p = Path(run_dir) / "items.jsonl"
    if not p.exists():
        sys.exit(f"{p} is missing: score the writing run first (open_teacher_test.py score --run {run_dir}).")
    return {r["item_id"]: r for r in (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())}


def run_cost(run_dir):
    """(gpu_hours excluding start-up, load_seconds, output_tokens, n_calls) of one run, from run_log.json."""
    meta = json.loads((Path(run_dir) / "run_log.json").read_text(encoding="utf-8"))
    gpus = int((meta.get("meta") or {}).get("gpu_count", 1))
    wall = sum(s.get("wall_seconds", 0) for s in meta["sessions"])
    out = sum(s.get("out_tokens", 0) for s in meta["sessions"])
    calls = sum(s.get("calls", 0) for s in meta["sessions"])
    load = (meta.get("meta") or {}).get("load_seconds")
    return gpus * wall / 3600, load, out, calls


def first_ok(rows, key):
    by = {}
    for r in rows:
        if r.get("http_status") == 200 and r.get(key) not in by:
            by[r[key]] = r
    return by


def bootstrap(per_q, seed=20261118):
    """95% interval of the mean of per-question values, resampling QUESTIONS (not answers)."""
    vals = list(per_q)
    if not vals:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(vals) for _ in vals) / len(vals) for _ in range(BOOT))
    return means[int(0.025 * BOOT)], means[int(0.975 * BOOT) - 1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for a in ("--write-on", "--write-off", "--answers-on", "--answers-off", "--set-dir", "--out"):
        ap.add_argument(a, required=True)
    ap.add_argument("--sheet", default=None, help="the filled check_sheet.csv (regrade with your corrections)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    set_dir = Path(args.set_dir)
    questions = [json.loads(l) for l in (set_dir / "answer_set.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    composition = json.loads((set_dir / "composition.json").read_text(encoding="utf-8"))
    write_runs = {"on": Path(args.write_on), "off": Path(args.write_off)}
    answer_runs = {"on": Path(args.answers_on), "off": Path(args.answers_off)}
    for m, d in answer_runs.items():
        meta = json.loads((d / "run_log.json").read_text(encoding="utf-8"))
        if meta.get("kind") != "answers" or meta.get("thinking") != m:
            sys.exit(f"{d} is not the thinking-{m} answer run.")
        if meta.get("question_ids") != [q["qid"] for q in questions]:
            sys.exit(f"{d} did not answer this answer set.")
    items = {m: load_items(d) for m, d in write_runs.items()}
    sandbox = gb.rscript_path()   # the R sandbox, after its self-test (R expressions are graded there)
    report = {"rule": {"accuracy_margin_points": ACC_MARGIN, "usable_margin_points": USABLE_MARGIN,
                       "generation_speedup_min": SPEEDUP_MIN, "category_flag_points": CATEGORY_FLAG,
                       "blocking_categories": list(BLOCKING_CATEGORIES),
                       "nature": "descriptive engineering criterion, not a statistical non-inferiority claim"}}

    # ---- 1. usability of the writing runs (no R: the same test validate and answer-set use) ----
    first, count = ott.SMOKE_SETS["K"]
    slots = ott.slots_for_ids([f"BM{n:04d}" for n in range(first, first + count)])
    usability, failures = {}, []
    for m, d in write_runs.items():
        rows = {}
        for r in ott.read_rows(d):
            if r["item_id"] not in rows or (r.get("http_status") == 200 and rows[r["item_id"]].get("http_status") != 200):
                rows[r["item_id"]] = r
        for block in ("primary", "reserve"):
            ids = [i for i in slots if (int(i[2:]) < first + ott.K_PRIMARY) == (block == "primary")]
            ok_by_cat = Counter()
            n_by_cat = Counter()
            ok = 0
            for iid in ids:
                item, problems = ott.usable_reply(rows.get(iid), slots[iid])
                good = item is not None and not problems
                ok += good
                n_by_cat[slots[iid]["category"]] += 1
                ok_by_cat[slots[iid]["category"]] += good
                if not good:
                    failures.append({"mode": m, "block": block, "item_id": iid, "category": slots[iid]["category"],
                                     "problems": problems})
            usability[f"{m}_{block}"] = {"usable": ok, "of": len(ids), "rate_pct": round(100 * ok / len(ids), 1),
                                         "by_category": {c: f"{ok_by_cat[c]}/{n_by_cat[c]}" for c in sorted(n_by_cat)}}
    report["usability"] = usability
    report["writing_failures"] = failures

    # ---- 2. thinking-off verification: no reply of the thinking-off runs may show thinking ----
    verify = {}
    for kind, d in (("writing", write_runs["off"]), ("answering", answer_runs["off"])):
        rows = [r for r in ott.read_rows(d) if r.get("http_status") == 200]
        bad = [(r.get("answer_id") or r.get("item_id"), ott.thinking_evidence(r)) for r in rows if ott.thinking_evidence(r)]
        verify[kind] = {"replies": len(rows), "with_thinking": len(bad), "examples": bad[:5]}
    report["thinking_off_verification"] = verify

    # ---- 3. keys, the owner's sheet, and grading ----
    sheet = {}
    if args.sheet:
        with open(args.sheet, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                sheet[row["qid"]] = row
    key_items, key_notes = {}, {}
    for q in questions:
        it = dict(items[q["origin"]].get(q["item_id"]) or {})
        if not it:
            sys.exit(f"{q['item_id']} has no scored item in the thinking-{q['origin']} writing run.")
        note = []
        if it.get("answer_type") == "number" and it.get("key_source") != "r":
            note.append("number key not confirmed by R")
        s = sheet.get(q["qid"])
        if s and s.get("key_correct", "").strip().lower() == "no" and s.get("corrected_key", "").strip():
            it["canonical_answer"] = s["corrected_key"].strip()
            note.append("key corrected on the owner's sheet")
        key_items[q["qid"]], key_notes[q["qid"]] = it, note
    graded = []
    per_q = {m: {} for m in answer_runs}
    for m, d in answer_runs.items():
        rows = first_ok(ott.read_rows(d), "answer_id")
        for q in questions:
            extra_ok = [x.strip() for x in (sheet.get(q["qid"], {}).get("accept_also") or "").split("|") if x.strip()]
            vals = []
            for n in range(1, json.loads((d / "run_log.json").read_text(encoding="utf-8"))["samples"] + 1):
                rec = rows.get(f"{q['qid']}-s{n}")
                content = ott.reply_parts(rec)[0] if rec else ""
                fa = ott.final_answer(content)
                ok, how = grade(fa, key_items[q["qid"]], sandbox, extra_ok)
                vals.append(ok)
                usage = (rec or {}).get("response", {}) or {}
                graded.append({"mode": m, "qid": q["qid"], "sample": n, "origin": q["origin"], "category": q["category"],
                               "answer_type": q["answer_type"], "final_answer": fa, "key": key_items[q["qid"]]["canonical_answer"],
                               "correct": ok, "how": how, "format_failure": fa is None,
                               "output_tokens": (usage.get("usage") or {}).get("completion_tokens")})
            per_q[m][q["qid"]] = sum(vals) / len(vals)
    (out / "graded_answers.jsonl").write_text("".join(json.dumps(g, ensure_ascii=False) + "\n" for g in graded), encoding="utf-8")

    # ---- 4. the sheet for the owner ----
    sheet_rows = []
    for q in questions:
        maj = {}
        for m in answer_runs:
            fas = [g["final_answer"] for g in graded if g["mode"] == m and g["qid"] == q["qid"]]
            c = Counter(norm(a) for a in fas if a)
            maj[m] = c.most_common(1)[0][0] if c else ""
        reasons = []
        if maj["on"] != maj["off"]:
            reasons.append("the two modes' most common answers differ")
        if q["answer_type"] == "short_text":
            reasons.append("short-text answer")
        reasons += key_notes[q["qid"]]
        if reasons:
            prev = sheet.get(q["qid"], {})
            sheet_rows.append({"qid": q["qid"], "item_id": q["item_id"], "origin": q["origin"], "category": q["category"],
                               "answer_type": q["answer_type"], "question": q["question"],
                               "choices": " | ".join(q.get("choices") or []), "key": key_items[q["qid"]]["canonical_answer"],
                               "answers_on": " | ".join(str(g["final_answer"]) for g in graded if g["mode"] == "on" and g["qid"] == q["qid"]),
                               "answers_off": " | ".join(str(g["final_answer"]) for g in graded if g["mode"] == "off" and g["qid"] == q["qid"]),
                               "reason": "; ".join(reasons), "key_correct": prev.get("key_correct", ""),
                               "corrected_key": prev.get("corrected_key", ""), "accept_also": prev.get("accept_also", "")})
    with open(out / "check_sheet.csv", "w", encoding="utf-8", newline="") as f:
        cols = ["qid", "item_id", "origin", "category", "answer_type", "question", "choices", "key", "answers_on",
                "answers_off", "reason", "key_correct", "corrected_key", "accept_also"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(sheet_rows)
    pending = sum(1 for r in sheet_rows if not r["key_correct"])

    # ---- 5. correctness summary ----
    qids = [q["qid"] for q in questions]
    acc = {}
    for m in answer_runs:
        mine = [g for g in graded if g["mode"] == m]
        lo, hi = bootstrap(per_q[m][i] for i in qids)
        by_cat = {}
        for c in sorted({q["category"] for q in questions}):
            ids = [q["qid"] for q in questions if q["category"] == c]
            by_cat[c] = round(100 * sum(per_q[m][i] for i in ids) / len(ids), 1)
        acc[m] = {"mean_pct": round(100 * sum(g["correct"] for g in mine) / max(len(mine), 1), 1),
                  "question_bootstrap_95_pct": [round(100 * lo, 1), round(100 * hi, 1)],
                  "format_failures": sum(g["format_failure"] for g in mine), "answers": len(mine), "by_category": by_cat}
    dlo, dhi = bootstrap(per_q["off"][i] - per_q["on"][i] for i in qids)
    acc["difference_off_minus_on_pct"] = round(acc["off"]["mean_pct"] - acc["on"]["mean_pct"], 1)
    acc["difference_question_bootstrap_95_pct"] = [round(100 * dlo, 1), round(100 * dhi, 1)]
    flags = [{"category": c, "on_pct": acc["on"]["by_category"][c], "off_pct": acc["off"]["by_category"][c],
              "blocking": c in BLOCKING_CATEGORIES}
             for c in acc["on"]["by_category"] if acc["on"]["by_category"][c] - acc["off"]["by_category"][c] >= CATEGORY_FLAG]
    report["correctness"] = acc
    report["category_flags"] = flags
    report["answer_set"] = {"n_questions": len(questions), "by_origin_and_category": composition["by_origin_and_category"],
                            "replacements": composition["replacements"], "unfilled": composition["unfilled"]}

    # ---- 6. cost: generation (main) and answering (separate); start-up time separate ----
    cost = {}
    for m in write_runs:
        gh, load, outtok, calls = run_cost(write_runs[m])
        n_usable = usability[f"{m}_primary"]["usable"] + usability[f"{m}_reserve"]["usable"]
        cost[f"generation_{m}"] = {"gpu_hours_excluding_startup": round(gh, 4), "startup_seconds": load,
                                   "calls_including_failed": calls, "usable_questions": n_usable,
                                   "gpu_hours_per_usable_question": round(gh / max(n_usable, 1), 5),
                                   "output_tokens_per_call": round(outtok / max(calls, 1)),
                                   "projected_gpu_hours_232k": round(gh / max(n_usable, 1) * PROJECTED_GENERATIONS)}
        gh, load, outtok, calls = run_cost(answer_runs[m])
        cost[f"answering_{m}"] = {"gpu_hours_excluding_startup": round(gh, 4), "startup_seconds": load,
                                  "answers": calls, "answers_per_gpu_hour": round(calls / max(gh, 1e-9), 1),
                                  "output_tokens_per_answer": round(outtok / max(calls, 1))}
    speedup = cost["generation_on"]["gpu_hours_per_usable_question"] / max(cost["generation_off"]["gpu_hours_per_usable_question"], 1e-12)
    cost["generation_speedup_off_vs_on"] = round(speedup, 2)
    report["cost"] = cost

    # ---- 7. the pre-set rule ----
    a_ok = acc["off"]["mean_pct"] >= acc["on"]["mean_pct"] - ACC_MARGIN
    u_ok = usability["off_primary"]["rate_pct"] >= usability["on_primary"]["rate_pct"] - USABLE_MARGIN
    s_ok = speedup >= SPEEDUP_MIN
    blocked = any(f["blocking"] for f in flags)
    verified = verify["writing"]["with_thinking"] == 0 and verify["answering"]["with_thinking"] == 0
    if pending:
        outcome = f"NOT FINAL: {pending} question(s) on check_sheet.csv still need your look; fill it in and rerun with --sheet"
    elif not verified:
        outcome = "NOT USABLE: thinking-off replies show thinking, so the check did not test thinking off; explain before deciding"
    elif a_ok and u_ok and s_ok and not blocked:
        outcome = "THINKING OFF meets the pre-set criterion"
    elif a_ok and u_ok and s_ok and blocked:
        outcome = "THINKING ON unless the owner reviews the flagged category and records a decision (blocking category flag)"
    else:
        outcome = "THINKING ON (the pre-set criterion for thinking off is not met)"
    report["rule_outcome"] = {"accuracy_within_5": a_ok, "usable_within_5": u_ok, "generation_2x_cheaper": s_ok,
                              "blocking_flag": blocked, "thinking_off_verified": verified,
                              "sheet_items_pending": pending, "outcome": outcome}
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- printed summary ----
    print("THINKING ON/OFF CHECK (observational; the 5-point rule is a descriptive engineering criterion)")
    print(f"Answer set: {len(questions)} question(s); by origin and category: {composition['by_origin_and_category']}; "
          f"{len(composition['replacements'])} replacement(s), {len(composition['unfilled'])} unfilled")
    print("1. USABILITY (first attempt, primary slots BM8001-BM8040):")
    for m in ("on", "off"):
        u = usability[f"{m}_primary"]
        print(f"   thinking {m}: {u['usable']}/{u['of']} ({u['rate_pct']}%) by category {u['by_category']}; "
              f"reserve block {usability[f'{m}_reserve']['usable']}/{usability[f'{m}_reserve']['of']}")
    for f_ in failures:
        print(f"   FAILED ({f_['mode']}, {f_['block']}) {f_['item_id']} [{f_['category']}]: {'; '.join(f_['problems'])}")
    print("2. ANSWER CORRECTNESS (mean over all answers; 95% interval resamples questions):")
    for m in ("on", "off"):
        a = acc[m]
        print(f"   thinking {m}: {a['mean_pct']}% {a['question_bootstrap_95_pct']}, format failures {a['format_failures']}/{a['answers']}; by category {a['by_category']}")
    print(f"   off minus on: {acc['difference_off_minus_on_pct']} points, 95% interval {acc['difference_question_bootstrap_95_pct']}")
    for fl in flags:
        print(f"   FLAG {fl['category']}: on {fl['on_pct']}% vs off {fl['off_pct']}%" + (" (BLOCKING)" if fl["blocking"] else ""))
    print(f"   thinking-off verification: writing {verify['writing']['with_thinking']}/{verify['writing']['replies']}, "
          f"answering {verify['answering']['with_thinking']}/{verify['answering']['replies']} repl(ies) show thinking")
    print("3. COST (start-up excluded, shown separately):")
    for k, v in cost.items():
        print(f"   {k}: {v}")
    print(f"Owner's sheet: {len(sheet_rows)} question(s) in {out / 'check_sheet.csv'}; {pending} not yet filled in")
    print(f"RULE: accuracy within 5: {a_ok}; usable within 5: {u_ok}; generation >= 2x cheaper: {s_ok}; blocking flag: {blocked}")
    print(f"OUTCOME: {outcome}")
    print(f"Wrote {out / 'report.json'}, {out / 'graded_answers.jsonl'}, {out / 'check_sheet.csv'}")


if __name__ == "__main__":
    main()
