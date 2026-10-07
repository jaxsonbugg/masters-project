"""
generate_benchmark.py - ask Claude (via the API) to write the benchmark questions.

WHAT THIS IS
The project's benchmark is a fixed set of about 1,000 statistics/R questions with known answers,
used as the "final exam" for the small Pythia models. We have Claude Sonnet 5.5 write the questions.
This script does that in two ways that share ONE code path for building each request:

  trial   - writes a small number of questions (default 20) with ordinary API calls, one at a time,
            so you see results immediately. It has a hard dollar cap and stops itself before it can
            exceed it. Use this to test the prompt and measure real cost.
  submit  - sends the same requests to the Message Batches API (half price, results within hours).
            Use this for the full 1,000. Then run `fetch` to download the results.

Because both use build_request(), a prompt that works in the trial works unchanged in the big run.

HOW A QUESTION GETS MADE (plain steps)
1. blueprint(n): a fixed, repeatable list of n "slots". Each slot says which category, subtopic,
   difficulty and answer type one question must have (for example: "numerical / z-score probability /
   intro / number"). The list is built so that any 20 slots in a row already have the target mix, and
   1,000 slots are just 50 copies of that pattern with different subtopics. No randomness is left to
   chance: running it again gives the same slots.
2. build_request(): fills the prompt in data/prompts/benchmark_generation_v1.md with one slot's details
   and attaches a JSON "output schema" so Claude must answer with a clean, machine-readable object.
3. The request is sent. Claude may "think" first (adaptive thinking); those hidden thinking tokens are
   billed as output tokens, which is the expensive kind.
4. The reply is parsed and checked (valid JSON, right fields, short answer, not cut off), and the real
   token counts the API reports are turned into dollars.

WHY THE COST CAP WORKS
Each call has max_tokens (here 5000), the most output it can ever produce. So the most any single call
can cost is known in advance: (input tokens x input price + 5000 x output price). The script adds that
worst case up BEFORE starting and refuses to run if it could exceed your cap; and while running, it
stops if (money spent so far + worst case of the next call) would pass the cap.

This script never prints or stores your API key. It reads ANTHROPIC_API_KEY from the environment.

EXAMPLES (run with the project's virtual environment Python)
  python generate_benchmark.py plan --n 20
  python generate_benchmark.py check --items <path to items.jsonl>          (free automatic checks)
  python generate_benchmark.py trial --n 20 --cap-usd 3.00 --dry-run     (no API call, no cost)
  python generate_benchmark.py trial --n 20 --cap-usd 3.00               (real calls)
  python generate_benchmark.py submit --n 1000 --cap-usd 30              (later: Batch API)
  python generate_benchmark.py fetch --manifest <path to batch_manifest.json>
"""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

try:
    sys.stdout.reconfigure(encoding="utf-8")  # so quotes and symbols print on Windows
except Exception:
    pass

# ---------------------------------------------------------------------------------------------
# Settings that define "the teacher run". Every one of these is written into the run log.
# ---------------------------------------------------------------------------------------------
MODEL = "claude-sonnet-5-5"          # exact API model id (a pinned snapshot)
EFFORT = "medium"                    # how hard the model thinks: low < medium < high < xhigh < max
MAX_TOKENS = 5000                    # output ceiling per call, INCLUDING thinking tokens
PRICE_IN_PER_MTOK = 2.00             # standard price, USD per million input tokens (Sonnet 5.5)
PRICE_OUT_PER_MTOK = 10.00           # standard price, USD per million output tokens
BATCH_FACTOR = 0.5                   # the Batch API charges half
TYPICAL_IN, TYPICAL_OUT = 1200, 1500 # rough guess of tokens per question, only for the "expected" line
PROMPT_VERSION = "v1"

REPO = Path(__file__).resolve().parents[2]
PROMPT_FILE = REPO / "data" / "prompts" / "benchmark_generation_v1.md"

# ---------------------------------------------------------------------------------------------
# The blueprint: which kinds of questions, in which proportions.
# This mix is a PROPOSAL (README Section 10 lists it as an open decision to confirm with Dr. Lee).
# The pattern below has 20 slots; 1,000 questions = this pattern 50 times.
# Each tuple is (category, difficulty). Counts: numerical 6, conceptual 4, r_generation 4,
# r_interpretation 3, output_interpretation 3; intro 8, intermediate 7, graduate 5 (40/35/25 %).
# ---------------------------------------------------------------------------------------------
PATTERN = [
    ("numerical", "intro"), ("conceptual", "intro"), ("r_generation", "intro"), ("output_interpretation", "intro"),
    ("numerical", "intermediate"), ("conceptual", "intermediate"), ("r_interpretation", "intro"), ("numerical", "graduate"),
    ("r_generation", "intermediate"), ("output_interpretation", "intermediate"), ("conceptual", "graduate"), ("numerical", "intro"),
    ("r_interpretation", "intermediate"), ("r_generation", "intro"), ("numerical", "intermediate"), ("conceptual", "intermediate"),
    ("output_interpretation", "graduate"), ("r_generation", "graduate"), ("r_interpretation", "intro"), ("numerical", "graduate"),
]

# Default answer type for each category. r_interpretation alternates between a number and short text.
ANSWER_TYPE = {
    "numerical": "number", "conceptual": "multiple_choice", "r_generation": "r_expression",
    "output_interpretation": "multiple_choice",
}

SUBTOPICS = {
    "numerical": [
        "mean and standard deviation of a small data set", "median and quartiles", "probability of independent events",
        "conditional probability and Bayes' rule", "binomial probability", "normal probability from a z-score",
        "standard error of the sample mean", "confidence interval for a mean from summary numbers",
        "one-sample t statistic", "two-sample difference-in-means test statistic", "chi-square statistic from a table",
        "correlation coefficient from summary values", "regression slope from summary statistics",
        "expected value and variance of a discrete variable", "Poisson probability", "sample size for a margin of error",
        "z-test for a proportion", "combinations and permutations",
    ],
    "conceptual": [
        "meaning of a p-value", "Type I and Type II errors", "interpreting a confidence interval",
        "assumptions of linear regression", "the central limit theorem", "correlation versus causation",
        "bias and variance of an estimator", "sampling methods and sampling bias", "independent versus mutually exclusive events",
        "effect of outliers on the mean and median", "choosing between a t-test and a z-test", "multiple comparisons",
        "statistical power", "the likelihood function", "overfitting", "interpreting R-squared",
        "paired versus independent samples", "the bootstrap",
    ],
    "r_generation": [
        "summary statistic of a vector", "creating and subsetting a vector", "adding a column to a data frame",
        "filtering rows of a data frame", "sorting data", "sapply over columns", "random draws with set.seed",
        "fitting a linear model and extracting a coefficient", "running a t-test and extracting the p-value",
        "counting with table", "writing a small function", "recoding with ifelse", "seq and rep", "cumulative sums",
        "matrix operations",
    ],
    "r_interpretation": [
        "vector arithmetic and recycling", "indexing with positive and negative indices", "NA handling in mean and sum",
        "factor levels and as.numeric", "result of an apply-family call", "result of seq and rep",
        "paste and substr", "logical operators on vectors", "data frame subsetting result", "sorting with order",
        "integer division and modulo", "cumsum and diff", "fix a misspelled function name", "fix an off-by-one error",
        "fix a wrong argument such as na.rm",
    ],
    "output_interpretation": [
        "meaning of a regression coefficient in a coefficient table", "R-squared and residual standard error",
        "conclusion from t-test output", "p-value in an ANOVA table", "chi-square test output",
        "confidence interval in test output", "accuracy or sensitivity from a confusion matrix", "a correlation matrix",
        "logistic regression coefficient as an odds ratio", "paired t-test output", "summary() of a numeric vector",
    ],
}

# The strict JSON shape every question must come back in (the "output schema").
ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "answer_type": {"type": "string", "enum": ["number", "multiple_choice", "r_expression", "short_text"]},
        "choices": {"type": "array", "items": {"type": "string"}},
        "canonical_answer": {"type": "string"},
        "answer_tolerance": {"type": "number"},
        "r_check": {"type": "string"},
        "explanation": {"type": "string"},
        "difficulty": {"type": "string", "enum": ["intro", "intermediate", "graduate"]},
        "category": {"type": "string", "enum": ["numerical", "conceptual", "r_generation", "r_interpretation", "output_interpretation"]},
        "subtopic": {"type": "string"},
    },
    "required": ["question", "answer_type", "choices", "canonical_answer", "answer_tolerance", "r_check",
                 "explanation", "difficulty", "category", "subtopic"],
    "additionalProperties": False,
}


def utc_now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------------------------
# Prompt file handling
# ---------------------------------------------------------------------------------------------
def load_prompt():
    """Read the prompt file into named sections and return them with the file's SHA-256 hash."""
    raw = PROMPT_FILE.read_bytes()
    text = raw.decode("utf-8")
    sections, key, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^<<<([A-Z]+)(?: ([a-z_]+))?>>>\s*$", line)
        if m:
            if key is not None:
                sections[key] = "\n".join(buf).strip()
            key = (m.group(1), m.group(2))
            buf = []
        elif key is not None:
            buf.append(line)
    return sections, hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------------------------
def blueprint(n):
    """Return n slots. Deterministic: the same n always gives the same slots."""
    # A fixed shuffle of each category's subtopic list (seeded, so repeatable) to cycle through.
    import random
    shuffled = {}
    for cat, lst in SUBTOPICS.items():
        r = random.Random(f"benchmark-v1-{cat}")
        copy = list(lst)
        r.shuffle(copy)
        shuffled[cat] = copy
    counters = {c: 0 for c in SUBTOPICS}
    mc_count = 0
    slots = []
    for i in range(n):
        cat, diff = PATTERN[i % len(PATTERN)]
        k = counters[cat]
        counters[cat] += 1
        sub = shuffled[cat][k % len(shuffled[cat])]
        if cat == "r_interpretation":
            # "fix ..." and text-producing subtopics have a short text answer; the rest print a number.
            atype = "short_text" if (sub.startswith("fix") or sub.startswith("paste") or sub.startswith("factor")) else "number"
        else:
            atype = ANSWER_TYPE[cat]
        letter = ""
        if atype == "multiple_choice":
            letter = "ABCD"[mc_count % 4]  # rotate the correct letter so answers are balanced
            mc_count += 1
        slots.append({"item_id": f"BM{i + 1:04d}", "category": cat, "subtopic": sub, "difficulty": diff,
                      "answer_type": atype, "preferred_letter": letter})
    return slots


# ---------------------------------------------------------------------------------------------
# The single place where a request is built (used by trial AND batch)
# ---------------------------------------------------------------------------------------------
def build_request(slot, prompt):
    user = prompt[("USER", None)].format(
        item_id=slot["item_id"], category=slot["category"], category_text=prompt[("CAT", slot["category"])],
        subtopic=slot["subtopic"], difficulty=slot["difficulty"], difficulty_text=prompt[("DIFF", slot["difficulty"])],
        answer_type=slot["answer_type"],
        answer_type_text=prompt[("TYPE", slot["answer_type"])].format(preferred_letter=slot["preferred_letter"] or "any letter"),
    )
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": prompt[("SYSTEM", None)],
        "messages": [{"role": "user", "content": user}],
        # Structured output (a JSON schema) plus the effort level. Thinking is left at its default
        # (adaptive: the model decides how much to think). Temperature cannot be set on this model.
        "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": ITEM_SCHEMA}},
    }


def est_input_tokens(params):
    """Deliberately generous upper estimate: one token per 3 characters."""
    chars = len(params["system"]) + sum(len(m["content"]) for m in params["messages"]) + len(json.dumps(ITEM_SCHEMA))
    return math.ceil(chars / 3.0)


def cost_usd(in_tok, out_tok, batch=False):
    c = (in_tok * PRICE_IN_PER_MTOK + out_tok * PRICE_OUT_PER_MTOK) / 1_000_000
    return c * BATCH_FACTOR if batch else c


def worst_case(params, batch=False):
    return cost_usd(est_input_tokens(params), MAX_TOKENS, batch)


# ---------------------------------------------------------------------------------------------
# Checking a returned item
# ---------------------------------------------------------------------------------------------
def check_item(item, slot, stop_reason):
    """Return a list of problems (empty list = the item looks fine)."""
    problems = []
    if stop_reason == "max_tokens":
        problems.append("cut off at max_tokens")
    for k in ITEM_SCHEMA["required"]:
        if k not in item:
            problems.append(f"missing field {k}")
    if problems:
        return problems
    for k in ("category", "subtopic", "difficulty", "answer_type"):
        if item[k] != slot[k]:
            problems.append(f"{k} differs from the slot ({item[k]!r} vs {slot[k]!r})")
    if not item["question"].strip():
        problems.append("empty question")
    if not item["canonical_answer"].strip():
        problems.append("empty canonical_answer")
    if len(item["canonical_answer"]) > 100:
        problems.append("canonical_answer longer than about 20 tokens")
    if item["answer_type"] == "multiple_choice":
        if len(item["choices"]) != 4:
            problems.append("multiple choice without exactly 4 choices")
        if item["canonical_answer"].strip() not in list("ABCD"):
            problems.append("multiple choice answer is not a letter A-D")
    elif item["choices"]:
        problems.append("choices given for a non-multiple-choice item")
    if item["answer_type"] == "number":
        try:
            float(item["canonical_answer"].replace(",", ""))
        except ValueError:
            problems.append("number answer is not a plain number")
    if item["answer_type"] == "r_expression" and not item["r_check"].strip():
        problems.append("r_expression item without an r_check")
    # An R check must actually test the student's answer, which is stored in the variable `candidate`.
    # (Found in the first trial: one check re-tested the answer key itself and would pass for any answer.)
    if item["r_check"].strip() and "candidate" not in item["r_check"]:
        problems.append("r_check never uses the variable candidate, so it would pass for any answer")
    # Cheap consistency test for number answers: the key should equal the last number in the model's own
    # worked explanation. (Found in the first trial: two keys contradicted their own working.)
    if item["answer_type"] == "number":
        try:
            key = float(item["canonical_answer"].replace(",", ""))
            nums = re.findall(r"-?\d+(?:\.\d+)?", item["explanation"].replace(",", ""))
            if nums:
                last = float(nums[-1])
                tol = max(float(item["answer_tolerance"]), 0.0011 * max(1.0, abs(last)))
                if abs(last - key) > tol:
                    problems.append(f"key {key:g} differs from the last number in the explanation ({last:g})")
        except ValueError:
            pass
    return problems


def first_text(message):
    for b in message.content:
        if b.type == "text":
            return b.text
    return ""


# ---------------------------------------------------------------------------------------------
# Output folders (dated, never overwritten - README Section 12)
# ---------------------------------------------------------------------------------------------
def new_output_dir(kind):
    paths = yaml.safe_load((REPO / "configs" / "paths.yaml").read_text())
    root = Path(paths["teacher_outputs"])
    date = utc_now().strftime("%Y-%m-%d")
    nn = 1
    while True:
        d = root / f"{date}_sonnet-5-5_benchmark-{kind}{nn:02d}"
        if not d.exists():
            d.mkdir(parents=True)
            return d
        nn += 1


def run_meta(kind, n, cap, sha):
    return {
        "run_kind": kind, "started_utc": utc_now().isoformat(timespec="seconds"), "items_requested": n,
        "model_id": MODEL, "effort": EFFORT, "thinking_mode": "adaptive (API default; cannot be disabled on this model)",
        "sampling": "API defaults (temperature/top_p cannot be set on this model)", "max_tokens": MAX_TOKENS,
        "prompt_file": str(PROMPT_FILE.relative_to(REPO)), "prompt_version": PROMPT_VERSION, "prompt_sha256": sha,
        "prices_usd_per_mtok": {"input": PRICE_IN_PER_MTOK, "output": PRICE_OUT_PER_MTOK, "batch_factor": BATCH_FACTOR},
        "cap_usd": cap,
    }


# ---------------------------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------------------------
def cmd_plan(args):
    slots = blueprint(args.n)
    print(f"{'id':<8}{'category':<23}{'difficulty':<14}{'answer type':<17}subtopic")
    for s in slots:
        print(f"{s['item_id']:<8}{s['category']:<23}{s['difficulty']:<14}{s['answer_type']:<17}{s['subtopic']}")
    from collections import Counter
    print("\ncategories:", dict(Counter(s["category"] for s in slots)))
    print("difficulty:", dict(Counter(s["difficulty"] for s in slots)))
    print("answer types:", dict(Counter(s["answer_type"] for s in slots)))


def preflight(slots, prompt, cap, batch):
    """Print the money picture and return (ok, worst_total). Nothing is sent."""
    reqs = [build_request(s, prompt) for s in slots]
    w_each = max(worst_case(r, batch) for r in reqs)
    w_total = sum(worst_case(r, batch) for r in reqs)
    typical = len(slots) * cost_usd(TYPICAL_IN, TYPICAL_OUT, batch)
    print(f"Model {MODEL}, effort {EFFORT}, max_tokens {MAX_TOKENS}, {'BATCH' if batch else 'standard'} pricing")
    print(f"Estimated input tokens per call (generous): about {est_input_tokens(reqs[0])}")
    print(f"Worst case for ONE call (all {MAX_TOKENS} output tokens used): ${w_each:.4f}")
    print(f"Worst case for all {len(slots)} calls: ${w_total:.2f}")
    print(f"Typical expectation (about {TYPICAL_IN} in / {TYPICAL_OUT} out per question): ${typical:.2f}")
    print(f"Your cap: ${cap:.2f}")
    ok = w_total <= cap
    print("Cap check:", "OK, even the worst case fits under the cap" if ok else
          "FAILED, the worst case could exceed the cap; lower --n or max_tokens, or raise --cap-usd")
    return ok, w_total, reqs


def cmd_trial(args):
    import anthropic

    prompt, sha = load_prompt()
    slots = blueprint(args.n)
    ok, w_total, reqs = preflight(slots, prompt, args.cap_usd, batch=False)
    if args.dry_run:
        print("\n--- First request exactly as it would be sent (dry run: nothing was sent) ---")
        print("SYSTEM:\n" + reqs[0]["system"])
        print("\nUSER:\n" + reqs[0]["messages"][0]["content"])
        print("\noutput_config:", json.dumps({"effort": EFFORT, "format": "json_schema (ITEM_SCHEMA)"}))
        return
    if not ok:
        sys.exit(2)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set in this environment. Nothing was sent.")

    out = new_output_dir("trial")
    meta = run_meta("trial", args.n, args.cap_usd, sha)
    print(f"\nOutput folder: {out}\n")
    client = anthropic.Anthropic(max_retries=2)
    spent, calls, items, workspace_ids = 0.0, [], [], set()
    stopped = None
    with open(out / "responses.jsonl", "w", encoding="utf-8") as resp_f:
        for slot, req in zip(slots, reqs):
            if spent + worst_case(req) > args.cap_usd:
                stopped = f"stopped before {slot['item_id']}: spent ${spent:.4f} + worst case would exceed the cap"
                print(stopped)
                break
            t0 = time.time()
            try:
                raw = client.messages.with_raw_response.create(**req)
                msg = raw.parse()
            except (anthropic.BadRequestError, anthropic.AuthenticationError,
                    anthropic.PermissionDeniedError, anthropic.NotFoundError) as e:
                stopped = f"stopped at {slot['item_id']}: {type(e).__name__}: {e}"
                print(stopped)
                break
            except anthropic.APIError as e:
                calls.append({"item_id": slot["item_id"], "error": f"{type(e).__name__}: {e}"})
                print(f"{slot['item_id']}: error {type(e).__name__}, continuing")
                continue
            ws = raw.headers.get("anthropic-workspace-id")
            if ws:
                workspace_ids.add(ws)
            u = msg.usage
            c = cost_usd(u.input_tokens, u.output_tokens)
            spent += c
            text = first_text(msg)
            try:
                item = json.loads(text)
                problems = check_item(item, slot, msg.stop_reason)
            except json.JSONDecodeError as e:
                item, problems = None, [f"reply is not valid JSON ({e})"]
            call = {"item_id": slot["item_id"], "request_id": msg._request_id, "stop_reason": msg.stop_reason,
                    "input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "cost_usd": round(c, 6),
                    "seconds": round(time.time() - t0, 1), "problems": problems}
            calls.append(call)
            resp_f.write(json.dumps({"item_id": slot["item_id"], "response": msg.model_dump(mode="json")},
                                    ensure_ascii=False) + "\n")
            resp_f.flush()
            if item is not None:
                items.append({**slot, **item, "problems": problems})
            print(f"{slot['item_id']}: in {u.input_tokens} out {u.output_tokens} ${c:.4f} "
                  f"({call['seconds']}s) {'OK' if not problems else 'PROBLEMS: ' + '; '.join(problems)}  [total ${spent:.4f}]")

    meta.update({"finished_utc": utc_now().isoformat(timespec="seconds"), "calls": calls,
                 "workspace_ids_seen": sorted(workspace_ids), "stopped_early_reason": stopped,
                 "total_input_tokens": sum(c.get("input_tokens", 0) for c in calls),
                 "total_output_tokens": sum(c.get("output_tokens", 0) for c in calls),
                 "total_cost_usd": round(spent, 6), "items_parsed": len(items),
                 "items_with_problems": sum(1 for i in items if i["problems"])})
    (out / "batch_log.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    with open(out / "items.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    # A small review copy inside the repository (backed up by Git).
    review = REPO / "results" / "benchmark_trial"
    review.mkdir(parents=True, exist_ok=True)
    shutil.copy(out / "items.jsonl", review / f"{out.name}_items.jsonl")
    shutil.copy(out / "batch_log.json", review / f"{out.name}_log.json")
    n_ok = sum(1 for i in items if not i["problems"])
    print(f"\nDone. {len(items)} items parsed, {n_ok} without problems. Total cost ${spent:.4f} of cap ${args.cap_usd:.2f}.")
    print(f"Tokens: {meta['total_input_tokens']} in, {meta['total_output_tokens']} out. Workspace id(s): {meta['workspace_ids_seen']}")
    print(f"Saved in {out} and a review copy in {review}")


def cmd_submit(args):
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    prompt, sha = load_prompt()
    slots = blueprint(args.n)
    if args.first:
        slots = slots[: args.first]
    ok, w_total, reqs = preflight(slots, prompt, args.cap_usd, batch=True)
    if args.dry_run or not ok:
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set in this environment. Nothing was sent.")
    out = new_output_dir("batch")
    client = anthropic.Anthropic(max_retries=2)
    batch = client.messages.batches.create(requests=[
        Request(custom_id=s["item_id"], params=MessageCreateParamsNonStreaming(**r)) for s, r in zip(slots, reqs)])
    manifest = run_meta("batch", len(slots), args.cap_usd, sha)
    manifest.update({"batch_id": batch.id, "slots": slots, "output_dir": str(out)})
    (out / "batch_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Submitted batch {batch.id} with {len(slots)} requests. Status: {batch.processing_status}")
    print(f"Manifest: {out / 'batch_manifest.json'}")
    print("Watch it in the Console: Settings > Workspaces > (your workspace) > Batches. Then run:")
    print(f"  python generate_benchmark.py fetch --manifest \"{out / 'batch_manifest.json'}\"")


def cmd_fetch(args):
    import anthropic

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    slots = {s["item_id"]: s for s in manifest["slots"]}
    client = anthropic.Anthropic(max_retries=2)
    batch = client.messages.batches.retrieve(manifest["batch_id"])
    rc = batch.request_counts
    print(f"Batch {batch.id}: {batch.processing_status} (processing {rc.processing}, succeeded {rc.succeeded}, "
          f"errored {rc.errored}, expired {rc.expired}, canceled {rc.canceled})")
    if batch.processing_status != "ended":
        print("Not finished yet. Run fetch again later (batches finish within 24 hours, usually much sooner).")
        return
    out = Path(manifest["output_dir"])
    items, calls, spent = [], [], 0.0
    with open(out / "responses.jsonl", "w", encoding="utf-8") as resp_f:
        for r in client.messages.batches.results(batch.id):
            iid = r.custom_id
            if r.result.type != "succeeded":
                calls.append({"item_id": iid, "result": r.result.type})
                continue
            msg = r.result.message
            u = msg.usage
            c = cost_usd(u.input_tokens, u.output_tokens, batch=True)
            spent += c
            try:
                item = json.loads(first_text(msg))
                problems = check_item(item, slots[iid], msg.stop_reason)
            except json.JSONDecodeError as e:
                item, problems = None, [f"reply is not valid JSON ({e})"]
            calls.append({"item_id": iid, "stop_reason": msg.stop_reason, "input_tokens": u.input_tokens,
                          "output_tokens": u.output_tokens, "cost_usd": round(c, 6), "problems": problems})
            resp_f.write(json.dumps({"item_id": iid, "response": msg.model_dump(mode="json")}, ensure_ascii=False) + "\n")
            if item is not None:
                items.append({**slots[iid], **item, "problems": problems})
    items.sort(key=lambda i: i["item_id"])
    manifest.update({"fetched_utc": utc_now().isoformat(timespec="seconds"), "calls": calls,
                     "total_input_tokens": sum(c.get("input_tokens", 0) for c in calls),
                     "total_output_tokens": sum(c.get("output_tokens", 0) for c in calls),
                     "total_cost_usd_batch": round(spent, 6), "items_parsed": len(items),
                     "items_with_problems": sum(1 for i in items if i["problems"])})
    (out / "batch_log.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with open(out / "items.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"Fetched {len(items)} items; batch cost ${spent:.4f}. Saved in {out}")


def cmd_check(args):
    """Re-run the automatic checks on an existing items.jsonl file. Free: no API call."""
    n_bad = 0
    for line in open(args.items, encoding="utf-8"):
        item = json.loads(line)
        problems = check_item(item, item, "end_turn")
        if problems:
            n_bad += 1
            print(f"{item['item_id']}: " + "; ".join(problems))
    print(f"\n{n_bad} item(s) flagged by the automatic checks. These checks catch only some errors; "
          "the answer keys still need to be verified by running R or recomputing (see README Phase 3).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="re-run the automatic checks on an items.jsonl file (free)")
    p.add_argument("--items", required=True)
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("plan", help="print the blueprint (no API call)")
    p.add_argument("--n", type=int, default=20)
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("trial", help="write n questions with ordinary calls and a hard dollar cap")
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--cap-usd", type=float, default=3.00)
    p.add_argument("--dry-run", action="store_true", help="show the cost picture and one request; send nothing")
    p.set_defaults(fn=cmd_trial)
    p = sub.add_parser("submit", help="send the requests to the Batch API (half price)")
    p.add_argument("--n", type=int, default=1000)
    p.add_argument("--first", type=int, default=None, help="only submit the first N slots (for a tiny test batch)")
    p.add_argument("--cap-usd", type=float, default=30.0)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_submit)
    p = sub.add_parser("fetch", help="download the results of a submitted batch")
    p.add_argument("--manifest", required=True)
    p.set_defaults(fn=cmd_fetch)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
