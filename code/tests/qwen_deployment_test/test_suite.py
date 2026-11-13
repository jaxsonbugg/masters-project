"""Local test suite for code/generation/open_teacher_test.py (see README.md in this folder).
A fake model server stands in for llama-server (and vLLM). Nothing here touches Redhawk, Talon or the network.
Usage: python test_suite.py [work_dir]      (work_dir defaults to a new temporary folder that is deleted at the end)
Needs R (path in configs/paths.yaml) for the scoring checks. Model-written R may only run in the R sandbox, which is
not built yet; the fake server's replies are R code we wrote ourselves, so section [2] sets the test-only switch
MP_TRUSTED_TEST_R=1 after checking that `score` and `verify` refuse without it."""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PY = os.environ.get("OTT_TEST_PYTHON", sys.executable)
CODE = Path(__file__).resolve().parents[2]            # .../code
OTT = str(CODE / "generation" / "open_teacher_test.py")
GEN = str(CODE / "generation" / "generate_benchmark.py")
OWN_TMP = len(sys.argv) < 2
S = Path(sys.argv[1]) if not OWN_TMP else Path(tempfile.mkdtemp(prefix="ott_suite_"))
WORK = S / "suite"
shutil.rmtree(WORK, ignore_errors=True); WORK.mkdir(parents=True)
# `score` copies its results into results/open_teacher_test/ inside the repository; remember what was there so the
# tests can remove only what they created.
REVIEW = CODE.parent / "results" / "open_teacher_test"
REVIEW_BEFORE = set(p.name for p in REVIEW.glob("*")) if REVIEW.exists() else None

# ------------------------------------------------------------------ fake server
STATE = {"mode": "good", "calls": {}, "fail_once": set(), "failed": set(), "cur": 0, "max": 0, "delay": 0.0,
         "usage": (2000, 8000), "http500_every": 0, "n": 0}
LOCK = threading.Lock()

def make_item(cat, sub, diff, atype):
    it = {"question": "x", "answer_type": atype, "choices": [], "working": "w", "r_solution": "", "canonical_answer": "",
          "answer_tolerance": 0, "r_check": "", "explanation": "A short explanation sentence.", "difficulty": diff,
          "category": cat, "subtopic": sub}
    if atype == "number":
        it.update(question="A fair coin is tossed 5 times. What is the probability of exactly 2 heads? Give your answer to 3 decimal places.",
                  r_solution="cat(dbinom(2, 5, 0.5))", canonical_answer="0.313", answer_tolerance=0.0005)
    elif atype == "multiple_choice":
        it.update(question="Which statement about the sample mean is true?",
                  choices=["It is unbiased for the population mean", "It is always equal to the median", "It ignores outliers", "It has zero variance"],
                  canonical_answer="A")
    elif atype == "r_expression":
        it.update(question="Write one line of R that returns the sum of the integers from 1 to 10.", canonical_answer="sum(1:10)",
                  r_check="isTRUE(all.equal(eval(parse(text = candidate)), 55))")
    return it

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        user = body["messages"][1]["content"]
        iid = re.search(r"item (BM\d{4})", user).group(1)
        g = lambda k: re.search(rf"^{k}: (\S+)", user, re.M).group(1)
        cat, diff, atype = g("Category"), g("Difficulty"), g("Answer type")
        sub = re.search(r"^Subtopic: (.+)$", user, re.M).group(1)
        with LOCK:
            STATE["calls"][iid] = STATE["calls"].get(iid, 0) + 1
            STATE["cur"] += 1; STATE["max"] = max(STATE["max"], STATE["cur"]); STATE["n"] += 1; n = STATE["n"]
        time.sleep(STATE["delay"])
        with LOCK: STATE["cur"] -= 1
        if (iid in STATE["fail_once"] and iid not in STATE["failed"]) or (STATE["http500_every"] and n % STATE["http500_every"] == 0):
            STATE["failed"].add(iid)
            self.send_response(500); self.end_headers(); self.wfile.write(b"boom"); return
        item = make_item(cat, sub, diff, atype)
        mode = STATE["mode"]; fin = "stop"
        if mode == "badjson": content = "I believe the answer is 42."
        elif mode == "truncated": content, fin = "", "length"
        elif mode == "slotmismatch": item["category"] = "conceptual" if cat != "conceptual" else "numerical"; content = json.dumps(item)
        else: content = "```json\n" + json.dumps(item) + "\n```" if int(iid[2:]) % 2 else json.dumps(item)
        pt, ct = STATE["usage"]
        out = {"model": body["model"], "choices": [{"message": {"content": content, "reasoning_content": "let me think"}, "finish_reason": fin}],
               "usage": {"prompt_tokens": pt, "completion_tokens": ct}}
        data = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(data)

srv = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_port}/v1"

def reset(**kw):
    STATE.update({"mode": "good", "calls": {}, "fail_once": set(), "failed": set(), "cur": 0, "max": 0, "delay": 0.0,
                  "usage": (2000, 8000), "http500_every": 0, "n": 0}); STATE.update(kw)

def cli(root, *args):
    r = subprocess.run([PY, OTT, "--out-root", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond: passed += 1; print(f"  PASS  {name}")
    else: failed += 1; print(f"  FAIL  {name}  {detail}")

def last_run(root, pattern="*"):
    return sorted(Path(root).glob(pattern))[-1]

def rows(d): return [json.loads(l) for l in (Path(d) / "responses.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

# ------------------------------------------------------------------ 1. dev slots are separate from main slots
print("\n[1] smoke slots are separate from the main slots")
R1 = WORK / "r1"; reset()
rc, out = cli(R1, "run", "--backend", "redhawk", "--base-url", URL, "--smoke-set", "A")
d = last_run(R1, "*smokeA*"); meta = json.loads((d / "run_log.json").read_text())
check("smoke A runs BM9001-BM9002 only", meta["slot_ids"] == ["BM9001", "BM9002"] and meta["slot_set"] == "dev_smoke", meta["slot_ids"])
rc, out = cli(R1, "run", "--backend", "redhawk", "--base-url", URL, "--smoke-set", "B")
meta = json.loads((last_run(R1, "*smokeB*") / "run_log.json").read_text())
check("smoke B runs BM9003-BM9004", meta["slot_ids"] == ["BM9003", "BM9004"], meta["slot_ids"])
rc, out = cli(R1, "run", "--backend", "redhawk", "--base-url", URL, "--n", "5", "--start", "9001")
check("a main run refuses development slots", rc != 0 and "main run may only contain" in out, out[-200:])
rc, out = cli(R1, "run", "--backend", "redhawk", "--base-url", URL, "--n", "100", "--start", "50")
check("a main run refuses slots beyond BM0120", rc != 0 and "main run may only contain" in out, out[-200:])
check("smoke runs never touched BM0021-BM0120 slot ids", all(int(r["item_id"][2:]) >= 9000 for r in rows(d)))

# ------------------------------------------------------------------ 2. smoke validate + score end to end
print("\n[2] smoke replies are saved, tied to slots, and parse and score through the real pipeline")
d = last_run(R1, "*smokeA*")
rc, out = cli(R1, "validate", "--run", str(d))
check("validate exits 0 on a clean smoke run", rc == 0 and "VALIDATE_RESULT infra=PASS quality_replies=0 replies=2" in out, out[-300:])
rs = rows(d)
check("every row is dev_test_only and has a slot id and an attempt", all(r["use"] == "dev_test_only" and r["item_id"] and r["attempt"] == 1 for r in rs))
check("separate reasoning was captured", any("reasoning_content" in json.dumps(r) for r in rs))
# Model-written R may only run in the R sandbox (workflow.md Section 4, safeguard 10), which is not built yet, so
# without the test-only switch `score` and `verify` must refuse before doing anything (fail closed).
ENV_NO_SWITCH = {k: v for k, v in os.environ.items() if k != "MP_TRUSTED_TEST_R"}
r0 = subprocess.run([PY, OTT, "--out-root", str(R1), "score", "--run", str(d)], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", env=ENV_NO_SWITCH)
check("score refuses to run R without the R sandbox (fail closed, nothing written)",
      r0.returncode != 0 and "Refusing to run R" in r0.stdout + r0.stderr and not (d / "items.jsonl").exists(),
      (r0.stdout + r0.stderr)[-300:])
# From here on the switch is set: the fake server's replies are R code we wrote ourselves (make_item above),
# not model output, which is the only case the switch is for.
os.environ["MP_TRUSTED_TEST_R"] = "1"
rc, out = cli(R1, "score", "--run", str(d))
check("score (with R) parses both replies and passes every check", rc == 0 and "passed every automatic check on the first attempt 2/2" in out, out[-500:])
items = [json.loads(l) for l in (d / "items.jsonl").read_text(encoding="utf-8").splitlines()]
num = [i for i in items if i["answer_type"] == "number"][0]
check("the number key came from R (0.3125 rounded half up to 0.313)", num["key_source"] == "r" and num["canonical_answer"] == "0.313", num.get("canonical_answer"))
vr = subprocess.run([PY, GEN, "verify", "--items", str(d / "items.jsonl")], capture_output=True, text=True, encoding="utf-8")
check("the existing `verify` command accepts the scored items", "ok" in vr.stdout and vr.returncode == 0, vr.stdout[-300:] + vr.stderr[-300:])
vr0 = subprocess.run([PY, GEN, "verify", "--items", str(d / "items.jsonl")], capture_output=True, text=True,
                     encoding="utf-8", errors="replace", env=ENV_NO_SWITCH)
check("verify refuses to run R without the R sandbox (fail closed)",
      vr0.returncode != 0 and "Refusing to run R" in vr0.stdout + vr0.stderr, (vr0.stdout + vr0.stderr)[-300:])

# ------------------------------------------------------------------ 3. validate: infrastructure vs model quality
print("\n[3] validate separates INFRASTRUCTURE failures (exit 1) from MODEL-QUALITY findings (exit 2)")
def fresh(mode="good", set_="A", **kw):
    reset(mode=mode, **kw); root = WORK / f"r3_{mode}_{time.time_ns()}"
    cli(root, "run", "--backend", "redhawk", "--base-url", URL, "--smoke-set", set_)
    return root, last_run(root, "*smoke*")
root, d = fresh("badjson"); rc, out = cli(root, "validate", "--run", str(d))
check("invalid JSON -> exit 2 (quality only)", rc == 2 and "infra=PASS" in out and "not parseable JSON" in out, out[-300:])
root, d = fresh("truncated"); rc, out = cli(root, "validate", "--run", str(d))
check("truncated reply -> exit 2 (quality only)", rc == 2 and "cut off at max_tokens" in out and "infra=PASS" in out, out[-300:])
root, d = fresh("slotmismatch"); rc, out = cli(root, "validate", "--run", str(d))
check("reply whose fields disagree with its slot -> exit 2 (quality)", rc == 2 and "differs from the slot" in out, out[-300:])
root, d = fresh("good")
orig = (d / "responses.jsonl").read_text(encoding="utf-8").splitlines()
(d / "responses.jsonl").write_text(orig[0] + "\n", encoding="utf-8")
rc, out = cli(root, "validate", "--run", str(d)); check("a missing slot (incomplete run) -> exit 1 infrastructure", rc == 1 and "INCOMPLETE" in out, out[-300:])
(d / "responses.jsonl").write_text("\n".join(orig + [orig[0]]) + "\n", encoding="utf-8")
rc, out = cli(root, "validate", "--run", str(d)); check("duplicate slot reply -> exit 1 infrastructure", rc == 1 and "exactly one" in out, out[-300:])
foreign = json.loads(orig[0]); foreign["item_id"] = "BM0050"
(d / "responses.jsonl").write_text("\n".join(orig + [json.dumps(foreign)]) + "\n", encoding="utf-8")
rc, out = cli(root, "validate", "--run", str(d)); check("a reply for a slot outside the run -> exit 1", rc == 1 and "not part of this run" in out, out[-300:])
(d / "responses.jsonl").write_text("\n".join(orig) + "\n" + orig[0][:40], encoding="utf-8")
rc, out = cli(root, "validate", "--run", str(d)); check("a half-written last line -> exit 1", rc == 1 and "not valid JSON" in out, out[-300:])
(d / "responses.jsonl").write_text("\n".join(orig) + "\n", encoding="utf-8")
rc, out = cli(root, "validate", "--run", str(d)); check("restored file validates clean (exit 0)", rc == 0, out[-200:])
m = json.loads((d / "run_log.json").read_text()); good_meta = json.dumps(m, indent=2)
for label, change in [("slot ids mixed with main slots", {"slot_ids": ["BM9001", "BM0050"]}), ("sampling changed", {"sampling": {"temperature": 0.2}}),
                      ("prompt hash differs", {"prompt_sha256": "0" * 64}), ("attempts_per_slot 2", {"attempts_per_slot": 2}),
                      ("slot_set unknown", {"slot_set": "other"}), ("not marked dev_test_only", {"use": "benchmark"})]:
    (d / "run_log.json").write_text(json.dumps({**m, **change}, indent=2))
    rc, out = cli(root, "validate", "--run", str(d)); check(f"invalid metadata ({label}) -> exit 1", rc == 1 and "INFRASTRUCTURE FAIL" in out, out[-250:])
(d / "run_log.json").unlink()
rc, out = cli(root, "validate", "--run", str(d)); check("missing run_log.json -> exit 1", rc == 1 and "run_log.json is missing" in out, out[-250:])
(d / "run_log.json").write_text(good_meta)
bad = json.loads(orig[0]); bad["response"]["usage"] = {}
(d / "responses.jsonl").write_text("\n".join([json.dumps(bad)] + orig[1:]) + "\n", encoding="utf-8")
rc, out = cli(root, "validate", "--run", str(d)); check("malformed reply envelope (no token counts) -> exit 1", rc == 1 and "token counts" in out, out[-250:])

# ------------------------------------------------------------------ 4. resume safety (Redhawk backend, free)
print("\n[4] a resumed run cannot overwrite, repeat or mix")
R4 = WORK / "r4"; reset(fail_once={"BM0022"})
rc, out = cli(R4, "run", "--backend", "redhawk", "--base-url", URL, "--n", "4", "--start", "21", "--concurrency", "2")
d = last_run(R4, "*_test*"); first = rows(d); snap = (d / "responses.jsonl").read_bytes()
check("first run: 3 ok, 1 errored", sorted(r["http_status"] for r in first) == [200, 200, 200, 500], [r["http_status"] for r in first])
check("the run lock was removed after the run", not (d / "run.lock").exists())
rc, out = cli(R4, "validate", "--run", str(d)); check("validate calls the half-finished run INFRASTRUCTURE incomplete (exit 1)", rc == 1 and "INCOMPLETE" in out, out[-250:])
rc, out = cli(R4, "run", "--backend", "redhawk", "--base-url", URL, "--n", "4", "--start", "21")
check("a second main run is refused without --new-run", rc != 0 and "main run folder already exists" in out, out[-250:])
calls_before = dict(STATE["calls"])
rc, out = cli(R4, "run", "--backend", "redhawk", "--base-url", URL, "--n", "4", "--start", "21", "--resume", str(d))
check("resume does not re-send the finished slots", STATE["calls"] == calls_before, (calls_before, STATE["calls"]))
check("resume does not re-send the errored slot without --retry-errors", "errored earlier and are NOT" in out and STATE["calls"].get("BM0022") == 1, out[-300:])
check("the saved file only grew by append (old bytes unchanged)", (d / "responses.jsonl").read_bytes().startswith(snap))
rc, out = cli(R4, "run", "--backend", "redhawk", "--base-url", URL, "--n", "4", "--start", "21", "--resume", str(d), "--max-tokens", "8192")
check("resume with different settings is refused", rc != 0 and "does not match the original run" in out and not (d / "run.lock").exists(), out[-300:])
(d / "run.lock").write_text('{"host":"x"}')
rc, out = cli(R4, "run", "--backend", "redhawk", "--base-url", URL, "--n", "4", "--start", "21", "--resume", str(d))
check("a lock file blocks a second writer", rc != 0 and "is locked" in out and (d / "run.lock").exists(), out[-250:])
snap2 = (d / "responses.jsonl").read_bytes()
rc, out = cli(R4, "run", "--backend", "redhawk", "--base-url", URL, "--n", "4", "--start", "21", "--resume", str(d), "--break-lock", "--retry-errors")
r = rows(d)
check("--break-lock plus --retry-errors re-sends only the errored slot, as attempt 2", [x["item_id"] for x in r[len(first):]] == ["BM0022"] and r[-1]["attempt"] == 2 and r[-1]["http_status"] == 200, [(x["item_id"], x.get("attempt")) for x in r[len(first):]])
check("old rows untouched after the retry", (d / "responses.jsonl").read_bytes().startswith(snap2))
rc, out = cli(R4, "validate", "--run", str(d)); check("after the retry the main run validates clean (exit 0)", rc == 0, out[-250:])
# a damaged file stops the resume and leaves no lock
(d / "responses.jsonl").write_text((d / "responses.jsonl").read_text(encoding="utf-8") + '{"item_id": "BM00', encoding="utf-8")
rc, out = cli(R4, "run", "--backend", "redhawk", "--base-url", URL, "--n", "4", "--start", "21", "--resume", str(d))
check("a half-written last line stops the resume cleanly (no lock left)", rc != 0 and "not valid JSON" in out and not (d / "run.lock").exists(), out[-250:])

# ------------------------------------------------------------------ 5. eight calls at once, errors, smoke cap check
print("\n[5] concurrency 8: nothing is sent twice, errored slots are not re-sent, the cap check sends one development slot")
R5 = WORK / "r5"; reset(delay=0.15, http500_every=9)
rc, out = cli(R5, "run", "--backend", "redhawk", "--base-url", URL, "--n", "100", "--start", "21", "--concurrency", "8")
d = last_run(R5, "*_test*"); rr = rows(d)
check("100 slots were answered or errored, with 8 calls in flight at once", len(rr) == 100 and STATE["max"] <= 8 and STATE["max"] >= 4, (len(rr), STATE["max"]))
check("some calls errored (every 9th) and the others succeeded", any(r["http_status"] != 200 for r in rr) and any(r["http_status"] == 200 for r in rr))
check("no automatic retries: no slot was sent twice", all(v == 1 for v in STATE["calls"].values()), {k: v for k, v in STATE["calls"].items() if v > 1})
calls_before = dict(STATE["calls"])
rc, out = cli(R5, "run", "--backend", "redhawk", "--base-url", URL, "--n", "100", "--start", "21", "--concurrency", "8", "--resume", str(d))
check("resume never re-sends finished or errored slots", STATE["calls"] == calls_before, [k for k in STATE["calls"] if STATE["calls"][k] != calls_before.get(k)])
R6 = WORK / "r6"; reset()
rc, out = cli(R6, "run", "--backend", "redhawk", "--base-url", URL, "--smoke-cap-check")
body_ok = rc == 0 and "BM9001" in out and "max_tokens 512" in out
check("smoke test A (cap check) sends exactly one dev slot with max_tokens 512", body_ok and sum(STATE["calls"].values()) == 1 and list(STATE["calls"]) == ["BM9001"], (STATE["calls"], out[-200:]))

# ------------------------------------------------------------------ 6. dry run prints the exact request, schema block included
print("\n[6] dry run")
reset(); rc, out = cli(WORK / "r7", "run", "--backend", "redhawk", "--dry-run")
check("dry run shows the prompt hash and the schema block and sends nothing", rc == 0 and "348db6ff84da29d22b2fcdeec9c13191df9d828b6af64b61146f2794b1888cc4" in out and "Output schema (JSON Schema):" in out and not STATE["calls"])
# ------------------------------------------------------------------ cleanup: leave nothing behind
if REVIEW.exists():
    for p in REVIEW.glob("*"):
        if REVIEW_BEFORE is None or p.name not in REVIEW_BEFORE:
            p.unlink()
    if REVIEW_BEFORE is None:
        REVIEW.rmdir()
srv.shutdown()
if OWN_TMP:
    shutil.rmtree(S, ignore_errors=True)
print(f"\n==== {passed} passed, {failed} failed ====")
sys.exit(1 if failed else 0)
