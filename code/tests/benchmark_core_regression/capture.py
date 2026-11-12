"""
capture.py - take a "snapshot" of what the shared benchmark functions in generate_benchmark.py produce.

WHAT THIS IS AND WHY
generate_benchmark.py holds the pieces that every teacher run depends on: the question slots (blueprint), the v6
prompt text, the output schema, the automatic checks, and the step where R writes the answer key of a number
question. open_teacher_test.py (the Qwen runs on Redhawk and Talon) imports these pieces. When the file was cleaned
up in November 2026 (the Claude-only commands were removed), we needed proof that none of these pieces changed
behaviour. A snapshot is a JSON file that records their outputs for fixed inputs; test_regression.py takes a fresh
snapshot and compares it with the saved one, item by item.

WHAT IS RECORDED
  slots     - every slot BM0001 to BM9132 (the main slots, the smoke sets A and B, the throughput set T), as one
              short hash per slot, plus the full text of the first 20 slots so a difference can be read.
  prompt    - the v6 prompt file's SHA-256 and every section load_prompt() returns.
  requests  - the system and user text build_request() makes for every slot BM0001-BM1000 and the development
              slots (hashes; full text for BM0001). The `model` and `output_config` fields are NOT recorded on
              purpose: they were Claude API settings and were removed in the cleanup.
  schema    - schema_for("v6") and ITEM_SCHEMA.
  replies   - hand-made replies (good items of every answer type, every kind of hard problem, soft flags, rounding
              ties, negative zero, exponent notation, unsafe R code) run through process_reply() the same way
              open_teacher_test.py does it (a stand-in message object). Needs R.
  checks    - check_item() on items with r_keyed False and True.
  absent_r_solution - number replies whose `r_solution` FIELD is missing entirely (added 2026-11-11). Records a
              known loophole, kept on purpose: such a reply passes with the model's own key. See absent_r_solution().
  verify    - verify_item() and the `verify` command's output file on a small items file. Needs R.
  items     - optional (--items): the same reply, check and verify steps on every item of an existing items.jsonl.

HOW TO RUN (with the project's Python; R must be installed, see configs/paths.yaml)
  python capture.py --out snapshot.json                     the synthetic snapshot
  python capture.py --out snap_b2.json --items <items.jsonl> also an existing items file
"""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "code" / "generation"))
import generate_benchmark as gb  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEV_IDS = [f"BM{n:04d}" for n in list(range(9001, 9005)) + list(range(9101, 9133))]
SCHEMA_FIELDS = list(gb.ITEM_SCHEMA["properties"])


def h(obj):
    """Short, stable hash of any JSON-able value."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:20]


def message(text, stop_reason="end_turn"):
    """The same stand-in for an API reply that open_teacher_test.py builds before calling process_reply."""
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])


def base_item(slot, **fields):
    it = {"question": "x", "answer_type": slot["answer_type"], "choices": [], "working": "work shown here",
          "r_solution": "", "canonical_answer": "", "answer_tolerance": 0, "r_check": "",
          "explanation": "A worked explanation of the answer.", "difficulty": slot["difficulty"],
          "category": slot["category"], "subtopic": slot["subtopic"]}
    it.update(fields)
    return it


def find_slot(slots, **want):
    for s in slots:
        if all(s[k] == v for k, v in want.items()):
            return s
    raise LookupError(want)


def reply_cases(slots):
    """(name, slot, reply text, stop_reason). Covers the paths process_reply and check_item can take."""
    num = find_slot(slots, category="numerical", answer_type="number")
    rin = find_slot(slots, category="r_interpretation", answer_type="number")
    rtx = find_slot(slots, category="r_interpretation", answer_type="short_text")
    mc = find_slot(slots, category="conceptual")
    oi = find_slot(slots, category="output_interpretation")
    rg = find_slot(slots, category="r_generation")
    q3 = "Two dice are rolled. Find the probability. Round to 3 decimal places."
    mcq = dict(question="Which statement about a p-value is correct?", choices=["a", "b", "c", "d"], canonical_answer="B")
    J = lambda it: json.dumps(it)
    cases = [
        ("number good", num, J(base_item(num, question=q3, r_solution="cat(dbinom(2, 5, 0.5))", canonical_answer="0.313",
                                          answer_tolerance=0.0005)), "end_turn"),
        ("number typed key differs (soft flag)", num, J(base_item(num, question=q3, r_solution="cat(207.0202)",
                                                                   canonical_answer="207.01", answer_tolerance=0.005)), "end_turn"),
        ("number typed key not a number (soft flag)", num, J(base_item(num, question=q3, r_solution="cat(1/3)",
                                                                        canonical_answer="one third")), "end_turn"),
        ("rounding tie halves up", num, J(base_item(num, question=q3, r_solution="cat(0.3125)", canonical_answer="0.313",
                                                     answer_tolerance=0.0005)), "end_turn"),
        ("negative zero", num, J(base_item(num, question=q3, r_solution="cat(-0.0001)", canonical_answer="0.000",
                                            answer_tolerance=0.0005)), "end_turn"),
        ("exponent notation", num, J(base_item(num, question="Find p. Round to 6 decimal places.",
                                                r_solution="cat(1.5e-05)", canonical_answer="0.000015",
                                                answer_tolerance=0.0000005)), "end_turn"),
        ("whole number from exact code", rin, J(base_item(rin, question="What does sum(1:4) print?",
                                                           r_solution="cat(sum(1:4))", canonical_answer="10")), "end_turn"),
        ("no rounding stated, non-integer (hard)", num, J(base_item(num, question="Find the probability.",
                                                                     r_solution="cat(1/3)", canonical_answer="0.333")), "end_turn"),
        ("r_solution prints two numbers (hard)", num, J(base_item(num, question=q3, r_solution="cat(1, 2)",
                                                                   canonical_answer="1.000")), "end_turn"),
        ("r_solution R error (hard)", num, J(base_item(num, question=q3, r_solution="stop('boom')",
                                                        canonical_answer="1.000")), "end_turn"),
        ("r_solution unsafe library() (hard)", num, J(base_item(num, question=q3, r_solution="library(MASS); cat(1)",
                                                                 canonical_answer="1.000")), "end_turn"),
        ("number without r_solution (hard)", num, J(base_item(num, question=q3, canonical_answer="0.313")), "end_turn"),
        ("multiple choice good", mc, J(base_item(mc, **mcq)), "end_turn"),
        ("output interpretation good", oi, J(base_item(oi, **mcq)), "end_turn"),
        ("multiple choice 3 choices", mc, J(base_item(mc, **{**mcq, "choices": ["a", "b", "c"]})), "end_turn"),
        ("multiple choice key not a letter", mc, J(base_item(mc, **{**mcq, "canonical_answer": "the second"})), "end_turn"),
        ("r_expression good", rg, J(base_item(rg, question="Write one line of R that returns the sum of 1 to 10.",
                                               canonical_answer="sum(1:10)", r_check="isTRUE(eval(parse(text=candidate)) == 55)")), "end_turn"),
        ("r_expression without r_check", rg, J(base_item(rg, question="Write R code.", canonical_answer="sum(1:10)")), "end_turn"),
        ("r_check ignores candidate", rg, J(base_item(rg, question="Write R code.", canonical_answer="sum(1:10)",
                                                       r_check="sum(1:10) == 55")), "end_turn"),
        ("answer key inside the question", rg, J(base_item(rg, question="Explain rep(c(1,2,3), times = c(3,2,1)) here.",
                                                            canonical_answer="rep(c(1,2,3), times = c(3,2,1))",
                                                            r_check="identical(eval(parse(text=candidate)), rep(1:3, 3:1))")), "end_turn"),
        ("short text good", rtx, J(base_item(rtx, question="Which function is misspelled in mena(x)?",
                                              canonical_answer="mean")), "end_turn"),
        ("choices on a non-MC item", rtx, J(base_item(rtx, question="Name it.", canonical_answer="mean",
                                                       choices=["a", "b"])), "end_turn"),
        ("thinking aloud 'Wait,'", mc, J(base_item(mc, **{**mcq, "question": "Which is right? Wait, let us redo it."})), "end_turn"),
        ("'wait' as normal English", mc, J(base_item(mc, **{**mcq, "question": "Customers wait at a clinic. Which is right?"})), "end_turn"),
        ("'Actually,' self-correction", mc, J(base_item(mc, **{**mcq, "question": "A test. Actually, to keep it simple, use this."})), "end_turn"),
        ("trailing ellipsis", mc, J(base_item(mc, **{**mcq, "question": "At least one of the three must be..."})), "end_turn"),
        ("ellipsis after code is allowed", rg, J(base_item(rg, question="Complete cv <- function(x) ...",
                                                            canonical_answer="sd(x)/mean(x)",
                                                            r_check="is.character(candidate)")), "end_turn"),
        ("ellipsis inside text is allowed", mc, J(base_item(mc, **{**mcq, "question": "For X1, ..., Xn iid, which is right?"})), "end_turn"),
        ("explanation too short", mc, J(base_item(mc, **{**mcq, "explanation": "invalid"})), "end_turn"),
        ("category differs from the slot", mc, J({**base_item(mc, **mcq), "category": "numerical"}), "end_turn"),
        ("missing field", mc, J({k: v for k, v in base_item(mc, **mcq).items() if k != "explanation"}), "end_turn"),
        ("not valid JSON", mc, '{"question": "unfinished', "end_turn"),
        ("cut off at max_tokens", mc, J(base_item(mc, **mcq)), "max_tokens"),
        ("refusal", mc, "", "refusal"),
        ("canonical answer too long", rtx, J(base_item(rtx, question="Name it.", canonical_answer="m" * 120)), "end_turn"),
    ]
    return cases


def check_cases(slots):
    """check_item on its own, with r_keyed False (the model's typed key is judged) and True."""
    num = find_slot(slots, category="numerical", answer_type="number")
    out = []
    for name, fields in [
        ("decimals mismatch", dict(question="Round to 3 decimal places.", r_solution="cat(1)", canonical_answer="0.74",
                                   answer_tolerance=0.0005)),
        ("tolerance below half a decimal", dict(question="Round to 2 decimal places.", r_solution="cat(1)",
                                                canonical_answer="0.94", answer_tolerance=0.001)),
        ("whole number tolerance 0 ok", dict(question="Give the whole number.", r_solution="cat(1)", canonical_answer="12")),
        ("key vs explanation, no r_solution", dict(question="Round to 1 decimal places.", canonical_answer="0.8",
                                                   answer_tolerance=0.05, explanation="The result is 0.735 overall.")),
        ("not a plain number", dict(question="Round to 2 decimal places.", r_solution="cat(1)", canonical_answer="about 1",
                                    answer_tolerance=0.005)),
    ]:
        item = base_item(num, **fields)
        out.append({"case": name,
                    "r_keyed_false": gb.check_item(dict(item), num, "end_turn", r_keyed=False),
                    "r_keyed_true": gb.check_item(dict(item), num, "end_turn", r_keyed=True)})
    return out


def verify_items(slots):
    num = find_slot(slots, category="numerical", answer_type="number")
    mc = find_slot(slots, category="conceptual")
    rg = find_slot(slots, category="r_generation")
    rows = [
        {"item_id": "V1", **base_item(num, question="Round to 3 decimal places.", r_solution="cat(0.3125)",
                                      canonical_answer="0.313", answer_tolerance=0.0005), "key_source": "r"},
        {"item_id": "V2", **base_item(num, question="Round to 3 decimal places.", r_solution="cat(0.7348)",
                                      canonical_answer="0.800", answer_tolerance=0.0005)},
        {"item_id": "V3", **base_item(num, question="Round to 2 decimal places.", r_solution="cat(0.940869)",
                                      canonical_answer="0.94", answer_tolerance=0.005), "soft_flags": ["a soft note"]},
        {"item_id": "V4", **base_item(rg, question="Write R code for the sum of 1 to 10.", canonical_answer="sum(1:10)",
                                      r_check="isTRUE(eval(parse(text=candidate)) == 55)")},
        {"item_id": "V5", **base_item(rg, question="Write R code for the sum of 1 to 10.", canonical_answer="sum(1:10)",
                                      r_check="is.character(candidate) || is.null(candidate)")},
        {"item_id": "V6", **base_item(mc, question="Which is right?", choices=["a", "b", "c", "d"], canonical_answer="C")},
    ]
    return rows


def absent_r_solution(slots, rscript):
    """Number replies in which the `r_solution` FIELD IS MISSING ALTOGETHER (not present-but-empty, which is the
    separate case "number without r_solution (hard)" above).

    DOCUMENTED BEHAVIOR, KEPT ON PURPOSE (a known loophole, docs/methodology/workflow.md Section 10.2):
    check_item() treats a reply without an `r_solution` field as an old prompt-v1 item. It then requires only the
    v1 fields, skips the "number answer without r_solution" and "explanation too short" checks, and process_reply()
    keeps the model's own typed key (key_source "model") instead of a key computed by R. So such a number question
    passes with no hard problem. `verify` still flags it ("no r_solution, so R cannot recompute this key").
    This fixture records that behavior so any later change to it is deliberate and visible; it does not fix it."""
    num = find_slot(slots, category="numerical", answer_type="number")
    q3 = "Two dice are rolled. Find the probability. Round to 3 decimal places."
    full = base_item(num, question=q3, r_solution="cat(dbinom(2, 5, 0.5))", canonical_answer="0.313",
                     answer_tolerance=0.0005, explanation="The binomial probability is 0.3125, so the answer is 0.313.")
    shapes = {
        "no r_solution and no working field (prompt-v1 shape)":
            {k: v for k, v in full.items() if k not in ("r_solution", "working")},
        "no r_solution field, working present":
            {k: v for k, v in full.items() if k != "r_solution"},
        "no r_solution field, typed key contradicts the explanation":
            {**{k: v for k, v in full.items() if k != "r_solution"}, "canonical_answer": "0.800"},
    }
    out = []
    for name, reply in shapes.items():
        assert "r_solution" not in reply
        out.append({"case": name, "slot": num["item_id"],
                    "process_reply": process(num, json.dumps(reply), "end_turn", rscript),
                    "check_item_r_keyed_false": gb.check_item(dict(reply), num, "end_turn", r_keyed=False),
                    "check_item_r_keyed_true": gb.check_item(dict(reply), num, "end_turn", r_keyed=True),
                    "verify_item": list(gb.verify_item({"item_id": "A", **reply}, rscript))})
    return out


def process(slot, text, stop_reason, rscript):
    item, hard, soft = gb.process_reply(message(text, stop_reason), slot, rscript)
    return {"item": item, "hard": hard, "soft": soft}


def run_verify_command(rows):
    """The `verify` command, run as a separate process exactly as a person would, on a temporary items file."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "fixture_items.jsonl"
        p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        r = subprocess.run([sys.executable, str(REPO / "code" / "generation" / "generate_benchmark.py"), "verify",
                            "--items", str(p)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        out_file = Path(tmp) / "fixture_items_verified.jsonl"
        written = [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines()] if out_file.exists() else None
        stdout = r.stdout.replace(str(out_file), "<verified file>")
    return {"returncode": r.returncode, "stdout": stdout, "written": written}


def item_as_reply(item):
    """Rebuild the reply the model sent from a saved, processed item: the schema fields only, with the model's own
    typed key put back where R replaced it."""
    reply = {k: item[k] for k in SCHEMA_FIELDS if k in item}
    if "model_canonical_answer" in item:
        reply["canonical_answer"] = item["model_canonical_answer"]
    return reply


def snapshot(items_path=None):
    rscript = gb.rscript_path()
    all_slots = gb.blueprint(9132)
    main = gb.select_slots(1000, 1)
    prompt, sha = gb.load_prompt()
    slot_by_id = {s["item_id"]: s for s in all_slots}
    req_ids = [s["item_id"] for s in main] + DEV_IDS

    def req(slot):
        r = gb.build_request(slot, prompt)
        return {"system": r["system"], "messages": r["messages"]}

    snap = {
        "prompt_version": gb.PROMPT_VERSION,
        "prompt_file": str(gb.PROMPT_FILE.relative_to(REPO)).replace("\\", "/"),
        "prompt_sha256": sha,
        "prompt_sections": {f"{k[0]} {k[1] or ''}".strip(): v for k, v in sorted(prompt.items(), key=lambda kv: (kv[0][0], kv[0][1] or ""))},
        "schema_v6": gb.schema_for("v6"),
        "item_schema": gb.ITEM_SCHEMA,
        "slots_first20": main[:20],
        "slots_hash_each": {s["item_id"]: h(s) for s in all_slots if s["item_id"] in set(req_ids)},
        "slots_hash_all_9132": h(all_slots),
        "select_slots_21_100_hash": h(gb.select_slots(100, 21)),
        "request_BM0001": req(main[0]),
        "requests_hash_each": {i: h(req(slot_by_id[i])) for i in req_ids},
        "replies": [{"case": name, "slot": slot["item_id"], **process(slot, text, stop, rscript)}
                    for name, slot, text, stop in reply_cases(main)],
        "checks": check_cases(main),
        "absent_r_solution": absent_r_solution(main, rscript),
    }
    vrows = verify_items(main)
    snap["verify_item"] = [{"item_id": r["item_id"], "result": list(gb.verify_item(dict(r), rscript))} for r in vrows]
    snap["verify_command"] = run_verify_command(vrows)
    if items_path:
        rows = [json.loads(line) for line in Path(items_path).read_text(encoding="utf-8").splitlines() if line.strip()]
        out = []
        for it in rows:
            slot = slot_by_id.get(it["item_id"]) or {k: it[k] for k in ("item_id", "category", "subtopic", "difficulty", "answer_type")}
            out.append({"item_id": it["item_id"],
                        "reprocessed": process(slot, json.dumps(item_as_reply(it)), "end_turn", rscript),
                        "check_item": gb.check_item(dict(it), it, "end_turn", r_keyed=it.get("key_source") == "r"),
                        "verify_item": list(gb.verify_item(dict(it), rscript))})
        snap["items_file"] = Path(items_path).name
        snap["items"] = out
    return snap


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="where to write the snapshot JSON")
    ap.add_argument("--items", default=None, help="optional items.jsonl to include")
    args = ap.parse_args()
    snap = snapshot(args.items)
    Path(args.out).write_text(json.dumps(snap, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}: {len(snap['replies'])} reply cases, {len(snap['requests_hash_each'])} requests"
          + (f", {len(snap['items'])} items from {snap['items_file']}" if args.items else ""))


if __name__ == "__main__":
    main()
