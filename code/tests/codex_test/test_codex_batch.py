"""Tests for code/verification/codex_batch.py (the Codex grader tool) and code/generation/separation.py.

Everything is local: Codex is replaced by fake_codex.py (through a .cmd wrapper on Windows), so no call reaches OpenAI and
no allowance is used. The workspace, the key folder and the outputs are temporary folders outside the repository.
Usage: python test_codex_batch.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "code" / "generation"))
sys.path.insert(0, str(REPO / "code" / "verification"))
import separation  # noqa: E402
import generate_set as gs  # noqa: E402

PY = sys.executable
TOOL = str(REPO / "code" / "verification" / "codex_batch.py")
passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {str(detail)[:500]}")


T = Path(tempfile.mkdtemp(prefix="grader_test_"))
WS, KEYS, OUT = T / "ws", T / "keys", T / "vlogs"
FAKE = T / "fake_codex.cmd"
FAKE.write_text(f'@echo off\r\n"{PY}" "{HERE / "fake_codex.py"}" %*\r\nexit /b %ERRORLEVEL%\r\n', encoding="ascii")
LOG = T / "calls.jsonl"


def tool(*args, env_extra=None):
    env = {**os.environ, "FAKE_CODEX_LOG": str(LOG), **(env_extra or {})}
    r = subprocess.run([PY, TOOL, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return r.returncode, r.stdout + r.stderr


# A synthetic benchmark: real manifest fingerprint, made-up questions (the real benchmark is not needed for these tests).
man_path = REPO / "data" / "slots" / "benchmark_slots.manifest.json"
man = json.loads(man_path.read_text(encoding="utf-8"))
SECRET = "KEY-THAT-CODEX-MUST-NOT-SEE"


def bm_row(k, iid=None, **over):
    return {"position": k, "item_id": iid or f"BM{k:04d}", "status": "usable", "slot_scheme": "taxonomy-v2",
            "slots_file_sha256": man["slots_sha256"],
            "item": {"question": f"Question {k}: what is 2 + {k}?", "choices": ["one", "two", "three", "four"] if k % 2 else [],
                     "canonical_answer": f"{SECRET}-{k}", "answer_type": "multiple_choice" if k % 2 else "number"}, **over}


items = T / "bench.jsonl"
items.write_text("".join(json.dumps(bm_row(k)) + "\n" for k in range(1, 8)), encoding="utf-8")
base = ["--workspace", str(WS), "--keys", str(KEYS)]

# ------------------------------------------------------------------ 1. build-screen
print("[1] build-screen: only final-benchmark questions, three files per folder, no key, key file kept apart")
rc, out = tool("build-screen", "--items", str(items), "--manifest", str(man_path), "--batch-size", "4", "--date", "2026-11-21", *base)
b1, b2 = WS / "2026-11-21_screen_01", WS / "2026-11-21_screen_02"
check("7 questions in batches of 4 give two folders", rc == 0 and b1.exists() and b2.exists(), out)
check("each folder holds exactly batch.jsonl, instructions.md and schema.json",
      {p.name for p in b1.iterdir()} == {"batch.jsonl", "instructions.md", "schema.json"})
batch1 = (b1 / "batch.jsonl").read_text(encoding="utf-8")
check("the batch carries anonymous ids, the questions and the choices, and never the answer key",
      '"S-01-001"' in batch1 and "Question 1" in batch1 and '"A": "one"' in batch1 and SECRET not in batch1
      and "BM0001" not in batch1)
key1 = json.loads((KEYS / "2026-11-21_screen_01_key.json").read_text(encoding="utf-8"))
check("the key linking anonymous ids to benchmark items is in the separate key folder, not the workspace",
      key1["ids"]["S-01-001"]["item_id"] == "BM0001" and not list(WS.rglob("*key*")))
check("the instructions in the folder are the pinned screen_v1 text", (b1 / "instructions.md").read_text(encoding="utf-8").startswith(
    "You are reviewing exam questions"))
bad = T / "bad.jsonl"
for label, row in (("a development item (DV)", bm_row(1, iid="DV0001")), ("a training item (TR)", bm_row(1, iid="TR000001")),
                   ("an item from another slot file", bm_row(1, slots_file_sha256="f" * 64)),
                   ("an item without a fingerprint", {**bm_row(1), "slot_scheme": None}),
                   ("a failed slot", bm_row(1, status="failed"))):
    bad.write_text(json.dumps(row) + "\n", encoding="utf-8")
    rc, out = tool("build-screen", "--items", str(bad), "--manifest", str(man_path), "--date", "2026-11-22", *base)
    check(f"build-screen refuses {label}", rc != 0 and not (WS / "2026-11-22_screen_01").exists(), out[-200:])
rc, out = tool("build-screen", "--items", str(items), "--manifest", str(REPO / "data" / "slots" / "dev_slots.manifest.json"), *base)
check("build-screen refuses the development set's manifest (Codex never sees it)", rc != 0 and "BENCHMARK slot manifest only" in out)
rc, out = tool("build-screen", "--items", str(items), "--manifest", str(man_path), "--workspace", str(REPO / "tmp_ws"), "--keys", str(KEYS))
check("a workspace inside the repository is refused", rc != 0 and "inside the repository" in out and not (REPO / "tmp_ws").exists())
mdir = T / "slots"
mdir.mkdir()
shutil.copy(man_path, mdir / "benchmark_slots.manifest.json")
(mdir / "benchmark_excluded_spares.json").write_text(json.dumps({"ids": ["BM0003"], "reason": "calibration"}), encoding="utf-8")
rc, out = tool("build-screen", "--items", str(items), "--manifest", str(mdir / "benchmark_slots.manifest.json"), "--date", "2026-11-23", *base)
check("a permanently excluded (calibration) spare is refused", rc != 0 and "excluded" in out)

# ------------------------------------------------------------------ 2. run
print("[2] run: dry run by default; the real call gets the instructions and exactly the batch; provenance recorded")
rc, out = tool("run", "--batch", str(b1), "--codex", str(FAKE))
check("without --real nothing calls Codex (dry run only)", rc == 0 and "Dry run" in out and not LOG.exists(), out[-300:])
rc, out = tool("run", "--batch", str(b1), "--codex", str(FAKE), "--real", "--effort", "medium")
calls = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines()]
ex = next(c for c in calls if c["argv"][:1] == ["exec"])
run1 = json.loads((b1 / "run.json").read_text(encoding="utf-8"))
check("the real run is accepted", rc == 0 and run1["accepted_run"], out[-300:])
check("the prompt Codex received holds the pinned instructions and exactly the batch's ids and questions, and no key",
      ex["stdin"].startswith("You are reviewing exam questions") and "Batch ids (4): S-01-001, S-01-002, S-01-003, S-01-004" in ex["stdin"]
      and batch1 in ex["stdin"] and SECRET not in ex["stdin"] and "S-02-001" not in ex["stdin"])
import hashlib  # noqa: E402
check("the prompt's SHA-256 in run.json is the SHA-256 of what Codex received, and the saved prompt.txt matches",
      run1["prompt_sha256"] == hashlib.sha256(ex["stdin"].encode("utf-8")).hexdigest()
      == hashlib.sha256((b1 / "prompt.txt").read_bytes()).hexdigest())
a = ex["argv"]
check("the call uses a read-only sandbox, --ephemeral, --ignore-user-config, the schema and the batch folder as root",
      a[a.index("--sandbox") + 1] == "read-only" and "--ephemeral" in a and "--ignore-user-config" in a
      and a[a.index("--output-schema") + 1].endswith("schema.json") and a[a.index("-C") + 1] == str(b1.resolve()))
check("unneeded tools are switched off (apps, plugins, browser, computer use, image tools, multi-agent, hooks, web search)",
      all(f in a for f in ("apps", "plugins", "browser_use", "computer_use", "image_generation", "multi_agent", "hooks"))
      and 'web_search="disabled"' in a)
check("provenance: version, model, reasoning setting, batch and prompt SHA-256, times, token counts, exit status",
      run1["codex_version"] == "codex-cli 9.9.9-fake" and run1["model"] == "fake-model-1" and run1["reasoning_effort"] == "medium"
      and run1["usage"] == {"input_tokens": 1200, "cached_input_tokens": 0, "output_tokens": 300}
      and run1["exit_status"] == 0 and run1["started_utc"] and run1["finished_utc"] and len(run1["batch_sha256"]) == 64)
rc, out = tool("run", "--batch", str(b1), "--codex", str(FAKE), "--real")
check("a folder that already holds outputs is not run again (results are never overwritten)", rc != 0 and "must hold exactly" in out)
rc, out = tool("run", "--batch", str(b2), "--codex", str(FAKE), "--real", env_extra={"FAKE_CODEX_NO_FEATURE": "computer_use"})
check("an unknown feature name stops the run before anything is sent", rc != 0 and "does not know the feature" in out
      and not (b2 / "prompt.txt").exists())

# ------------------------------------------------------------------ 3. import and report
print("[3] import: exact coverage only; mapped back to benchmark items; report for the owner")
rc, out = tool("import", "--batch", str(b1), "--keys", str(KEYS), "--out-root", str(OUT))
res = OUT / "2026-11-21_codex_screen" / "2026-11-21_screen_01"
rows = [json.loads(l) for l in (res / "screen_results.jsonl").read_text(encoding="utf-8").splitlines()]
check("a clean batch imports: 4 verdicts mapped back to BM0001-BM0004, 1 flagged", rc == 0 and len(rows) == 4
      and rows[0]["item_id"] == "BM0001" and rows[0]["verdict"] == "flag" and sum(r["verdict"] == "flag" for r in rows) == 1, out)
check("the batch, verdicts, run record, instructions, schema and key are kept with the results",
      {p.name for p in res.iterdir()} == {"screen_results.jsonl", "batch.jsonl", "verdicts.json", "run.json", "instructions.md",
                                          "schema.json", "key.json"})
rc, out = tool("import", "--batch", str(b1), "--keys", str(KEYS), "--out-root", str(OUT))
check("an imported batch is never overwritten", rc != 0 and "never overwritten" in out)
rc, out = tool("report", "--date", "2026-11-21", "--items", str(items), "--out-root", str(OUT))
sheet = (OUT / "2026-11-21_codex_screen" / "screen_flags.csv").read_text(encoding="utf-8-sig")
check("the owner's flag sheet lists the flagged question with Codex's reason, the key and decision columns",
      rc == 0 and "BM0001" in sheet and "a needed value is not given" in sheet and f"{SECRET}-1" in sheet and "owner_decision" in sheet)

# ------------------------------------------------------------------ 4. failure handling
print("[4] failures: each is caught, nothing is imported")


def fresh_batch(tag):
    rc, out = tool("build-screen", "--items", str(items), "--manifest", str(man_path), "--count", "3", "--date", tag, *base)
    return WS / f"{tag}_screen_01"


FAILURES = (("malformed", "import", "not valid JSON"), ("missing", "import", "missing verdicts"),
            ("extra", "import", "not in the batch"), ("duplicate", "import", "more than one verdict"),
            ("bad_enum", "import", "is not pass or flag"), ("empty", "import", "not valid JSON"),
            ("nonzero", "run", "exit status 3"), ("tool_use", "run", "command_execution"))
for k, (mode, where, expect) in enumerate(FAILURES, 1):
    tag = f"2030-{k:02d}-01"     # one dated batch folder per failure mode
    bf = fresh_batch(tag)
    rc_run, out_run = tool("run", "--batch", str(bf), "--codex", str(FAKE), "--real", env_extra={"FAKE_CODEX_MODE": mode})
    rc_imp, out_imp = tool("import", "--batch", str(bf), "--keys", str(KEYS), "--out-root", str(OUT))
    nothing = not (OUT / f"{tag}_codex_screen").exists()
    if where == "run":
        check(f"{mode}: the run is rejected and import refuses it", rc_run != 0 and expect in out_run and rc_imp != 0 and nothing,
              (out_run[-200:], out_imp[-200:]))
    else:
        check(f"{mode}: import refuses the batch ({expect})", rc_imp != 0 and expect in out_imp and nothing, out_imp[-300:])
bt = fresh_batch("2031-01-01")
rc, out = subprocess.run([PY, TOOL, "run", "--batch", str(bt), "--codex", str(FAKE), "--real", "--timeout", "3"],
                         capture_output=True, text=True, env={**os.environ, "FAKE_CODEX_MODE": "timeout"}).returncode, ""
runt = json.loads((bt / "run.json").read_text(encoding="utf-8"))
check("a run that times out is rejected", rc != 0 and runt["exit_status"] == "timeout" and not runt["accepted_run"])
bc = fresh_batch("2032-01-01")
tool("run", "--batch", str(bc), "--codex", str(FAKE), "--real")
(bc / "batch.jsonl").write_text((bc / "batch.jsonl").read_text(encoding="utf-8").replace("Question 1", "Question 99"), encoding="utf-8")
rc, out = tool("import", "--batch", str(bc), "--keys", str(KEYS), "--out-root", str(OUT))
check("a batch file changed after the run is refused at import", rc != 0 and "changed" in out)

# ------------------------------------------------------------------ 5. separation and exclusion
print("[5] separation: training-side code refuses Codex material; excluded spares are never replacements")
check("a path in the Codex workspace, key folder or results is Codex material",
      separation.is_codex_path(T / "codex_workspace" / "x.jsonl") and separation.is_codex_path(OUT / "2026-11-21_codex_screen" / "a.jsonl")
      and not separation.is_codex_path(T / "bench.jsonl"))
cx = T / "codex_out"
cx.mkdir()
(cx / "items.jsonl").write_text(json.dumps({"item_id": "TR000001"}) + "\n", encoding="utf-8")
r = subprocess.run([PY, str(REPO / "code" / "generation" / "generate_set.py"), "collect-train", "--items", str(cx / "items.jsonl"),
                    "--manifest", str(REPO / "data" / "slots" / "tv_slots.manifest.json"), "--version", "x", "--out-dir", str(T / "sets")],
                   capture_output=True, text=True)
check("collect-train refuses an input from a Codex folder", r.returncode != 0 and "Codex material" in (r.stdout + r.stderr), r.stderr[-300:])
plain = T / "plain.jsonl"
plain.write_text(json.dumps({"item_id": "TR000001", "question": "q", "codex_verdict": "pass"}) + "\n", encoding="utf-8")
r = subprocess.run([PY, str(REPO / "code" / "verification" / "decontaminate.py"), "train-pairs", "--cands", str(plain),
                    "--out", str(T / "tp.jsonl"), "--no-embeddings"], capture_output=True, text=True)
check("decontaminate refuses a row carrying a Codex field", r.returncode != 0 and "Codex field" in (r.stdout + r.stderr), r.stderr[-300:])
r = subprocess.run([PY, str(REPO / "code" / "verification" / "decontaminate.py"), "train-pairs", "--cands", str(cx / "items.jsonl"),
                    "--out", str(T / "tp2.jsonl"), "--no-embeddings"], capture_output=True, text=True)
check("decontaminate refuses an input from a Codex folder", r.returncode != 0 and "Codex material" in (r.stdout + r.stderr))
rows_fb = [{"item_id": "BM0001", "status": "failed", "slot": {"category": "c", "difficulty": "d", "answer_type": "a"}},
           {"item_id": "BM0002", "status": "usable", "slot": {"category": "c", "difficulty": "d", "answer_type": "a"}},
           {"item_id": "BM0003", "status": "usable", "slot": {"category": "c", "difficulty": "d", "answer_type": "a"}}]
rows_fb = [{**r, "slot_scheme": "taxonomy-v2", "slots_file_sha256": man["slots_sha256"]} for r in rows_fb]
pos, needs = gs.fill_bench(rows_fb, man, 1, excluded={"BM0002"})
check("fill-bench never uses an excluded (calibration) spare: BM0002 is skipped and BM0003 fills the position",
      pos[0]["item_id"] == "BM0003" and pos[0]["replaces"] == "BM0001")
greps = subprocess.run(["git", "-C", str(REPO), "grep", "-l", "-i", "codex", "--", "code/generation/generate_set.py",
                        "code/verification/decontaminate.py"], capture_output=True, text=True).stdout
check("training-side code mentions Codex only through the separation guard (no reads of Codex output)",
      all("separation" in (REPO / f).read_text(encoding="utf-8") for f in greps.split()))

shutil.rmtree(T, ignore_errors=True)
print(f"\n==== codex tool tests: {passed} passed, {failed} failed ====")
sys.exit(1 if failed else 0)
