"""Tests for code/verification/key_check.py, key_check_schemas.py and the solve kinds of codex_batch.py (plan "five-solver AI
key check", 2026-11-24).

Everything is local: Claude is replaced by fake_claude.py and Codex by ../codex_test/fake_codex.py (through .cmd wrappers on
Windows), so no call reaches Anthropic or OpenAI. The comparison tests run REAL R in the R sandbox (its self-test runs first),
on synthetic questions written for the tests. Workspaces, keys and outputs are temporary folders outside the repository.
Usage: python test_key_check.py"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "code" / "generation"))
sys.path.insert(0, str(REPO / "code" / "verification"))
import generate_benchmark as gb  # noqa: E402
import key_check as kc  # noqa: E402
import key_check_schemas as kcs  # noqa: E402

PY = sys.executable
TOOL = str(REPO / "code" / "verification" / "key_check.py")
CBTOOL = str(REPO / "code" / "verification" / "codex_batch.py")
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {str(detail)[:700]}")


T = Path(tempfile.mkdtemp(prefix="key_check_test_"))
WS, KEYS, LOGS = T / "ws", T / "keys", T / "vlogs"
FAKE = T / "fake_claude.cmd"
FAKE.write_text(f'@echo off\r\n"{PY}" "{HERE / "fake_claude.py"}" %*\r\nexit /b %ERRORLEVEL%\r\n', encoding="ascii")
FAKE_CODEX = T / "fake_codex.cmd"
FAKE_CODEX.write_text(f'@echo off\r\n"{PY}" "{HERE.parent / "codex_test" / "fake_codex.py"}" %*\r\nexit /b %ERRORLEVEL%\r\n',
                      encoding="ascii")
LOG = T / "calls.jsonl"


def tool(*args, env_extra=None, script=TOOL):
    env = {**os.environ, "FAKE_CLAUDE_LOG": str(LOG), "ANTHROPIC_API_KEY": "sk-test-must-never-reach-the-solver",
           "ANTHROPIC_BASE_URL": "http://example.invalid", **(env_extra or {})}
    r = subprocess.run([PY, script, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return r.returncode, r.stdout + r.stderr


man_path = REPO / "data" / "slots" / "benchmark_slots.manifest.json"
man = json.loads(man_path.read_text(encoding="utf-8"))
SECRET = "KEY-THE-SOLVERS-MUST-NOT-SEE"


def bm(k, at, question, key, **item):
    return {"position": k, "item_id": f"BM{k:04d}", "status": "usable", "slot_scheme": "taxonomy-v2",
            "slots_file_sha256": man["slots_sha256"],
            "slot": {"category": "numerical", "subtopic": "test subtopic", "difficulty": "intro"},
            "item": {"question": question, "answer_type": at, "choices": item.pop("choices", []), "canonical_answer": key,
                     "answer_tolerance": item.pop("answer_tolerance", 0), "r_solution": item.pop("r_solution", ""),
                     "r_check": item.pop("r_check", ""), "working": SECRET, "explanation": SECRET, **item}}


items = [bm(1, "number", "X ~ Binomial(2, 0.5). Find P(X <= 1).", "0.75", r_solution="cat(pbinom(1, 2, 0.5))"),
         bm(2, "multiple_choice", "Which is the mean of 1, 2, 3?", "A", choices=["2", "3", "6", "1"]),
         bm(3, "r_expression", "x is a numeric vector. Write an expression for its mean.", "mean(x)",
            r_check=f"x <- c(1, 2, 3); isTRUE(all.equal(eval(parse(text = candidate)), mean(x))) # {SECRET}"),
         bm(4, "short_text", "Name the t-test that does not assume equal variances.", "Welch")]
POS = T / "positions.jsonl"
POS.write_text("".join(json.dumps(r) + "\n" for r in items), encoding="utf-8")
base = ["--workspace", str(WS), "--keys", str(KEYS)]

# ------------------------------------------------------------------ 1. build
print("[1] build: blind batches (no key, working, r_solution, r_check or explanation), three files, key kept apart")
rc, out = tool("build", "--role", "C1", "--positions", str(POS), "--date", "2026-11-24", *base)
b = WS / "2026-11-24_kc-c1_01"
check("the C1 batch is built", rc == 0 and b.exists(), out)
check("the folder holds exactly batch.jsonl, instructions.md and schema.json",
      {p.name for p in b.iterdir()} == {"batch.jsonl", "instructions.md", "schema.json"})
text = (b / "batch.jsonl").read_text(encoding="utf-8")
check("the batch never carries the key, working, explanation, r_solution or r_check",
      SECRET not in text and "pbinom" not in text and "all.equal" not in text and "BM0001" not in text and '"Welch"' not in text,
      text)
check("the batch shows the answer type, category, subtopic, difficulty, question and choices",
      all(f in text for f in ('"answer_type"', '"category"', '"subtopic"', '"difficulty"', '"question"', '"choices"')))
check("the instructions are the approved analytic text",
      (b / "instructions.md").read_text(encoding="utf-8").startswith("You are an expert in statistics"))
key = json.loads((KEYS / "2026-11-24_kc-c1_01_key.json").read_text(encoding="utf-8"))
check("the key file maps anonymous ids to items and records the instruction SHA-256",
      key["ids"]["K-01-001"]["item_id"] == "BM0001" and len(key["instructions_sha256"]) == 64 and not list(WS.rglob("*key*")))
rc, out = tool("build", "--role", "C3", "--positions", str(POS), "--date", "2026-11-24", *base)
c3text = (WS / "2026-11-24_kc-c3_01" / "batch.jsonl").read_text(encoding="utf-8")
check("the C3 batch shows only answer type, question and choices", rc == 0 and '"subtopic"' not in c3text
      and '"question"' in c3text, out)
rc, out = tool("build-variants", "--positions", str(POS), "--date", "2026-11-24", *base)
vtext = (WS / "2026-11-24_kc-variants_01" / "batch.jsonl").read_text(encoding="utf-8")
check("the variants batch holds only the r_expression question, with its key (it is not a blind solver)",
      rc == 0 and vtext.count('"id"') == 1 and '"answer_key": "mean(x)"' in vtext and SECRET not in vtext, out)
bad = T / "bad.jsonl"
bad.write_text(json.dumps({**items[0], "item_id": "DV0001"}) + "\n", encoding="utf-8")
rc, out = tool("build", "--role", "C1", "--positions", str(bad), "--date", "2026-11-24", "--label", "bad", *base)
check("a non-benchmark item is refused", rc != 0 and "not a benchmark item" in out, out)

# ------------------------------------------------------------------ 2. run-claude: isolation and billing
print("[2] run-claude: dry run by default; no ANTHROPIC_* variable ever reaches the solver; subscription login required")
LOG.unlink(missing_ok=True)
rc, out = tool("run-claude", "--batch", str(b), "--claude", str(FAKE))
check("without --real nothing is called", rc == 0 and "Dry run" in out and not LOG.exists(), out)
rc, out = tool("run-claude", "--batch", str(b), "--claude", str(FAKE), "--real")
calls = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines()]
solve = [c for c in calls if "-p" in c["argv"]]
check("the run is accepted", rc == 0 and json.loads((b / "run.json").read_text())["accepted_run"], out)
check("no ANTHROPIC_* variable reaches any CLI call (auth status, version, solve)",
      calls and all(c["anthropic_env"] == [] for c in calls), [c["anthropic_env"] for c in calls])
check("this session's CLAUDECODE / CLAUDE_CODE_* variables are removed too",
      all(not any(n.startswith(("CLAUDECODE", "CLAUDE_CODE_")) for n in c["claude_env"]) for c in calls))
check("the auth status is checked before the solve call", calls[0]["argv"][:2] == ["auth", "status"] and len(solve) == 1)
argv = solve[0]["argv"]
check("the solver gets no tools, no MCP, no settings, no saved session, the schema and the pinned model",
      argv[argv.index("--tools") + 1] == "" and "--strict-mcp-config" in argv and argv[argv.index("--setting-sources") + 1] == ""
      and "--no-session-persistence" in argv and "--json-schema" in argv and argv[argv.index("--model") + 1] == "claude-opus-5-5")
check("the solver runs in the batch folder (outside the repository) and gets the prompt on stdin",
      Path(solve[0]["cwd"]).resolve() == b.resolve() and "<<<BATCH START>>>" in solve[0]["stdin"] and SECRET not in solve[0]["stdin"])
run = json.loads((b / "run.json").read_text())
check("run.json records model, usage, key source 'none', the login method without the e-mail address",
      run["model"] == "fake-claude-1" and run["usage"]["output_tokens"] == 700 and run["api_key_source"] == "none"
      and run["login"].get("authMethod") == "claude.ai" and "email" not in json.dumps(run))


def fresh(tag, role="C1"):
    rc, out = tool("build", "--role", role, "--positions", str(POS), "--date", "2026-11-24", "--label", tag, *base)
    return WS / f"2026-11-24_{tag}_01"


for auth in ("api_key", "logged_out"):
    f = fresh(f"auth-{auth.replace('_', '')}")
    LOG.unlink(missing_ok=True)
    rc, out = tool("run-claude", "--batch", str(f), "--claude", str(FAKE), "--real", env_extra={"FAKE_CLAUDE_AUTH": auth})
    sent = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if "-p" in json.loads(l)["argv"]]
    check(f"login {auth}: refused before any solve call is made", rc != 0 and "REFUSED" in out and not sent, out)
for mode, what in (("api_source", "key source"), ("no_source", "did not report its key source"), ("tool_use", "offered tools"),
                   ("error_result", "error")):
    f = fresh(f"mode-{mode.replace('_', '')}")
    rc, out = tool("run-claude", "--batch", str(f), "--claude", str(FAKE), "--real", env_extra={"FAKE_CLAUDE_MODE": mode})
    rj = json.loads((f / "run.json").read_text())
    check(f"{mode}: the run is rejected", rc == 2 and not rj["accepted_run"] and what in json.dumps(rj["audit_problems"]) +
          str(rj.get("exit_status")), out)
    rc, out = tool("import", "--batch", str(f), "--keys", str(KEYS), "--out-root", str(T / "imp"))
    check(f"{mode}: nothing is imported", rc != 0 and not (T / "imp" / f"mode-{mode.replace('_', '')}").exists(), out)

# ------------------------------------------------------------------ 3. import and validation
print("[3] import: exact format only; results land in the key-check folder")
rc, out = tool("import", "--batch", str(b), "--keys", str(KEYS), "--out-root", str(LOGS / "2026-11-24_key_check_with_codex"))
res = LOGS / "2026-11-24_key_check_with_codex" / "kc-c1" / b.name / "solve_results.jsonl"
check("a valid reply is imported, mapped back to items", rc == 0 and res.exists()
      and json.loads(res.read_text(encoding="utf-8").splitlines()[0])["item_id"] == "BM0001", out)
ids = ["M-01-001", "M-01-002"]
rows = {"M-01-001": {"answer_type": "number"}, "M-01-002": {"answer_type": "r_expression"}}
good = {"answers": [{"id": "M-01-001", "status": "computed", "r_code": "answer <- 1", "answer_expression": "",
                     "test_inputs": [], "correct_options": [], "note": ""},
                    {"id": "M-01-002", "status": "computed", "r_code": "", "answer_expression": "mean(x)",
                     "test_inputs": [{"kind": "question_data", "code": "x <- 1:3"}] * 4, "correct_options": [], "note": ""}]}
_, p = kcs.validate("solve-compute", json.dumps(good), ids, rows)
check("a correct computational reply validates", not p, p)
for name, change, frag in (
        ("computed without r_code", lambda g: g["answers"][0].update(r_code=""), "without r_code"),
        ("r_expression with r_code", lambda g: g["answers"][1].update(r_code="x"), "r_code must be empty"),
        ("fewer than four inputs without a reason", lambda g: g["answers"][1].update(test_inputs=good["answers"][1]["test_inputs"][:2]),
         "fewer than four"),
        ("not_applicable with code", lambda g: g["answers"][0].update(status="not_applicable"), "must be empty"),
        ("unknown status", lambda g: g["answers"][0].update(status="maybe"), "does not match"),
        ("missing id", lambda g: g["answers"].pop(), "missing entries")):
    g = json.loads(json.dumps(good))
    change(g)
    _, p = kcs.validate("solve-compute", json.dumps(g), ids, rows)
    check(f"rejected: {name}", any(frag in x for x in p), p)

# ------------------------------------------------------------------ 4. Codex solve kinds
print("[4] codex_batch.py: the solve kinds build blind batches with the same formats")
rc, out = tool("build-solve-compute", "--items", str(POS), "--manifest", str(man_path), "--date", "2026-11-24", "--label",
               "kc-x2", "--workspace", str(T / "cws"), "--keys", str(T / "ckeys"), script=CBTOOL)
cbatch = T / "cws" / "2026-11-24_kc-x2_01"
ctext = (cbatch / "batch.jsonl").read_text(encoding="utf-8") if cbatch.exists() else ""
check("the Codex X2 batch is built, blind, with the answer type and the compute instructions",
      rc == 0 and '"answer_type": "r_expression"' in ctext and SECRET not in ctext and "pbinom" not in ctext
      and "status" in (cbatch / "schema.json").read_text() and "writing R code" in (cbatch / "instructions.md").read_text(), out)

# ------------------------------------------------------------------ 5. comparison rules (real R in the sandbox)
print("[5] compare: the rules per answer type, with real R in the sandbox")
ok, sb = gb.run_r("cat(1 + 1)", gb.rscript_path())
check("the R sandbox runs", ok and sb.strip() == "2", sb)
RS = gb.rscript_path()
CFG = kc.CFG


def A(ans, opts=(), conf="high"):
    return {"answer": ans, "correct_options": list(opts), "working": "w", "confidence": conf}


def Cn(code, opts=()):
    return {"status": "computed", "r_code": code, "answer_expression": "", "test_inputs": [], "correct_options": list(opts),
            "note": ""}


def Cx(expr, inputs):
    return {"status": "computed", "r_code": "", "answer_expression": expr,
            "test_inputs": [{"kind": k, "code": c} for k, c in inputs], "correct_options": [], "note": ""}


PASS3 = {"verdict": "pass", "issue_type": "none", "reason": "clear"}


def judge(item, c1, x1, c2, x2, c3=PASS3, variants=None, screen=None):
    roles = {"c1": {item["item_id"]: c1}, "x1": {item["item_id"]: x1}, "c2": {item["item_id"]: c2},
             "x2": {item["item_id"]: x2}, "c3": {item["item_id"]: c3},
             "variants": {item["item_id"]: variants} if variants else {}}
    return kc.compare_item(item, roles, screen or {}, set(), RS, CFG, None)


num_ok = bm(11, "number", "q", "0.75", r_solution="cat(pbinom(1, 2, 0.5))")
v = judge(num_ok, A("0.75"), A("0.75"), Cn("answer <- pbinom(1, 2, 0.5)"), Cn("answer <- 1 - 0.5^2"))
check("number: both R programs reproduce the key -> consensus-supported", v["verdict"] == "consensus-supported", v["reasons"])
num_bad = bm(12, "number", "q", "0.5", r_solution="cat(dbinom(1, 2, 0.5))")
v = judge(num_bad, A("0.75"), A("0.75"), Cn("answer <- pbinom(1, 2, 0.5)"), Cn("answer <- 1 - 0.5^2"))
check("number: a wrong key with a MATCHING wrong r_solution is contested as 'likely wrong key'",
      v["verdict"] == "contested" and v["reasons"][0].startswith("likely wrong key") and "0.5 " in v["notes"][0] + " ",
      (v["reasons"], v["notes"]))
v = judge(num_ok, A("0.80"), A("0.75"), Cn("answer <- pbinom(1, 2, 0.5)"), Cn("answer <- 1 - 0.5^2"))
check("number: an analytic solver that gives a different value makes it contested",
      v["verdict"] == "contested" and any("C1 (analytic)" in r for r in v["reasons"]), v["reasons"])
v = judge(bm(13, "number", "q", "0.94", answer_tolerance=0.005), A("0.9409"), A("0.94"), Cn("answer <- 0.940869"),
          Cn("answer <- 0.9412"))
check("number: unrounded R values within the key's rounding are accepted", v["verdict"] == "consensus-supported", v["reasons"])

mc = bm(21, "multiple_choice", "q", "A", choices=["2", "3", "6", "1"])
mcc = "value <- mean(c(1, 2, 3)); opts <- c(A = 2, B = 3, C = 6, D = 1); answer <- names(opts)[opts == value]"
v = judge(mc, A("A", "A"), A("A", "A"), Cn(mcc, "A"), Cn(mcc, "A"))
check("multiple choice: computed letters agree with the key -> consensus-supported",
      v["verdict"] == "consensus-supported" and "computed (C2, X2)" in v["notes"][-1], (v["reasons"], v["notes"]))
v = judge(mc, A("A", "AC"), A("A", "A"), Cn(mcc, "A"), Cn(mcc, "A"))
check("multiple choice: a solver marking a second option correct makes it contested",
      v["verdict"] == "contested" and any("also marks C" in r for r in v["reasons"]), v["reasons"])
v = judge(mc, A("A", "A"), A("A", "A"), Cn('answer <- "A"', "A"), Cn('answer <- "A"', "A"))
check("multiple choice: a hardcoded letter is not counted as computation (the analytic pair decides)",
      "analytic (C1, X1)" in v["notes"][-1] and any("not supported by a computed value" in n for n in v["notes"]), v["notes"])
v = judge(mc, A("B", "B"), A("A", "A"), Cn(mcc, "A"), Cn(mcc, "A"))
check("multiple choice: an analytic solver contradicting the computed pair makes it contested",
      v["verdict"] == "contested" and any("C1 answers B" in r for r in v["reasons"]), v["reasons"])

st = bm(31, "short_text", "q", "Welch")
NA_ = {"status": "not_applicable", "r_code": "", "answer_expression": "", "test_inputs": [], "correct_options": [],
       "note": "conceptual"}
v = judge(st, A("welch."), A(" Welch"), NA_, NA_)
check("short text: normalized matches -> consensus-supported", v["verdict"] == "consensus-supported", v["reasons"])
v = judge(st, A("Student"), A("Welch"), *[{"status": "not_applicable", "r_code": "", "answer_expression": "", "test_inputs": [],
                                           "correct_options": [], "note": "c"}] * 2)
check("short text: a different answer is contested", v["verdict"] == "contested", v["reasons"])
v = judge(st, A("Welch"), A("Welch"), *[{"status": "not_applicable", "r_code": "", "answer_expression": "", "test_inputs": [],
                                         "correct_options": [], "note": "c"}] * 2,
          c3={"verdict": "flag", "issue_type": "ambiguous", "reason": "two readings"})
check("every type: a C3 flag makes it contested", v["verdict"] == "contested" and any("C3 flags" in r for r in v["reasons"]))

INP = [("question_data", "x <- c(1, 2, 3)"), ("variation", "set.seed(1); x <- rexp(10)"),
       ("variation", "set.seed(2); x <- runif(7)"), ("edge", "x <- c(5, 5, 5, 0)")]
GOODV = {"key_concern": "", "variants": [
    {"expression": "median(x)", "what_is_wrong": "median not mean", "counterexample": "x <- c(1, 2, 10)"},
    {"expression": "sum(x) / (length(x) - 1)", "what_is_wrong": "n - 1", "counterexample": "x <- c(1, 2, 3)"},
    {"expression": "max(x)", "what_is_wrong": "max", "counterexample": "x <- c(1, 2)"}]}
rx = bm(41, "r_expression", "x is a numeric vector; give its mean.", "mean(x)",
        r_check="x <- c(1, 2, 3); isTRUE(all.equal(eval(parse(text = candidate)), mean(x)))")
v = judge(rx, A("sum(x)/length(x)"), A("mean(x)"), Cx("mean(x)", INP), Cx("sum(x) / length(x)", INP), variants=GOODV)
check("r_expression: equivalent expressions on every input -> consensus-supported",
      v["verdict"] == "consensus-supported", (v["reasons"], v["check_flags"]))
check("r_expression: the r_check's single data set accepts median(x) (equal on 1, 2, 3): reported as a generalization "
      "limit, apart from question-data failures",
      any(f.startswith("generalization limit") and "median" in f for f in v["check_flags"])
      and not any(f.startswith("check too loose") for f in v["check_flags"]), v["check_flags"])
vr = {x["variant"]: x["class"] for x in v["harness"]["variants"]}
check("r_expression: the harness (not the agent) classifies the variants: median wrong only in generalization, n - 1 wrong "
      "on the question data", vr.get(1) == "wrong only in generalization" and vr.get(2) == "wrong on the question data", vr)
check("r_expression: each variant's own counterexample is run and shows the difference",
      all(x["own_counterexample_shows_difference"] for x in v["harness"]["variants"]), v["harness"]["variants"])
v = judge(rx, A("mean(x)"), A("mean(x)"), Cx("median(x)", INP), Cx("mean(x)", INP), variants=GOODV)
check("r_expression (a): a solver that matches the key only on the question's data is caught on other inputs",
      v["verdict"] == "contested" and any("possible coincidental match" in r and "C2" in r for r in v["reasons"]), v["reasons"])
strict = bm(42, "r_expression", "x is a numeric vector; give its mean.", "sum(x)/length(x)",
            r_check='identical(gsub(" ", "", candidate), "sum(x)/length(x)")')
v = judge(strict, A("sum(x)/length(x)"), A("sum(x)/length(x)"), Cx("mean(x)", INP), Cx("sum(x)/length(x)", INP),
          variants=GOODV)
check("r_expression (b): an equivalent expression rejected by a too-strict r_check: key supported, check flagged",
      v["verdict"] == "consensus-supported" and any(f.startswith("check too strict") and "C2" in f for f in v["check_flags"]),
      (v["reasons"], v["check_flags"]))
loose = bm(43, "r_expression", "x is a numeric vector; give its mean.", "mean(x)", r_check="is.numeric(eval(parse(text = "
           "candidate), envir = list(x = c(1, 2, 3))))")
v = judge(loose, A("mean(x)"), A("mean(x)"), Cx("mean(x)", INP), Cx("mean(x)", INP), variants=GOODV)
check("r_expression (c): an r_check that accepts a variant wrong on the question data is flagged 'too loose'",
      any(f.startswith("check too loose") and "wrong on the question data" in f for f in v["check_flags"]), v["check_flags"])
MINP = [("question_data", "m <- matrix(1:6, 2, dimnames = list(NULL, c('a', 'b', 'c')))"),
        ("variation", "set.seed(3); m <- matrix(rnorm(12), 3, dimnames = list(NULL, c('a', 'b', 'c', 'd')))"),
        ("variation", "m <- matrix(c(2, 4, 6, 8), 2, dimnames = list(NULL, c('u', 'v')))"),
        ("edge", "m <- matrix(7, 1, 1, dimnames = list(NULL, 'z'))")]
form = bm(44, "r_expression", "m is a numeric matrix with column names; give the column means.", "colMeans(m)",
          r_check="m <- matrix(1:6, 2, dimnames = list(NULL, c('a','b','c'))); identical(eval(parse(text = candidate)), "
                  "colMeans(m))")
v = judge(form, A("colMeans(m)"), A("colMeans(m)"), Cx("unname(colMeans(m))", MINP), Cx("colMeans(m)", MINP),
          variants={"key_concern": "", "variants": [
              {"expression": "rowMeans(m)", "what_is_wrong": "rows", "counterexample": "m <- matrix(1:4, 2, dimnames = list(NULL, c('a','b')))"},
              {"expression": "colSums(m)", "what_is_wrong": "sums", "counterexample": "m <- matrix(1:4, 2, dimnames = list(NULL, c('a','b')))"},
              {"expression": "apply(m, 2, median)", "what_is_wrong": "median", "counterexample": "m <- matrix(c(1, 2, 9), 3, dimnames = list(NULL, 'a'))"}]})
check("r_expression (d): same values with a different form is reported separately, for Jaxson to decide",
      v["verdict"] == "contested" and any(r.startswith("same values, different form: C2") for r in v["reasons"])
      and any("same values, different form" in n for n in v["notes"]), (v["reasons"], v["notes"]))
wrongkey = bm(45, "r_expression", "x is a numeric vector; give its sample variance.", "mean((x - mean(x))^2)",
              r_check="x <- c(1, 2, 3); isTRUE(all.equal(eval(parse(text = candidate)), mean((x - mean(x))^2)))")
v = judge(wrongkey, A("var(x)"), A("var(x)"), Cx("var(x)", INP), Cx("sum((x - mean(x))^2) / (length(x) - 1)", INP),
          variants=GOODV)
check("r_expression: when C2 and X2 agree with each other and not with the key -> 'likely wrong key'",
      v["verdict"] == "contested" and v["reasons"][0].startswith("likely wrong key"), v["reasons"])
v = judge(rx, A("mean(x)"), A("mean(x)"), Cx("mean(x)", INP), Cx("mean(x)", INP),
          variants={**GOODV, "key_concern": "the key ignores missing values the question mentions"})
check("r_expression: a key concern from the variants agent sends the question to Jaxson",
      v["verdict"] == "contested" and any("suspects the key" in r for r in v["reasons"]), v["reasons"])
v = judge(rx, A("mean(x)"), A("mean(x)"), Cx("mean(x)", INP[:2]), Cx("mean(x)", INP[:1]), variants=GOODV)
check("r_expression: few inputs are accepted when both solvers say the question fixes its data",
      v["verdict"] == "consensus-supported" and any("fixes its data" in n for n in v["notes"]), (v["reasons"], v["notes"]))
v = judge(rx, A("mean(x)"), A("mean(x)"), Cx("mean(x)", INP + [("variation", "y <- 1")]), Cx("mean(x)", INP),
          variants=GOODV)
check("r_expression: an input on which the key errors is not counted (outside the question's scope)",
      v["verdict"] == "consensus-supported" and any("not counted" in n and "[5]" in n for n in v["notes"]),
      (v["reasons"], v["notes"]))
miss = kc.compare_item(num_ok, {"c1": {}, "x1": {}, "c2": {}, "x2": {}, "c3": {}, "variants": {}}, {}, set(), RS, CFG, None)
check("a question without solver results is 'incomplete', never consensus-supported", miss["verdict"] == "incomplete",
      miss["verdict"])
check("the word 'confirmed' is never a verdict", "confirmed" not in json.dumps([v["verdict"], miss["verdict"]]))

print(f"\n==== key check tests: {passed} passed, {failed} failed ====")
sys.exit(1 if failed else 0)
