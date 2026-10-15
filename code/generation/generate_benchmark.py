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
2. build_request(): fills the prompt file (data/prompts/benchmark_generation_v6.md by default; choose
   another with --prompt) with one slot's details and attaches a JSON "output schema" so Claude must
   answer with a clean, machine-readable object.
3. The request is sent. Claude may "think" first (adaptive thinking); those hidden thinking tokens are
   billed as output tokens, which is the expensive kind.
4. process_reply(): the reply is parsed and checked (valid JSON, right fields, short answer, not cut off,
   question text finished). The checks sort problems into two kinds:
     HARD problem = the question is unusable, so it is regenerated (see step 6).
     SOFT flag    = the question is kept but a person should look at it (see step 5).
5. For a NUMBER question the key is taken from R, not from the model: apply_r_key() runs the model's
   r_solution code, rounds R's number the way the question says (halves up), and writes that as the key.
   The model's own typed key is kept as model_canonical_answer; if the two disagree the item gets a soft
   flag. Example (trial 7, BM0013): the model typed 4.867, its code prints 4.25, so the key becomes 4.250.
   R fixes slips of arithmetic or typing. It cannot notice code that answers a different question than the
   one written, which is why the soft flag and, later, a blind re-solve exist.
6. run_attempts(): a question with a hard problem is asked for again with the same prompt, up to
   MAX_ATTEMPTS (3) attempts in all. Every attempt is saved; failed ones go to rejected_attempts.jsonl.
   A key disagreement is deliberately NOT a reason to regenerate: that would quietly remove questions whose
   arithmetic is hard to do in one's head and make the benchmark easier than intended. A refusal by the API
   is not retried: the run stops after saving that call's log, because refusals repeat.
7. The real token counts the API reports are turned into dollars.

WHY THE COST CAP WORKS
Each call has max_tokens (here 5000), the most output it can ever produce. So the most any single call
can cost is known in advance: (input tokens x input price + 5000 x output price). The script adds that
worst case up BEFORE starting and refuses to run if it could exceed your cap; and while running, it
stops if (money spent so far + worst case of the next call) would pass the cap.

This script never prints or stores your API key. It reads ANTHROPIC_API_KEY from the environment.

EXAMPLES (run with the project's virtual environment Python)
  python generate_benchmark.py plan --n 20
  python generate_benchmark.py check --items <path to items.jsonl>          (free automatic checks)
  python generate_benchmark.py verify --items <path to items.jsonl>         (free: runs R to test the keys)
  python generate_benchmark.py trial --n 20 --cap-usd 3.00 --dry-run     (no API call, no cost)
  python generate_benchmark.py trial --n 20 --cap-usd 3.00               (real calls)
  python generate_benchmark.py --effort high trial --n 20 --cap-usd 3.00 (same, thinking harder)
  python generate_benchmark.py replay --responses <path to responses.jsonl> --n 20   (free: re-check saved replies)
  python generate_benchmark.py submit --n 1000 --cap-usd 30              (later: Batch API)
  python generate_benchmark.py fetch --manifest <path to batch_manifest.json> [--retry-failed --cap-usd 5]
(--prompt and --effort go BEFORE the command name.)
"""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
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
PROMPT_VERSION = "v6"                # which prompt file is used; change with --prompt (see set_prompt)
MAX_ATTEMPTS = 3                     # tries per question: one first attempt plus up to two regenerations

REPO = Path(__file__).resolve().parents[2]
PROMPT_FILE = REPO / "data" / "prompts" / f"benchmark_generation_{PROMPT_VERSION}.md"


def set_prompt(version):
    """Choose the prompt file (v1 to v6). Trial, submit and fetch all read the same global, so they cannot drift."""
    global PROMPT_VERSION, PROMPT_FILE
    PROMPT_VERSION = version
    PROMPT_FILE = REPO / "data" / "prompts" / f"benchmark_generation_{version}.md"


def set_effort(level):
    """Choose how hard the model thinks (low < medium < high < xhigh < max) without editing the code."""
    global EFFORT
    EFFORT = level

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
# The ORDER of the fields matters: the model writes them top to bottom, so `working` (the calculation)
# and `r_solution` (R code that recomputes it) come BEFORE `canonical_answer`. The key is therefore
# written after the work, not before it. (Prompt v1 had no `working` or `r_solution`.)
ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "answer_type": {"type": "string", "enum": ["number", "multiple_choice", "r_expression", "short_text"]},
        "choices": {"type": "array", "items": {"type": "string"}},
        "working": {"type": "string"},
        "r_solution": {"type": "string"},
        "canonical_answer": {"type": "string"},
        "answer_tolerance": {"type": "number"},
        "r_check": {"type": "string"},
        "explanation": {"type": "string"},
        "difficulty": {"type": "string", "enum": ["intro", "intermediate", "graduate"]},
        "category": {"type": "string", "enum": ["numerical", "conceptual", "r_generation", "r_interpretation", "output_interpretation"]},
        "subtopic": {"type": "string"},
    },
    "required": ["question", "answer_type", "choices", "working", "r_solution", "canonical_answer",
                 "answer_tolerance", "r_check", "explanation", "difficulty", "category", "subtopic"],
    "additionalProperties": False,
}


def schema_for(version):
    """The output schema for a prompt version.
    v1-v3 and v6: the original field order (`working` sits after `question`; v6 is v3 plus three content rules).
    v4: `working` is the FIRST field. The API refused every v4 request (trial 4), most likely because a
        reasoning/scratchpad field in the reply is what its `reasoning_extraction` safety check looks for.
    v5: no `working` field at all; the model does its reasoning in its own thinking, not in the reply."""
    if version in ("v1", "v2", "v3", "v6"):
        return ITEM_SCHEMA
    props = ITEM_SCHEMA["properties"]
    if version == "v4":
        order = ["working"] + [k for k in props if k != "working"]
        return {**ITEM_SCHEMA, "properties": {k: props[k] for k in order}}
    return {**ITEM_SCHEMA, "properties": {k: v for k, v in props.items() if k != "working"},
            "required": V5_REQUIRED}


# Fields that exist in prompt-v1 items (the first trial), so old files can still be checked.
V1_REQUIRED = [k for k in ITEM_SCHEMA["required"] if k not in ("working", "r_solution")]
# Fields of prompt-v5 items: everything except `working`.
V5_REQUIRED = [k for k in ITEM_SCHEMA["required"] if k != "working"]


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
        "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": schema_for(PROMPT_VERSION)}},
    }


def est_input_tokens(params):
    """Deliberately generous upper estimate: one token per 3 characters."""
    chars = len(params["system"]) + sum(len(m["content"]) for m in params["messages"]) + len(json.dumps(schema_for(PROMPT_VERSION)))
    return math.ceil(chars / 3.0)


def cost_usd(in_tok, out_tok, batch=False):
    c = (in_tok * PRICE_IN_PER_MTOK + out_tok * PRICE_OUT_PER_MTOK) / 1_000_000
    return c * BATCH_FACTOR if batch else c


def worst_case(params, batch=False):
    return cost_usd(est_input_tokens(params), MAX_TOKENS, batch)


# ---------------------------------------------------------------------------------------------
# Checking a returned item
# ---------------------------------------------------------------------------------------------
WORD_NUMBERS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def stated_decimals(question):
    """How many decimal places the question asks for ('3 decimal places', 'two decimals', 'whole number'), or None."""
    q = question.lower()
    m = re.search(r"\b(\d+|zero|one|two|three|four|five|six)\s+decimal(?:\s+place)?s?\b", q)
    if m:
        v = m.group(1)
        return int(v) if v.isdigit() else WORD_NUMBERS[v]
    if "whole number" in q or "nearest integer" in q:
        return 0
    return None


def check_item(item, slot, stop_reason, r_keyed=False):
    """Return a list of problems (empty list = the item looks fine).

    r_keyed=True means the script will take the key of a NUMBER question from R's output (see apply_r_key),
    so it does not judge the model's typed number: its decimals, tolerance and format are repaired by that
    step instead of being treated as failures."""
    problems = []
    legacy = "r_solution" not in item  # an item written by prompt v1 (no working, no r_solution)
    if stop_reason == "max_tokens":
        problems.append("cut off at max_tokens")
    # v2-v4 items have `working`; v5 items do not (see schema_for). Which fields to require follows the item.
    required = V1_REQUIRED if legacy else (ITEM_SCHEMA["required"] if "working" in item else V5_REQUIRED)
    for k in required:
        if k not in item:
            problems.append(f"missing field {k}")
    if problems:
        return problems
    for k in ("category", "subtopic", "difficulty", "answer_type"):
        if item[k] != slot[k]:
            problems.append(f"{k} differs from the slot ({item[k]!r} vs {slot[k]!r})")
    if not item["question"].strip():
        problems.append("empty question")
    # The model sometimes "thinks aloud" inside the question text (found in trial 3, BM0015: "...must be... no:
    # exactly 2 statisticians..."). R cannot catch this because the code and key can still be consistent.
    text = item["question"] + " " + " ".join(item["choices"])
    marker = re.search(r"\bno:|\bwait\b|\bhmm\b|\bsorry\b|\blet me\b|\boops\b|\.\.\.\s*(no|wait|hmm)\b", text, re.I)
    if marker:
        problems.append(f"question text looks unfinished or self-correcting (found {marker.group(0)!r})")
    # A question that trails off ("... must be... ") is unfinished (trial 7, BM0015). Only a TRAILING ellipsis
    # counts: "..." inside the text is normal, for example "X1, ..., Xn".
    if re.search(r"(\.\.\.|…)\s*$", item["question"]):
        problems.append("question text ends with an ellipsis, so it looks unfinished")
    # A placeholder explanation such as "invalid" shows the model gave up (trial 7, BM0020).
    if not legacy and len(item["explanation"].strip()) < 10:
        problems.append("explanation is empty or only a few characters, so the item looks unfinished")
    number_r_keyed = r_keyed and item["answer_type"] == "number"
    if not item["canonical_answer"].strip() and not number_r_keyed:
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
    if item["answer_type"] == "number" and not number_r_keyed:
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
    # Prompt v2 items: a number answer must come with R code that recomputes it (verify runs that code).
    if not legacy and item["answer_type"] == "number" and not item["r_solution"].strip():
        problems.append("number answer without r_solution (no R code to recompute the key)")
    # Rounding rules (prompt v3): when the question states how to round, the key must be written with
    # exactly that many decimals and the allowed error must cover a tie rounded the other way.
    # (Found in trial 2: BM0005 asked for 3 decimals but the key was "0.74"; BM0001's exact value 0.3125
    # was rounded to 0.312 by R but written 0.313 in the key.)
    if item["answer_type"] == "number" and not number_r_keyed:
        d = stated_decimals(item["question"])
        if d is not None:
            key_text = item["canonical_answer"].strip().replace(",", "")
            key_decimals = len(key_text.split(".")[1]) if "." in key_text else 0
            if key_decimals != d:
                problems.append(f"the question asks for {d} decimal place(s) but the key has {key_decimals}")
            # (only for answers with decimals: a whole-number answer from exact code output may have tolerance 0)
            if d >= 1 and float(item["answer_tolerance"]) < 0.5 * 10 ** (-d) - 1e-12:
                problems.append(f"answer_tolerance {item['answer_tolerance']:g} is below half of the last decimal place "
                                f"({0.5 * 10 ** (-d):g}), so a tie rounded the other way would be marked wrong")
    # Cheap consistency test for number answers: the key should equal the last number in the model's own
    # worked explanation. (Found in the first trial: two keys contradicted their own working.)
    # Only used for items WITHOUT r_solution: when R code exists, R is the authority and `verify` compares
    # against it (the text test gave a false alarm on BM0020 in trial 2, where the key was right).
    if item["answer_type"] == "number" and not (item.get("r_solution") or "").strip():
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
        "cap_usd": cap, "max_attempts": MAX_ATTEMPTS,
        "number_key_source": "R output of r_solution (the model's typed key is kept as model_canonical_answer)",
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
    print(f"(A question that fails the checks is regenerated, up to {MAX_ATTEMPTS} attempts in all. Retries are not in "
          f"the worst case above; the live cap check stops the run before spending past the cap.)")
    print(f"Your cap: ${cap:.2f}")
    ok = w_total <= cap
    print("Cap check:", "OK, even the worst case fits under the cap" if ok else
          "FAILED, the worst case could exceed the cap; lower --n or max_tokens, or raise --cap-usd")
    return ok, w_total, reqs


def run_attempts(client, slot, req, rscript, resp_f, calls, rejected, state, cap_usd,
                 first_attempt=1, workspace_ids=None):
    """Get ONE question for one slot, asking again if it fails the automatic checks.

    HOW IT WORKS: each attempt is a fresh API call with the SAME prompt (we deliberately do not tell the model
    what was wrong, so the share of first attempts that pass stays an honest measure of the prompt). An attempt
    passes when process_reply finds no hard problems. After MAX_ATTEMPTS attempts in total the last one is kept
    and marked final_status "failed". Every attempt's reply is saved, and every failed attempt is added to
    `rejected` so nothing is thrown away unseen.

    The run must stop (state["stopped"] is set and we return) on a refusal, on a request-level error such as a
    suspended model, or when the next call could push spending past the cap. `state["spent"]` is the money
    spent so far across all slots.

    Returns the row to keep for this slot, or None if no reply came back."""
    import anthropic

    last_row = None
    for attempt in range(first_attempt, MAX_ATTEMPTS + 1):
        if state["spent"] + worst_case(req) > cap_usd:
            state["stopped"] = (f"stopped before {slot['item_id']} attempt {attempt}: spent ${state['spent']:.4f} "
                                f"+ worst case would exceed the cap")
            print(state["stopped"])
            break
        t0 = time.time()
        try:
            raw = client.messages.with_raw_response.create(**req)
            msg = raw.parse()
        except (anthropic.BadRequestError, anthropic.AuthenticationError,
                anthropic.PermissionDeniedError, anthropic.NotFoundError) as e:
            state["stopped"] = f"stopped at {slot['item_id']}: {type(e).__name__}: {e}"
            print(state["stopped"])
            break
        except anthropic.APIError as e:
            calls.append({"item_id": slot["item_id"], "attempt": attempt, "error": f"{type(e).__name__}: {e}"})
            print(f"{slot['item_id']}: error {type(e).__name__}, continuing")
            continue
        ws = raw.headers.get("anthropic-workspace-id")
        if ws and workspace_ids is not None:
            workspace_ids.add(ws)
        u = msg.usage
        c = cost_usd(u.input_tokens, u.output_tokens)
        state["spent"] += c
        msg_dump = msg.model_dump(mode="json")
        refused = msg.stop_reason == "refusal"
        # A refusal is a normal HTTP 200 reply with no content, not an error and not bad JSON; process_reply
        # reports it as a refusal instead of trying to parse it (trial 4 did, and showed 20 misleading problems).
        item, hard, soft = process_reply(msg, slot, rscript)
        call = {"item_id": slot["item_id"], "attempt": attempt, "request_id": getattr(msg, "_request_id", None),
                "stop_reason": msg.stop_reason,
                # The WHOLE stop_details object exactly as the API sent it (None if the reply has none),
                # because its fields can be null and new fields may be added.
                "stop_details": msg_dump.get("stop_details"),
                # Which kinds of block came back, e.g. ["thinking", "text"]: shows whether the model thought.
                "content_blocks": [b.type for b in msg.content],
                "input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "cost_usd": round(c, 6),
                "seconds": round(time.time() - t0, 1), "problems": hard, "soft_flags": soft}
        calls.append(call)
        resp_f.write(json.dumps({"item_id": slot["item_id"], "attempt": attempt, "response": msg_dump},
                                ensure_ascii=False) + "\n")
        resp_f.flush()
        if refused:
            print(f"{slot['item_id']}: REFUSED. stop_details={json.dumps(call['stop_details'])} "
                  f"request_id={call['request_id']} in {u.input_tokens} out {u.output_tokens} ${c:.4f}  "
                  f"[total ${state['spent']:.4f}]")
            # Stop now (a refusal usually repeats for every item), but only AFTER this call's entry and raw
            # reply are saved above; the code after the loop still writes the run log and item files.
            state["stopped"] = f"stopped at {slot['item_id']}: refusal, stop_details={json.dumps(call['stop_details'])}"
            break
        status = "OK" if not hard else "HARD: " + "; ".join(hard)
        if soft:
            status += "  SOFT: " + "; ".join(soft)
        print(f"{slot['item_id']} [try {attempt}]: in {u.input_tokens} out {u.output_tokens} ${c:.4f} "
              f"({call['seconds']}s) {status}  [total ${state['spent']:.4f}]")
        row = {**slot, **(item or {}), "problems": hard, "soft_flags": soft, "attempts": attempt}
        if not hard:
            row["final_status"] = "ok"
            return row
        rejected.append(row)
        last_row = row
    return {**last_row, "final_status": "failed"} if last_row is not None else None


def cmd_trial(args):
    import anthropic

    prompt, sha = load_prompt()
    slots = blueprint(args.n)
    ok, w_total, reqs = preflight(slots, prompt, args.cap_usd, batch=False)
    if args.dry_run:
        print("\n--- First request exactly as it would be sent (dry run: nothing was sent) ---")
        print("SYSTEM:\n" + reqs[0]["system"])
        print("\nUSER:\n" + reqs[0]["messages"][0]["content"])
        print("\noutput_config:", json.dumps({"effort": EFFORT, "format": f"json_schema (schema_for {PROMPT_VERSION})"}))
        print("Output fields, in order:", ", ".join(schema_for(PROMPT_VERSION)["properties"]))
        return
    if not ok:
        sys.exit(2)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set in this environment. Nothing was sent.")
    rscript = rscript_path()  # find R BEFORE any money is spent: the keys of number questions come from R

    out = new_output_dir("trial")
    meta = run_meta("trial", args.n, args.cap_usd, sha)
    print(f"\nOutput folder: {out}\n")
    client = anthropic.Anthropic(max_retries=2)
    calls, items, rejected, workspace_ids = [], [], [], set()
    state = {"spent": 0.0, "stopped": None}
    with open(out / "responses.jsonl", "w", encoding="utf-8") as resp_f:
        for slot, req in zip(slots, reqs):
            row = run_attempts(client, slot, req, rscript, resp_f, calls, rejected, state, args.cap_usd,
                               workspace_ids=workspace_ids)
            if row is not None:
                items.append(row)
            if state["stopped"]:
                break
    spent, stopped = state["spent"], state["stopped"]

    usable = [i for i in items if i["final_status"] == "ok"]
    first_try = [i for i in usable if i["attempts"] == 1]
    soft_items = [i for i in items if i["soft_flags"]]
    retry_calls = sum(1 for c in calls if c.get("attempt", 1) > 1)
    meta.update({"finished_utc": utc_now().isoformat(timespec="seconds"), "calls": calls,
                 "workspace_ids_seen": sorted(workspace_ids), "stopped_early_reason": stopped,
                 "total_input_tokens": sum(c.get("input_tokens", 0) for c in calls),
                 "total_output_tokens": sum(c.get("output_tokens", 0) for c in calls),
                 "total_cost_usd": round(spent, 6), "items_parsed": len(items),
                 "usable_items": len(usable), "usable_on_first_attempt": len(first_try),
                 "failed_after_all_attempts": len(items) - len(usable), "retry_calls": retry_calls,
                 "rejected_attempts": len(rejected), "items_with_soft_flags": len(soft_items),
                 "items_with_problems": len(items) - len(usable)})
    (out / "batch_log.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    with open(out / "items.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    with open(out / "rejected_attempts.jsonl", "w", encoding="utf-8") as f:
        for it in rejected:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    # A small review copy inside the repository (backed up by Git).
    review = REPO / "results" / "benchmark_trial"
    review.mkdir(parents=True, exist_ok=True)
    shutil.copy(out / "items.jsonl", review / f"{out.name}_items.jsonl")
    shutil.copy(out / "batch_log.json", review / f"{out.name}_log.json")
    if rejected:
        shutil.copy(out / "rejected_attempts.jsonl", review / f"{out.name}_rejected_attempts.jsonl")
    per_usable = f"${spent / len(usable):.4f}" if usable else "n/a"
    print(f"\nDone. {len(items)} slot(s) finished: {len(usable)} usable ({len(first_try)} on the first attempt), "
          f"{len(items) - len(usable)} still failing after {MAX_ATTEMPTS} attempts. Retry calls: {retry_calls}. "
          f"Items with soft flags (look at these): {len(soft_items)}.")
    print(f"Total cost ${spent:.4f} of cap ${args.cap_usd:.2f}; cost per usable item {per_usable}.")
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
    if manifest.get("prompt_version") and manifest["prompt_version"] != PROMPT_VERSION:
        print(f"Using the prompt version this batch was submitted with ({manifest['prompt_version']}), not {PROMPT_VERSION}.")
        set_prompt(manifest["prompt_version"])
    if manifest.get("effort"):
        set_effort(manifest["effort"])   # regenerations must use the same effort as the batch
    slots = {s["item_id"]: s for s in manifest["slots"]}
    rscript = rscript_path()
    client = anthropic.Anthropic(max_retries=2)
    batch = client.messages.batches.retrieve(manifest["batch_id"])
    rc = batch.request_counts
    print(f"Batch {batch.id}: {batch.processing_status} (processing {rc.processing}, succeeded {rc.succeeded}, "
          f"errored {rc.errored}, expired {rc.expired}, canceled {rc.canceled})")
    if batch.processing_status != "ended":
        print("Not finished yet. Run fetch again later (batches finish within 24 hours, usually much sooner).")
        return
    out = Path(manifest["output_dir"])
    items, calls, rejected, spent = [], [], [], 0.0
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
            msg_dump = msg.model_dump(mode="json")
            # In a batch a refusal also comes back as a "succeeded" result; process_reply reports it, not parses it.
            item, hard, soft = process_reply(msg, slots[iid], rscript)
            calls.append({"item_id": iid, "attempt": 1, "message_id": msg_dump.get("id"), "stop_reason": msg.stop_reason,
                          "stop_details": msg_dump.get("stop_details"), "content_blocks": [b.type for b in msg.content],
                          "input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "cost_usd": round(c, 6),
                          "problems": hard, "soft_flags": soft})
            resp_f.write(json.dumps({"item_id": iid, "attempt": 1, "response": msg_dump}, ensure_ascii=False) + "\n")
            row = {**slots[iid], **(item or {}), "problems": hard, "soft_flags": soft, "attempts": 1,
                   "final_status": "failed" if hard else "ok"}
            if hard:
                rejected.append(row)
            items.append(row)

    # Regenerate the failures with ordinary (standard-price) calls, up to MAX_ATTEMPTS attempts per question.
    retry_spent, stopped = 0.0, None
    if args.retry_failed:
        have = {i["item_id"]: i for i in items}
        todo = [(slots[iid], have[iid]["attempts"] + 1 if iid in have else 1) for iid in sorted(slots)
                if iid not in have or have[iid]["final_status"] != "ok"]
        print(f"{len(todo)} question(s) failed or are missing; regenerating them with standard calls "
              f"(cap ${args.cap_usd:.2f}).")
        if todo:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                sys.exit("ANTHROPIC_API_KEY is not set in this environment. The batch results were not saved; run again.")
            prompt, _ = load_prompt()
            state = {"spent": 0.0, "stopped": None}
            with open(out / "responses.jsonl", "a", encoding="utf-8") as resp_f:
                for slot, first in todo:
                    row = run_attempts(client, slot, build_request(slot, prompt), rscript, resp_f, calls, rejected,
                                       state, args.cap_usd, first_attempt=first)
                    if row is not None:
                        have[slot["item_id"]] = row
                    if state["stopped"]:
                        break
            items, retry_spent, stopped = list(have.values()), state["spent"], state["stopped"]
    items.sort(key=lambda i: i["item_id"])
    usable = [i for i in items if i["final_status"] == "ok"]
    manifest.update({"fetched_utc": utc_now().isoformat(timespec="seconds"), "calls": calls,
                     "total_input_tokens": sum(c.get("input_tokens", 0) for c in calls),
                     "total_output_tokens": sum(c.get("output_tokens", 0) for c in calls),
                     "total_cost_usd_batch": round(spent, 6), "retry_cost_usd_standard": round(retry_spent, 6),
                     "stopped_early_reason": stopped, "items_parsed": len(items), "usable_items": len(usable),
                     "usable_on_first_attempt": sum(1 for i in usable if i["attempts"] == 1),
                     "items_with_soft_flags": sum(1 for i in items if i["soft_flags"]),
                     "rejected_attempts": len(rejected), "items_with_problems": len(items) - len(usable)})
    (out / "batch_log.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with open(out / "items.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    with open(out / "rejected_attempts.jsonl", "w", encoding="utf-8") as f:
        for it in rejected:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"Fetched {len(items)} items, {len(usable)} usable; batch cost ${spent:.4f}"
          + (f", regeneration cost ${retry_spent:.4f}" if args.retry_failed else "") + f". Saved in {out}")


def cmd_replay(args):
    """Run the checks and the R-key step over replies already saved in a responses.jsonl. Free: no API call.
    Use it to see what a changed checker would have done to a past trial."""
    from anthropic.types import Message

    rscript = rscript_path()
    slots = {s["item_id"]: s for s in blueprint(args.n)}
    n = n_hard = n_soft = 0
    for line in open(args.responses, encoding="utf-8"):
        rec = json.loads(line)
        slot = slots.get(rec["item_id"])
        if slot is None:
            continue
        n += 1
        item, hard, soft = process_reply(Message.model_validate(rec["response"]), slot, rscript)
        n_hard += bool(hard)
        n_soft += bool(soft)
        key = ""
        if item is not None and item.get("key_source") == "r":
            key = f" key {item['canonical_answer']} (R {item['r_value']}, model typed {item['model_canonical_answer']})"
        if hard or soft or args.all:
            print(f"{slot['item_id']} [{slot['category']}]{key}" + ("  HARD: " + "; ".join(hard) if hard else "")
                  + ("  SOFT: " + "; ".join(soft) if soft else ""))
    print(f"\n{n} replies replayed: {n_hard} with hard problems (would be regenerated), {n_soft} with soft flags.")


def cmd_check(args):
    """Re-run the automatic checks on an existing items.jsonl file. Free: no API call."""
    n_bad = 0
    for line in open(args.items, encoding="utf-8"):
        item = json.loads(line)
        problems = check_item(item, item, "end_turn", r_keyed=item.get("key_source") == "r")
        if problems:
            n_bad += 1
            print(f"{item['item_id']}: " + "; ".join(problems))
    print(f"\n{n_bad} item(s) flagged by the automatic checks. These checks catch only some errors; "
          "the answer keys still need to be verified by running R or recomputing (see README Phase 3).")


# ---------------------------------------------------------------------------------------------
# verify: use R to test the answer keys (free, no API call)
#
# WHY: in the first trial 3 of 8 numerical keys were wrong, and in one case the model's own written
# explanation had the arithmetic slip, so asking the same model to re-read it would not help. R does
# not share the model's blind spots in arithmetic, so we let R produce the number and compare it with
# the key. The code R runs was written by the model, so it is run in a throwaway folder with a time
# limit, and code that touches files, the network or the operating system is refused.
# ---------------------------------------------------------------------------------------------
# R functions we never run (model-written code executes on this PC).
UNSAFE_R = re.compile(
    r"\b(system2?|shell|shell\.exec|unlink|file\.remove|file\.rename|file\.create|file\.copy|dir\.create|"
    r"download\.file|url|socketConnection|setwd|Sys\.setenv|Sys\.setlocale|source|sys\.source|readline|readLines|"
    r"writeLines|readRDS|saveRDS|write|write\.csv|read\.csv|sink|install\.packages|library|require|"
    r"loadNamespace|dyn\.load|quit|q)\s*\(")
R_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
KEY_TOL = 0.0006  # keys are rounded to 3 decimals, so a correct key is within 0.0005 of R's value


def rscript_path():
    paths = yaml.safe_load((REPO / "configs" / "paths.yaml").read_text())
    p = Path(paths["rscript"])
    if not p.exists():
        sys.exit(f"Rscript not found at {p}. Install R or fix `rscript` in configs/paths.yaml.")
    return str(p)


def run_r(code, rscript):
    """Run R code in a temporary folder. Returns (ok, stdout_or_error_text)."""
    if UNSAFE_R.search(code):
        return False, "refused: code uses a function that is not allowed (" + UNSAFE_R.search(code).group(1) + ")"
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "code.R").write_text(code, encoding="utf-8")
        try:
            r = subprocess.run([rscript, "--vanilla", "code.R"], cwd=tmp, capture_output=True, text=True,
                               timeout=20, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return False, "R timed out after 20 s"
    if r.returncode != 0:
        return False, "R error: " + (r.stderr.strip().splitlines() or ["?"])[-1]
    return True, r.stdout


def r_string(s):
    """Write a Python string as an R string literal."""
    return json.dumps(s)  # JSON escapes (\" \\ \n \uXXXX) are valid R escapes


def r_check_result(item, candidate, rscript):
    """Run the item's r_check with `candidate` as the student's answer. Returns True, False or an error text."""
    code = (f"candidate <- {r_string(candidate)}\n"
            f".res <- withVisible({{\n{item['r_check']}\n}})$value\n"
            f"cat('RESULT:', isTRUE(.res), '\\n')\n")
    ok, out = run_r(code, rscript)
    if not ok:
        return out if out.startswith("refused") else False  # an R error on a wrong answer counts as "not TRUE"
    return "RESULT: TRUE" in out


def run_r_solution(item, rscript):
    """Run the item's r_solution code in R. Returns (r_text, problem): r_text is the ONE number the code printed,
    as text with up to 15 digits (for example "0.940869"), or None with a plain-language problem if R could
    not produce exactly one number. Used both to write the key (apply_r_key) and to check it (verify_item)."""
    sol = (item.get("r_solution") or "").strip()
    if not sol:
        return None, "no r_solution, so R cannot recompute this key"
    ok, out = run_r("options(digits = 15)\n" + sol, rscript)
    if not ok:
        return None, f"r_solution failed: {out}"
    nums = R_NUMBER.findall(re.sub(r"\[\d+\]", " ", out))
    if len(nums) != 1:
        return None, f"r_solution printed {len(nums)} numbers (expected exactly 1): {out.strip()[:80]!r}"
    return nums[0], None


def round_key(r_text, decimals):
    """Round R's number to `decimals` places, halves rounded UP, working on R's printed digits (not on a float).
    Example: "0.3125" to 3 places is "0.313" (Python's round() and R's round() both give 0.312, because they
    round a tie to the even digit; the question says "round" in the everyday sense, so we round half up)."""
    rounded = Decimal(r_text).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    if rounded == 0:
        rounded = abs(rounded)  # never write "-0.000"
    return format(rounded, "f")


def apply_r_key(item, rscript):
    """For a NUMBER question, replace the model's typed key with the one R computes from r_solution.

    WHY: the model writes the key from its head, and R cannot be fooled by a slip of arithmetic or typing
    (trial 7, BM0013: the model typed 4.867 while its own code and explanation give 4.25). R's value is rounded
    the way the question says. What R cannot do is notice that the code answers a different question than the
    one written, so the model's typed key is kept as `model_canonical_answer` and a disagreement is returned as
    a soft flag (a warning that a person should look, not a reason to throw the question away).

    Returns (hard_problems, soft_flags) and changes `item` in place."""
    hard, soft = [], []
    r_text, problem = run_r_solution(item, rscript)
    if problem:
        return [problem], soft
    value = Decimal(r_text)
    is_integer = value == value.to_integral_value()
    decimals = stated_decimals(item["question"])
    if decimals is None:
        if not is_integer:
            return ["the question does not say how to round, so R's value cannot be turned into a key"], soft
        decimals = 0
        tolerance_floor = 0.0           # an exact whole-number answer needs no tolerance
    else:
        tolerance_floor = 0.5 * 10 ** (-decimals) if (decimals >= 1 or not is_integer) else 0.0
    typed = item["canonical_answer"].strip()
    try:
        typed_decimals = len(typed.replace(",", "").split(".")[1]) if "." in typed else 0
        if abs(float(typed.replace(",", "")) - float(value)) > max(KEY_TOL, 0.5 * 10 ** (-typed_decimals) + 1e-9):
            soft.append(f"the model's typed key {typed} differs from R's {r_text}; the key is now R's value")
    except ValueError:
        soft.append(f"the model's typed key {typed!r} is not a number; the key is now R's value")
    item["model_canonical_answer"] = typed
    item["canonical_answer"] = round_key(r_text, decimals)
    item["key_source"] = "r"
    item["r_value"] = r_text
    item["answer_tolerance"] = max(float(item["answer_tolerance"]), tolerance_floor)
    return hard, soft


def process_reply(msg, slot, rscript):
    """Turn one API reply into (item, hard_problems, soft_flags), the single path used by trial, fetch and replay.
    hard problems mean "regenerate this question"; soft flags mean "keep it, but a person should look"."""
    if msg.stop_reason == "refusal":
        return None, ["refused by the API (stop_reason refusal); see stop_details"], []
    try:
        item = json.loads(first_text(msg))
    except json.JSONDecodeError as e:
        return None, [f"reply is not valid JSON ({e})"], []
    hard, soft = check_item(item, slot, msg.stop_reason, r_keyed=True), []
    if not any(p.startswith(("missing field", "cut off")) for p in hard):
        if item["answer_type"] == "number" and (item.get("r_solution") or "").strip():
            h, soft = apply_r_key(item, rscript)
            hard += h
        else:
            item["key_source"] = "model"   # multiple choice, R expressions and short text: no number for R to compute
    return item, hard, soft


def verify_item(item, rscript):
    """Return (status, issues, r_value). status is one of: ok, FLAGGED, not_machine_checkable."""
    issues, r_value, checked = [], None, False
    # 1. Number keys: let R recompute the number from the model's r_solution and compare.
    if item["answer_type"] == "number":
        r_text, problem = run_r_solution(item, rscript)
        if problem:
            issues.append(problem)
            # no r_solution at all means nothing was checked; any other problem means R was tried and failed
            checked = not problem.startswith("no r_solution")
        else:
            checked = True
            r_value = float(r_text)
            try:
                key_text = item["canonical_answer"].strip().replace(",", "")
                key = float(key_text)
                # A correctly rounded key is within half of its own last decimal place of R's value
                # (0.94 for R's 0.940869 is right when the question asks for 2 decimals). For an item whose
                # key came from R (key_source "r") this passes by construction; the model's own typed key is
                # compared separately, at generation time, and shows up as a soft flag.
                key_decimals = len(key_text.split(".")[1]) if "." in key_text else 0
                if abs(r_value - key) > max(KEY_TOL, 0.5 * 10 ** (-key_decimals) + 1e-9):
                    issues.append(f"KEY MISMATCH: key {key:g} but R computes {r_value:.6g}")
            except ValueError:
                issues.append("key is not a plain number")
    # 2. Items with an r_check: the key must pass it, and wrong answers must fail it.
    if (item.get("r_check") or "").strip():
        checked = True
        res_key = r_check_result(item, item["canonical_answer"], rscript)
        if res_key is not True:
            issues.append("r_check does not accept the key" + (f" ({res_key})" if isinstance(res_key, str) else ""))
        for wrong in ("NULL", "-999999", "'zzz'"):
            res_wrong = r_check_result(item, wrong, rscript)
            if res_wrong is True:
                issues.append(f"r_check is vacuous: it accepts the wrong answer {wrong}")
                break
    if issues:
        return "FLAGGED", issues, r_value
    return ("ok" if checked else "not_machine_checkable"), issues, r_value


def cmd_verify(args):
    """Run R on every item in an items.jsonl. Free: no API call. Writes <name>_verified.jsonl beside it."""
    rscript = rscript_path()
    path = Path(args.items)
    out_rows, counts = [], {}
    for line in open(path, encoding="utf-8"):
        item = json.loads(line)
        status, issues, r_value = verify_item(item, rscript)
        extra = check_item(item, item, "end_turn", r_keyed=item.get("key_source") == "r")  # also the free format checks
        if extra:
            status, issues = "FLAGGED", issues + extra
        counts[status] = counts.get(status, 0) + 1
        out_rows.append({**item, "verify_status": status, "verify_issues": issues, "r_value": r_value})
        for note in item.get("soft_flags") or []:
            print(f"{item['item_id']} [{item['category']}]: NOTE (soft flag from generation): {note}")
        if status == "FLAGGED":
            print(f"{item['item_id']} [{item['category']}]: " + "; ".join(issues))
        elif status == "not_machine_checkable":
            print(f"{item['item_id']} [{item['category']}]: not machine-checkable (needs a blind re-solve / other-family check)")
    dest = path.with_name(path.stem + "_verified.jsonl")
    with open(dest, "w", encoding="utf-8") as f:
        for row in out_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nSummary: {counts}   (wrote {dest})")
    print("ok = R agreed with the key; FLAGGED = R disagreed or the check is broken; not_machine_checkable = no "
          "code to run (multiple-choice and conceptual items), these need the other checks in README Phase 3.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompt", default=PROMPT_VERSION, choices=["v1", "v2", "v3", "v4", "v5", "v6"], help="which prompt file to use (default v6)")
    ap.add_argument("--effort", default=EFFORT, choices=["low", "medium", "high", "xhigh", "max"], help="how hard the model thinks (default medium)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("verify", help="run R to test the answer keys of an items.jsonl file (free)")
    p.add_argument("--items", required=True)
    p.set_defaults(fn=cmd_verify)
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
    p.add_argument("--retry-failed", action="store_true", help="regenerate failed or missing questions with standard calls")
    p.add_argument("--cap-usd", type=float, default=5.0, help="money cap for the regeneration calls only")
    p.set_defaults(fn=cmd_fetch)
    p = sub.add_parser("replay", help="re-run the checks and the R-key step on saved API replies (free)")
    p.add_argument("--responses", required=True, help="a responses.jsonl file from an earlier run")
    p.add_argument("--n", type=int, default=20, help="how many slots of the blueprint to match against")
    p.add_argument("--all", action="store_true", help="also list items with no problems")
    p.set_defaults(fn=cmd_replay)
    args = ap.parse_args()
    set_prompt(args.prompt)
    set_effort(args.effort)
    args.fn(args)


if __name__ == "__main__":
    main()
