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

WHEN NO DECISION IS DRAWN (outcome NOT USABLE, checked before anything else): a run fails infrastructure validation; the
answer records are not complete and paired (a MISSING record or an HTTP ERROR is a gap, never a wrong answer; a reply that is
wrong, cut off or has no "Final answer:" line is a valid, incorrect answer); fewer than 36 of 40 positions are filled or more
than 2 are unfilled in either origin half; or a thinking-off reply shows thinking.

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
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import open_teacher_test as ott  # noqa: E402  (reuses reply parsing, the usable test, final-answer extraction)
import generate_benchmark as gb  # noqa: E402

ACC_MARGIN, USABLE_MARGIN, SPEEDUP_MIN, CATEGORY_FLAG = 5.0, 5.0, 2.0, 10.0   # the pre-set rule (points, points, ratio, points)
# When is the comparison usable at all? (added 2026-11-18, before any result; the thresholds above are unchanged)
#  - all four runs pass INFRASTRUCTURE validation (`open_teacher_test.py validate`: exit 0 or 2);
#  - the answer records are COMPLETE and PAIRED: every question x sample has a saved HTTP-200 reply in BOTH modes, and both
#    runs used the same number of samples. A missing reply or an HTTP error is an infrastructure gap, never a wrong answer;
#    a reply that exists but is wrong, cut off or has no "Final answer:" line is a valid (incorrect) model answer;
#  - the shared set is complete enough: at most 4 of the 40 positions unfilled (at least 36 filled), and at most 2 unfilled in
#    either origin half, so the set stays balanced between the two modes. Otherwise the comparison is NOT USABLE.
SET_MIN_FILLED, SET_MAX_UNFILLED_PER_HALF = 36, 2
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


def final_answer_with_fix(content):
    """(answer, fixed). The pre-specified reading is the last "Final answer:" line (ott.final_answer).

    DOCUMENTED PARSER FIX (decided 2026-11-19, after the stage K run but BEFORE any answer was graded; applied identically
    to both modes): answering prompt v1 told the model, for R-expression questions, to give "one line of R code ... and
    nothing else", which conflicts with its own instruction to end with a "Final answer:" line. Many replies were therefore
    just the R line. When a reply has no "Final answer:" line but its whole content (thinking removed) is exactly ONE
    non-empty line, that line is taken as the answer (fixed=True). Everything else is unchanged: a reply with several
    lines and no "Final answer:" line, or an empty reply (for example cut off while thinking), is still a format failure.
    The report also shows the results WITHOUT this fix."""
    fa = ott.final_answer(content)
    if fa is not None:
        return fa, False
    lines = [l for l in ott.THINK.sub("", content or "").strip().splitlines() if l.strip()]
    if len(lines) == 1:
        return (lines[0].strip().strip("`$ ").strip() or None), True
    return None, False


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
                       "set_min_filled": SET_MIN_FILLED, "set_max_unfilled_per_half": SET_MAX_UNFILLED_PER_HALF,
                       "nature": "descriptive engineering criterion, not a statistical non-inferiority claim"}}

    # ---- 0. infrastructure validation of all four runs (the same `validate` the Talon job ran) ----
    validation = {}
    for name, d in (("writing_on", write_runs["on"]), ("writing_off", write_runs["off"]),
                    ("answers_on", answer_runs["on"]), ("answers_off", answer_runs["off"])):
        r = subprocess.run([sys.executable, str(Path(ott.__file__)), "validate", "--run", str(d)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = r.stdout.splitlines()
        validation[name] = {"exit": r.returncode, "infrastructure_pass": r.returncode in (0, 2),
                            "result": next((l for l in reversed(lines) if l.startswith("VALIDATE_RESULT")), None),
                            "infrastructure_failures": [l.strip() for l in lines if "INFRASTRUCTURE FAIL" in l][:10]}
    report["validation"] = validation
    samples = {m: json.loads((d / "run_log.json").read_text(encoding="utf-8")).get("samples") for m, d in answer_runs.items()}

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
                    infra = bool(problems) and problems[0].startswith(("no saved reply", "no reply (HTTP"))
                    failures.append({"mode": m, "block": block, "item_id": iid, "category": slots[iid]["category"],
                                     "kind": "infrastructure (no valid reply)" if infra else "model (reply failed a check)",
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
        for sf in it.get("soft_flags") or []:
            if "differs from R" in sf:   # R's value replaced the model's typed key: worth a look (adds a check, changes no rule)
                note.append("R's value replaced a different typed key (" + sf[:90] + ")")
        s = sheet.get(q["qid"])
        if s and s.get("key_correct", "").strip().lower() == "no" and s.get("corrected_key", "").strip():
            it["canonical_answer"] = s["corrected_key"].strip()
            note.append("key corrected on the owner's sheet")
        key_items[q["qid"]], key_notes[q["qid"]] = it, note
    # Every expected answer record gets a status. Only "answered" records are graded: a MISSING record (no row at all) or an
    # HTTP ERROR (rows, but none with HTTP 200) is an infrastructure gap, never counted as a wrong answer. An answered reply that
    # is wrong, cut off or lacks a "Final answer:" line is a valid model answer that is incorrect.
    graded, gaps = [], []
    per_q = {m: {} for m in answer_runs}
    records = {}
    n_samples = max((s or 0) for s in samples.values())
    for m, d in answer_runs.items():
        all_rows = ott.read_rows(d)
        rows = first_ok(all_rows, "answer_id")
        seen = {r.get("answer_id") for r in all_rows}
        counts = Counter()
        for q in questions:
            extra_ok = [x.strip() for x in (sheet.get(q["qid"], {}).get("accept_also") or "").split("|") if x.strip()]
            vals = []
            for n in range(1, n_samples + 1):
                aid = f"{q['qid']}-s{n}"
                rec = rows.get(aid)
                if rec is None:
                    status = "http_error" if aid in seen else "missing"
                    counts[status] += 1
                    gaps.append({"mode": m, "answer_id": aid, "status": status})
                    continue
                counts["answered"] += 1
                content, _, finish, usage = ott.reply_parts(rec)
                fa, fixed = final_answer_with_fix(content)
                ok, how = grade(fa, key_items[q["qid"]], sandbox, extra_ok)
                # the same answer read strictly (no parser fix): only differs when the fix was used
                ok_strict = ok if not fixed else False
                if fixed:
                    how = "single-line reply read by the documented parser fix; " + how
                if finish == "length":
                    how = "cut off at max_tokens; " + how
                vals.append(ok)
                graded.append({"mode": m, "qid": q["qid"], "sample": n, "status": "answered", "origin": q["origin"],
                               "category": q["category"], "answer_type": q["answer_type"], "final_answer": fa,
                               "key": key_items[q["qid"]]["canonical_answer"], "correct": ok, "how": how,
                               "single_line_fix": fixed, "correct_without_fix": ok_strict,
                               "format_failure": fa is None, "cut_off": finish == "length",
                               "output_tokens": usage.get("completion_tokens")})
            if vals:
                per_q[m][q["qid"]] = sum(vals) / len(vals)
        records[m] = {"expected": len(questions) * n_samples, "answered": counts["answered"],
                      "missing": counts["missing"], "http_error": counts["http_error"], "samples_in_run_log": samples[m]}
    complete = (samples["on"] == samples["off"] and all(r["answered"] == r["expected"] for r in records.values()))
    report["answer_records"] = {**records, "complete_and_paired": complete, "gaps": gaps[:50]}
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
    # only questions answered in BOTH modes enter the comparison (with complete records that is every question)
    qids = [q["qid"] for q in questions if q["qid"] in per_q["on"] and q["qid"] in per_q["off"]]
    acc = {}
    for m in answer_runs:
        mine = [g for g in graded if g["mode"] == m and g["qid"] in qids]
        lo, hi = bootstrap(per_q[m][i] for i in qids)
        by_cat = {}
        for c in sorted({q["category"] for q in questions if q["qid"] in qids}):
            ids = [q["qid"] for q in questions if q["category"] == c and q["qid"] in qids]
            by_cat[c] = round(100 * sum(per_q[m][i] for i in ids) / len(ids), 1)
        acc[m] = {"mean_pct": round(100 * sum(g["correct"] for g in mine) / max(len(mine), 1), 1),
                  "mean_pct_without_parser_fix": round(100 * sum(g["correct_without_fix"] for g in mine) / max(len(mine), 1), 1),
                  "parser_fix_used": sum(g["single_line_fix"] for g in mine),
                  "question_bootstrap_95_pct": [round(100 * lo, 1), round(100 * hi, 1)],
                  "format_failures": sum(g["format_failure"] for g in mine), "cut_off": sum(g["cut_off"] for g in mine),
                  "answers_graded": len(mine), "by_category": by_cat}
    acc["questions_compared"] = len(qids)
    dlo, dhi = bootstrap(per_q["off"][i] - per_q["on"][i] for i in qids)
    acc["difference_off_minus_on_pct"] = round(acc["off"]["mean_pct"] - acc["on"]["mean_pct"], 1)
    acc["difference_question_bootstrap_95_pct"] = [round(100 * dlo, 1), round(100 * dhi, 1)]
    flags = [{"category": c, "on_pct": acc["on"]["by_category"][c], "off_pct": acc["off"]["by_category"][c],
              "blocking": c in BLOCKING_CATEGORIES}
             for c in acc["on"]["by_category"] if acc["on"]["by_category"][c] - acc["off"]["by_category"][c] >= CATEGORY_FLAG]
    report["correctness"] = acc
    report["category_flags"] = flags
    unfilled = composition["unfilled"]
    unfilled_half = {m: sum(1 for u in unfilled if u["origin"] == m) for m in ("on", "off")}
    set_usable = (len(questions) >= SET_MIN_FILLED and max(unfilled_half.values()) <= SET_MAX_UNFILLED_PER_HALF)
    report["answer_set"] = {"n_questions": len(questions), "by_origin_and_category": composition["by_origin_and_category"],
                            "replacements": composition["replacements"], "unfilled": unfilled,
                            "unfilled_positions": [u["position"] for u in unfilled], "unfilled_by_origin": unfilled_half,
                            "complete_enough": set_usable,
                            "rule": f"usable only with at least {SET_MIN_FILLED} of {ott.K_PRIMARY} positions filled and at most "
                                    f"{SET_MAX_UNFILLED_PER_HALF} unfilled in either origin half"}

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
    # Conditions under which NO decision may be drawn. They are checked before the owner's sheet and the rule.
    unusable = []
    failed_runs = [k for k, v in validation.items() if not v["infrastructure_pass"]]
    if failed_runs:
        unusable.append(f"infrastructure validation failed for {', '.join(failed_runs)}")
    if not complete:
        unusable.append("the answer records are incomplete or unpaired (" + "; ".join(
            f"{m}: {r['answered']}/{r['expected']} answered, {r['missing']} missing, {r['http_error']} HTTP error(s), "
            f"{r['samples_in_run_log']} sample(s)" for m, r in records.items()) + ")")
    if not set_usable:
        unusable.append(f"the shared set is too incomplete ({len(unfilled)} of {ott.K_PRIMARY} positions unfilled, "
                        f"{unfilled_half['on']} in the thinking-on half and {unfilled_half['off']} in the thinking-off half; "
                        f"the limit is {ott.K_PRIMARY - SET_MIN_FILLED} in all and {SET_MAX_UNFILLED_PER_HALF} per half)")
    if not verified:
        unusable.append("thinking-off replies show thinking, so the check did not test thinking off")
    if unusable:
        outcome = "NOT USABLE: " + "; ".join(unusable) + ". No thinking-mode decision is drawn; explain or rerun first"
    elif pending:
        outcome = f"NOT FINAL: {pending} question(s) on check_sheet.csv still need your look; fill it in and rerun with --sheet"
    elif a_ok and u_ok and s_ok and not blocked:
        outcome = "THINKING OFF meets the pre-set criterion"
    elif a_ok and u_ok and s_ok and blocked:
        outcome = "THINKING ON unless the owner reviews the flagged category and records a decision (blocking category flag)"
    else:
        outcome = "THINKING ON (the pre-set criterion for thinking off is not met)"
    report["parser_fix_sensitivity"] = {
        "rule": "a reply with no 'Final answer:' line whose whole content is exactly one line is read as the answer "
                "(documented fix of 2026-11-19, decided before grading, applied to both modes)",
        "used_on": acc["on"]["parser_fix_used"], "used_off": acc["off"]["parser_fix_used"],
        "accuracy_on_without_fix": acc["on"]["mean_pct_without_parser_fix"],
        "accuracy_off_without_fix": acc["off"]["mean_pct_without_parser_fix"],
        "accuracy_within_5_without_fix": acc["off"]["mean_pct_without_parser_fix"] >= acc["on"]["mean_pct_without_parser_fix"] - ACC_MARGIN}
    report["rule_outcome"] = {"accuracy_within_5": a_ok, "usable_within_5": u_ok, "generation_2x_cheaper": s_ok,
                              "blocking_flag": blocked, "thinking_off_verified": verified,
                              "infrastructure_validated": not failed_runs, "answer_records_complete": complete,
                              "set_complete_enough": set_usable, "not_usable_because": unusable,
                              "sheet_items_pending": pending, "outcome": outcome}
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- printed summary ----
    print("THINKING ON/OFF CHECK (observational; the 5-point rule is a descriptive engineering criterion)")
    print("0. VALIDITY: " + "; ".join(f"{k} {'PASS' if v['infrastructure_pass'] else 'FAIL'}" for k, v in validation.items()))
    for m, r in records.items():
        print(f"   answers {m}: {r['answered']}/{r['expected']} answered, {r['missing']} missing, {r['http_error']} HTTP error(s)")
    print(f"   unfilled positions: {[u['position'] for u in unfilled] or 'none'} (on half {unfilled_half['on']}, off half {unfilled_half['off']}); "
          f"set complete enough: {set_usable}")
    print(f"Answer set: {len(questions)} question(s); by origin and category: {composition['by_origin_and_category']}; "
          f"{len(composition['replacements'])} replacement(s), {len(composition['unfilled'])} unfilled")
    print("1. USABILITY (first attempt, primary slots BM8001-BM8040):")
    for m in ("on", "off"):
        u = usability[f"{m}_primary"]
        print(f"   thinking {m}: {u['usable']}/{u['of']} ({u['rate_pct']}%) by category {u['by_category']}; "
              f"reserve block {usability[f'{m}_reserve']['usable']}/{usability[f'{m}_reserve']['of']}")
    for f_ in failures:
        print(f"   FAILED ({f_['mode']}, {f_['block']}) {f_['item_id']} [{f_['category']}]: {'; '.join(f_['problems'])}")
    print(f"2. ANSWER CORRECTNESS (mean over the answered records of the {acc['questions_compared']} questions answered in both modes; 95% interval resamples questions):")
    for m in ("on", "off"):
        a = acc[m]
        print(f"   thinking {m}: {a['mean_pct']}% {a['question_bootstrap_95_pct']}, format failures {a['format_failures']} and cut off {a['cut_off']} of {a['answers_graded']} graded; by category {a['by_category']}")
    print(f"   off minus on: {acc['difference_off_minus_on_pct']} points, 95% interval {acc['difference_question_bootstrap_95_pct']}")
    pf = report["parser_fix_sensitivity"]
    print(f"   parser fix (one-line replies read as the answer) used: on {pf['used_on']}, off {pf['used_off']}; WITHOUT it: "
          f"on {pf['accuracy_on_without_fix']}%, off {pf['accuracy_off_without_fix']}%, accuracy within 5: {pf['accuracy_within_5_without_fix']}")
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
