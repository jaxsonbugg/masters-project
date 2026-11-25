"""
key_check_schemas.py - the output formats of the five-solver key check, and the code that checks a reply against them
(plan "five-solver AI key check", 2026-11-24; docs/methodology/workflow.md Section 4, safeguard 6d).

WHAT THIS IS AND WHY. Every solver (Claude C1, C2, C3 and Codex X1, X2) and the two helper agents (known-wrong variants,
adjudicator briefs) must reply with one JSON object in a fixed format, so that code, not a person reading prose, compares
their answers with the keys. This module holds those formats (JSON schemas, passed to the model so it cannot reply in any
other shape) and a validator for each, which rejects a whole batch reply if it is not exactly right: one entry per question
id, no missing, extra or duplicate ids, allowed values only, and the fields each answer type needs. A rejected batch is run
again; nothing from it is used. It is shared by codex_batch.py (Codex runs X1 and X2) and key_check.py (Claude runs the rest),
so both families are held to the same format.

EXAMPLE. A computational reply for a number question:
  {"id": "M-01-003", "status": "computed", "r_code": "answer <- pbinom(3, 10, 0.2)", "answer_expression": "",
   "test_inputs": [], "correct_options": [], "note": "binomial CDF at 3"}
The validator accepts it. With "status": "computed" but an empty r_code it would reject the batch.
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROMPTS = REPO / "data" / "prompts"
ANALYTIC_PROMPT = PROMPTS / "key_check_analytic_v1.md"
COMPUTE_PROMPT = PROMPTS / "key_check_compute_v1.md"
AMBIGUITY_PROMPT = PROMPTS / "key_check_ambiguity_v1.md"
VARIANTS_PROMPT = PROMPTS / "key_check_variants_v1.md"
BRIEF_PROMPT = PROMPTS / "key_check_brief_v1.md"

LETTERS = ["A", "B", "C", "D"]
CONFIDENCE = ["high", "medium", "low"]
STATUSES = ["computed", "not_applicable", "unanswerable", "execution_unsupported"]
INPUT_KINDS = ["question_data", "variation", "edge"]
READINGS = ["key_likely_correct", "key_likely_wrong", "question_flawed", "check_flawed", "unclear"]
ISSUE_TYPES = ["none", "ambiguous", "missing_information", "invalid_assumption", "multiple_correct", "no_correct_option",
               "answer_format_unclear", "other"]
UNANSWERABLE = "UNANSWERABLE"
ANSWER_TYPES = ["multiple_choice", "number", "r_expression", "short_text"]


def _obj(props, top):
    """A strict JSON schema: {top: [ {props...}, ... ]}, every property required, nothing else allowed (the form both the
    Codex --output-schema and the Claude --json-schema options accept)."""
    return {"type": "object",
            "properties": {top: {"type": "array", "items": {"type": "object", "properties": props,
                                                              "required": list(props), "additionalProperties": False}}},
            "required": [top], "additionalProperties": False}


def analytic_schema():
    return _obj({"id": {"type": "string"}, "answer": {"type": "string"},
                 "correct_options": {"type": "array", "items": {"type": "string", "enum": LETTERS}},
                 "working": {"type": "string"}, "confidence": {"type": "string", "enum": CONFIDENCE}}, "answers")


def compute_schema():
    return _obj({"id": {"type": "string"}, "status": {"type": "string", "enum": STATUSES},
                 "r_code": {"type": "string"}, "answer_expression": {"type": "string"},
                 "test_inputs": {"type": "array", "items": {
                     "type": "object", "properties": {"kind": {"type": "string", "enum": INPUT_KINDS},
                                                      "code": {"type": "string"}},
                     "required": ["kind", "code"], "additionalProperties": False}},
                 "correct_options": {"type": "array", "items": {"type": "string", "enum": LETTERS}},
                 "note": {"type": "string"}}, "answers")


def ambiguity_schema():
    """The same format as the Codex screen (codex_batch.screen_schema), so C3 and the screen compare directly."""
    return _obj({"id": {"type": "string"}, "verdict": {"type": "string", "enum": ["pass", "flag"]},
                 "issue_type": {"type": "string", "enum": ISSUE_TYPES}, "reason": {"type": "string"}}, "verdicts")


def variants_schema():
    return _obj({"id": {"type": "string"}, "key_concern": {"type": "string"},
                 "variants": {"type": "array", "items": {
                     "type": "object", "properties": {"expression": {"type": "string"},
                                                      "what_is_wrong": {"type": "string"},
                                                      "counterexample": {"type": "string"}},
                     "required": ["expression", "what_is_wrong", "counterexample"], "additionalProperties": False}}},
                "variants")


def brief_schema():
    return _obj({"id": {"type": "string"}, "brief": {"type": "string"},
                 "reading": {"type": "string", "enum": READINGS},
                 "confidence": {"type": "string", "enum": CONFIDENCE}}, "briefs")


# kind: (instruction file, schema function, top-level key, letter for anonymous ids)
KINDS = {
    "solve-analytic": (ANALYTIC_PROMPT, analytic_schema, "answers", "K"),
    "solve-compute": (COMPUTE_PROMPT, compute_schema, "answers", "M"),
    "ambiguity": (AMBIGUITY_PROMPT, ambiguity_schema, "verdicts", "G"),
    "variants": (VARIANTS_PROMPT, variants_schema, "variants", "V"),
    "brief": (BRIEF_PROMPT, brief_schema, "briefs", "B"),
}
RESULTS_FILE = {"solve-analytic": "solve_results.jsonl", "solve-compute": "solve_results.jsonl",
                "ambiguity": "ambiguity_results.jsonl", "variants": "variants_results.jsonl", "brief": "brief_results.jsonl"}


def _entry_problems(kind, e, row):
    """Problems with one entry `e` for the batch row `row` (the question as shown to the solver)."""
    p = []
    at = (row or {}).get("answer_type")
    if kind == "solve-analytic":
        if not e["answer"].strip():
            p.append("empty answer")
        if len(set(e["correct_options"])) != len(e["correct_options"]):
            p.append("a letter is listed twice in correct_options")
        if at and at != "multiple_choice" and e["correct_options"]:
            p.append("correct_options given for a question that is not multiple choice")
        if at == "multiple_choice" and e["answer"].strip() not in LETTERS + [UNANSWERABLE]:
            p.append(f"multiple-choice answer {e['answer']!r} is not A, B, C, D or {UNANSWERABLE}")
        if not e["working"].strip():
            p.append("empty working")
    elif kind == "solve-compute":
        computed = e["status"] == "computed"
        if not computed:
            if e["r_code"].strip() or e["answer_expression"].strip() or e["test_inputs"]:
                p.append(f"status {e['status']} but code or test inputs given (they must be empty)")
            if not e["note"].strip():
                p.append(f"status {e['status']} needs a reason in note")
        elif at == "r_expression":
            if not e["answer_expression"].strip():
                p.append("r_expression question computed without an answer_expression")
            if e["r_code"].strip():
                p.append("r_expression question: r_code must be empty (the expression and the test inputs are used)")
            if not e["test_inputs"]:
                p.append("r_expression question computed without test inputs")
            elif len(e["test_inputs"]) < 4 and not e["note"].strip():
                p.append("fewer than four test inputs without a reason in note")
            if any(not t["code"].strip() for t in e["test_inputs"]):
                p.append("a test input has empty code")
        else:
            if not e["r_code"].strip():
                p.append("computed without r_code")
            if e["answer_expression"].strip() or e["test_inputs"]:
                p.append("answer_expression and test_inputs are only for r_expression questions")
        if len(set(e["correct_options"])) != len(e["correct_options"]):
            p.append("a letter is listed twice in correct_options")
        if at and at != "multiple_choice" and e["correct_options"]:
            p.append("correct_options given for a question that is not multiple choice")
    elif kind == "ambiguity":
        if e["verdict"] == "pass" and e["issue_type"] != "none":
            p.append("a pass must have issue_type none")
        if e["verdict"] == "flag" and e["issue_type"] == "none":
            p.append("a flag needs an issue_type")
        if not e["reason"].strip():
            p.append("empty reason")
    elif kind == "variants":
        if not 3 <= len(e["variants"]) <= 6:
            p.append(f"{len(e['variants'])} variants (3 to 6 are asked for)")
        for k, v in enumerate(e["variants"]):
            if not v["expression"].strip() or not v["counterexample"].strip():
                p.append(f"variant {k + 1}: empty expression or counterexample")
    elif kind == "brief":
        if not e["brief"].strip():
            p.append("empty brief")
    return p


def _type_ok(schema, v):
    """A small structural check of value `v` against a schema built by _obj (types, enums, required, no extra keys)."""
    t = schema.get("type")
    if t == "object":
        if not isinstance(v, dict) or set(v) != set(schema["required"]):
            return False
        return all(_type_ok(schema["properties"][k], v[k]) for k in v)
    if t == "array":
        return isinstance(v, list) and all(_type_ok(schema["items"], x) for x in v)
    if t == "string":
        return isinstance(v, str) and ("enum" not in schema or v in schema["enum"])
    return False


def validate(kind, text, ids, rows=None):
    """(entries by id, problems) for a batch reply. `rows` maps id -> the batch row (to know each answer type).
    Any problem rejects the whole batch."""
    _, schema_fn, top, _ = KINDS[kind]
    schema = schema_fn()
    item_schema = schema["properties"][top]["items"]
    try:
        obj = json.loads(text)
    except ValueError as e:
        return {}, [f"reply is not valid JSON ({e})"]
    if not isinstance(obj, dict) or set(obj) != {top} or not isinstance(obj[top], list):
        return {}, [f"reply must be an object with exactly one key, {top!r}, holding a list"]
    got, problems = {}, []
    for k, e in enumerate(obj[top]):
        if not _type_ok(item_schema, e):
            problems.append(f"entry {k}: does not match the format (fields {sorted(item_schema['required'])}, allowed values)")
            continue
        if e["id"] in got:
            problems.append(f"{e['id']}: more than one entry")
        problems += [f"{e['id']}: {x}" for x in _entry_problems(kind, e, (rows or {}).get(e["id"]))]
        got[e["id"]] = e
    missing = [i for i in ids if i not in got]
    extra = [i for i in got if i not in set(ids)]
    if missing:
        problems.append(f"missing entries for {missing}")
    if extra:
        problems.append(f"entries for ids not in the batch: {extra}")
    return got, problems
