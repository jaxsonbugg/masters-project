"""
set_prompts.py - the two generation prompts used from 2026-11-19 on (benchmark v7 and training v1): reading them,
building the request for one slot, and the format checks on a reply. Shared by generate_set.py (the generator) and
the tests, so the prompt text and the checks are defined in exactly one place.

WHAT THIS IS AND WHY
The full-size generator writes three kinds of material from frozen slot files (code/generation/variety.py):
  - BENCHMARK-STYLE items (the benchmark BM, the development set DV, smoke SM) with data/prompts/benchmark_generation_v7.md:
    an exam question plus an answer KEY and R code that recomputes or checks it;
  - TRAINING examples (TR, TRR, and the held-out training-style set TV) with data/prompts/training_generation_v1.md:
    a question plus a short worked answer and a final answer, the material the students learn from.
generate_benchmark.py (v6, the archived trials and the deployment tests) is NOT changed; its checks are reused here
and only tightened where the approved plan says so, so the regression snapshot of v6 stays exactly as it was.

WHAT IS NEW COMPARED WITH v6 (and why)
  1. The "Setting:" line. Each slot carries a context card (a real-world setting, or "none"). Its two wordings are
     sections of the prompt file (<<<SETTING context>>> and <<<SETTING none>>>), so the prompt's SHA-256 covers them.
  2. Benchmark v7 replies MUST contain `working` and `r_solution` (decided 2026-11-11). v6's legacy path, which
     checked a reply without them more loosely, is not used for v7.
  3. The "No:" false alarm is fixed (Talon Stage T, BM9115: a table row labeled "No:" was read as the model thinking
     aloud). Only a lowercase "no:" in the middle of a sentence ("... must be... no: exactly 2 ...") counts now.
  4. Training replies get their own format checks (no correctness checks; workflow.md Section 4, safeguard 9), and
     their text is assembled into the exact Question:/Answer:/Final answer: template the students see.

EXAMPLE (a training slot): numerical / "binomial probability" / intro / number / context "sports". The user message
ends with
    Setting: sports, athletes, teams, game scores, training times or season statistics. Use this setting ...
and an accepted reply becomes the training text
    Question: A basketball player makes 70% of her free throws. ... Give your answer to 3 decimal places.
    Answer: The number of made shots is binomial with n = 5 and p = 0.7.
    P(X = 4) = 5 x 0.7^4 x 0.3 = 0.36015.
    Final answer: 0.360
followed by Pythia's end-of-text token (id 0), at most 2,048 tokens in all.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_benchmark as gb  # noqa: E402  (v6 checks reused unchanged; the regression snapshot covers them)

REPO = gb.REPO
PROMPTS = {
    # kind: (prompt file, version label, item-id kinds the prompt may be used for)
    "benchmark": (REPO / "data" / "prompts" / "benchmark_generation_v7.md", "benchmark-v7", ("BM", "DV", "SM")),
    "training": (REPO / "data" / "prompts" / "training_generation_v1.md", "training-v1", ("TR", "TRR", "TV", "SM")),
}
SCHEMA_BLOCK_HEADER = "Output schema (JSON Schema):"   # the same adapter as open_teacher_test.py (schema sent as text)
NONE = "none"
MAX_TRAINING_TOKENS = 2048                             # Pythia's context length; the assembled example must fit
EOS_ID = 0                                             # Pythia's end-of-text token, appended to every example

# The benchmark v7 reply has exactly v6's fields (gb.ITEM_SCHEMA), all of them required.
BENCHMARK_SCHEMA = gb.ITEM_SCHEMA

# The training reply. The ORDER matters: the model writes top to bottom, so the worked answer comes before the final
# answer. r_solution is stored for later analysis and never checked (safeguard 9).
TRAINING_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "choices": {"type": "array", "items": {"type": "string"}},
        "answer_type": {"type": "string", "enum": ["number", "multiple_choice", "r_expression", "short_text"]},
        "worked_answer": {"type": "string"},
        "final_answer": {"type": "string"},
        "category": {"type": "string", "enum": ["numerical", "conceptual", "r_generation", "r_interpretation", "output_interpretation"]},
        "subtopic": {"type": "string"},
        "difficulty": {"type": "string", "enum": ["intro", "intermediate", "graduate"]},
        "context": {"type": "string"},
        "r_solution": {"type": "string"},
    },
    "required": ["question", "choices", "answer_type", "worked_answer", "final_answer", "category", "subtopic",
                 "difficulty", "context", "r_solution"],
    "additionalProperties": False,
}


def schema_for(kind):
    return {"benchmark": BENCHMARK_SCHEMA, "training": TRAINING_SCHEMA}[kind]


# ---------------------------------------------------------------------------------------------
# Prompt files
# ---------------------------------------------------------------------------------------------
def load_prompt(kind):
    """(sections, sha256, version label) of a prompt file. Sections are keyed (MARKER, name), as in generate_benchmark.
    The SHA-256 is of the file's bytes, exactly what configs/talon/prep_talon.sh pins with sha256sum."""
    path, version, _ = PROMPTS[kind]
    raw = path.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")
    sections, key, buf = {}, None, []
    for line in text.split("\n"):
        m = re.match(r"^<<<([A-Z]+)(?: ([a-z_]+))?>>>\s*$", line)
        if m:
            if key is not None:
                sections[key] = "\n".join(buf).strip()
            key = (m.group(1), m.group(2))
            buf = []
        elif key is not None:
            buf.append(line)
    for need in [("SYSTEM", None), ("USER", None), ("SETTING", "context"), ("SETTING", "none")]:
        if need not in sections:
            raise ValueError(f"{path.name} has no section {need}")
    return sections, hashlib.sha256(raw).hexdigest(), version


def id_kind(item_id):
    """'BM', 'DV', 'TV', 'SM', 'TR' or 'TRR' for a new-scheme id, or None."""
    m = re.fullmatch(r"(BM|DV|TV|SM)\d{4}|(TRR|TR)\d{6}", item_id or "")
    if not m:
        return None
    return m.group(1) or m.group(2)


def setting_text(slot, prompt):
    if slot["context"] == NONE:
        return prompt[("SETTING", "none")]
    return prompt[("SETTING", "context")].format(context_name=slot["context"], context_description=slot["context_text"])


def build_request(slot, prompt, kind):
    """The system text and the user message for one slot (before the schema block is appended)."""
    if slot.get("slot_scheme") != "taxonomy-v2":
        raise ValueError(f"{slot.get('item_id')}: not a taxonomy-v2 slot; v7 and training v1 need a frozen slot file")
    if id_kind(slot["item_id"]) not in PROMPTS[kind][2]:
        raise ValueError(f"{slot['item_id']}: a {kind} prompt may not be used for this id")
    letter = slot.get("preferred_letter") or "any letter"
    user = prompt[("USER", None)].format(
        item_id=slot["item_id"], category=slot["category"], category_text=prompt[("CAT", slot["category"])],
        subtopic=slot["subtopic"], difficulty=slot["difficulty"], difficulty_text=prompt[("DIFF", slot["difficulty"])],
        answer_type=slot["answer_type"],
        answer_type_text=prompt[("TYPE", slot["answer_type"])].format(preferred_letter=letter),
        setting_text=setting_text(slot, prompt), context=slot["context"],
    )
    return {"system": prompt[("SYSTEM", None)], "messages": [{"role": "user", "content": user}]}


def build_messages(slot, prompt, kind):
    """Chat messages exactly as sent: the schema JSON appended to the system text (the servers do not enforce a schema,
    and forcing JSON while the model thinks is unreliable; open_teacher_test.py explains this adapter)."""
    req = build_request(slot, prompt, kind)
    system = req["system"] + "\n\n" + SCHEMA_BLOCK_HEADER + "\n" + json.dumps(schema_for(kind))
    return [{"role": "system", "content": system}, {"role": "user", "content": req["messages"][0]["content"]}]


# ---------------------------------------------------------------------------------------------
# Thinking-aloud markers (the "No:" fix)
# ---------------------------------------------------------------------------------------------
# v6's list (generate_benchmark.check_item) without its case-insensitive `\bno:`, which matched a table row labeled
# "No:" (Talon Stage T, BM9115). "no:" now counts only in lowercase, after a lowercase word or punctuation and a space,
# in the middle of a sentence: "... must be... no: exactly 2 statisticians" still counts; "Yes: 14\nNo: 9" does not.
_MARKERS_CI = re.compile(r"\bwait\s*[,.:!—-]|[.!?]\s+wait\b|\bhmm\b|\bsorry\b|\blet me\b|\boops\b|"
                         r"\.\.\.\s*(no|wait|hmm)\b|(?:^|[.!?]\s+|\n\s*)actually,|\bto keep it simple\b|"
                         r"\bon second thought\b|\bscratch that\b", re.I)
_LOWER_NO = re.compile(r"(?<=[a-z,;.)] )no:")
# In a worked answer "Let me define X" is ordinary tutoring language, so only self-corrections count there.
_WORKED_MARKERS = re.compile(r"\bwait\s*[,.:!—-]|[.!?]\s+wait\b|\bhmm\b|\boops\b|\bsorry\b|"
                             r"(?:^|[.!?]\s+|\n\s*)actually,|\bon second thought\b|\bscratch that\b|"
                             r"\blet me (?:re-?check|recheck|reconsider|redo|re-?do|try again|think again|correct)\b|"
                             r"\bi made (?:a|an) (?:mistake|error)\b", re.I)
SELF_CORRECTION = "question text looks unfinished or self-correcting"


def thinking_aloud(text):
    """The first marker of a model thinking aloud in question text, or None."""
    m = _MARKERS_CI.search(text) or _LOWER_NO.search(text)
    return m.group(0) if m else None


# ---------------------------------------------------------------------------------------------
# Benchmark v7 checks
# ---------------------------------------------------------------------------------------------
def check_benchmark_item(item, slot, finish_reason="stop", r_keyed=True):
    """Hard problems of one benchmark-v7 reply (empty list = usable). v6's checks, plus: `working` and `r_solution`
    are required, and the thinking-aloud test uses the "No:" fix."""
    problems = []
    if finish_reason == "length":
        problems.append("cut off at max_tokens")
    for k in BENCHMARK_SCHEMA["required"]:
        if k not in item:
            problems.append(f"missing field {k}")
    if any(p.startswith("missing field") for p in problems):
        return problems
    for k in ("question", "working", "r_solution", "canonical_answer", "r_check", "explanation", "subtopic"):
        if not isinstance(item[k], str):
            return problems + [f"field {k} is not text"]
    if not isinstance(item["choices"], list) or not all(isinstance(c, str) for c in item["choices"]):
        return problems + ["choices is not a list of text"]
    if not isinstance(item["answer_tolerance"], (int, float)) or isinstance(item["answer_tolerance"], bool):
        return problems + ["answer_tolerance is not a number"]
    v6 = gb.check_item(item, slot, "max_tokens" if finish_reason == "length" else "end_turn", r_keyed=r_keyed)
    for p in v6:
        if p.startswith(SELF_CORRECTION) or p == "cut off at max_tokens":
            continue                                   # replaced below by the fixed marker test / already recorded
        problems.append(p)
    marker = thinking_aloud(item["question"] + " " + " ".join(item["choices"]))
    if marker:
        problems.append(f"{SELF_CORRECTION} (found {marker!r})")
    if not item["working"].strip():
        problems.append("empty working")
    return problems


# ---------------------------------------------------------------------------------------------
# Training v1 checks and the student text
# ---------------------------------------------------------------------------------------------
_LETTER_LABEL = re.compile(r"^\s*\(?[A-Da-d][.):]\s")
_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")


def check_training_item(item, slot, finish_reason="stop"):
    """Hard problems of one training-v1 reply (empty list = usable). FORMAT ONLY: nothing here judges whether the answer
    is correct (workflow.md Section 4, safeguard 9). The length limit is checked later, with the Pythia tokenizer
    (training_tokens), because the cluster job does not load a tokenizer."""
    problems = []
    if finish_reason == "length":
        problems.append("cut off at max_tokens")
    for k in TRAINING_SCHEMA["required"]:
        if k not in item:
            problems.append(f"missing field {k}")
    if any(p.startswith("missing field") for p in problems):
        return problems
    extra = sorted(set(item) - set(TRAINING_SCHEMA["properties"]))
    if extra:
        problems.append(f"unexpected field(s) {extra}")
    for k in ("question", "answer_type", "worked_answer", "final_answer", "category", "subtopic", "difficulty",
              "context", "r_solution"):
        if not isinstance(item[k], str):
            return problems + [f"field {k} is not text"]
    if not isinstance(item["choices"], list) or not all(isinstance(c, str) for c in item["choices"]):
        return problems + ["choices is not a list of text"]
    for k in ("category", "subtopic", "difficulty", "answer_type", "context"):
        if item[k] != slot[k]:
            problems.append(f"{k} differs from the slot ({item[k]!r} vs {slot[k]!r})")
    q, w, fa = item["question"].strip(), item["worked_answer"].strip(), item["final_answer"].strip()
    if not q:
        problems.append("empty question")
    if not w:
        problems.append("empty worked_answer")
    if not fa:
        problems.append("empty final_answer")
    marker = thinking_aloud(item["question"] + " " + " ".join(item["choices"]))
    if marker:
        problems.append(f"{SELF_CORRECTION} (found {marker!r})")
    if re.search(r"(\S)\s*(?:\.\.\.|…)\s*$", q) and re.search(r"(\S)\s*(?:\.\.\.|…)\s*$", q).group(1) not in ")({,=-":
        problems.append("question text ends with an ellipsis, so it looks unfinished")
    m = _WORKED_MARKERS.search(w)
    if m:
        problems.append(f"worked_answer thinks aloud or corrects itself (found {m.group(0)!r})")
    if re.search(r"final\s+answer", w, re.I):
        problems.append("worked_answer contains the words 'final answer' (the final answer has its own line)")
    if "```" in w or re.search(r"^\s*#{1,6}\s", w, re.M):
        problems.append("worked_answer uses markdown (a code fence or a heading)")
    if "\n" in fa:
        problems.append("final_answer has more than one line")
    if len(fa) > 100:
        problems.append("final_answer longer than about 20 tokens")
    if "`" in fa:
        problems.append("final_answer contains backticks")
    at = item["answer_type"]
    if at == "multiple_choice":
        if len(item["choices"]) != 4:
            problems.append("multiple choice without exactly 4 choices")
        elif len({c.strip().lower() for c in item["choices"]}) != 4:
            problems.append("multiple choice with repeated choices")
        if any(_LETTER_LABEL.match(c) for c in item["choices"]):
            problems.append("a choice starts with a letter label (the code adds A. to D.)")
        if fa not in list("ABCD"):
            problems.append("multiple choice final_answer is not a letter A-D")
    elif item["choices"]:
        problems.append("choices given for a non-multiple-choice item")
    if at == "number":
        plain = fa.replace(",", "")
        if not _NUMBER.match(plain):
            problems.append("number final_answer is not a plain number")
        else:
            d = gb.stated_decimals(q)
            got = len(plain.split(".")[1]) if "." in plain else 0
            if d is not None and got != d:
                problems.append(f"the question asks for {d} decimal place(s) but the final answer has {got}")
    return problems


def training_text(item):
    """The text a student trains on, without the end-of-text token (added as id 0 when tokenizing):
        Question: <question>
        A. <choice> ... D. <choice>      (multiple choice only)
        Answer: <worked answer>
        Final answer: <final answer>"""
    lines = ["Question: " + item["question"].strip()]
    if item["answer_type"] == "multiple_choice":
        lines += [f"{letter}. {c.strip()}" for letter, c in zip("ABCD", item["choices"])]
    lines.append("Answer: " + item["worked_answer"].strip())
    lines.append("Final answer: " + item["final_answer"].strip())
    return "\n".join(lines)


def pythia_tokenizer_path():
    """tokenizer.json of the pinned Pythia 70M checkpoint (the four sizes share one tokenizer)."""
    import yaml
    p = yaml.safe_load((REPO / "configs" / "paths.yaml").read_text())
    return Path(p["models_pythia"]) / "pythia-70m-deduped" / "step143000" / "tokenizer.json"


class TrainingLength:
    """Counts the tokens of an assembled example with the pinned Pythia tokenizer, end-of-text token included."""

    def __init__(self, tokenizer_file=None):
        from tokenizers import Tokenizer
        self.path = Path(tokenizer_file or pythia_tokenizer_path())
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.tok = Tokenizer.from_file(str(self.path))

    def count(self, text):
        return len(self.tok.encode(text, add_special_tokens=False).ids) + 1     # + the end-of-text token (id 0)

    def check(self, text, limit=MAX_TRAINING_TOKENS):
        n = self.count(text)
        return n, (None if n <= limit else f"assembled example is {n} tokens, above the {limit}-token limit")
