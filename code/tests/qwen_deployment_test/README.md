# Local tests for the Qwen3.6-27B deployment test

These tests check the plumbing of `code/generation/open_teacher_test.py` and the Redhawk scripts in `configs/redhawk/`
**without** touching Redhawk, Talon or the internet. They exist because a mistake found on a cluster costs queue time
(days, on Redhawk), while a mistake found here costs nothing.

**How they work.** A small fake server (`fake_server.py`) pretends to be the model server (llama-server on Redhawk, or
vLLM on Talon). It answers with realistic JSON replies that match each question slot, and it can be told to misbehave: return
invalid JSON, cut a reply off, fail once, or die while loading. The tests then run the real command-line tool and the
real job scripts against it and check what they do.

- `test_suite.py` (about 1 minute; needs R for the scoring checks): slot isolation (smoke slots BM9001-BM9004 versus main
  slots BM0021-BM0120), the two failure kinds of `validate` (infrastructure versus model quality), resume safety (no
  overwrite, no repeat, lock file, settings must match), 8 calls at once with no repeats, scoring through R. Every R run
  goes through the R sandbox (`code/generation/r_sandbox.py`; `docs/methodology/workflow.md` Section 4, safeguard 10), so
  the WSL2 sandbox must be set up (`recovery/r_sandbox.md`). The suite also checks that `score` and `verify` refuse when the
  sandbox fails its self-test.
- `shtest.sh` (a few minutes per part; four parts that can run at the same time): the Redhawk job scripts with fake
  `nvidia-smi`, `module`, `scontrol`, `squeue` and `llama-server`.
  - Parts 1-2, the single stages: GPU, weights, template and flag checks, the stage gates, the memory summary, queue wait,
    mandatory validation, the `module` command, and an incomplete main run followed by a deliberate resume.
  - Part 5, the preparation and submission scripts (`prep_cluster.sh`, `submit_pipeline.sh`): a first run, a refused second
    run, damaged copies, a failed submission, and every reason the submit script refuses (build not finished, weights not
    verified, wrong size, a pipeline job already waiting, the scheduler rejecting the request).
  - Parts 3-4, the one-job pipeline (`qwen_pipeline.sbatch`): the healthy A, B, main path; Stage B skipped or failed so the
    main run falls back to one sequence; Stage A failing so nothing else runs; every smoke reply a quality finding (stops
    unless acknowledged); a flash-attention crash retried once with it off (and never when the setting was explicit); too
    little time left for the main run; separate logs per stage; and the time-left parser.

**Run them** (from the repository root, in Git Bash):
```
python code/tests/qwen_deployment_test/test_suite.py
for p in 1 2 3 4 5; do bash code/tests/qwen_deployment_test/shtest.sh /tmp/ott_sh $p & done; wait
```
Each prints PASS or FAIL per check and ends with a count. They clean up after themselves (including the review copies
that `score` would otherwise leave in `results/open_teacher_test/`).

**What a pass does not prove.** The fake programs only imitate the real ones. Real `nvidia-smi` output, Slurm options,
module names, the llama.cpp build, flash attention on a V100 and real speed can only be checked on Redhawk, which is
what the GPU smoke tests are for.

## The Talon twin of these tests
The Talon scripts (`configs/talon/`) have their own tests in `code/tests/talon_deployment_test/`: `shtest_talon.sh` (parts 1-3: the
draft guard, GPU layout and memory checks for 1, 2 and 4 fake GPUs, the stage gates, the throughput stage, the pipeline, submit,
probe, prep and download guards), `test_throughput_report.py` (hand-computed throughput arithmetic), `test_talon_python.py` (Talon
and Redhawk output folders can never be mixed up; reasoning field names) and `fake_vllm_server.py`. They do not change how
the Redhawk tests here run, and these Redhawk tests must keep passing unchanged. See that folder's README.
