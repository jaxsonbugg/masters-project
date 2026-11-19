"""Tests for code/generation/answer_check.py and the thinking-check helpers in open_teacher_test.py.

Everything is synthetic: four fake run folders (two writing runs of set K, two answer runs) are built in a temporary
folder, so nothing touches Talon, the internet or any paid service. R expressions are graded in the R sandbox (its
self-test runs first), so the sandbox must be set up (recovery/r_sandbox.md).
Usage: python test_answer_check.py"""
import csv, json, shutil, subprocess, sys, tempfile
from pathlib import Path

CODE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CODE / "generation"))
import open_teacher_test as ott  # noqa: E402
import answer_check as ac  # noqa: E402
import generate_benchmark as gb  # noqa: E402

PY = sys.executable
OTT, AC = str(CODE / "generation" / "open_teacher_test.py"), str(CODE / "generation" / "answer_check.py")
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1; print(f"  PASS  {name}")
    else:
        failed += 1; print(f"  FAIL  {name}  {str(detail)[:400]}")


# ------------------------------------------------------------------ 1. small pieces
print("[1] final-answer extraction and grading rules")
check("the LAST 'Final answer:' line is used, markdown removed",
      ott.final_answer("Final answer: 1\nwork\n**Final answer:** `0.230`") == "0.230")
check("no 'Final answer:' line gives None (a format failure)", ott.final_answer("The answer is 4.") is None)
check("a <think> block is ignored", ott.final_answer("<think>Final answer: 9</think>\nFinal answer: 3") == "3")
num = {"answer_type": "number", "canonical_answer": "0.313", "answer_tolerance": 0.0005}
check("number: 0.313 is correct", ac.grade("0.313", num, None)[0])
check("number: 0.3125 is within the tolerance 0.0005 (a rounding tie either way)", ac.grade("0.3125", num, None)[0])
check("number: 0.32 is outside the tolerance", not ac.grade("0.32", num, None)[0])
check("number: '0.230' and '0.23' are the same number", ac.grade("0.23", {**num, "canonical_answer": "0.230"}, None)[0])
check("number: words with no number are wrong", not ac.grade("about a third", num, None)[0])
mc = {"answer_type": "multiple_choice", "canonical_answer": "C"}
check("multiple choice: 'C', '(C)' and 'C. text' all count as C",
      all(ac.grade(a, mc, None)[0] for a in ("C", "(C)", "C. The p-value", "c")))
check("multiple choice: 'B' is wrong", not ac.grade("B", mc, None)[0])
st = {"answer_type": "short_text", "canonical_answer": "nrow"}
check("short text: 'NROW()' matches 'nrow' after normalizing", ac.grade("NROW()", st, None)[0])
check("short text: an answer accepted on the owner's sheet counts", ac.grade("dim(x)[1]", st, None, ["dim(x)[1]"])[0])
check("missing final answer is wrong and named a format failure", ac.grade(None, num, None) == (False, "format failure: no 'Final answer:' line"))
plan = ott.k_positions()
check("the shared-set plan: positions 1-20 from thinking on, 21-40 from thinking off",
      [p[1] for p in plan] == ["on"] * 20 + ["off"] * 20)
check("each position's reserve slot has the same pattern position, hence the same category and difficulty",
      all((s := ott.slots_for_ids([p[2], p[3]])) and s[p[2]]["category"] == s[p[3]]["category"]
          and s[p[2]]["difficulty"] == s[p[3]]["difficulty"] for p in plan))

# ------------------------------------------------------------------ 2. end to end on synthetic run folders
print("[2] end to end: answer-set, grading, the owner's sheet, the pre-set rule")
T = Path(tempfile.mkdtemp(prefix="answer_check_test_"))
first, count = ott.SMOKE_SETS["K"]
slots = ott.slots_for_ids([f"BM{n:04d}" for n in range(first, first + count)])


def item_for(slot):
    it = {"question": "", "answer_type": slot["answer_type"], "choices": [], "working": "w", "r_solution": "",
          "canonical_answer": "", "answer_tolerance": 0, "r_check": "", "explanation": "A short explanation sentence.",
          "difficulty": slot["difficulty"], "category": slot["category"], "subtopic": slot["subtopic"]}
    t = slot["answer_type"]
    if t == "number":
        it.update(question=f"({slot['item_id']}) A fair coin is tossed 5 times. What is the probability of exactly 2 heads? "
                           "Give your answer to 3 decimal places.", r_solution="cat(dbinom(2, 5, 0.5))",
                  canonical_answer="0.313", answer_tolerance=0.0005)
    elif t == "multiple_choice":
        it.update(question=f"({slot['item_id']}) Which statement about the sample mean is true?",
                  choices=["It is unbiased for the population mean", "It is always equal to the median",
                           "It ignores outliers", "It has zero variance"], canonical_answer="A")
    elif t == "r_expression":
        it.update(question=f"({slot['item_id']}) Write one line of R that returns the sum of the integers from 1 to 10.",
                  canonical_answer="sum(1:10)", r_check="isTRUE(all.equal(eval(parse(text = candidate)), 55))")
    else:
        it.update(question=f"({slot['item_id']}) Which base R function returns the number of rows of a data frame?",
                  canonical_answer="nrow")
    return it


def write_run(name, mode, broken, wall):
    d = T / name; d.mkdir()
    rows = []
    for iid, slot in slots.items():
        content = "not json at all" if iid in broken else json.dumps(item_for(slot))
        msg = {"content": content}
        if mode == "on":
            msg["reasoning_content"] = "thinking"
        rows.append({"item_id": iid, "use": "dev_test_only", "backend": "talon", "attempt": 1, "http_status": 200,
                     "response": {"model": "qwen3.6-27b-bf16", "choices": [{"message": msg, "finish_reason": "stop"}],
                                  "usage": {"prompt_tokens": 1000, "completion_tokens": 4000 if mode == "on" else 400}}})
    (d / "responses.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    sampling, extra = ott.mode_params("talon", mode)
    meta = {"use": "dev_test_only", "backend": "talon", "model": "qwen3.6-27b-bf16", "thinking": mode, "sampling": sampling,
            "extra_params": extra, "slot_set": "dev_smoke", "slot_ids": list(slots), "max_tokens": 16384,
            "meta": {"gpu_count": "1", "load_seconds": "86"},
            "sessions": [{"wall_seconds": wall, "out_tokens": 60 * (4000 if mode == "on" else 400), "calls": 60}]}
    (d / "run_log.json").write_text(json.dumps(meta), encoding="utf-8")
    # what `score` would write: the scored items (number keys confirmed by R)
    items = []
    for iid, slot in slots.items():
        if iid in broken:
            continue
        it = {**slot, **item_for(slot), "final_status": "ok", "key_source": "r" if slot["answer_type"] == "number" else "model"}
        items.append(it)
    (d / "items.jsonl").write_text("".join(json.dumps(i) + "\n" for i in items), encoding="utf-8")
    return d


# BM8003 fails in the thinking-ON run -> position 3 (origin on) is replaced by reserve BM8043 (on).
# BM8025 and its reserve BM8045 both fail in the thinking-OFF run -> position 25 (origin off) stays unfilled.
w_on = write_run("w_on", "on", {"BM8003"}, 3600)
w_off = write_run("w_off", "off", {"BM8025", "BM8045"}, 600)
r = subprocess.run([PY, OTT, "--out-root", str(T), "answer-set", "--on", str(w_on), "--off", str(w_off)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
set_line = [l for l in r.stdout.splitlines() if l.startswith("ANSWER_SET=")]
check("answer-set ran", r.returncode == 0 and set_line, r.stdout[-400:] + r.stderr[-400:])
set_path = Path(set_line[0].split("=", 1)[1].strip())
comp = json.loads((set_path.parent / "composition.json").read_text(encoding="utf-8"))
qs = [json.loads(l) for l in set_path.read_text(encoding="utf-8").splitlines() if l.strip()]
check("position 3 was replaced by the reserve slot BM8043 from the same (thinking-on) run",
      [(x["position"], x["primary_slot"], x["used_slot"]) for x in comp["replacements"]] == [(3, "BM8003", "BM8043")], comp["replacements"])
check("position 25 stays unfilled and is reported, not silently dropped",
      [x["position"] for x in comp["unfilled"]] == [25] and len(qs) == 39, comp["unfilled"])
check("the composition counts questions by origin mode and category",
      sum(comp["by_origin_and_category"].values()) == 39 and all(k.split(" | ")[0] in ("on", "off") for k in comp["by_origin_and_category"]))


def answer_run(name, mode, answer_for, wall):
    d = T / name; d.mkdir()
    rows = []
    for q in qs:
        for n in (1, 2, 3):
            msg = {"content": f"Some working.\nFinal answer: {answer_for(q, n)}"}
            if mode == "on":
                msg["reasoning_content"] = "thinking"
            rows.append({"answer_id": f"{q['qid']}-s{n}", "qid": q["qid"], "item_id": q["item_id"], "sample": n,
                         "use": "dev_test_only", "backend": "talon", "http_status": 200,
                         "response": {"model": "qwen3.6-27b-bf16", "choices": [{"message": msg, "finish_reason": "stop"}],
                                      "usage": {"prompt_tokens": 300, "completion_tokens": 900 if mode == "on" else 60}}})
    (d / "responses.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
    sampling, extra = ott.mode_params("talon", mode)
    meta = {"kind": "answers", "use": "dev_test_only", "backend": "talon", "model": "qwen3.6-27b-bf16", "thinking": mode,
            "sampling": sampling, "extra_params": extra, "samples": 3, "question_ids": [q["qid"] for q in qs],
            "answer_prompt_sha256": ott.load_answer_prompt()[1], "meta": {"gpu_count": "1", "load_seconds": "80"},
            "sessions": [{"wall_seconds": wall, "out_tokens": len(rows) * 100, "calls": len(rows)}]}
    (d / "run_log.json").write_text(json.dumps(meta), encoding="utf-8")
    return d


KEY = {"number": "0.313", "multiple_choice": "A", "r_expression": "sum(1:10)", "short_text": "NROW()"}


def right(q, n):
    if q["answer_type"] == "r_expression" and n == 2:
        return "55L"   # right, but only the r_check (run in the sandbox) can tell
    return KEY[q["answer_type"]]


a_on = answer_run("a_on", "on", right, 1800)
a_off = answer_run("a_off", "off", right, 200)
out1 = T / "report1"


def run_check(out, a_off_dir, sheet=None):
    args = [PY, AC, "--write-on", str(w_on), "--write-off", str(w_off), "--answers-on", str(a_on),
            "--answers-off", str(a_off_dir), "--set-dir", str(set_path.parent), "--out", str(out)]
    if sheet:
        args += ["--sheet", str(sheet)]
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")


r = run_check(out1, a_off)
rep = json.loads((out1 / "report.json").read_text(encoding="utf-8")) if (out1 / "report.json").exists() else {}
check("answer_check runs end to end (R expressions graded in the sandbox)", r.returncode == 0 and rep, r.stdout[-600:] + r.stderr[-600:])
check("both modes score 100% when every answer is right (including '55L', judged by the r_check)",
      rep.get("correctness", {}).get("on", {}).get("mean_pct") == 100.0 and rep["correctness"]["off"]["mean_pct"] == 100.0,
      rep.get("correctness"))
check("usability: 39/40 primary slots usable in each mode, failures listed with reasons",
      rep["usability"]["on_primary"]["usable"] == 39 and rep["usability"]["off_primary"]["usable"] == 39
      and {(f["mode"], f["item_id"]) for f in rep["writing_failures"]} == {("on", "BM8003"), ("off", "BM8025"), ("off", "BM8045")})
gen = rep["cost"]
check("generation cost per usable question includes failed attempts (3600 s / 59 usable vs 600 s / 58 usable)",
      abs(gen["generation_on"]["gpu_hours_per_usable_question"] - round(1.0 / 59, 5)) < 1e-5
      and abs(gen["generation_off"]["gpu_hours_per_usable_question"] - round((600 / 3600) / 58, 5)) < 1e-5, gen)
check("start-up time is reported separately and answering throughput separately",
      gen["generation_on"]["startup_seconds"] == "86" and "answers_per_gpu_hour" in gen["answering_off"])
check("thinking-off verification: no thinking-off reply shows thinking",
      rep["thinking_off_verification"]["writing"]["with_thinking"] == 0 and rep["thinking_off_verification"]["answering"]["with_thinking"] == 0)
sheet_rows = list(csv.DictReader(open(out1 / "check_sheet.csv", encoding="utf-8")))
check("the owner's sheet lists the short-text questions and the outcome waits for it",
      sheet_rows and all("short-text" in s["reason"] for s in sheet_rows) and rep["rule_outcome"]["outcome"].startswith("NOT FINAL"),
      (len(sheet_rows), rep["rule_outcome"]))
for s in sheet_rows:
    s["key_correct"] = "yes"
filled = T / "sheet_filled.csv"
with open(filled, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(sheet_rows[0])); w.writeheader(); w.writerows(sheet_rows)
r = run_check(T / "report2", a_off, filled)
rep2 = json.loads((T / "report2" / "report.json").read_text(encoding="utf-8"))
check("with the sheet filled in, equal accuracy, equal usability and a 2x+ cheaper generation: thinking off meets the criterion",
      rep2["rule_outcome"]["outcome"] == "THINKING OFF meets the pre-set criterion" and rep2["cost"]["generation_speedup_off_vs_on"] >= 2,
      rep2["rule_outcome"])


def worse_on_numbers(q, n):
    return "0.5" if q["category"] == "numerical" else right(q, n)


a_off_bad = answer_run("a_off_bad", "off", worse_on_numbers, 200)
r = run_check(T / "report3", a_off_bad, filled)
rep3 = json.loads((T / "report3" / "report.json").read_text(encoding="utf-8"))
check("new disagreements go on the sheet, so the outcome waits for the owner (NOT FINAL)",
      rep3["rule_outcome"]["outcome"].startswith("NOT FINAL"), rep3["rule_outcome"])
sheet3 = list(csv.DictReader(open(T / "report3" / "check_sheet.csv", encoding="utf-8")))
for s in sheet3:
    s["key_correct"] = "yes"   # the owner confirms the keys: thinking off's "0.5" really is wrong
filled3 = T / "sheet_filled3.csv"
with open(filled3, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(sheet3[0])); w.writeheader(); w.writerows(sheet3)
r = run_check(T / "report3", a_off_bad, filled3)
rep3 = json.loads((T / "report3" / "report.json").read_text(encoding="utf-8"))
flags = {f["category"]: f["blocking"] for f in rep3["category_flags"]}
check("thinking off wrong on numerical questions: a blocking numerical flag and the outcome is thinking on",
      flags.get("numerical") is True and rep3["rule_outcome"]["outcome"].startswith("THINKING ON"), (flags, rep3["rule_outcome"]))
check("the accuracy difference has a question-level bootstrap interval",
      len(rep3["correctness"]["difference_question_bootstrap_95_pct"]) == 2
      and rep3["correctness"]["difference_question_bootstrap_95_pct"][0] <= rep3["correctness"]["difference_off_minus_on_pct"])
rows_sheet3 = list(csv.DictReader(open(T / "report3" / "check_sheet.csv", encoding="utf-8")))
check("questions where the modes' most common answers differ are put on the owner's sheet",
      any("differ" in s["reason"] for s in rows_sheet3))
leak = answer_run("a_off_leak", "off", right, 200)
lines = [json.loads(l) for l in (leak / "responses.jsonl").read_text(encoding="utf-8").splitlines()]
lines[0]["response"]["choices"][0]["message"]["reasoning_content"] = "I am thinking"
(leak / "responses.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
r = run_check(T / "report4", leak, filled)
rep4 = json.loads((T / "report4" / "report.json").read_text(encoding="utf-8"))
check("a thinking-off reply that shows thinking makes the check NOT USABLE until explained",
      rep4["rule_outcome"]["outcome"].startswith("NOT USABLE"), rep4["rule_outcome"])

shutil.rmtree(T, ignore_errors=True)
print(f"\n==== answer check tests: {passed} passed, {failed} failed ====")
sys.exit(1 if failed else 0)
