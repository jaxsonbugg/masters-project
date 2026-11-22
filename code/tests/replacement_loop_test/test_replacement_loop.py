"""Tests for code/verification/replacement_loop.py (approved plan "resolve the Codex flags", revision 2, 2026-11-21).

Everything is local and fake: Talon is fake_talon.py (ssh and scp over a temporary folder), the teacher is the fake vLLM server
of the Talon tests, Codex is code/tests/codex_test/fake_codex.py. The real generate_set.py runs, validates and collects, so the
run folders and fingerprints are genuine. No Talon job, no Codex call, no R (collect_r_keys is off here).
Usage: python test_replacement_loop.py"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import yaml

HERE = Path(__file__).resolve().parent
CODE = HERE.parents[1]
REPO = CODE.parent
sys.path.insert(0, str(CODE / "generation"))
sys.path.insert(0, str(CODE / "verification"))
import variety  # noqa: E402
import replacement_loop as rl  # noqa: E402

PY = sys.executable
FAKE_VLLM = str(CODE / "tests" / "talon_deployment_test" / "fake_vllm_server.py")
FAKE_TALON = str(HERE / "fake_talon.py")
passed = failed = 0
T = Path(tempfile.mkdtemp(prefix="rl_test_"))


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {str(detail)[:600]}")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


# ---------------------------------------------------------------- shared fixtures
FAKE_CODEX = T / "fake_codex.cmd"
FAKE_CODEX.write_text(f'@echo off\r\n"{PY}" "{CODE / "tests" / "codex_test" / "fake_codex.py"}" %*\r\nexit /b %ERRORLEVEL%\r\n',
                      encoding="ascii")
BASE_SLOTS = T / "base_slots"
variety.cmd_deal(SimpleNamespace(set="benchmark", n=1150, seed="benchmark-rltest", out=str(BASE_SLOTS),
                                 overwrite=False, taxonomy=str(variety.TAXONOMY_FILE), contexts=str(variety.CONTEXTS_FILE)))
MAN0 = json.loads((BASE_SLOTS / "benchmark_slots.manifest.json").read_text(encoding="utf-8"))
SLOTS0 = {s["item_id"]: s for s in variety.read_slots(BASE_SLOTS / "benchmark_slots.jsonl")}
# position 7's candidates fail every attempt in every round (so it stays open for 3 rounds and reaches the owner packet)
BAD = "BM1157,BM1158,BM1159,BM1163,BM1164,BM1165,BM1166,BM1167,BM1168"
port = free_port()
srv = subprocess.Popen([PY, FAKE_VLLM, str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env={**os.environ, "FAKE_DELAY": "0.0", "FAKE_BAD_ITEMS": BAD,
                            "FAKE_SERVER_ARGS": "--served-model-name qwen3.6-27b-bf16"})
time.sleep(1.5)


def make_env(name, **over):
    """A fresh world: PC slot folder, fake Talon home (repo copy with the dealt slot file), baseline positions, flags."""
    E = T / name
    slots = E / "slots"
    shutil.copytree(BASE_SLOTS, slots)
    talon = E / "talon"
    (talon / "repo" / "data" / "slots").mkdir(parents=True)
    (talon / "repo" / "data" / "prompts").mkdir(parents=True)
    (talon / "teacher_outputs").mkdir()
    for f in ("benchmark_slots.jsonl", "benchmark_slots.manifest.json"):
        shutil.copy2(BASE_SLOTS / f, talon / "repo" / "data" / "slots" / f)
    shutil.copy2(REPO / "data" / "prompts" / "benchmark_generation_v8.md", talon / "repo" / "data" / "prompts")
    # 12 baseline positions; position 3 holds a spare (an earlier substitution)
    pos = []
    for k in range(1, 13):
        iid = "BM1005" if k == 3 else f"BM{k:04d}"
        pos.append({"position": k, "item_id": iid, "status": "usable", "slot": SLOTS0[iid], "slot_scheme": "taxonomy-v2",
                    "slots_file_sha256": MAN0["slots_sha256"], "item": {"question": f"q {iid}", "choices": []}})
    (E / "positions.jsonl").write_text("".join(json.dumps(p) + "\n" for p in pos), encoding="utf-8")
    scr = E / "screen" / "2026-11-21_screen_01"
    scr.mkdir(parents=True)
    flags = [("BM0005", "ambiguous", "Two readings of the question are possible."),
             ("BM0007", "no_correct_option", "None of the options equals the correct value."),
             ("BM0009", "invalid_assumption", "The reported p-value is inconsistent with the stated statistic and degrees of freedom."),
             ("BM0011", "invalid_assumption", "The reported p-value is inconsistent with the stated statistic and degrees of freedom.")]
    (scr / "screen_results.jsonl").write_text("".join(json.dumps({"item_id": i, "verdict": "flag", "issue_type": t, "reason": r})
                                                      + "\n" for i, t, r in flags), encoding="utf-8")
    (E / "fix_classification.json").write_text(json.dumps({"BM0009": {"class": "not_computable"},
                                                           "BM0011": {"class": "display_only"}}))
    cfg = {"loop_id": "test_loop", "rounds": 3, "candidates_per_position": 3, "max_total_gpu_hours": 4.0,
           "max_gpu_hours_per_job": 1.0, "slots_per_job_max": 5, "max_codex_batches": 40, "max_retries_per_step": 1,
           "max_resumes_per_shard": 2, "gpu_hours_per_1000_slots": 3.5, "load_hours_per_job": 0.05, "collect_r_keys": False,
           "inputs": {"positions": str(E / "positions.jsonl"), "screen_results": str(E / "screen"),
                      "fix_classification": str(E / "fix_classification.json"), "extra_open": []},
           "local": {"state_root": str(E / "state"), "slots_dir": str(slots), "teacher_outputs": str(E / "pc_outputs")},
           "talon": {"host": "talon", "ssh": [PY, FAKE_TALON, "ssh"], "scp": [PY, FAKE_TALON, "scp"],
                     "root": "/fake/talon_project", "repo": "/fake/talon_project/repo",
                     "outputs": "/fake/talon_project/teacher_outputs", "env": dict(rl.APPROVED_ENV)},
           "codex": {"model": "gpt-6.2-sol", "effort": "medium", "batch_size": 50, "timeout_seconds": 60,
                     "cli": str(FAKE_CODEX), "workspace": str(E / "ws"), "keys": str(E / "keys"), "out_root": str(E / "vlogs")}}
    for k, v in over.items():
        cfg[k] = v
    (E / "pc_outputs").mkdir()
    (E / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return E


def run(E, *extra, **env):
    e = {**os.environ, "FAKE_TALON_DIR": str(E / "talon"), "FAKE_VLLM_URL": f"http://127.0.0.1:{port}/v1",
         "FAKE_CODEX_LOG": str(E / "codex.log"), **{k: str(v) for k, v in env.items()}}
    e.pop("RL_CRASH_AT", None) if "RL_CRASH_AT" not in env else None
    r = subprocess.run([PY, str(CODE / "verification" / "replacement_loop.py"), "run", "--config", str(E / "config.yaml"),
                        "--poll-seconds", "0", *extra], capture_output=True, text=True, encoding="utf-8", env=e)
    return r.returncode, r.stdout + r.stderr


def ledger(E):
    return json.loads((E / "state" / "test_loop" / "ledger.json").read_text(encoding="utf-8"))


def submits(E):
    lines = [l for l in (E / "talon" / "commands.log").read_text(encoding="utf-8").splitlines() if "submit_pipeline.sh" in l]
    import re
    return Counter(re.search(r"GEN_SHARD=(\S+) GEN_FIRST=(\d+) GEN_COUNT=(\d+)", l).groups() for l in lines)


def stop_reports(E):
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted((E / "state" / "test_loop").glob("stop_report_*.json"))]


try:
    # ------------------------------------------------------------ 1. the standing approval cannot be widened
    print("[1] configuration limits and allowed actions")
    E0 = make_env("limits")
    cfg0 = rl.load_config(E0 / "config.yaml")
    for label, change in [("TIME_GENERATE 02:00:00", lambda c: c["talon"]["env"].__setitem__("TIME_GENERATE", "02:00:00")),
                          ("GPU_COUNT 2", lambda c: c["talon"]["env"].__setitem__("GPU_COUNT", 2)),
                          ("a 6 GPU-hour budget (above the 5.0 cap)", lambda c: c.__setitem__("max_total_gpu_hours", 6.0)),
                          ("300 slots per job", lambda c: c.__setitem__("slots_per_job_max", 300)),
                          ("2 retries", lambda c: c.__setitem__("max_retries_per_step", 2)),
                          ("4 rounds", lambda c: c.__setitem__("rounds", 4))]:
        c = yaml.safe_load((E0 / "config.yaml").read_text())
        change(c)
        bad = E0 / "bad.yaml"
        bad.write_text(yaml.safe_dump(c))
        try:
            rl.load_config(bad)
            refused = False
        except SystemExit as e:
            refused = "refused" in str(e)
        check(f"a configuration with {label} is refused at load", refused)
    tal = rl.Talon(cfg0)
    good = tal.submit_cmd(1, 12, 1, 3)
    for label, cmd in [("scancel", "scancel 501"), ("rm", "rm -rf ~/talon_project"),
                       ("another stage", good.replace("generate", "pipeline")),
                       ("two GPUs", good.replace("GPU_COUNT=1", "GPU_COUNT=2")),
                       ("a 2-hour wall time", good.replace("TIME_GENERATE=01:00:00", "TIME_GENERATE=02:00:00")),
                       ("the primary slot file", good.replace("benchmark_replacements.jsonl", "benchmark_slots.jsonl")),
                       ("the training prompt", good.replace("GEN_PROMPT=benchmark", "GEN_PROMPT=training")),
                       ("an appended command", good + "; rm -rf ~"),
                       ("a repository refresh", "cd ~/talon_project && git archive"),
                       ("cat of another file", "cat /fake/talon_project/repo/configs/talon/talon_settings.sh")]:
        try:
            tal.ssh(cmd)
            ok = False
        except rl.StopLoop as s:
            ok = s.condition == "action not allowed"
        check(f"a remote command that is not allowed ({label}) stops the controller before anything is sent", ok)
    for label, fn in [("copy to another Talon file", lambda: tal.scp_to(E0 / "config.yaml", "/fake/talon_project/repo/configs/talon/common.sh")),
                      ("copy from outside the outputs", lambda: tal.scp_from("/fake/talon_project/models", T))]:
        try:
            fn()
            ok = False
        except rl.StopLoop as s:
            ok = s.condition == "action not allowed"
        check(f"{label} is refused", ok)
    check("the approved submission command is accepted by the allow-list",
          any(__import__("re").fullmatch(p, good) for p in tal.allowed_ssh))

    plan = rl.open_positions(cfg0)
    check("round-1 open positions: the earlier substitution (3), the serious flags (5, 7) and the not-computable printout "
          "flag (9); the display-only printout flag (11) stays for the owner's hand fix",
          sorted(plan) == [3, 5, 7, 9], plan)

    # ------------------------------------------------------------ 2. end to end, with a crash at every step
    print("[2] end to end over three rounds, killed at every step and resumed")
    E = make_env("e2e")
    outs = []
    for point in ["after_deal", "after_upload", "after_intent", "after_sbatch", "after_build", "before_codex_run"]:
        rc, out = run(E, RL_CRASH_AT=point)
        outs.append((point, rc))
        check(f"killed at {point}: the process died there (exit 99) and the ledger is readable", rc == 99 and ledger(E), out[-500:])
    rc, out = run(E)
    L = ledger(E)
    sub = submits(E)
    check("after the crashes the loop ran to its end: round 3 finished with position 7 open (stop: round limit)",
          rc == 3 and L["stopped"]["condition"] == "round limit" and L["rounds"]["3"]["still_open"] == [7], out[-800:])
    check("no shard was ever submitted twice (the crash right after sbatch was reconciled, not resubmitted)",
          all(n == 1 for n in sub.values()) and len(sub) == 5, sub)
    sh1 = L["rounds"]["1"]["shards"]["1"]["attempts"]
    check("shard 1's ledger shows the crash before sbatch as 'not_submitted' and the crash after it as a reconciled job",
          [a["state"] for a in sh1] == ["not_submitted", "finished"] and sh1[1].get("reconciled"), sh1)
    reps = variety.read_slots(E / "slots" / "benchmark_replacements.jsonl")
    check("the crash right after dealing did not deal twice: 12 + 3 + 3 candidates, BM1151-BM1168",
          [r["item_id"] for r in reps] == [f"BM{k}" for k in range(1151, 1169)], [r["item_id"] for r in reps][:3])
    check("every candidate keeps its position's dealt subtopic, difficulty, answer type, setting and letter",
          all(all(r[k] == SLOTS0[r["replaces"]][k] for k in ("subtopic", "difficulty", "answer_type", "context", "preferred_letter"))
              for r in reps))
    final = [json.loads(l) for l in Path(L["positions_current"]).read_text(encoding="utf-8").splitlines()]
    byk = {p["position"]: p for p in final}
    check("position 3 (screen flagged BM1151, the fake's first id) took BM1152; positions 5 and 9 took their first candidates",
          (byk[3]["item_id"], byk[5]["item_id"], byk[9]["item_id"]) == ("BM1152", "BM1154", "BM1160"),
          (byk[3]["item_id"], byk[5]["item_id"], byk[9]["item_id"]))
    check("each filled position records the original slot it replaces and the Codex batches that passed it",
          byk[5]["replaces"] == "BM0005" and byk[5]["codex_screen"] and byk[5]["codex_align"])
    check("positions that were not open are unchanged (position 11 keeps its question for the owner's hand fix)",
          byk[11]["item_id"] == "BM0011" and byk[1]["item_id"] == "BM0001")
    pk = list(__import__("csv").DictReader(open(E / "state" / "test_loop" / "owner_review_packet.csv", encoding="utf-8-sig")))
    check("the owner-review packet lists all 9 candidates of position 7 from all three rounds, with status and verdicts",
          len(pk) == 9 and {r["position"] for r in pk} == {"7"} and all(r["status"] == "failed" for r in pk), len(pk))
    check("the Codex batch interrupted by the crash was counted and retried once; the alignment batch ran once (3 runs)",
          L["codex_batches_run"] == 3, L["codex_batches_run"])
    check("the stop report says the controller stops before the hand corrections, the audit and the freeze",
          "before the owner's hand corrections" in stop_reports(E)[-1]["note"])
    rc, out = run(E)
    check("a finished loop does nothing when started again", rc == 0 and "already ended" in out and submits(E) == sub, out[-300:])

    # ------------------------------------------------------------ 3. the GPU budget
    print("[3] the total GPU budget is a hard stop")
    E = make_env("budget", max_total_gpu_hours=2.0)
    rc, out = run(E, FAKE_TALON_HOURS="0.8")
    check("with a 2.0 budget and jobs that really take 0.8 h, the third job is never submitted (1.6 measured + 1.0 > 2.0): "
          "budget stop", rc == 3 and stop_reports(E)[-1]["condition"] == "budget" and sum(submits(E).values()) == 2,
          (out[-400:], submits(E)))
    L = ledger(E)
    check("before stopping it waited for the two running jobs to be measured (no stop on the pessimistic 1.0 charge)",
          any("waiting for them to be measured" in h["event"] for h in L["history"])
          and all(abs((a.get("gpu_hours") or 0) - 0.8) < 0.01 for s in L["rounds"]["1"]["shards"].values() for a in s["attempts"]),
          [h["event"] for h in L["history"]][-4:])
    E = make_env("budget_defer", max_total_gpu_hours=2.0)
    rc, out = run(E, "--max-steps", "12")
    L = ledger(E)
    check("with the same 2.0 budget and short jobs, the third job waits for the first two to be measured, then is submitted",
          sum(submits(E).values()) == 3 and any("waiting for them to be measured" in h["event"] for h in L["history"])
          and not (L.get("stopped") or {}).get("condition") == "budget", (submits(E), L.get("stopped")))

    # ------------------------------------------------------------ 4. bounded retries, unfinished shards
    print("[3b] amend-budget: only the GPU budget may change, the old version must be the one the loop started with")
    E = make_env("amend", max_total_gpu_hours=2.0)
    rc, out = run(E, FAKE_TALON_HOURS="0.8")
    old_cfg = E / "config_old.yaml"
    shutil.copy2(E / "config.yaml", old_cfg)
    def amend(*extra):
        r = subprocess.run([PY, str(CODE / "verification" / "replacement_loop.py"), "amend-budget", "--config",
                            str(E / "config.yaml"), *extra], capture_output=True, text=True, encoding="utf-8")
        return r.returncode, r.stdout + r.stderr
    c = yaml.safe_load(old_cfg.read_text()); c["max_total_gpu_hours"] = 3.0; c["candidates_per_position"] = 2
    (E / "config.yaml").write_text(yaml.safe_dump(c, sort_keys=False))
    rca, outa = amend("--old-config", str(old_cfg), "--reason", "test")
    check("an amendment that also changes another setting is refused, and the ledger is unchanged",
          rca != 0 and "only max_total_gpu_hours" in outa and not ledger(E).get("amendments"), outa[-300:])
    c["candidates_per_position"] = 3
    (E / "config.yaml").write_text(yaml.safe_dump(c, sort_keys=False))
    rca, outa = amend("--old-config", str(E / "positions.jsonl"), "--reason", "test")
    check("an amendment whose --old-config is not the starting version is refused", rca != 0 and "not the configuration" in outa)
    rca, outa = amend("--old-config", str(old_cfg), "--reason", "owner raised the budget (test)")
    rc, out = run(E, "--max-steps", "6")
    L = ledger(E)
    check("a budget-only amendment is recorded in the ledger and the loop resumes: the third job is submitted",
          rca == 0 and L["amendments"][-1]["new"] == 3.0 and sum(n for (sh, first, cnt), n in submits(E).items() if first == "1") == 3,
          (outa[-200:], out[-300:], submits(E)))

    print("[4] a failing job is retried once; an unfinished shard resumes under the same identifier")
    E = make_env("retry")
    rc, out = run(E, FAKE_TALON_FAIL_TAG="benchmark-benchmark-p1n12-2of3")
    check("a job that fails twice stops the loop (repeated failure) after exactly one retry",
          rc == 3 and stop_reports(E)[-1]["condition"] == "repeated failure" and submits(E)[("2/3", "1", "12")] == 2,
          (out[-400:], submits(E)))
    E = make_env("unfinished")
    rc, out = run(E, "--max-steps", "12", FAKE_TALON_UNFINISHED_ONCE="benchmark-benchmark-p1n12-1of3")
    L = ledger(E)
    a1 = L["rounds"]["1"]["shards"]["1"]["attempts"]
    check("a shard that hits the time limit unfinished is resubmitted with the same identifier and completes",
          [a["state"] for a in a1] == ["unfinished", "finished"] and submits(E)[("1/3", "1", "12")] == 2, a1)

    print("[4b] a dropped connection while waiting is retried; it never turns a job into a failure")
    E = make_env("conn_blip")
    rc, out = run(E, "--max-steps", "14", FAKE_TALON_DOWN_CALLS="4")
    L = ledger(E)
    states = [a["state"] for s in L["rounds"]["1"]["shards"].values() for a in s["attempts"]]
    check("four failed status reads (VPN drop) are retried while waiting; no job is marked failed and none is resubmitted",
          "failed" not in states and sum(n for (sh, first, cnt), n in submits(E).items() if first == "1") == 3
          and any("Talon unreachable" in h["event"] for h in L["history"]), (states, out[-400:]))
    E = make_env("conn_long")
    rc, out = run(E, FAKE_TALON_DOWN_CALLS="50", RL_CONN_TOLERANCE_SECONDS="0")
    L = ledger(E)
    states = [a["state"] for s in L["rounds"]["1"]["shards"].values() for a in s["attempts"]]
    check("a connection that stays down past the tolerance stops the loop, and the jobs are still recorded as submitted, "
          "not failed", rc == 3 and stop_reports(E)[-1]["condition"] == "repeated failure" and "failed" not in states,
          (states, out[-300:]))

    # ------------------------------------------------------------ 5. a lost answer from sbatch
    print("[5] a submission whose answer was lost: reconciled, or a stop when it cannot be established")
    E = make_env("lost")
    rc, out = run(E, FAKE_TALON_LOSE_ANSWER="benchmark-benchmark-p1n12-1of3")
    check("a dropped connection during sbatch stops with 'submission uncertain' (nothing resubmitted)",
          rc == 3 and stop_reports(E)[-1]["condition"] == "submission uncertain" and sum(submits(E).values()) == 1, out[-400:])
    rc, out = run(E, "--max-steps", "4", FAKE_TALON_UNREADABLE_LOG="1")
    check("when submit_log.txt cannot be read, the controller stops again rather than risk a duplicate",
          rc == 3 and stop_reports(E)[-1]["condition"] == "submission uncertain" and sum(submits(E).values()) == 1
          and ledger(E)["rounds"]["1"]["shards"]["1"]["attempts"][-1]["state"] == "submitting", out[-400:])
    rc, out = run(E, "--max-steps", "4")
    a = ledger(E)["rounds"]["1"]["shards"]["1"]["attempts"]
    check("with every source readable, the job found in the queue / submit log is adopted, not submitted again",
          a[-1]["state"] in ("submitted", "finished") and a[-1].get("reconciled") and submits(E)[("1/3", "1", "12")] == 1, a)

    # ------------------------------------------------------------ 6. Codex retries
    print("[6] a rejected Codex batch is retried once; a second rejection stops the loop")
    E = make_env("codexfail")
    rc, out = run(E, FAKE_CODEX_FAIL_FIRST="2", FAKE_CODEX_COUNTER=str(E / "codex_counter.txt"))
    check("two rejected answers for the same batch stop the loop (repeated failure)",
          rc == 3 and stop_reports(E)[-1]["condition"] == "repeated failure" and "rejected again" in stop_reports(E)[-1]["detail"],
          out[-500:])
    E = make_env("codexmax", max_codex_batches=1)
    rc, out = run(E)
    check("the Codex budget stops the loop before a batch beyond max_codex_batches is sent",
          rc == 3 and stop_reports(E)[-1]["condition"] == "budget" and ledger(E)["codex_batches_run"] == 1, out[-400:])

    # ------------------------------------------------------------ 7. the ledger
    print("[7] the ledger: atomic writes, configuration pinned")
    E = make_env("ledger")
    run(E, "--max-steps", "2")
    (E / "state" / "test_loop" / "ledger.json.tmp").write_text("{half a ledg")
    rc, out = run(E, "--max-steps", "1")
    check("a half-written temporary file (a crash during a save) is ignored; the last complete ledger is used",
          ledger(E)["phase"] in ("submit", "wait"), out[-300:])
    c = yaml.safe_load((E / "config.yaml").read_text())
    c["candidates_per_position"] = 2
    (E / "config.yaml").write_text(yaml.safe_dump(c, sort_keys=False))
    rc, out = run(E)
    check("a configuration changed after the loop started is refused (ledger mismatch), and the ledger is not overwritten",
          rc == 3 and "ledger mismatch" in out and ledger(E)["config_sha256"] != rl.load_config(E / "config.yaml")["_sha256"], out[-300:])
finally:
    srv.terminate()

shutil.rmtree(T, ignore_errors=True)
print(f"\n==== replacement loop tests: {passed} passed, {failed} failed ====")
sys.exit(1 if failed else 0)
