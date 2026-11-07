"""
generate_benchmark.py - the shared benchmark library: question slots, the generation prompt, the output schema,
the automatic checks, and the step where R writes and verifies answer keys. Also four free command-line checks.

WHAT THIS IS
The project's benchmark is a fixed set of about 1,000 statistics/R questions with known answers, used as the
"final exam" for the small Pythia models. The teacher model (Qwen3.6-27B on Talon, with Redhawk as the fallback)
writes the questions. The client that talks to the teacher is open_teacher_test.py; it imports the pieces below so
that the prompt and the checks are defined in exactly one place and cannot drift. This file makes no model calls.
(The original Claude API commands were removed on 2026-11-06; see docs/methodology/workflow.md Section 2.2 and the Git tag
pre-cleanup-claude-era.)

HOW A QUESTION GETS MADE (plain steps)
1. blueprint(n): a fixed, repeatable list of n "slots". Each slot says which category, subtopic,
   difficulty and answer type one question must have (for example: "numerical / z-score probability /
   intro / number"). The list is built so that any 20 slots in a row already have the target mix, and
   1,000 slots are just 50 copies of that pattern with different subtopics. No randomness is left to
   chance: running it again gives the same slots.
2. build_request(): fills the prompt file (data/prompts/benchmark_generation_v6.md) with one slot's details and
   returns the system text and the user message. open_teacher_test.py appends the output schema as text.
3. The teacher writes one question as a JSON object.
4. process_reply(): the reply is parsed and checked (valid JSON, right fields, short answer, not cut off,
   question text finished). The checks sort problems into two kinds:
     HARD problem = the question is unusable, so it is asked for again.
     SOFT flag    = the question is kept but a person should look at it.
5. For a NUMBER question the key is taken from R, not from the model: apply_r_key() runs the model's
   r_solution code, rounds R's number the way the question says (halves up), and writes that as the key.
   The model's own typed key is kept as model_canonical_answer; if the two disagree the item gets a soft
   flag. Example: the model typed 4.867, its code prints 4.25, so the key becomes 4.250.
   R fixes slips of arithmetic or typing. It cannot notice code that answers a different question than the
   one written, which is why the soft flag and, later, a blind re-solve exist.

FREE COMMANDS (no model call; run with the project's virtual environment Python)
  python generate_benchmark.py plan --n 20 [--start 21]                 print the slots
  python generate_benchmark.py check --items <items.jsonl>              re-run the automatic checks
  python generate_benchmark.py verify --items <items.jsonl>             run R to test the answer keys
  python generate_benchmark.py dupcheck --items <new.jsonl> --against <earlier files or patterns>   near-duplicates
"""

import argparse
import glob
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml

try:
    sys.stdout.reconfigure(encoding="utf-8")  # so quotes and symbols print on Windows
except Exception:
    pass

PROMPT_VERSION = "v6"                # the generation prompt in use (data/prompts/benchmark_generation_v6.md)

REPO = Path(__file__).resolve().parents[2]
PROMPT_FILE = REPO / "data" / "prompts" / f"benchmark_generation_{PROMPT_VERSION}.md"


# ---------------------------------------------------------------------------------------------
# The blueprint: which kinds of questions, in which proportions.
# This mix is a PROPOSAL (docs/methodology/workflow.md Section 3; an open decision to confirm with Dr. Lee).
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
# written after the work, not before it.
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
    """The output schema for a prompt version. Only v6 is in use (the older prompts were Claude-era experiments,
    archived under the Git tag pre-cleanup-claude-era)."""
    if version != "v6":
        raise ValueError(f"unknown prompt version {version!r}; only v6 is in use")
    return ITEM_SCHEMA


# Fields check_item() requires when a reply leaves out `r_solution` (and `working`), or only `working`. The checks
# follow the fields a reply actually contains, so a reply without `working` is still checked instead of rejected
# outright. (Kept unchanged from the Claude-era code, where prompts v1 and v5 produced such items; a reply that
# omits these fields is treated the same way today.)
REQUIRED_WITHOUT_R_SOLUTION = [k for k in ITEM_SCHEMA["required"] if k not in ("working", "r_solution")]
REQUIRED_WITHOUT_WORKING = [k for k in ITEM_SCHEMA["required"] if k != "working"]


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


def select_slots(n, start=1):
    """n slots beginning at question number `start` (1 = BM0001). Because the blueprint repeats a 20-slot
    pattern, any run of 20 (or a multiple of 20) slots has the same mix of categories, difficulties and answer
    types, so `start=21, n=100` gives BM0021 to BM0120: the same mix as the first 20, with none of their slots."""
    return blueprint(start - 1 + n)[start - 1:]


# ---------------------------------------------------------------------------------------------
# The single place where the text sent to the teacher is built
# ---------------------------------------------------------------------------------------------
def build_request(slot, prompt):
    """The system text and the user message for one slot. The teacher client (open_teacher_test.py) sends these,
    with the output schema appended to the system text."""
    user = prompt[("USER", None)].format(
        item_id=slot["item_id"], category=slot["category"], category_text=prompt[("CAT", slot["category"])],
        subtopic=slot["subtopic"], difficulty=slot["difficulty"], difficulty_text=prompt[("DIFF", slot["difficulty"])],
        answer_type=slot["answer_type"],
        answer_type_text=prompt[("TYPE", slot["answer_type"])].format(preferred_letter=slot["preferred_letter"] or "any letter"),
    )
    return {
        "system": prompt[("SYSTEM", None)],
        "messages": [{"role": "user", "content": user}],
    }



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
    legacy = "r_solution" not in item  # a reply with no r_solution field (Claude-era prompt v1 wrote such items)
    if stop_reason == "max_tokens":
        problems.append("cut off at max_tokens")
    # Which fields to require follows the item (see REQUIRED_WITHOUT_R_SOLUTION above).
    required = (REQUIRED_WITHOUT_R_SOLUTION if legacy else
                (ITEM_SCHEMA["required"] if "working" in item else REQUIRED_WITHOUT_WORKING))
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
    # "wait" alone is normal English ("customers wait at a clinic", batch BM0056), so it only counts as an
    # interjection ("Wait, ..."). "Actually, to keep it simple, consider this version instead" (batch BM0047)
    # is the model changing its mind inside the question.
    marker = re.search(r"\bno:|\bwait\s*[,.:!\u2014-]|[.!?]\s+wait\b|\bhmm\b|\bsorry\b|\blet me\b|\boops\b|"
                       r"\.\.\.\s*(no|wait|hmm)\b|(?:^|[.!?]\s+|\n\s*)actually,|\bto keep it simple\b|"
                       r"\bon second thought\b|\bscratch that\b", text, re.I)
    if marker:
        problems.append(f"question text looks unfinished or self-correcting (found {marker.group(0)!r})")
    # A question that trails off ("... must be... ") is unfinished (trial 7, BM0015). Only a TRAILING ellipsis
    # counts: "..." inside the text is normal, for example "X1, ..., Xn".
    # An ellipsis right after code ("cv <- function(x) ...", meaning "write the body") is a normal way to
    # show a template to complete (batch BM0063), so it is allowed after ) ( { , = or <- .
    m_end = re.search(r"(\S)\s*(?:\.\.\.|\u2026)\s*$", item["question"])
    if m_end and m_end.group(1) not in ")({,=-" :
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
    # Rule 4: the answer must not appear in the question (batch BM0078 spelled out its own answer).
    if item["answer_type"] in ("r_expression", "short_text"):
        squash = lambda s: re.sub(r"\s+", "", s)
        key_text = squash(item["canonical_answer"])
        if len(key_text) >= 10 and key_text in squash(item["question"]):
            problems.append("the answer key appears word for word inside the question")
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
# Commands (all free: no model call)
# ---------------------------------------------------------------------------------------------
def cmd_plan(args):
    slots = select_slots(args.n, args.start)
    print(f"{'id':<8}{'category':<23}{'difficulty':<14}{'answer type':<17}subtopic")
    for s in slots:
        print(f"{s['item_id']:<8}{s['category']:<23}{s['difficulty']:<14}{s['answer_type']:<17}{s['subtopic']}")
    from collections import Counter
    print("\ncategories:", dict(Counter(s["category"] for s in slots)))
    print("difficulty:", dict(Counter(s["difficulty"] for s in slots)))
    print("answer types:", dict(Counter(s["answer_type"] for s in slots)))


def _question_text(item, mask_digits):
    """The text compared by dupcheck: question plus choices, lower-case, spaces squeezed, optionally with every
    number replaced by # (so "6 coin tosses" and "8 coin tosses" look the same)."""
    text = (item["question"] + " " + " ".join(item.get("choices") or [])).lower()
    if mask_digits:
        text = re.sub(r"\d+(?:\.\d+)?", "#", text)
    return re.sub(r"\s+", " ", text).strip()


def _similarity(a, b):
    """0 to 1 text similarity (1 = identical). The cheap upper bounds skip pairs that cannot reach a high score."""
    from difflib import SequenceMatcher
    m = SequenceMatcher(None, a, b, autojunk=False)
    return m.ratio() if m.real_quick_ratio() > 0.5 and m.quick_ratio() > 0.5 else 0.0


def cmd_dupcheck(args):
    """Free: does any question in --items look like a question in the --against files (earlier trials, the pilot),
    or like another question in the same file? Two scores per pair: with numbers kept (about 1.0 means the same
    question) and with numbers masked (high means the same template with different numbers). Prints a person's
    review list; it never deletes anything."""
    def load(path):
        return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]

    new = load(args.items)
    refs = []
    for pattern in args.against:
        for f in sorted(glob.glob(pattern)):
            if Path(f).resolve() == Path(args.items).resolve():
                continue
            refs += [(Path(f).name.replace("_items.jsonl", ""), r) for r in load(f)]
    print(f"{len(new)} question(s) checked against {len(refs)} earlier question(s) from {len(args.against)} pattern(s).")
    texts = {k: [_question_text(r, k) for r in new] for k in (False, True)}
    ref_texts = {k: [_question_text(r, k) for _, r in refs] for k in (False, True)}
    rows, dups, templates = [], 0, 0
    for i, item in enumerate(new):
        best = {}
        for k in (False, True):
            scored = [(_similarity(texts[k][i], ref_texts[k][j]), j) for j in range(len(refs))]
            best[k] = max(scored, default=(0.0, None))
        (s_keep, j_keep), (s_mask, j_mask) = best[False], best[True]
        is_dup, is_tpl = s_keep >= args.dup, s_mask >= args.template
        dups += is_dup
        templates += is_tpl and not is_dup
        rows.append((s_mask, item["item_id"], s_keep, j_keep, s_mask, j_mask))
        if is_dup or is_tpl:
            j = j_keep if is_dup else j_mask
            src, other = refs[j]
            print(f"{item['item_id']} [{item['subtopic']}] vs {src} {other['item_id']}: same-numbers {s_keep:.2f}, "
                  f"template {s_mask:.2f}  {'DUPLICATE' if is_dup else 'same template'}\n   NEW: {item['question'][:150]!r}"
                  f"\n   OLD: {other['question'][:150]!r}")
    if args.top:
        print(f"\nTop {args.top} closest matches to an earlier question (template score, to calibrate thresholds):")
        for s_mask, iid, s_keep, j_keep, _, j_mask in sorted(rows, reverse=True)[: args.top]:
            src, other = refs[j_mask]
            print(f"  {iid} vs {src} {other['item_id']}: template {s_mask:.2f}, same-numbers {s_keep:.2f}")
    # similar pairs inside the file itself
    inside = []
    for a in range(len(new)):
        for b in range(a + 1, len(new)):
            s = _similarity(texts[True][a], texts[True][b])
            if s >= args.template:
                inside.append((s, new[a]["item_id"], new[b]["item_id"]))
    for s, a, b in sorted(inside, reverse=True):
        print(f"inside the file: {a} and {b} look alike (template score {s:.2f})")
    print(f"\nSummary: {dups} duplicate(s) of an earlier question (same-numbers score >= {args.dup}), "
          f"{templates} more with the same template (>= {args.template}), {len(inside)} similar pair(s) inside the file.")


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
          "the answer keys still need to be verified by running R or recomputing (see docs/methodology/workflow.md Phase 3).")


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
    """Turn one teacher reply into (item, hard_problems, soft_flags). `msg` is any object with `.stop_reason` and
    `.content` (a list of blocks with `.type` and `.text`); open_teacher_test.py builds such a stand-in from each
    cluster reply. hard problems mean "regenerate this question"; soft flags mean "keep it, but a person should look"."""
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
          "code to run (multiple-choice and conceptual items), these need the other checks in docs/methodology/workflow.md Phase 3.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("verify", help="run R to test the answer keys of an items.jsonl file (free)")
    p.add_argument("--items", required=True)
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("check", help="re-run the automatic checks on an items.jsonl file (free)")
    p.add_argument("--items", required=True)
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("plan", help="print the blueprint (free)")
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--start", type=int, default=1, help="first question number to include (21 = start at BM0021)")
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("dupcheck", help="does a new question look like an earlier question? (free)")
    p.add_argument("--items", required=True, help="the items.jsonl to check")
    p.add_argument("--against", required=True, nargs="+", help="earlier items files or glob patterns")
    p.add_argument("--dup", type=float, default=0.80, help="same-numbers similarity that counts as a duplicate")
    p.add_argument("--template", type=float, default=0.80, help="numbers-masked similarity that counts as the same template")
    p.add_argument("--top", type=int, default=0, help="also list the N closest matches (to calibrate the thresholds)")
    p.set_defaults(fn=cmd_dupcheck)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
