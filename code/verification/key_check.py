"""
key_check.py - the five-solver AI key check of the benchmark (plan "five-solver AI key check", approved by Jaxson 2026-11-24;
docs/methodology/workflow.md Section 4, safeguard 6d).

WHAT THIS IS AND WHY
Every benchmark question has an answer key written by Qwen. R already re-checks number keys (through Qwen's own r_solution)
and R-code keys (through Qwen's own r_check), and Codex screened every question for clarity without seeing keys. Three kinds
of wrong key could still pass: a wrong multiple-choice or short-text key on a clear question; a number key whose r_solution
computes the wrong quantity (key and code share the mistake); and an R-code key whose r_check, tested on one data set only,
accepts wrong code that happens to give the same output there, or rejects a different but equivalent correct answer.
So five independent solvers that never see the key answer every question, and code compares their answers with the key:

  C1 Claude, analytic     C2 Claude, computational (writes R; our sandbox runs it)     C3 Claude, ambiguity read
  X1 Codex, analytic      X2 Codex, computational (writes R; our sandbox runs it)      the existing Codex screen

Two helper agents see the key and never vote: the VARIANTS agent writes plausible wrong R answers (with a counterexample each)
for the r_expression questions, to test the r_checks; the ADJUDICATOR writes a short brief for each contested question.

HOW A QUESTION IS JUDGED (by code, `compare`; the rules per type are in workflow.md safeguard 6d)
  number          C2 and X2 must both reproduce the key within its tolerance, and C1 and X1 must not give a different value.
  multiple choice C2 and X2 decide when the options can be computed (their code must compute the result, not just name a
                  letter); otherwise C1 and X1 decide. No solver may mark a second option correct.
  r_expression    an equivalence harness runs the key and every solver's expression on many inputs (the question's data, two
                  or more variations and an edge case, written blind by C2 and X2), compares outputs strictly (class,
                  dimensions, names, values) and by values only, and runs the r_check on the key, the solvers and the
                  known-wrong variants. The r_check is supporting evidence only: a check that rejects an equivalent answer
                  ("too strict") or accepts a wrong one ("too loose") is flagged for Jaxson.
  short text      C1 and X1 (and C2, X2 when they computed) must match the key after normalization.
  every question  a flag from C3 or the Codex screen sends it to Jaxson.
A question that passes every rule is "consensus-supported" (never "confirmed" or "verified": agreement of models is evidence,
not proof; the claim about key accuracy comes from Jaxson's audit). Otherwise it is "contested" and goes to Jaxson with a
brief. No model writes or changes a key; Jaxson decides every change.

ISOLATION AND BILLING
Claude solvers run like Codex: one CLI process per batch, in a folder outside the repository, with NO tools (--tools ""), no
MCP servers, no settings files and no saved session; the event stream is audited and a batch is rejected if anything but the
final answer appears. The prompt holds everything; nothing is read from disk. A real call happens only with --real, after
Jaxson's approval.
The Anthropic API (API-key billing) is NEVER used (Jaxson's rule, 2026-11-24). Three layers enforce it:
  1. every ANTHROPIC_* variable (the API key among them) is removed from the solver's environment; there is no option to
     pass one;
  2. before any call, `claude auth status` (a local check) must show a subscription login and no API key, or nothing is sent;
  3. after a run, the event stream's reported key source must be "none", or the batch is rejected.
Every model-written R runs only in the R sandbox (generate_benchmark.run_r).

THE STEPS
  pilot-ids      a seeded, stratified 25-question pilot list (every answer type)
  build          Claude batches for C1, C2, C3 (--role); Codex batches are built with codex_batch.py build-solve-*
  build-variants batches for the variants agent (r_expression questions; shows question and key)
  run-claude     run one Claude batch (dry run unless --real)
  import         validate a Claude batch reply and copy it to data/verification_logs/<date>_key_check_with_codex/<label>/
  compare        run all solver R in the sandbox, apply the rules, write verdicts.jsonl and summary.json
  build-briefs   batches for the adjudicator (contested questions; shows everything)
  review         key_check_review.csv for Jaxson (contested and check-flagged questions, with briefs)
  audit-merge    the audit sheet with the key-check evidence added (a new file; the original is never changed)
  usage          token totals of the Claude runs (for docs/logs/cost_log.md: subscription usage)

EXAMPLE
  python key_check.py build --role C1 --positions <positions.jsonl> --only pilot_ids.txt --date 2026-11-24
  python key_check.py run-claude --batch <key_check_workspace>/2026-11-24_kc-c1_01            (dry run)
  python key_check.py run-claude --batch <key_check_workspace>/2026-11-24_kc-c1_01 --real     (only with approval)
  python key_check.py import --batch <key_check_workspace>/2026-11-24_kc-c1_01
  python key_check.py compare --positions <positions.jsonl> --date 2026-11-24 --allow-incomplete
"""
import argparse
import collections
import concurrent.futures
import csv
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "code" / "generation"))
sys.path.insert(0, str(REPO / "code" / "verification"))
import codex_batch as cb  # noqa: E402
import generate_benchmark as gb  # noqa: E402
import key_check_schemas as kcs  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TOOL_VERSION = "key_check-1"
CFG = yaml.safe_load((REPO / "configs" / "key_check.yaml").read_text(encoding="utf-8"))
LOGS = REPO / "data" / "verification_logs"
ROLE_KIND = {"C1": "solve-analytic", "C2": "solve-compute", "C3": "ambiguity"}
SHOWN = {"solve-analytic": ("answer_type", "category", "subtopic", "difficulty", "question", "choices"),
         "solve-compute": ("answer_type", "category", "subtopic", "difficulty", "question", "choices"),
         "ambiguity": ("answer_type", "question", "choices")}
SYSTEM_PROMPT = ("You are a careful expert in statistics and in the R programming language. Follow the user's instructions "
                 "exactly and reply only in the required JSON format.")
ALLOWED_CLAUDE_TOOLS = {"StructuredOutput"}  # how the CLI returns --json-schema output; any other tool rejects the batch
# Removed from every solver's environment: this session's own variables (so the solver is a fresh, separate process) and
# EVERY ANTHROPIC_* variable (so the API key can never be used; Jaxson's rule, 2026-11-24).
STRIP_ENV_PREFIXES = ("ANTHROPIC_", "CLAUDECODE", "CLAUDE_CODE_", "CLAUDE_AGENT_SDK", "CLAUDE_PID", "CLAUDE_EFFORT")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def write_jsonl(p, rows):
    Path(p).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")


def kc_paths():
    p = yaml.safe_load((REPO / "configs" / "paths.yaml").read_text())
    for k in ("key_check_workspace", "key_check_keys", "claude_cli", "benchmark_work"):
        if not p.get(k):
            sys.exit(f"{k} is not set in configs/paths.yaml")
    return Path(p["key_check_workspace"]), Path(p["key_check_keys"]), Path(p["claude_cli"]), Path(p["benchmark_work"])


# =============================================================================================
# building batches
# =============================================================================================
def shown_row(r, fields):
    it, sl = r["item"], r.get("slot") or {}
    full = {"question": it["question"], "choices": {L: c for L, c in zip("ABCD", it.get("choices") or [])},
            "answer_type": it.get("answer_type"), "category": sl.get("category"), "subtopic": sl.get("subtopic"),
            "difficulty": sl.get("difficulty")}
    return {f: full[f] for f in fields}


def write_batches(rows, shown_fn, kind, label, date, batch_size, workspace, keys, source, role=None):
    """One folder per batch with exactly batch.jsonl, instructions.md and schema.json (the Codex layout), and a key file in
    the separate key folder. `shown_fn(row)` gives what the agent may see for that question."""
    instr_path, schema_fn, _, letter = kcs.KINDS[kind]
    instr, instr_sha = cb.instructions_text(instr_path)
    made = []
    for b in range(0, len(rows), batch_size):
        nn = len(list(workspace.glob(f"{date}_{label}_*"))) + 1
        name = f"{date}_{label}_{nn:02d}"
        folder = workspace / name
        if folder.exists():
            sys.exit(f"{folder} exists; batches are never overwritten")
        folder.mkdir(parents=True)
        lines, key = [], {}
        for k, r in enumerate(rows[b:b + batch_size], 1):
            anon = f"{letter}-{nn:02d}-{k:03d}"
            lines.append(json.dumps({"id": anon, **shown_fn(r)}, ensure_ascii=False))
            key[anon] = {"item_id": r["item_id"], "position": r.get("position")}
        text = "\n".join(lines) + "\n"
        (folder / "batch.jsonl").write_text(text, encoding="utf-8", newline="\n")
        (folder / "instructions.md").write_text(instr, encoding="utf-8", newline="\n")
        (folder / "schema.json").write_text(json.dumps(schema_fn(), indent=1), encoding="utf-8", newline="\n")
        keys.mkdir(parents=True, exist_ok=True)
        (keys / f"{name}_key.json").write_text(json.dumps({
            "batch": name, "kind": kind, "role": role, "label": label, "date": date,
            "instructions_file": instr_path.relative_to(REPO).as_posix(), "instructions_sha256": instr_sha,
            "batch_sha256": cb.sha256_bytes(text.encode("utf-8")), "source": str(source), "ids": key,
            "tool_version": TOOL_VERSION, "built_utc": utc_now()}, indent=1), encoding="utf-8", newline="\n")
        made.append(folder)
        print(f"built {folder} ({len(key)} questions)")
    return made


def select_rows(positions, manifest, only=None, exclude=None, answer_type=None):
    wanted = [l.strip() for l in Path(only).read_text(encoding="utf-8").splitlines() if l.strip()] if only else None
    rows = cb.benchmark_rows(positions, manifest, wanted)
    if exclude:
        skip = {l.strip() for l in Path(exclude).read_text(encoding="utf-8").splitlines() if l.strip()}
        rows = [r for r in rows if r["item_id"] not in skip]
    if answer_type:
        rows = [r for r in rows if r["item"]["answer_type"] == answer_type]
    return rows


def cmd_build(a):
    ws, keys, _, _ = kc_paths()
    ws, keys = cb.check_outside_repo(a.workspace or ws), cb.check_outside_repo(a.keys or keys)
    kind = ROLE_KIND[a.role]
    rows = select_rows(a.positions, a.manifest, a.only, a.exclude)
    hits = kcs.keys_in_text(cb.instructions_text(kcs.KINDS[kind][0])[0], cb.benchmark_rows(a.positions, a.manifest))
    if hits:
        sys.exit(f"the {kind} instructions quote the answer key of {hits[:5]}; a blind solver must never see a key. "
                 f"Nothing was built.")
    date = a.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return write_batches(rows, lambda r: shown_row(r, SHOWN[kind]), kind, a.label or f"kc-{a.role.lower()}", date,
                         a.batch_size or CFG["claude_batch_size"], ws, keys, a.positions, role=a.role)


def cmd_build_variants(a):
    ws, keys, _, _ = kc_paths()
    ws, keys = cb.check_outside_repo(a.workspace or ws), cb.check_outside_repo(a.keys or keys)
    rows = select_rows(a.positions, a.manifest, a.only, a.exclude, answer_type="r_expression")
    date = a.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return write_batches(rows, lambda r: {"question": r["item"]["question"], "answer_key": r["item"]["canonical_answer"]},
                         "variants", a.label or "kc-variants", date, a.batch_size or CFG["claude_batch_size"], ws, keys,
                         a.positions, role="variants")


def cmd_pilot_ids(a):
    """A seeded pilot of 25 questions covering every answer type (8 number, 7 multiple choice, 6 r_expression, 4 short
    text), so the instructions, the runners and the harness are tested on real questions before the full run."""
    pos = read_jsonl(a.positions)
    rng = random.Random(a.seed)
    want = {"number": 8, "multiple_choice": 7, "r_expression": 6, "short_text": 4}
    ids = []
    for at, n in want.items():
        pool = sorted(p["item_id"] for p in pos if p["item"]["answer_type"] == at)
        ids += sorted(rng.sample(pool, n))
    Path(a.out).write_text("".join(i + "\n" for i in ids), encoding="utf-8", newline="\n")
    print(f"{len(ids)} pilot ids (seed {a.seed!r}) -> {a.out}")


# =============================================================================================
# running a Claude batch (subscription login only; the Anthropic API is never used)
# =============================================================================================
def claude_command(cli, schema_text, model):
    return [str(cli), "-p", "--output-format", "stream-json", "--verbose", "--tools", "", "--strict-mcp-config",
            "--setting-sources", "", "--no-session-persistence", "--system-prompt", SYSTEM_PROMPT,
            "--json-schema", schema_text, "--model", model]


def claude_env():
    """The solver's environment: without this session's variables and without ANY ANTHROPIC_* variable."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith(STRIP_ENV_PREFIXES)}


API_WORDS = re.compile(r"api[_ ]?key|console|apikey", re.I)
# A usage or rate limit of the subscription (owner's rule, 2026-11-25: no token cap; stop the Claude side when the CLI reports
# a limit, never wait it out or retry). run-claude then exits with code 3, and the batch stays unrun for a later session.
USAGE_LIMIT = re.compile(r"usage limit|rate limit|limit reached|limit will reset|resets at|too many requests|\b429\b|"
                         r"out of (?:extra )?usage|quota", re.I)


def check_subscription_login(cli, env):
    """Layer 2: `claude auth status --json` (local) must show a logged-in subscription and nothing that points to an API
    key. Returns (ok, record): the record keeps only the login method fields, never the e-mail address or any token."""
    r = subprocess.run([str(cli), "auth", "status", "--json"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120, env=env)
    try:
        st = json.loads(r.stdout)
    except ValueError:
        return False, {"error": "auth status is not JSON", "exit": r.returncode}
    keep = {k: v for k, v in st.items() if isinstance(v, (str, bool, int)) and "mail" not in k.lower()
            and "token" not in k.lower() and "org" not in k.lower() and "id" != k.lower()[-2:]}
    # The login method must be exactly the claude.ai (subscription) login, and no API-key field may be set. (Fixed
    # 2026-11-25 after the first real check: the field consoleProfileSignInOffered, an offer to sign in to the Console, had
    # been read as an API-key sign; the rule now looks only at the login method and at API-key fields.)
    logged_in = st.get("loggedIn", st.get("logged_in"))
    api_hint = [k for k, v in st.items() if re.search(r"api[_ ]?key", k, re.I) and v not in (None, False, "", "none")]
    ok = logged_in is True and st.get("authMethod") == "claude.ai" and not api_hint and r.returncode == 0
    keep["api_key_indicators"] = api_hint
    return ok, keep


def audit_claude_events(text):
    """(problems, info) from the stream-json events. Rejected: any tool other than the structured-output return, any MCP
    server, an error result, and any key source other than "none" (layer 3: an API key was used)."""
    problems, info = [], {"model": None, "usage": {}, "total_cost_usd": None, "tools_offered": None, "output": None,
                          "result_text": None, "num_turns": None, "api_key_source": None}
    allowed_ids = set()
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            problems.append(f"event line {n} is not JSON")
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            info["tools_offered"] = ev.get("tools") or []
            bad = [x for x in info["tools_offered"] if x not in ALLOWED_CLAUDE_TOOLS]
            if bad:
                problems.append(f"the solver was offered tools {bad}; only the structured-output return is allowed")
            if ev.get("mcp_servers"):
                problems.append(f"MCP servers were connected: {ev['mcp_servers']}")
            info["model"] = ev.get("model") or info["model"]
            info["api_key_source"] = ev.get("apiKeySource")
            if ev.get("apiKeySource") not in (None, "none"):
                problems.append(f"the CLI reports key source {ev.get('apiKeySource')!r}: the Anthropic API key must never "
                                f"be used")
        elif t == "assistant":
            msg = ev.get("message") or {}
            info["model"] = msg.get("model") or info["model"]
            for blk in msg.get("content") or []:
                if blk.get("type") == "tool_use":
                    if blk.get("name") in ALLOWED_CLAUDE_TOOLS:
                        allowed_ids.add(blk.get("id"))
                        info["output"] = blk.get("input")
                    else:
                        problems.append(f"event line {n}: the solver used the tool {blk.get('name')!r}")
        elif t == "user":
            for blk in (ev.get("message") or {}).get("content") or []:
                if isinstance(blk, dict) and blk.get("type") == "tool_result" and blk.get("tool_use_id") not in allowed_ids:
                    problems.append(f"event line {n}: a tool result for a tool that is not allowed")
        elif t == "rate_limit_event":
            # the subscription's usage windows (for example five_hour and seven_day utilization), recorded per run
            info["rate_limit"] = ev.get("rate_limit_info")
        elif t == "result":
            if ev.get("is_error") or ev.get("subtype") not in (None, "success"):
                problems.append(f"the run ended with an error ({ev.get('subtype')})")
            info["usage"] = ev.get("usage") or {}
            info["total_cost_usd"] = ev.get("total_cost_usd")
            info["num_turns"] = ev.get("num_turns")
            info["result_text"] = ev.get("result")
            if isinstance(ev.get("structured_output"), dict):
                info["output"] = ev["structured_output"]
    if info["api_key_source"] is None:
        problems.append("the CLI did not report its key source; cannot confirm that no API key was used")
    return problems, info


def reply_text(info):
    if isinstance(info["output"], dict):
        return json.dumps(info["output"], ensure_ascii=False)
    t = (info["result_text"] or "").strip()
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", t)


def cmd_run_claude(a):
    folder = cb.check_outside_repo(a.batch)
    _, _, cli_default, _ = kc_paths()
    cli = Path(a.claude or cli_default)
    present = {p.name for p in folder.iterdir()}
    if present != cb.EXPECTED_FILES:
        sys.exit(f"{folder} must hold exactly {sorted(cb.EXPECTED_FILES)} before a run; it holds {sorted(present)}. "
                 f"Nothing was sent.")
    prompt, ids = cb.build_prompt(folder)
    schema_text = json.dumps(json.loads((folder / "schema.json").read_text(encoding="utf-8")), separators=(",", ":"))
    model = a.model or CFG["claude_model"]
    cmd = claude_command(cli, schema_text, model)
    shown_cmd = [c if c else '""' for c in cmd[:-4]] + ["--json-schema", "<schema.json>", "--model", model]
    if not a.real:
        print("Dry run (no Claude call; pass --real only with the owner's approval). The command would be:\n  "
              + " ".join(shown_cmd) + "\nBilling: subscription login only; every ANTHROPIC_* variable removed; "
              + f"`auth status` checked before the call.\nPrompt: {len(prompt)} characters, {len(ids)} questions, "
              + f"SHA-256 {cb.sha256_bytes(prompt.encode('utf-8'))}")
        return 0
    if not cli.exists():
        sys.exit(f"the Claude CLI {cli} does not exist (did the VS Code extension update? set claude_cli in configs/paths.yaml)")
    env = claude_env()
    ok, login = check_subscription_login(cli, env)
    if not ok:
        sys.exit(f"REFUSED before any call: the CLI's login is not a plain subscription login ({login}). The Anthropic API "
                 f"is never used. Nothing was sent.")
    version = subprocess.run([str(cli), "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=120, env=env).stdout.strip()
    (folder / "prompt.txt").write_text(prompt, encoding="utf-8", newline="\n")
    run = {"tool_version": TOOL_VERSION, "batch": folder.name, "claude_cli": str(cli), "claude_version": version,
           "command": shown_cmd, "login": login, "prompt_sha256": cb.sha256_bytes(prompt.encode("utf-8")),
           "batch_sha256": cb.sha256_bytes((folder / "batch.jsonl").read_bytes()),
           "instructions_sha256_in_folder": cb.sha256_bytes((folder / "instructions.md").read_bytes()),
           "n_ids": len(ids), "started_utc": utc_now(), "timeout_seconds": a.timeout}
    t0 = time.time()
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=a.timeout, cwd=str(folder), env=env)
        run["exit_status"], stdout, stderr = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        run["exit_status"] = "timeout"
        stdout = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr or b"").decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
    run["finished_utc"], run["wall_seconds"] = utc_now(), round(time.time() - t0, 1)
    (folder / "events.jsonl").write_text(stdout, encoding="utf-8", newline="\n")
    (folder / "stderr.txt").write_text(stderr, encoding="utf-8", newline="\n")
    problems, info = audit_claude_events(stdout)
    limit_hit = bool(USAGE_LIMIT.search(stderr or "")) or bool(USAGE_LIMIT.search(info["result_text"] or ""))
    (folder / "verdicts.json").write_text(reply_text(info), encoding="utf-8", newline="\n")
    run.update({"model_requested": model, "model_reported": info["model"] or "not reported",
                "model": info["model"] or model, "usage": info["usage"],
                "cost_usd_equivalent_reported": info["total_cost_usd"], "api_key_source": info["api_key_source"],
                "num_turns": info["num_turns"], "tools_offered": info["tools_offered"], "audit_problems": problems,
                "rate_limit": info.get("rate_limit")})
    if run["exit_status"] != 0:
        problems = problems + [f"exit status {run['exit_status']}"]
    run["accepted_run"] = not problems
    run["usage_limit_reported"] = limit_hit and not run["accepted_run"]
    (folder / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8", newline="\n")
    windows = ((info.get("rate_limit") or {}).get("unifiedWindows") or {})
    print(f"{folder.name}: exit {run['exit_status']}, {run['wall_seconds']}s, model {run['model']}, "
          f"output tokens {info['usage'].get('output_tokens')}, key source {info['api_key_source']}, plan usage "
          + ", ".join(f"{k} {v.get('utilization')}" for k, v in windows.items()))
    if run["usage_limit_reported"]:
        # keep the evidence, but return the folder to its unrun state so it can be run again in a later session
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        keep = folder.parent / "_usage_limit_attempts" / f"{folder.name}_{stamp}"
        keep.mkdir(parents=True)
        for f in cb.OUTPUT_FILES:
            if (folder / f).exists():
                (folder / f).rename(keep / f)
        print(f"USAGE LIMIT reported by the CLI: the Claude side stops here (Jaxson's rule). The batch is unrun again; "
              f"the attempt is kept in {keep}")
        return 3
    if problems:
        print("RUN REJECTED: " + "; ".join(problems))
        return 2
    return 0


# =============================================================================================
# import
# =============================================================================================
def check_root(date):
    return LOGS / f"{date}_key_check_with_codex"


def cmd_import(a):
    folder = cb.check_outside_repo(a.batch)
    _, keys, _, _ = kc_paths()
    key = json.loads((Path(a.keys or keys) / f"{folder.name}_key.json").read_text(encoding="utf-8"))
    run = json.loads((folder / "run.json").read_text(encoding="utf-8")) if (folder / "run.json").exists() else None
    if run is None or not run.get("accepted_run"):
        sys.exit(f"{folder.name}: no accepted run; nothing imported. Re-run the batch.")
    batch = (folder / "batch.jsonl").read_bytes()
    if cb.sha256_bytes(batch) != key["batch_sha256"] or cb.sha256_bytes(batch) != run["batch_sha256"]:
        sys.exit(f"{folder.name}: batch.jsonl changed since it was built or run; nothing imported")
    kind, ids = key["kind"], list(key["ids"])
    shown = {r["id"]: r for r in map(json.loads, batch.decode("utf-8").splitlines()) if r}
    entries, problems = kcs.validate(kind, (folder / "verdicts.json").read_text(encoding="utf-8"), ids, shown)
    if problems:
        print(f"{folder.name}: NOT IMPORTED ({len(problems)} problem(s)); re-run the batch:")
        for p in problems:
            print("  ", p)
        return 2
    out = Path(a.out_root or check_root(key["date"])) / key["label"] / folder.name
    if out.exists():
        sys.exit(f"{out} exists; an imported batch is never overwritten")
    out.mkdir(parents=True)
    rows = [{"item_id": info["item_id"], "position": info["position"], "batch": folder.name, "anon_id": anon,
             "kind": kind, "role": key.get("role"), "model": run.get("model"),
             **{f: x for f, x in entries[anon].items() if f != "id"}} for anon, info in key["ids"].items()]
    write_jsonl(out / kcs.RESULTS_FILE[kind], rows)
    for f in ("batch.jsonl", "verdicts.json", "run.json", "instructions.md", "schema.json"):
        (out / f).write_bytes((folder / f).read_bytes())
    (out / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8", newline="\n")
    print(f"{folder.name}: imported {len(rows)} {kind} entries -> {out}")
    return 0


# =============================================================================================
# loading results
# =============================================================================================
def latest_by_item(files):
    """{item_id: row}, the latest run winning (ordered by run.json finished_utc, as in readiness_check)."""
    def finished(f):
        rj = f.parent / "run.json"
        return json.loads(rj.read_text(encoding="utf-8")).get("finished_utc", "") if rj.exists() else ""
    out = {}
    for f in sorted(files, key=finished):
        for r in read_jsonl(f):
            out[r["item_id"]] = {**r, "source": f"{f.parent.parent.name}/{f.parent.name}"}
    return out


def load_role(logs, label, results_name, codex=False):
    pat = f"*_codex_{label}/*/{results_name}" if codex else f"*_key_check_with_codex/{label}/*/{results_name}"
    return latest_by_item(Path(logs).glob(pat))


def load_screen(logs, overrides_path):
    import readiness_check as rc
    screen = rc.latest_results(logs, "screen_results.jsonl")
    overrides = set()
    if overrides_path and Path(overrides_path).exists():
        overrides = {o["item_id"] for o in json.loads(Path(overrides_path).read_text(encoding="utf-8"))}
    return screen, overrides


# =============================================================================================
# R: solver code and the equivalence harness (all in the R sandbox)
# =============================================================================================
R_SOLVER = r"""options(digits = 15, warn = 1)
.kc_res <- tryCatch(local({
%s
list(answer = if (exists("answer", inherits = FALSE)) answer else NULL,
     value = if (exists("value", inherits = FALSE)) value else NULL)
}), error = function(e) list(error = conditionMessage(e)))
.kc_fmt <- function(x) paste(format(x, digits = 15), collapse = "|")
if (!is.null(.kc_res$error)) {
  cat("\n<<KC_ERROR>>", gsub("[\r\n]+", " ", .kc_res$error), "<<KC_END>>\n")
} else {
  cat("\n<<KC_ANSWER>>", if (is.null(.kc_res$answer)) "<<NULL>>" else .kc_fmt(.kc_res$answer), "<<KC_END>>\n")
  cat("<<KC_VALUE>>", if (is.null(.kc_res$value)) "<<NULL>>" else substr(.kc_fmt(.kc_res$value), 1, 300), "<<KC_END>>\n")
}
"""


def run_solver_code(code, rscript):
    """Run a solver's r_code. Returns {status: ok|error|refused|failed, answer, value, error}."""
    ok, out = gb.run_r(R_SOLVER % code, rscript)
    if not ok:
        return {"status": "refused" if str(out).startswith("refused") else "failed", "answer": None, "value": None,
                "error": str(out)[:300]}
    m = re.search(r"<<KC_ERROR>> (.*?) <<KC_END>>", out, re.S)
    if m:
        return {"status": "error", "answer": None, "value": None, "error": m.group(1)[:300]}
    ans = re.search(r"<<KC_ANSWER>> (.*?) <<KC_END>>", out, re.S)
    val = re.search(r"<<KC_VALUE>> (.*?) <<KC_END>>", out, re.S)
    a = ans.group(1).strip() if ans else "<<NULL>>"
    return {"status": "ok" if a != "<<NULL>>" else "error", "answer": None if a == "<<NULL>>" else a,
            "value": None if not val or val.group(1).strip() == "<<NULL>>" else val.group(1).strip(),
            "error": "the code did not create an object named answer" if a == "<<NULL>>" else None}


R_HARNESS = r"""options(digits = 15, warn = 1)
.kc_tol <- %(tol)s
.kc_values <- function(x) {
  if (is.factor(x)) return(as.character(x))
  if (inherits(x, "Date") || inherits(x, "POSIXt")) return(as.character(x))
  if (is.data.frame(x) || is.list(x)) return(unlist(lapply(x, .kc_values), use.names = FALSE))
  x <- unclass(x); attributes(x) <- NULL; x
}
.kc_same <- function(a, b) {
  s <- tryCatch(identical(class(a), class(b)) && isTRUE(all.equal(a, b, tolerance = .kc_tol)), error = function(e) FALSE)
  v <- tryCatch({ va <- .kc_values(a); vb <- .kc_values(b)
    length(va) == length(vb) && isTRUE(all.equal(va, vb, tolerance = .kc_tol, check.attributes = FALSE)) },
    error = function(e) FALSE)
  c(s, s || v)
}
.kc_run <- function(code, expr) {
  env <- new.env(parent = globalenv())
  ok <- tryCatch({ eval(parse(text = code), envir = env); TRUE }, error = function(e) conditionMessage(e))
  if (!isTRUE(ok)) return(list(status = "input_error", msg = ok))
  set.seed(20261124)
  tryCatch(list(status = "ok", value = eval(parse(text = expr), envir = env)),
           error = function(e) list(status = "error", msg = conditionMessage(e)))
}
.kc_show <- function(r) {
  s <- if (r$status != "ok") r$msg else tryCatch(paste(utils::capture.output(utils::str(r$value, vec.len = 4,
         give.attr = FALSE)), collapse = " / "), error = function(e) "<unprintable>")
  substr(gsub("[\r\n\t]+", " ", s), 1, 300)
}
.kc_exprs <- list(%(exprs)s)
.kc_inputs <- list(%(inputs)s)
for (.i in seq_along(.kc_inputs)) {
  .res <- lapply(.kc_exprs, function(e) .kc_run(.kc_inputs[[.i]], e))
  for (.nm in names(.res)) {
    .r <- .res[[.nm]]
    .cmp <- if (.r$status == "ok" && .res$key$status == "ok") .kc_same(.r$value, .res$key$value) else c(NA, NA)
    cat("<<KC>>", .i, .nm, .r$status, .cmp[1], .cmp[2], .kc_show(.r), "\n", sep = "\t")
  }
  if (!is.null(.res$c2) && !is.null(.res$x2) && .res$c2$status == "ok" && .res$x2$status == "ok") {
    .cmp <- .kc_same(.res$c2$value, .res$x2$value)
    cat("<<KC>>", .i, "c2~x2", "ok", .cmp[1], .cmp[2], "", "\n", sep = "\t")
  }
}
"""


def harness_code(exprs, inputs, tol):
    ex = ",\n  ".join(f"{name} = {gb.r_string(e)}" for name, e in exprs.items())
    ins = ",\n  ".join(gb.r_string(i["code"]) for i in inputs)
    return R_HARNESS % {"tol": repr(float(tol)), "exprs": ex, "inputs": ins}


def parse_harness(out, offset=0):
    """{(input_index, name): {status, strict, values, show}} from the harness output (input indexes start at 1)."""
    res = {}
    b = {"TRUE": True, "FALSE": False}
    for line in out.splitlines():
        k = line.find("<<KC>>\t")
        if k < 0:
            continue
        parts = line[k:].rstrip("\n").split("\t")
        if len(parts) < 7:
            continue
        res[(int(parts[1]) + offset, parts[2])] = {"status": parts[3], "strict": b.get(parts[4]), "values": b.get(parts[5]),
                                                   "show": parts[6]}
    return res


def run_harness(exprs, inputs, rscript, tol):
    """Evaluate every expression on every input. One sandbox run for all inputs; if it fails (for example a time limit),
    one run per input, so one slow input cannot hide the others."""
    ok, out = gb.run_r(harness_code(exprs, inputs, tol), rscript)
    if ok:
        res = parse_harness(out)
        if len({i for i, _ in res}) == len(inputs):
            return res, None
    res, failures = {}, []
    for k, inp in enumerate(inputs, 1):
        ok1, out1 = gb.run_r(harness_code(exprs, [inp], tol), rscript)
        if ok1:
            res.update(parse_harness(out1, offset=k - 1))
        else:
            failures.append(f"input {k}: {str(out1)[:150]}")
    return res, "; ".join(failures) or None


def r_check_verdict(item, expr, rscript):
    v = gb.r_check_result(item, expr, rscript)
    return v if isinstance(v, bool) else f"refused: {v}"


# =============================================================================================
# comparing answers with the key
# =============================================================================================
def key_tolerance(item):
    """The tolerance a number answer is compared with: the item's answer_tolerance or half a unit in the key's last written
    digit, whichever is larger (0.94 covers 0.935 to 0.945; 2.6e-12 covers 2.55e-12 to 2.65e-12)."""
    kt = item["canonical_answer"].strip().replace(",", "")
    try:
        half = 0.5 * 10 ** Decimal(kt).as_tuple().exponent
    except (InvalidOperation, TypeError):
        half = 0.0
    return max(float(item.get("answer_tolerance") or 0), float(half))


def as_number(s):
    if s is None:
        return None
    t = str(s).strip().replace(",", "").split("|")[0].strip().strip('"').rstrip("%").strip()
    try:
        return float(t)
    except ValueError:
        return None


def norm_text(s):
    """Normalize a short-text answer or key before an exact comparison: case, spaces, a final period, and R's print
    formatting (the index markers [1], [5] and the quotes R puts around strings) are ignored (Jaxson's decision after the
    pilot, 2026-11-25). Example: '[1] "(Intercept)" "x"   "groupB"' and '(Intercept) x groupB' compare equal."""
    t = str(s or "").strip().casefold()
    t = re.sub(r"(?m)^\s*\[\d+\]", " ", t)          # index markers at line starts
    t = re.sub(r"\s\[\d+\]\s", " ", t)              # index markers inside a flattened printout
    t = re.sub(r"[\"'`]", " ", t)                   # quotes around strings
    return re.sub(r"\s+", " ", t).strip(" .")


HARDCODED = re.compile(r"""^answer\s*(<-|=)\s*["'][A-D]["']\s*;?\s*$""")


def hardcoded_letter(code):
    """True if the code assigns a literal letter to answer as a plain top-level line (a letter not chosen by computation)."""
    for line in code.splitlines():
        line = line.split("#")[0].rstrip()
        if line and not line.startswith((" ", "\t")) and HARDCODED.match(line):
            return True
    return False


def judge_number(item, ev, cfg):
    reasons, notes = [], []
    key = as_number(item["canonical_answer"])
    tol = key_tolerance(item)
    if key is None:
        return ["the key is not a plain number"], notes
    vals = {}
    for s in ("c2", "x2"):
        e = ev.get(s)
        if not e:
            continue
        if e["status"] != "computed":
            reasons.append(f"{s.upper()} did not compute ({e['status']}: {e['note'][:120]})")
        elif e["run"]["status"] != "ok":
            reasons.append(f"{s.upper()} code failed ({e['run']['status']}: {(e['run'].get('error') or '')[:120]})")
        else:
            v = as_number(e["run"]["answer"])
            if v is None:
                reasons.append(f"{s.upper()} code returned a non-number ({str(e['run']['answer'])[:60]})")
            else:
                vals[s] = v
    matches = {s: abs(v - key) <= tol + 1e-9 * abs(key) for s, v in vals.items()}
    for s, m in matches.items():
        if not m:
            reasons.append(f"{s.upper()} computes {vals[s]:.6g}, key {key:g} (tolerance {tol:g})")
    if len(vals) == 2 and not any(matches.values()) and abs(vals["c2"] - vals["x2"]) <= max(tol, 1e-9 * abs(key)):
        reasons.insert(0, f"likely wrong key: C2 and X2 agree on {vals['c2']:.6g}; key {key:g}")
    for s in ("c1", "x1"):
        e = ev.get(s)
        if not e:
            continue
        if e["answer"].strip() == kcs.UNANSWERABLE:
            reasons.append(f"{s.upper()} says unanswerable: {e['working'][:120]}")
            continue
        v = as_number(e["answer"])
        if v is None:
            reasons.append(f"{s.upper()} answer is not a plain number ({e['answer'][:60]})")
        elif abs(v - key) > tol + cfg["analytic_relative_allowance"] * abs(key) + 1e-12:
            reasons.append(f"{s.upper()} (analytic) gives {v:g}, key {key:g}")
    if ev.get("r_solution") is not None:
        notes.append(f"Qwen's r_solution gives {ev['r_solution']} (supporting evidence only)")
    return reasons, notes


def judge_mc(item, ev):
    reasons, notes = [], []
    key = item["canonical_answer"].strip()
    comp = {}
    for s in ("c2", "x2"):
        e = ev.get(s)
        if not e or e["status"] != "computed":
            continue
        r = e["run"]
        letter = (r.get("answer") or "").strip('"')
        if r["status"] != "ok":
            reasons.append(f"{s.upper()} code failed ({r['status']}: {(r.get('error') or '')[:120]})")
        elif letter not in kcs.LETTERS:
            reasons.append(f"{s.upper()} code returned {str(r['answer'])[:40]!r}, not a letter")
        elif hardcoded_letter(e["r_code"]) or r.get("value") is None:
            notes.append(f"{s.upper()} letter not supported by a computed value (not counted as computation)")
        else:
            comp[s] = letter
    analytic = {s: ev[s]["answer"].strip() for s in ("c1", "x1") if ev.get(s)}
    if len(comp) == 2:
        deciding, other, basis = comp, analytic, "computed (C2, X2)"
    else:
        deciding, other, basis = analytic, comp, "analytic (C1, X1)"
    notes.append(f"deciding pair: {basis}")
    for s, L in {**deciding, **other}.items():
        if L != key:
            reasons.append(f"{s.upper()} answers {L}, key {key}")
    for s in ("c1", "x1", "c2", "x2"):
        e = ev.get(s)
        if not e:
            continue
        opts = e.get("correct_options") or []
        extra = [o for o in opts if o != key]
        if extra:
            reasons.append(f"{s.upper()} also marks {', '.join(extra)} correct")
        if s in ("c1", "x1") and not opts and e["answer"].strip() in kcs.LETTERS:
            reasons.append(f"{s.upper()} judges no option correct")
    return reasons, notes


def judge_short(item, ev):
    reasons = []
    key = item["canonical_answer"]
    kn = as_number(key)

    def same(ans):
        if kn is not None and as_number(ans) is not None:
            return abs(as_number(ans) - kn) <= key_tolerance(item) + 1e-9 * abs(kn)
        return norm_text(ans) == norm_text(key)
    for s in ("c1", "x1"):
        e = ev.get(s)
        if e and not same(e["answer"]):
            reasons.append(f"{s.upper()} answers {e['answer'][:80]!r}, key {key!r}")
    for s in ("c2", "x2"):
        e = ev.get(s)
        if e and e["status"] == "computed":
            r = e["run"]
            if r["status"] != "ok":
                reasons.append(f"{s.upper()} code failed ({r['status']}: {(r.get('error') or '')[:120]})")
            elif not same(str(r["answer"]).strip('"')):
                reasons.append(f"{s.upper()} computes {str(r['answer'])[:80]!r}, key {key!r}")
    return reasons, []


def judge_rexpr(item, ev, harness, rchecks, variants, cfg):
    """The r_expression rules (plan of 2026-11-24). Returns reasons, check_flags, notes and a compact summary."""
    reasons, flags, notes = [], [], []
    inputs, res = harness["inputs"], harness["results"]
    n_in = len(inputs)
    qd = [k for k, i in enumerate(inputs, 1) if i["kind"] == "question_data"]
    counted = [k for k in range(1, n_in + 1) if (res.get((k, "key")) or {}).get("status") == "ok"]
    key_bad_qd = [k for k in qd if k not in counted]
    if qd and len(key_bad_qd) == len(qd):
        reasons.append("the key fails on the question's own data (" +
                       "; ".join((res.get((k, "key")) or {}).get("show", "no result")[:100] for k in key_bad_qd) + ")")
    out_of_scope = [k for k in range(1, n_in + 1) if k not in counted and k not in qd]
    if out_of_scope:
        notes.append(f"inputs {out_of_scope} not counted: the key errors on them (outside the question's scope)")
    fixed = all(ev.get(s) and ev[s]["status"] == "computed" and len(ev[s]["test_inputs"]) < 4 for s in ("c2", "x2"))
    need = 1 if fixed else cfg["min_test_inputs"]
    if fixed:
        notes.append("both computational solvers say the question fixes its data (fewer than four inputs)")
    if len(counted) < need:
        reasons.append(f"only {len(counted)} usable test input(s) (need {need})")

    def summary(name):
        rows = [res.get((k, name)) for k in counted]
        if not any(rows):
            return None
        diff = [k for k, r in zip(counted, rows) if not (r and r["values"])]
        form = [k for k, r in zip(counted, rows) if r and r["values"] and not r["strict"]]
        return {"strict_all": not diff and not form, "values_all": not diff, "differs_on": diff, "form_differs_on": form,
                "differs_on_question_data": [k for k in diff if k in qd]}
    summ = {name: summary(name) for name in harness["exprs"]}
    for s in ("c2", "x2"):
        e = ev.get(s)
        if not e:
            continue
        if e["status"] != "computed":
            reasons.append(f"{s.upper()} did not compute ({e['status']}: {e['note'][:120]})")
            continue
        sm = summ.get(s)
        if sm is None:
            reasons.append(f"{s.upper()} expression produced no result")
        elif sm["values_all"] and not sm["strict_all"]:
            reasons.append(f"same values, different form: {s.upper()} on inputs {sm['form_differs_on']} "
                           f"(Jaxson decides whether the question asks for that form)")
        elif not sm["values_all"]:
            if qd and not sm["differs_on_question_data"]:
                reasons.append(f"{s.upper()} matches the key on the question's data but differs on inputs {sm['differs_on']}: "
                               f"a possible coincidental match (key or solver too narrow)")
            else:
                reasons.append(f"{s.upper()} differs from the key on inputs {sm['differs_on']}")
    pair = [res.get((k, "c2~x2")) for k in counted]
    if (summ.get("c2") and summ.get("x2") and not summ["c2"]["values_all"] and not summ["x2"]["values_all"]
            and pair and all(p and p["values"] for p in pair)):
        reasons.insert(0, "likely wrong key: C2 and X2 agree with each other on every input, not with the key")
    for s in ("c1", "x1"):
        e = ev.get(s)
        if not e:
            continue
        if e["answer"].strip() == kcs.UNANSWERABLE:
            reasons.append(f"{s.upper()} says unanswerable: {e['working'][:120]}")
        elif summ.get(s) is None or not summ[s]["values_all"]:
            reasons.append(f"{s.upper()} (analytic) expression differs from the key on inputs "
                           f"{(summ.get(s) or {}).get('differs_on', 'all')}")
    # the r_check, as supporting evidence
    if rchecks.get("key") is not True:
        flags.append(f"the r_check does not accept the key ({rchecks.get('key')})")
    for s in ("c1", "x1", "c2", "x2"):
        sm, rcv = summ.get(s), rchecks.get(s)
        if sm is None or rcv is None:
            continue
        if sm["strict_all"] and rcv is not True:
            flags.append(f"check too strict: rejects {s.upper()}, which equals the key on every input")
        elif sm["values_all"] and rcv is not True:
            notes.append(f"the r_check rejects {s.upper()} (same values, different form)")
        elif not sm["values_all"] and rcv is True:
            flags.append(f"check too loose: accepts {s.upper()}, which differs from the key on inputs {sm['differs_on']}")
    # the known-wrong variants (classified by the harness, never by the agent's own claim)
    vrep = []
    for k, v in enumerate(variants.get("variants", []) if variants else [], 1):
        name = f"v{k}"
        sm, rcv = summ.get(name), rchecks.get(name)
        cx = harness["cx_index"].get(name)
        cx_r = res.get((cx, name)) if cx else None
        cx_shows = bool(cx and cx in counted and cx_r and not cx_r["values"])
        if sm is None:
            cls = "no result"
        elif sm["values_all"]:
            cls = "not shown wrong (equals the key on every input; set aside)"
        elif not qd:
            cls = "wrong (the question gives no data of its own)"
        elif sm["differs_on_question_data"]:
            cls = "wrong on the question data"
        else:
            cls = "wrong only in generalization"
        if cls.startswith("wrong") and rcv is True:
            if cls == "wrong only in generalization":
                flags.append(f"generalization limit: the r_check accepts variant {k} ({v['what_is_wrong'][:60]}), which is "
                             f"wrong only on other valid data")
            else:
                flags.append(f"check too loose: accepts variant {k} ({v['what_is_wrong'][:60]}), {cls}")
        vrep.append({"variant": k, "expression": v["expression"], "what_is_wrong": v["what_is_wrong"], "class": cls,
                     "r_check_accepts": rcv, "own_counterexample_shows_difference": cx_shows})
    if variants and variants.get("key_concern", "").strip():
        reasons.append(f"the variants agent suspects the key: {variants['key_concern'][:200]}")
    return reasons, flags, notes, {"inputs": [{"k": k, "kind": i["kind"], "src": i["src"]} for k, i in enumerate(inputs, 1)],
                                   "counted": counted, "expressions": summ, "r_check": rchecks, "variants": vrep,
                                   "harness_failures": harness.get("failures")}


def analytic_ev(r):
    return {f: r[f] for f in ("answer", "correct_options", "working", "confidence")} if r else None


def compute_ev(r, rscript):
    if not r:
        return None
    e = {f: r[f] for f in ("status", "r_code", "answer_expression", "test_inputs", "correct_options", "note")}
    e["run"] = run_solver_code(r["r_code"], rscript) if r["status"] == "computed" and r["r_code"].strip() \
        else {"status": "not_run"}
    return e


def compare_item(p, roles, screen, overrides, rscript, cfg, harness_dir):
    it, iid = p["item"], p["item_id"]
    at = it["answer_type"]
    ev = {"c1": analytic_ev(roles["c1"].get(iid)), "x1": analytic_ev(roles["x1"].get(iid)),
          "c2": compute_ev(roles["c2"].get(iid), rscript), "x2": compute_ev(roles["x2"].get(iid), rscript)}
    missing = [s.upper() for s in ("c1", "x1", "c2", "x2") if ev[s] is None]
    c3 = roles["c3"].get(iid)
    if c3 is None:
        missing.append("C3")
    reasons, flags, notes, harness_summary = [], [], [], None
    if at == "number":
        if (it.get("r_solution") or "").strip():
            rt, prob = gb.run_r_solution(it, rscript)
            ev["r_solution"] = rt if rt is not None else f"failed: {prob}"
        reasons, notes = judge_number(it, ev, cfg)
    elif at == "multiple_choice":
        reasons, notes = judge_mc(it, ev)
    elif at == "short_text":
        reasons, notes = judge_short(it, ev)
    elif at == "r_expression":
        var = roles["variants"].get(iid)
        if var is None:
            missing.append("variants")
        exprs = {"key": it["canonical_answer"]}
        for s in ("c1", "x1"):
            if ev[s] and ev[s]["answer"].strip() != kcs.UNANSWERABLE:
                exprs[s] = ev[s]["answer"]
        for s in ("c2", "x2"):
            if ev[s] and ev[s]["status"] == "computed":
                exprs[s] = ev[s]["answer_expression"]
        inputs, cx_index = [], {}
        for s in ("c2", "x2"):
            for t in (ev[s] or {}).get("test_inputs") or []:
                inputs.append({"kind": t["kind"], "code": t["code"], "src": s})
        for k, v in enumerate((var or {}).get("variants", []), 1):
            exprs[f"v{k}"] = v["expression"]
            inputs.append({"kind": "counterexample", "code": v["counterexample"], "src": f"v{k}"})
            cx_index[f"v{k}"] = len(inputs)
        res, failures = run_harness(exprs, inputs, rscript, cfg["equivalence_tolerance"]) if inputs else ({}, "no inputs")
        harness = {"exprs": exprs, "inputs": inputs, "results": res, "cx_index": cx_index, "failures": failures}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            fut = {name: pool.submit(r_check_verdict, it, e, rscript) for name, e in exprs.items()}
            rchecks = {name: f.result() for name, f in fut.items()}
        reasons, flags, notes, harness_summary = judge_rexpr(it, ev, harness, rchecks, var, cfg)
        if harness_dir:
            (harness_dir / f"{iid}.json").write_text(json.dumps(
                {"item_id": iid, "exprs": exprs, "inputs": inputs, "r_check": rchecks, "failures": failures,
                 "results": [{"input": k, "name": n, **v} for (k, n), v in sorted(res.items())]},
                indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    if c3 and c3["verdict"] == "flag":
        reasons.append(f"C3 flags it ({c3['issue_type']}): {c3['reason'][:160]}")
    s = screen.get(iid)
    if s and s["verdict"] == "flag":
        if iid in overrides:
            notes.append(f"the Codex screen flagged it ({s['issue_type']}); kept by Jaxson's logged override")
        else:
            reasons.append(f"the Codex screen flags it ({s['issue_type']}): {s['reason'][:160]}")
    verdict = "incomplete" if missing else ("contested" if reasons else "consensus-supported")
    return {"position": p["position"], "item_id": iid, "answer_type": at, "category": p["slot"]["category"],
            "difficulty": p["slot"]["difficulty"], "key": it["canonical_answer"], "verdict": verdict,
            "missing": missing, "reasons": reasons, "check_flags": flags, "notes": notes,
            "evidence": {**ev, "c3": {f: c3[f] for f in ("verdict", "issue_type", "reason")} if c3 else None,
                         "codex_screen": {f: s[f] for f in ("verdict", "issue_type", "reason")} if s else None},
            "harness": harness_summary,
            "sources": {k: (roles[k].get(iid) or {}).get("source") for k in roles}}


def cmd_compare(a):
    pos = read_jsonl(a.positions)
    if a.only:
        want = {l.strip() for l in Path(a.only).read_text(encoding="utf-8").splitlines() if l.strip()}
        pos = [p for p in pos if p["item_id"] in want]
    logs = Path(a.logs)
    roles = {"c1": load_role(logs, a.c1, "solve_results.jsonl"), "c2": load_role(logs, a.c2, "solve_results.jsonl"),
             "c3": load_role(logs, a.c3, "ambiguity_results.jsonl"),
             "x1": load_role(logs, a.x1, "solve_results.jsonl", codex=True),
             "x2": load_role(logs, a.x2, "solve_results.jsonl", codex=True),
             "variants": load_role(logs, a.variants, "variants_results.jsonl")}
    screen, overrides = load_screen(logs, a.overrides)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(a.out or check_root(a.date)) / f"compare_{stamp}"
    out.mkdir(parents=True)
    harness_dir = Path(a.harness_dir) if a.harness_dir else kc_paths()[3] / f"{a.date}_key_check" / f"harness_{stamp}"
    harness_dir.mkdir(parents=True, exist_ok=True)
    rscript = gb.rscript_path()
    # several questions at once (each one's R runs are independent sandbox processes); results keep benchmark order
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
        futs = [pool.submit(compare_item, p, roles, screen, overrides, rscript, CFG, harness_dir) for p in pos]
        rows = []
        for n, f in enumerate(futs, 1):
            rows.append(f.result())
            if n % 100 == 0:
                print(f"  {n}/{len(pos)} compared", flush=True)
    incomplete = [r["item_id"] for r in rows if r["verdict"] == "incomplete"]
    if incomplete and not a.allow_incomplete:
        print(f"WARNING: {len(incomplete)} question(s) lack a solver result (first: {incomplete[:5]}); they are marked "
              f"incomplete, never consensus-supported.")
    write_jsonl(out / "verdicts.jsonl", rows)
    summ = {"compared_utc": utc_now(), "positions": a.positions, "n": len(rows), "harness_dir": str(harness_dir),
            "verdict": dict(collections.Counter(r["verdict"] for r in rows)),
            "by_type": {at: dict(collections.Counter(r["verdict"] for r in rows if r["answer_type"] == at))
                        for at in kcs.ANSWER_TYPES},
            "check_flagged": sum(bool(r["check_flags"]) for r in rows),
            "check_flag_kinds": dict(collections.Counter(f.split(":")[0] for r in rows for f in r["check_flags"])),
            "likely_wrong_key": sum(any(x.startswith("likely wrong key") for x in r["reasons"]) for r in rows),
            "sources": {k: sorted({v.get("source", "").split("/")[0] for v in roles[k].values()}) for k in roles},
            "config": CFG, "tool_version": TOOL_VERSION}
    (out / "summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: summ[k] for k in ("n", "verdict", "by_type", "check_flagged", "likely_wrong_key")}, indent=1))
    print(f"-> {out}")
    return 0


# =============================================================================================
# briefs, review sheet, audit merge, usage
# =============================================================================================
def latest_compare(date):
    folders = sorted(check_root(date).glob("compare_*"))
    if not folders:
        sys.exit(f"no compare_* folder under {check_root(date)}")
    return folders[-1]


def evidence_text(v):
    """A compact, readable summary of the evidence for the adjudicator (at most about 3,500 characters)."""
    e = v["evidence"]
    parts = [f"reasons: {v['reasons']}", f"check flags: {v['check_flags']}"]
    for s in ("c1", "x1"):
        if e.get(s):
            parts.append(f"{s.upper()} (analytic): answer {e[s]['answer']!r}; options {e[s]['correct_options']}; "
                         f"{e[s]['working'][:300]}")
    for s in ("c2", "x2"):
        if e.get(s):
            x = e[s]
            parts.append(f"{s.upper()} (computational, {x['status']}): " + (
                f"expression {x['answer_expression']!r}" if x["answer_expression"] else
                f"code {x['r_code'][:400]!r} -> {x['run']}") + f"; note {x['note'][:150]!r}")
    if e.get("r_solution"):
        parts.append(f"Qwen's r_solution gives {e['r_solution']}")
    for s in ("c3", "codex_screen"):
        if e.get(s):
            parts.append(f"{s}: {e[s]['verdict']} ({e[s]['issue_type']}) {e[s]['reason'][:200]}")
    if v.get("harness"):
        parts.append("harness: " + json.dumps({k: v["harness"][k] for k in ("inputs", "expressions", "variants")},
                                              ensure_ascii=False)[:1500])
    return "\n".join(parts)[:3500]


def cmd_build_briefs(a):
    ws, keys, _, _ = kc_paths()
    ws, keys = cb.check_outside_repo(a.workspace or ws), cb.check_outside_repo(a.keys or keys)
    folder = Path(a.compare) if a.compare else latest_compare(a.date)
    verdicts = [v for v in read_jsonl(folder / "verdicts.jsonl") if v["verdict"] == "contested" or v["check_flags"]]
    items = {p["item_id"]: p for p in read_jsonl(a.positions)}
    rows = [{**items[v["item_id"]], "_v": v} for v in verdicts]

    def shown(r):
        it = r["item"]
        return {"answer_type": it["answer_type"], "question": it["question"],
                "choices": {L: c for L, c in zip("ABCD", it.get("choices") or [])}, "answer_key": it["canonical_answer"],
                "answer_tolerance": it.get("answer_tolerance"), "r_check": it.get("r_check", ""),
                "evidence": evidence_text(r["_v"])}
    return write_batches(rows, shown, "brief", a.label or "kc-brief", a.date, a.batch_size or 10, ws, keys, folder,
                         role="brief")


def solver_cell(e, s):
    x = e.get(s)
    if not x:
        return ""
    if s in ("c1", "x1"):
        return x["answer"]
    return (x["answer_expression"] or (x.get("run") or {}).get("answer") or "") + f" [{x['status']}]"


def cmd_review(a):
    folder = Path(a.compare) if a.compare else latest_compare(a.date)
    verdicts = read_jsonl(folder / "verdicts.jsonl")
    briefs = load_role(LOGS, a.briefs, "brief_results.jsonl")
    items = {p["item_id"]: p for p in read_jsonl(a.positions)}
    rows = [v for v in verdicts if v["verdict"] != "consensus-supported" or v["check_flags"]]
    out = folder / "key_check_review.csv"
    if out.exists():
        sys.exit(f"{out} exists; the review sheet is never overwritten (Jaxson's decisions may be in it)")
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["position", "item_id", "answer_type", "verdict", "reasons", "check_flags", "question", "choices", "key",
                    "C1", "X1", "C2", "X2", "C3_and_screen", "brief", "brief_reading",
                    "owner_decision (key_correct/key_wrong/question_flawed/check_revision)", "owner_corrected_key",
                    "owner_note"])
        for v in sorted(rows, key=lambda v: v["position"]):
            it, e, b = items[v["item_id"]]["item"], v["evidence"], briefs.get(v["item_id"]) or {}
            w.writerow([v["position"], v["item_id"], v["answer_type"], v["verdict"], "\n".join(v["reasons"]),
                        "\n".join(v["check_flags"]), it["question"],
                        "\n".join(f"{L}. {c}" for L, c in zip("ABCD", it.get("choices") or [])), it["canonical_answer"],
                        solver_cell(e, "c1"), solver_cell(e, "x1"), solver_cell(e, "c2"), solver_cell(e, "x2"),
                        " | ".join(f"{s}: {e[s]['verdict']} {e[s]['issue_type']}" for s in ("c3", "codex_screen") if e.get(s)),
                        b.get("brief", ""), b.get("reading", ""), "", "", ""])
    print(f"{len(rows)} question(s) for Jaxson -> {out}")


def cmd_audit_merge(a):
    folder = Path(a.compare) if a.compare else latest_compare(a.date)
    verdicts = {v["item_id"]: v for v in read_jsonl(folder / "verdicts.jsonl")}
    briefs = load_role(LOGS, a.briefs, "brief_results.jsonl")
    rows = list(csv.DictReader(open(a.audit, encoding="utf-8-sig")))
    out = folder / "audit_sheet_with_key_check.csv"
    if out.exists():
        sys.exit(f"{out} exists; never overwritten")
    extra = ["key_check_verdict", "key_check_reasons", "key_check_check_flags", "C1", "X1", "C2", "X2", "brief",
             "brief_reading"]
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) + extra)
        w.writeheader()
        for r in rows:
            v = verdicts.get(r["item_id"]) or {}
            e = v.get("evidence") or {}
            b = briefs.get(r["item_id"]) or {}
            w.writerow({**r, "key_check_verdict": v.get("verdict", "not compared"),
                        "key_check_reasons": "\n".join(v.get("reasons", [])),
                        "key_check_check_flags": "\n".join(v.get("check_flags", [])),
                        "C1": solver_cell(e, "c1"), "X1": solver_cell(e, "x1"), "C2": solver_cell(e, "c2"),
                        "X2": solver_cell(e, "x2"), "brief": b.get("brief", ""), "brief_reading": b.get("reading", "")})
    print(f"{len(rows)} audit rows with the key-check evidence -> {out}")


def cmd_usage(a):
    ws, _, _, _ = kc_paths()
    tot, n, sources = {}, 0, collections.Counter()
    for rj in sorted(Path(a.workspace or ws).glob(f"{a.prefix}*/run.json")):
        r = json.loads(rj.read_text(encoding="utf-8"))
        n += 1
        sources[str(r.get("api_key_source"))] += 1
        for k, v in (r.get("usage") or {}).items():
            if isinstance(v, (int, float)):
                tot[k] = tot.get(k, 0) + v
    print(json.dumps({"runs": n, "usage": tot, "key_sources": dict(sources)}, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    man_default = str(REPO / "data" / "slots" / "benchmark_slots.manifest.json")
    p = sub.add_parser("pilot-ids")
    p.add_argument("--positions", required=True)
    p.add_argument("--seed", default="key-check-pilot-2026-11-24")
    p.add_argument("--out", required=True)
    for name in ("build", "build-variants"):
        p = sub.add_parser(name)
        if name == "build":
            p.add_argument("--role", required=True, choices=sorted(ROLE_KIND))
        p.add_argument("--positions", required=True)
        p.add_argument("--manifest", default=man_default)
        p.add_argument("--only", default=None)
        p.add_argument("--exclude", default=None)
        p.add_argument("--label", default=None)
        p.add_argument("--date", default=None)
        p.add_argument("--batch-size", type=int, default=0)
        p.add_argument("--workspace", default=None)
        p.add_argument("--keys", default=None)
    p = sub.add_parser("run-claude")
    p.add_argument("--batch", required=True)
    p.add_argument("--claude", default=None, help="the Claude CLI (default claude_cli in configs/paths.yaml; tests: a fake)")
    p.add_argument("--model", default=None)
    p.add_argument("--timeout", type=float, default=CFG["claude_timeout_seconds"])
    p.add_argument("--real", action="store_true", help="actually call Claude (only with the owner's approval)")
    p = sub.add_parser("import")
    p.add_argument("--batch", required=True)
    p.add_argument("--keys", default=None)
    p.add_argument("--out-root", default=None)
    p = sub.add_parser("compare")
    p.add_argument("--positions", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--only", default=None)
    p.add_argument("--logs", default=str(LOGS))
    for r, d in (("c1", "kc-c1"), ("c2", "kc-c2"), ("c3", "kc-c3"), ("x1", "kc-x1"), ("x2", "kc-x2"),
                 ("variants", "kc-variants")):
        p.add_argument(f"--{r}", default=d, help=f"label of the {r} results (default {d})")
    p.add_argument("--overrides", default=str(LOGS / "2026-11-24_readiness" / "screen_overrides.json"))
    p.add_argument("--out", default=None)
    p.add_argument("--harness-dir", default=None)
    p.add_argument("--allow-incomplete", action="store_true")
    p.add_argument("--workers", type=int, default=1, help="questions compared at once (default 1)")
    p = sub.add_parser("build-briefs")
    p.add_argument("--positions", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--compare", default=None)
    p.add_argument("--label", default=None)
    p.add_argument("--batch-size", type=int, default=0)
    p.add_argument("--workspace", default=None)
    p.add_argument("--keys", default=None)
    for name in ("review", "audit-merge"):
        p = sub.add_parser(name)
        p.add_argument("--positions", required=name == "review")
        p.add_argument("--date", required=True)
        p.add_argument("--compare", default=None)
        p.add_argument("--briefs", default="kc-brief")
        if name == "audit-merge":
            p.add_argument("--audit", default=str(LOGS / "2026-11-24_audit" / "audit_sheet.csv"))
    p = sub.add_parser("usage")
    p.add_argument("--prefix", default="")
    p.add_argument("--workspace", default=None)
    a = ap.parse_args(argv)
    fn = {"pilot-ids": cmd_pilot_ids, "build": cmd_build, "build-variants": cmd_build_variants, "run-claude": cmd_run_claude,
          "import": cmd_import, "compare": cmd_compare, "build-briefs": cmd_build_briefs, "review": cmd_review,
          "audit-merge": cmd_audit_merge, "usage": cmd_usage}[a.cmd]
    rc = fn(a)
    sys.exit(rc if isinstance(rc, int) else 0)


if __name__ == "__main__":
    main()
