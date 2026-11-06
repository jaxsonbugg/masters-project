# Local tests for the Talon scripts (configs/talon)

These check the plumbing of the Talon draft scripts and the small Talon additions to `code/generation/open_teacher_test.py`
**without** touching Talon, the internet or any paid service. They follow the Redhawk tests in `code/tests/qwen_deployment_test/`.

**The fakes are placeholders.** No real vLLM or Talon output existed when these were written. The scripts were deliberately written so
that no pass or fail depends on the wording of a log (only on HTTP answers, exit codes and `nvidia-smi` numbers), because the first
Redhawk pipeline job stopped on a log-wording check that agreed with my fake and not with the real program. After the first real Talon
run, its real log and a real reply replace the placeholders in `fake_vllm_server.py` and `shtest_talon.sh`.

- `shtest_talon.sh <work_dir> <1|2|3>` (a few minutes per part; the parts may run at the same time):
  - part 1: the draft guard (the review flag is read from the file, not the environment), UNSET and shared paths, layout checks (no preferred
    default, GPU_COUNT = TENSOR_PARALLEL x REPLICAS), Stage A healthy, 1, 2 and 4 fake GPUs, weights/version/flag/server failures, Stage B gates,
    quality findings, truncation and reasoning-only replies;
  - part 2: the throughput stage (one server start, one run per concurrency) and its report, truncation findings, the pipeline (A, B, main),
    the one-attempt-per-slot rule, and stops at the first failure;
  - part 3: `submit_pipeline.sh` refusals and option building, the probe scripts (accepted GPU request forms, record file, read-only), `prep_talon.sh`
    and `fetch_talon.sh` guards, and file hygiene (no carriage returns, `bash -n`).
- `test_throughput_report.py`: the throughput arithmetic on synthetic run folders, every expected number worked out by hand in a comment.
- `test_talon_python.py`: on Linux a talon run uses `talon_outputs` and a redhawk run `redhawk_outputs`, never the other way round; set T is BM9101-BM9132;
  both reasoning field names (`reasoning_content`, `reasoning`) are read.

**Run them** (from the repository root, in Git Bash; give the work folder as a bash-style path, never `C:/...`):
```
export OTT_TEST_PYTHON=/c/masters_project_large/envs/probe/Scripts/python.exe     # a Python with httpx and pyyaml
python code/tests/talon_deployment_test/test_throughput_report.py
python code/tests/talon_deployment_test/test_talon_python.py
for p in 1 2 3; do bash code/tests/talon_deployment_test/shtest_talon.sh /tmp/tt $p & done; wait
```

**What a pass does not prove.** Everything about Talon itself (host, partitions, GPU request syntax, modules, vLLM's real flags and output,
real speed, storage, allocation) can only be checked on the cluster. That is what the probe and the smoke stages are for.
