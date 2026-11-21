"""
codex_batch.py - run Codex, the grader, on benchmark material in a controlled, recorded and separated way.

WHAT THIS IS AND WHY (docs/methodology/workflow.md Section 2.3 and Section 4, safeguard 6c)
Codex is used only like a teacher grading tests (owner's decision, 2026-11-21): it SCREENS the final benchmark questions now
(is each one fit to be an exam question?) and, later in the pilot, GRADES the benchmark answers of finished models. Nothing
it produces may ever reach Qwen or Pythia: OpenAI's Usage Policies forbid using its outputs as training material or training
signals. This tool is the only way Codex touches the project. Whatever Codex returns is stored only in folders with "codex"
in their name, and training-side code refuses those (code/generation/separation.py).

THE STEPS (screening; grading follows the same pattern later)
  build-screen  Check that every item is a final-benchmark question (a BM id with the benchmark slot-file fingerprint, not an
                excluded spare; DV, TV, TR, TRR and SM items are refused). Give each an anonymous id (S-<batch>-<k>), and
                write ONE folder per batch in the Codex workspace (outside the repository) holding exactly three files:
                batch.jsonl (id, question, choices; never the key), instructions.md (the pinned screen_v1 text) and
                schema.json (the verdict format). The key linking anonymous ids to benchmark items is written to the separate
                codex_keys folder, which Codex never sees.
  run           Build the full prompt (the instructions, the batch's SHA-256 and id list, then every item between markers),
                so Codex never has to open a file, and run `codex exec` with: the batch folder as working root, a read-only
                sandbox, --ephemeral (no saved session), --ignore-user-config (no personal settings, extensions or MCP
                servers), the unneeded tools switched off, the verdict schema enforced, the event stream saved. A real call
                happens ONLY with --real, and only after the owner has approved it.
                These settings are layers of defense, NOT a guarantee of isolation; the event stream is audited and the batch
                rejected if Codex ran any command or tool. For strict isolation run it under a separate Windows account.
  import        Accept the verdicts only if they match the schema exactly: one verdict per id, no missing, extra or duplicate
                ids, allowed values only, and a clean audited run. Then map the anonymous ids back to benchmark items and copy
                the batch, verdicts and provenance to data/verification_logs/<date>_codex_screen/.
  report        Collect all imported batches into screen_flags.csv for the owner, who decides every flag (fix, replace with
                a spare, or keep with a note).

PROVENANCE (no monetary cost logging, owner's decision 2026-11-21): run.json records the CLI version, the model and reasoning
setting (from the event stream), the instruction, prompt and batch SHA-256 values, the UTC times, the token counts, the exact
command and the exit status.

EXAMPLE
  python codex_batch.py build-screen --items <benchmark_filled.jsonl> --manifest data/slots/benchmark_slots.manifest.json --batch-size 50
  python codex_batch.py run --batch <codex_workspace>/2026-11-21_screen_01 --real          (only with the owner's approval)
  python codex_batch.py import --batch <codex_workspace>/2026-11-21_screen_01
  python codex_batch.py report --date 2026-11-21
"""

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "code" / "generation"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TOOL_VERSION = "codex_batch-1"
SCREEN_PROMPT = REPO / "data" / "prompts" / "screen_v1.md"
ISSUE_TYPES = ["none", "ambiguous", "missing_information", "invalid_assumption", "multiple_correct", "no_correct_option",
               "answer_format_unclear", "other"]
# Tools Codex does not need for judging text already in its prompt: switched off for every run (names checked against
# `codex features list` before a real run; an unknown name stops the run instead of being silently ignored).
DISABLE_FEATURES = ["apps", "plugins", "remote_plugin", "browser_use", "browser_use_external", "browser_use_full_cdp_access",
                    "in_app_browser", "computer_use", "image_generation", "view_image", "multi_agent", "hooks", "goals",
                    "tool_suggest"]
CONFIG_OVERRIDES = ['web_search="disabled"']
# Event-stream items that are allowed in a run; anything else (a command, a tool or MCP call, a web search, a file change)
# rejects the batch.
ALLOWED_ITEM_TYPES = {"reasoning", "agent_message"}
EXPECTED_FILES = {"batch.jsonl", "instructions.md", "schema.json"}
OUTPUT_FILES = {"prompt.txt", "events.jsonl", "stderr.txt", "verdicts.json", "run.json"}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def paths():
    p = yaml.safe_load((REPO / "configs" / "paths.yaml").read_text())
    for k in ("codex_workspace", "codex_keys", "codex_cli"):
        if not p.get(k):
            sys.exit(f"{k} is not set in configs/paths.yaml")
    return Path(p["codex_workspace"]), Path(p["codex_keys"]), Path(p["codex_cli"])


def check_outside_repo(folder):
    f = Path(folder).resolve()
    try:
        f.relative_to(REPO.resolve())
    except ValueError:
        return f
    sys.exit(f"{f} is inside the repository; Codex must only ever run in a workspace outside it. Nothing was written.")


def instructions_text(path=SCREEN_PROMPT):
    raw = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
    if "=== INSTRUCTIONS ===\n" not in raw:
        sys.exit(f"{path} has no '=== INSTRUCTIONS ===' line")
    return raw.split("=== INSTRUCTIONS ===\n", 1)[1].strip() + "\n", sha256_bytes(raw.encode("utf-8"))


def screen_schema():
    return {
        "type": "object",
        "properties": {"verdicts": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "verdict": {"type": "string", "enum": ["pass", "flag"]},
                           "issue_type": {"type": "string", "enum": ISSUE_TYPES}, "reason": {"type": "string"}},
            "required": ["id", "verdict", "issue_type", "reason"], "additionalProperties": False}}},
        "required": ["verdicts"], "additionalProperties": False,
    }


# ---------------------------------------------------------------------------------------------
# build-screen
# ---------------------------------------------------------------------------------------------
def benchmark_rows(items_path, manifest_path):
    """The final-benchmark rows, after checking each is a BM item with the benchmark's slot fingerprint and not excluded."""
    import generate_set as gs
    import set_prompts as sp
    man = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if man.get("set") != "benchmark":
        sys.exit("build-screen takes the BENCHMARK slot manifest only; Codex never sees the development, TV or training sets")
    excluded = gs.excluded_spares(manifest_path)
    rows = [json.loads(l) for l in Path(items_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in rows:
        iid = r.get("item_id", "")
        if sp.id_kind(iid) != "BM":
            sys.exit(f"{iid}: not a benchmark item; Codex sees benchmark questions only (DV, TV, TR, TRR and SM are refused)")
        gs.require_fingerprint(r, man)
        if iid in excluded:
            sys.exit(f"{iid}: a permanently excluded spare (calibration); refused")
        if r.get("status", "usable") != "usable":
            sys.exit(f"{iid}: status {r.get('status')!r}; only usable final-benchmark questions are screened")
    return rows


def cmd_build_screen(args):
    workspace, keys, _ = paths()
    workspace, keys = check_outside_repo(args.workspace or workspace), check_outside_repo(args.keys or keys)
    rows = benchmark_rows(args.items, args.manifest)
    if args.first or args.count:
        rows = rows[args.first:args.first + args.count] if args.count else rows[args.first:]
    instr, instr_sha = instructions_text()
    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    made = []
    for b in range(0, len(rows), args.batch_size):
        nn = len(list(workspace.glob(f"{date}_screen_*"))) + 1
        name = f"{date}_screen_{nn:02d}"
        folder = workspace / name
        if folder.exists():
            sys.exit(f"{folder} exists; batches are never overwritten")
        folder.mkdir(parents=True)
        part = rows[b:b + args.batch_size]
        lines, key = [], {}
        for k, r in enumerate(part, 1):
            anon = f"S-{nn:02d}-{k:03d}"
            it = r["item"]
            choices = {L: c for L, c in zip("ABCD", it.get("choices") or [])}
            lines.append(json.dumps({"id": anon, "question": it["question"], "choices": choices}, ensure_ascii=False))
            key[anon] = {"item_id": r["item_id"], "position": r.get("position")}
        batch_text = "\n".join(lines) + "\n"
        (folder / "batch.jsonl").write_text(batch_text, encoding="utf-8", newline="\n")
        (folder / "instructions.md").write_text(instr, encoding="utf-8", newline="\n")
        (folder / "schema.json").write_text(json.dumps(screen_schema(), indent=1), encoding="utf-8", newline="\n")
        keys.mkdir(parents=True, exist_ok=True)
        (keys / f"{name}_key.json").write_text(json.dumps({
            "batch": name, "kind": "screen", "instructions_file": str(SCREEN_PROMPT.relative_to(REPO).as_posix()),
            "instructions_sha256": instr_sha, "batch_sha256": sha256_bytes(batch_text.encode("utf-8")),
            "items_file": str(args.items), "manifest": str(args.manifest), "ids": key, "tool_version": TOOL_VERSION,
            "built_utc": utc_now()}, indent=1), encoding="utf-8", newline="\n")
        made.append(folder)
    for f in made:
        print(f"built {f} ({len(json.loads((keys / (f.name + '_key.json')).read_text(encoding='utf-8'))['ids'])} questions)")
    return made


# ---------------------------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------------------------
def build_prompt(folder):
    instr = (folder / "instructions.md").read_text(encoding="utf-8")
    batch = (folder / "batch.jsonl").read_bytes()
    ids = [json.loads(l)["id"] for l in batch.decode("utf-8").splitlines() if l.strip()]
    prompt = (instr + "\n" + f"Batch SHA-256: {sha256_bytes(batch)}\n" + f"Batch ids ({len(ids)}): {', '.join(ids)}\n"
              + "<<<BATCH START>>>\n" + batch.decode("utf-8") + "<<<BATCH END>>>\n")
    return prompt, ids


def codex_command(codex, folder, model=None, effort=None):
    cmd = [str(codex), "exec", "-C", str(folder), "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral",
           "--ignore-user-config", "--color", "never", "--output-schema", str(folder / "schema.json"),
           "-o", str(folder / "verdicts.json"), "--json"]
    for f in DISABLE_FEATURES:
        cmd += ["--disable", f]
    for o in CONFIG_OVERRIDES:
        cmd += ["-c", o]
    if effort:
        cmd += ["-c", f'model_reasoning_effort="{effort}"']
    if model:
        cmd += ["-m", model]
    return cmd + ["-"]


def find_key(obj, names):
    """The first value of any key in `names` anywhere in a nested JSON object."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in names and isinstance(v, (str, int, float)):
                return v
            found = find_key(v, names)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = find_key(v, names)
            if found is not None:
                return found
    return None


def audit_events(text):
    """(problems, usage, model, effort) from the JSONL event stream."""
    problems, usage, model, effort = [], {}, None, None
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            problems.append(f"event line {n} is not JSON")
            continue
        item = ev.get("item") if isinstance(ev, dict) else None
        if isinstance(item, dict) and item.get("type") and item["type"] not in ALLOWED_ITEM_TYPES:
            problems.append(f"event line {n}: Codex used {item['type']!r}; only reasoning and a final message are allowed")
        if isinstance(ev, dict) and isinstance(ev.get("usage"), dict):
            for k, v in ev["usage"].items():
                if isinstance(v, (int, float)):
                    usage[k] = usage.get(k, 0) + v
        model = model or find_key(ev, {"model"})
        effort = effort or find_key(ev, {"reasoning_effort", "effort", "model_reasoning_effort"})
    return problems, usage, model, effort


def check_features(codex):
    out = subprocess.run([str(codex), "features", "list"], capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=120)
    known = {l.split()[0] for l in out.stdout.splitlines() if l.strip()}
    unknown = [f for f in DISABLE_FEATURES if f not in known]
    if unknown:
        sys.exit(f"this Codex CLI does not know the feature(s) {unknown}; update DISABLE_FEATURES after checking "
                 f"`codex features list`. Nothing was sent.")


def cmd_run(args):
    folder = check_outside_repo(args.batch)
    _, _, codex_default = paths()
    codex = Path(args.codex or codex_default)
    present = {p.name for p in folder.iterdir()}
    if present != EXPECTED_FILES:
        sys.exit(f"{folder} must hold exactly {sorted(EXPECTED_FILES)} before a run; it holds {sorted(present)}. Nothing was sent.")
    prompt, ids = build_prompt(folder)
    cmd = codex_command(codex, folder, args.model, args.effort)
    if not args.real:
        print("Dry run (no Codex call; pass --real only with the owner's approval). The command would be:\n  "
              + " ".join(cmd) + f"\nPrompt: {len(prompt)} characters, {len(ids)} questions, SHA-256 "
              f"{sha256_bytes(prompt.encode('utf-8'))}")
        return 0
    if not codex.exists():
        sys.exit(f"the Codex CLI {codex} does not exist (did the VS Code extension update? set codex_cli in configs/paths.yaml)")
    version = subprocess.run([str(codex), "--version"], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=120).stdout.strip()
    check_features(codex)
    (folder / "prompt.txt").write_text(prompt, encoding="utf-8", newline="\n")
    run = {"tool_version": TOOL_VERSION, "batch": folder.name, "codex_cli": str(codex), "codex_version": version,
           "command": cmd, "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
           "batch_sha256": sha256_bytes((folder / "batch.jsonl").read_bytes()),
           "instructions_sha256_in_folder": sha256_bytes((folder / "instructions.md").read_bytes()),
           "n_ids": len(ids), "started_utc": utc_now(), "timeout_seconds": args.timeout}
    t0 = time.time()
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=args.timeout)
        run["exit_status"] = r.returncode
        stdout, stderr = r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        run["exit_status"] = "timeout"
        stdout = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr or b"").decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
    run["finished_utc"], run["wall_seconds"] = utc_now(), round(time.time() - t0, 1)
    (folder / "events.jsonl").write_text(stdout, encoding="utf-8", newline="\n")
    (folder / "stderr.txt").write_text(stderr, encoding="utf-8", newline="\n")
    problems, usage, model, effort = audit_events(stdout)
    run.update({"usage": usage, "model": model or "not reported", "reasoning_effort": effort or args.effort or "not reported",
                "audit_problems": problems})
    if run["exit_status"] != 0:
        problems = problems + [f"exit status {run['exit_status']}"]
    run["accepted_run"] = not problems
    (folder / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8", newline="\n")
    print(f"{folder.name}: exit {run['exit_status']}, {run['wall_seconds']}s, model {run['model']}, usage {usage}")
    if problems:
        print("RUN REJECTED: " + "; ".join(problems))
        return 2
    return 0


# ---------------------------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------------------------
def validate_verdicts(text, ids):
    """(verdicts by id, problems). Exact coverage: every id once, nothing else, allowed values only."""
    problems = []
    try:
        obj = json.loads(text)
    except ValueError as e:
        return {}, [f"verdicts are not valid JSON ({e})"]
    if not isinstance(obj, dict) or set(obj) != {"verdicts"} or not isinstance(obj["verdicts"], list):
        return {}, ["verdicts must be an object with exactly one key, 'verdicts', holding a list"]
    got = {}
    for k, v in enumerate(obj["verdicts"]):
        if not isinstance(v, dict) or set(v) != {"id", "verdict", "issue_type", "reason"}:
            problems.append(f"verdict {k}: must have exactly id, verdict, issue_type and reason")
            continue
        if not all(isinstance(v[f], str) for f in v):
            problems.append(f"verdict {k}: every field must be text")
            continue
        if v["verdict"] not in ("pass", "flag"):
            problems.append(f"{v['id']}: verdict {v['verdict']!r} is not pass or flag")
        if v["issue_type"] not in ISSUE_TYPES:
            problems.append(f"{v['id']}: issue_type {v['issue_type']!r} is not allowed")
        if v["verdict"] == "pass" and v["issue_type"] != "none":
            problems.append(f"{v['id']}: a pass must have issue_type none")
        if v["verdict"] == "flag" and v["issue_type"] == "none":
            problems.append(f"{v['id']}: a flag needs an issue_type")
        if not v["reason"].strip():
            problems.append(f"{v['id']}: empty reason")
        if v["id"] in got:
            problems.append(f"{v['id']}: more than one verdict")
        got[v["id"]] = v
    missing = [i for i in ids if i not in got]
    extra = [i for i in got if i not in set(ids)]
    if missing:
        problems.append(f"missing verdicts for {missing}")
    if extra:
        problems.append(f"verdicts for ids not in the batch: {extra}")
    return got, problems


def cmd_import(args):
    folder = check_outside_repo(args.batch)
    _, keys, _ = paths()
    key = json.loads((Path(args.keys or keys) / f"{folder.name}_key.json").read_text(encoding="utf-8"))
    run = json.loads((folder / "run.json").read_text(encoding="utf-8")) if (folder / "run.json").exists() else None
    if run is None or not run.get("accepted_run"):
        sys.exit(f"{folder.name}: no accepted run (run.json missing or the run was rejected); nothing imported. Re-run the batch.")
    batch = (folder / "batch.jsonl").read_bytes()
    if sha256_bytes(batch) != key["batch_sha256"] or sha256_bytes(batch) != run["batch_sha256"]:
        sys.exit(f"{folder.name}: batch.jsonl changed since it was built or run; nothing imported")
    ids = list(key["ids"])
    verdicts, problems = validate_verdicts((folder / "verdicts.json").read_text(encoding="utf-8")
                                           if (folder / "verdicts.json").exists() else "", ids)
    if problems:
        print(f"{folder.name}: NOT IMPORTED ({len(problems)} problem(s)); re-run the batch:")
        for p in problems:
            print("  ", p)
        return 2
    date = folder.name.split("_screen_")[0]
    out = Path(args.out_root or (REPO / "data" / "verification_logs")) / f"{date}_codex_screen" / folder.name
    if out.exists():
        sys.exit(f"{out} exists; an imported batch is never overwritten")
    out.mkdir(parents=True)
    rows = []
    for anon, info in key["ids"].items():
        v = verdicts[anon]
        rows.append({"item_id": info["item_id"], "position": info["position"], "batch": folder.name, "anon_id": anon,
                     "verdict": v["verdict"], "issue_type": v["issue_type"], "reason": v["reason"]})
    (out / "screen_results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                             encoding="utf-8", newline="\n")
    for f in ("batch.jsonl", "verdicts.json", "run.json", "instructions.md", "schema.json"):
        (out / f).write_bytes((folder / f).read_bytes())
    (out / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8", newline="\n")
    n_flag = sum(r["verdict"] == "flag" for r in rows)
    print(f"{folder.name}: imported {len(rows)} verdicts ({n_flag} flagged) -> {out}")
    return 0


# ---------------------------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------------------------
def cmd_report(args):
    root = Path(args.out_root or (REPO / "data" / "verification_logs")) / f"{args.date}_codex_screen"
    rows = []
    for f in sorted(root.glob("*/screen_results.jsonl")):
        rows += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    items = {}
    if args.items:
        for l in Path(args.items).read_text(encoding="utf-8").splitlines():
            if l.strip():
                r = json.loads(l)
                items[r["item_id"]] = r
    flagged = [r for r in rows if r["verdict"] == "flag"]
    with open(root / "screen_flags.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["position", "item_id", "issue_type", "codex_reason", "question", "choices", "answer_key",
                    "owner_decision (fix/replace/keep)", "owner_note"])
        for r in sorted(flagged, key=lambda r: r["position"] or 0):
            it = (items.get(r["item_id"]) or {}).get("item") or {}
            w.writerow([r["position"], r["item_id"], r["issue_type"], r["reason"], it.get("question", ""),
                        "\n".join(f"{L}. {c}" for L, c in zip("ABCD", it.get("choices") or [])),
                        it.get("canonical_answer", ""), "", ""])
    by_type = {}
    for r in flagged:
        by_type[r["issue_type"]] = by_type.get(r["issue_type"], 0) + 1
    summary = {"date": args.date, "screened": len(rows), "flagged": len(flagged),
               "flag_rate": round(len(flagged) / max(1, len(rows)), 4), "by_issue_type": by_type}
    (root / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=1))
    print(f"owner sheet: {root / 'screen_flags.csv'}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build-screen")
    p.add_argument("--items", required=True, help="the final benchmark positions (fill-bench output)")
    p.add_argument("--manifest", required=True, help="data/slots/benchmark_slots.manifest.json")
    p.add_argument("--batch-size", type=int, default=50)
    p.add_argument("--first", type=int, default=0, help="skip this many positions (for the first small batch)")
    p.add_argument("--count", type=int, default=0, help="take only this many positions")
    p.add_argument("--date", default=None)
    p.add_argument("--workspace", default=None, help="tests only; normally codex_workspace from configs/paths.yaml")
    p.add_argument("--keys", default=None, help="tests only; normally codex_keys from configs/paths.yaml")
    p = sub.add_parser("run")
    p.add_argument("--batch", required=True)
    p.add_argument("--codex", default=None, help="the Codex CLI (default codex_cli in configs/paths.yaml; tests: a fake)")
    p.add_argument("--model", default=None)
    p.add_argument("--effort", default=None, help="reasoning effort, recorded and passed as model_reasoning_effort")
    p.add_argument("--timeout", type=float, default=1800)
    p.add_argument("--real", action="store_true", help="actually call Codex (only with the owner's approval)")
    p = sub.add_parser("import")
    p.add_argument("--batch", required=True)
    p.add_argument("--keys", default=None)
    p.add_argument("--out-root", default=None)
    p = sub.add_parser("report")
    p.add_argument("--date", required=True)
    p.add_argument("--items", default=None, help="the benchmark positions, to show question and key on the owner sheet")
    p.add_argument("--out-root", default=None)
    args = ap.parse_args(argv)
    fn = {"build-screen": cmd_build_screen, "run": cmd_run, "import": cmd_import, "report": cmd_report}[args.cmd]
    rc = fn(args)
    sys.exit(rc if isinstance(rc, int) else 0)


if __name__ == "__main__":
    main()
