"""
Tests for code/generation/throughput_report.py using SYNTHETIC run folders. No server, no GPU, no cluster.

Every expected number below is worked out by hand in the comment next to it, so a mistake in the report's arithmetic
shows up as a mismatch, not as two wrong numbers agreeing with each other.

Run:  python code/tests/talon_deployment_test/test_throughput_report.py
(needs the same Python as the other tests: httpx and pyyaml installed; see code/tests/qwen_deployment_test/README.md)
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "generation"))
import throughput_report as tr  # noqa: E402

passed = failed = 0


def chk(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name} {detail}")


def reply(i, finish="stop", content='{"a": 1}', reasoning="thinking...", field="reasoning_content", status=200,
          prompt=1200, completion=3000):
    msg = {"content": content}
    if reasoning:
        msg[field] = reasoning
    row = {"item_id": f"BM{9100 + i:04d}", "use": "dev_test_only", "http_status": status, "attempt": 1, "seconds": 10.0}
    if status == 200:
        row["response"] = {"choices": [{"message": msg, "finish_reason": finish}],
                           "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}
    else:
        row["response"], row["error"] = None, "boom"
    return row


def make_run(root, name, rows, wall, gpus=2, extra_meta=None, peak=None):
    d = Path(root) / name
    d.mkdir(parents=True)
    meta = {"backend": "talon", "slot_ids": [f"BM{9100 + i:04d}" for i in range(1, 33)],
            "meta": {"gpu_count": str(gpus), "tensor_parallel": str(gpus), "replicas": "1", "max_num_seqs": "8",
                     "max_model_len": "20480", "load_seconds": "95", **(extra_meta or {})},
            "sessions": [{"concurrency": 8, "wall_seconds": wall}]}
    if gpus is None:
        del meta["meta"]["gpu_count"]
    (d / "run_log.json").write_text(json.dumps(meta), encoding="utf-8")
    (d / "responses.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    if peak:
        (d / "gpu_peak.txt").write_text(peak, encoding="utf-8")
    return d


def run_report(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = tr.main(list(argv))
    return rc, buf.getvalue()


tmp = tempfile.mkdtemp(prefix="thr_")
try:
    print("[T1] arithmetic on a mixed run: 2 GPUs, 1800 s (0.5 h), 32 replies = 30 good + 1 cut off with reasoning only + 1 HTTP 500")
    rows_a = [reply(i) for i in range(1, 31)]
    rows_a.append(reply(31, finish="length", content="", reasoning="long thinking"))          # truncated AND exhausted
    rows_a.append(reply(32, status=500))                                                       # an HTTP error
    A = make_run(tmp, "A_2gpu", rows_a, wall=1800, gpus=2, peak="gpu 0 peak_used_MiB 61000 total_MiB 81559\ngpu 1 peak_used_MiB 60500 total_MiB 81559\n")
    a = tr.analyse_run(A)
    chk("30 successes (the cut-off reply and the HTTP error are not examples)", a["successes"] == 30, a["successes"])
    chk("replies 32, HTTP errors 1", a["replies"] == 32 and a["http_errors"] == 1)
    # examples per hour = 30 / 0.5 h = 60
    chk("60 successful examples per hour", abs(a["examples_per_hour"] - 60.0) < 1e-9, a["examples_per_hour"])
    # GPU-hours per 1,000 = 2 GPUs x 0.5 h / 30 x 1000 = 33.333...
    chk("33.33 GPU-hours per 1,000 successful examples", abs(a["gpu_hours_per_1000"] - 33.3333333) < 1e-4, a["gpu_hours_per_1000"])
    # truncation rate = 1 cut-off / 31 replies with HTTP 200 = 3.2258 %
    chk("truncation rate 1/31", abs(a["trunc_rate"] - 1 / 31) < 1e-9 and a["truncated"] == 1)
    chk("reasoning-exhaustion rate 1/31 (reasoning present, no usable JSON)", abs(a["exhaust_rate"] - 1 / 31) < 1e-9 and a["exhausted"] == 1)
    # output tokens = 31 replies x 3000 = 93000 over 1800 s = 51.67 tok/s
    chk("output tokens per second 51.67", abs(a["tok_per_s"] - 93000 / 1800) < 1e-6, a["tok_per_s"])

    print("[T2] a second layout and the projection: 1 GPU, 3600 s (1 h), 32 good replies")
    B = make_run(tmp, "B_1gpu", [reply(i) for i in range(1, 33)], wall=3600, gpus=1)
    b = tr.analyse_run(B)
    # GPU-hours per 1,000 = 1 x 1 h / 32 x 1000 = 31.25 ; examples per hour = 32
    chk("1 GPU: 31.25 GPU-hours per 1,000 and 32 examples per hour", abs(b["gpu_hours_per_1000"] - 31.25) < 1e-9 and abs(b["examples_per_hour"] - 32) < 1e-9)
    rc, out = run_report("--run", str(A), "--run", str(B))
    # best 31.25 x 200 = 6,250 GPU-hours; worst 33.333 x 200 = 6,667 GPU-hours; days at 16 GPUs = 6250 / 16 / 24 = 16.3
    chk("projection: best 6,250 GPU-hours and worst 6,667 GPU-hours for 200,000", "6,250 GPU-hours" in out and "6,667 GPU-hours" in out, out[-900:])
    chk("days arithmetic: 6,250 GPU-hours on 16 GPUs = 16.3 days", "if 16 GPUs were available at once: about 16.3 days" in out)
    chk("peak memory from gpu_peak.txt is shown", "peak GPU memory: gpu 0 peak_used_MiB 61000" in out)
    chk("context-length note and UNVERIFIED note are always printed", "CONTEXT NOTE" in out and "128K" in out and "UNVERIFIED (ask Miami Research Computing)" in out)
    chk("exit code 0 when no layout is above the threshold (3.2% < 5%)", rc == 0, rc)

    print("[T3] a failed layout is listed as a result, not ignored")
    rc, out = run_report("--run", str(B), "--failed", "1gpu-bf16-tp1=out of memory while loading 54 GB weights")
    chk("failed layout printed with its reason", "NO THROUGHPUT (it did not run): out of memory while loading 54 GB weights" in out)
    chk("the projection still uses the layouts that did run", "31.25 GPU-hours per 1,000 -> 6,250 GPU-hours" in out)

    print("[T4] truncation / reasoning exhaustion above the threshold is a finding, exit 2, and cannot be hidden")
    rows_c = [reply(i) for i in range(1, 29)] + [reply(i, finish="length", content="", reasoning="x") for i in range(29, 33)]
    C = make_run(tmp, "C_cut", rows_c, wall=1800, gpus=2)
    rc, out = run_report("--run", str(C))
    # 4 of 32 = 12.5 % > 5 %
    chk("exit code 2 and a FINDINGS block naming 12.5%", rc == 2 and "FINDINGS" in out and "12.5%" in out and "should not be called comparable" in out, out[-700:])
    rc, out = run_report("--run", str(C), "--threshold", "0.2")
    chk("a looser threshold (20%) accepts the same run", rc == 0)

    print("[T5] the reasoning field may be called 'reasoning' (newer vLLM): still understood")
    rows_d = [reply(i, field="reasoning", content="", reasoning="thought") if i == 1 else reply(i, field="reasoning") for i in range(1, 33)]
    D = make_run(tmp, "D_newname", rows_d, wall=1800, gpus=2)
    d = tr.analyse_run(D)
    chk("empty content + reasoning under the name 'reasoning' counts as exhaustion", d["exhausted"] == 1 and d["successes"] == 31, (d["exhausted"], d["successes"]))

    print("[T6] reaching the context limit counts as truncation even if the server said 'stop'")
    rows_e = [reply(i) for i in range(1, 32)] + [reply(32, prompt=2000, completion=18480)]    # 2000 + 18480 = 20480 = limit
    E = make_run(tmp, "E_limit", rows_e, wall=1800, gpus=2)
    e = tr.analyse_run(E)
    chk("prompt + output = max_model_len is counted as truncated and not as a success", e["truncated"] == 1 and e["successes"] == 31, (e["truncated"], e["successes"]))

    print("[T7] unusable input is refused with a plain message (exit 1), never a guess")
    F = make_run(tmp, "F_nogpus", [reply(1)], wall=100, gpus=None)
    rc, out = run_report("--run", str(F))
    chk("a run folder without gpu_count is refused", rc == 1 and "no gpu_count" in out, out)
    G = Path(tmp) / "G_empty"
    G.mkdir()
    rc, out = run_report("--run", str(G))
    chk("a folder without run_log.json is refused", rc == 1 and "run_log.json is missing" in out, out)
    H = make_run(tmp, "H_nowall", [reply(1)], wall=0, gpus=2)
    rc, out = run_report("--run", str(H))
    chk("a run with no finished session (wall 0) is refused", rc == 1 and "wall_seconds" in out, out)

    print("[T8] no successes: GPU-hours per 1,000 is 'n/a', no projection")
    K = make_run(tmp, "K_allbad", [reply(i, status=500) for i in range(1, 5)], wall=100, gpus=2)
    rc, out = run_report("--run", str(K))
    chk("n/a and 'No layout produced a successful example'", "n/a (no successful example)" in out and "No layout produced a successful example" in out, out)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"==== throughput report tests: {passed} passed, {failed} failed ====")
sys.exit(1 if failed else 0)
