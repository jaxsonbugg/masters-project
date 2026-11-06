"""
Tests for the small Talon additions to code/generation/open_teacher_test.py. No server, no cluster, no network.

What is checked, and why:
  - On Linux (the clusters) a talon run writes under talon_outputs and a redhawk run under redhawk_outputs, never the other way
    round, and an UNSET talon_outputs stops with a message that points at the Talon scripts (not at Redhawk).
  - Commands without a backend keep the old Redhawk path (so nothing about Redhawk changed).
  - Run folders of the two clusters can never be mistaken for each other ("one main run per backend" looks only at its own label).
  - Development set T is BM9101-BM9132 (32 slots), separate from the smoke sets and from the main slots.
  - The reasoning text is found under both field names: reasoning_content (llama.cpp, older vLLM) and reasoning (newer vLLM).
Run:  python code/tests/talon_deployment_test/test_talon_python.py   (needs httpx and pyyaml, like the other tests)
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "generation"))
import open_teacher_test as ott  # noqa: E402

passed = failed = 0


def chk(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name} {detail}")


class FakeOS:
    """Stands in for the os module INSIDE open_teacher_test only, so the code believes it runs on Linux (os.name == 'posix')
    while pathlib, which reads the real os module, keeps working on Windows. Everything except .name is the real os."""
    def __init__(self, real, name):
        self._real, self.name = real, name

    def __getattr__(self, attr):
        return getattr(self._real, attr)


tmp = Path(tempfile.mkdtemp(prefix="talon_py_"))
real_paths, real_os = ott.paths, ott.os
try:
    rh, tl = tmp / "redhawk_out", tmp / "talon_out"
    rh.mkdir(); tl.mkdir()
    table = {"teacher_outputs": str(tmp / "pc_out"), "redhawk_outputs": str(rh), "talon_outputs": str(tl)}
    ott.paths = lambda: table
    ott.os = FakeOS(real_os, "posix")   # pretend to be on a cluster (Linux); restored in finally

    print("[I1] the output folder follows the backend's cluster")
    chk("talon -> talon_outputs", ott.outputs_root("talon") == tl, ott.outputs_root("talon"))
    chk("redhawk -> redhawk_outputs", ott.outputs_root("redhawk") == rh)
    chk("no backend -> redhawk_outputs, as before this change", ott.outputs_root() == rh)
    d = ott.new_run_dir("talon", "smokeA")
    chk("a new talon run folder is created under talon_outputs with the talon-bf16 label", d.parent == tl and "talon-bf16_smokeA01" in d.name)
    d2 = ott.new_run_dir("redhawk", "test")
    (d2 / "responses.jsonl").write_text("")
    chk("a redhawk main run is not counted as a talon main run (and the reverse)",
        ott.existing_main_runs("talon") == [] and ott.existing_main_runs("redhawk") == [d2])

    print("[I2] UNSET talon_outputs stops with a Talon message")
    table["talon_outputs"] = "UNSET"
    try:
        ott.outputs_root("talon")
        chk("UNSET talon_outputs stops", False)
    except SystemExit as e:
        msg = str(e)
        chk("UNSET talon_outputs stops and names talon_outputs and configs/talon", "talon_outputs is UNSET" in msg and "configs/talon" in msg, msg)
    chk("an UNSET talon key does not affect the redhawk path", ott.outputs_root("redhawk") == rh)

    print("[I3] on Windows (the PC) both backends use the PC folder, as before")
    ott.os = FakeOS(real_os, "nt")
    chk("PC: teacher_outputs for talon and redhawk", ott.outputs_root("talon") == ott.outputs_root("redhawk") == Path(table["teacher_outputs"]))
    ott.os = FakeOS(real_os, "posix")

    print("[S1] development set T")
    slots, kind, label = ott.choose_slots(argparse.Namespace(smoke_cap_check=False, smoke_set="T", n=100, start=21))
    ids = [s["item_id"] for s in slots]
    chk("set T is 32 slots BM9101-BM9132, a smoke (development) run labelled smokeT",
        len(ids) == 32 and ids[0] == "BM9101" and ids[-1] == "BM9132" and kind == "smoke" and label == "smokeT", (ids[:2], ids[-1:], kind, label))
    main_ids = set(range(ott.MAIN_FIRST, ott.MAIN_LAST + 1))
    chk("set T shares no slot number with the main slots or with sets A and B",
        not ({int(i[2:]) for i in ids} & (main_ids | {9001, 9002, 9003, 9004})))
    chk("the talon backend exists and its label differs from redhawk's",
        "talon" in ott.BACKENDS and ott.BACKENDS["talon"]["label"] != ott.BACKENDS["redhawk"]["label"])
    chk("the talon model alias equals SERVED_NAME in configs/talon/talon_settings.sh",
        'SERVED_NAME="${SERVED_NAME-' + ott.BACKENDS["talon"]["model"] + '}"' in (HERE.parents[2] / "configs" / "talon" / "talon_settings.sh").read_text(encoding="utf-8"))

    print("[R1] both reasoning field names")
    rec = lambda field: {"response": {"choices": [{"message": {"content": "{}", field: "thought"}, "finish_reason": "stop"}], "usage": {}}}
    chk("reasoning_content (llama.cpp, older vLLM)", ott.reply_parts(rec("reasoning_content"))[1] == "thought")
    chk("reasoning (newer vLLM)", ott.reply_parts(rec("reasoning"))[1] == "thought")
    chk("neither: falls back to <think> blocks in the content (unchanged)",
        ott.reply_parts({"response": {"choices": [{"message": {"content": "<think>t</think>{}"}, "finish_reason": "stop"}]}})[1] == "<think>t</think>")
finally:
    ott.paths, ott.os = real_paths, real_os
    shutil.rmtree(tmp, ignore_errors=True)

print(f"==== talon python tests: {passed} passed, {failed} failed ====")
sys.exit(1 if failed else 0)
