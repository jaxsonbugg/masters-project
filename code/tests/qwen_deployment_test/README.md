# Local tests for the Qwen3.6-27B deployment test

These tests check the plumbing of `code/generation/open_teacher_test.py` and the Redhawk scripts in `configs/redhawk/`
**without** touching Redhawk, the internet or any paid service. They exist because a mistake found on the cluster or in a
paid run costs queue time or money, while a mistake found here costs nothing.

**How they work.** A small fake server (`fake_server.py`) pretends to be the model server (llama-server on Redhawk, or
Novita). It answers with realistic JSON replies that match each question slot, and it can be told to misbehave: return
invalid JSON, cut a reply off, fail once, or die while loading. The tests then run the real command-line tool and the
real job scripts against it and check what they do.

- `test_suite.py` (about 1 minute; needs R for the scoring checks): slot isolation (smoke slots BM9001-BM9004 versus main
  slots BM0021-BM0120), the two failure kinds of `validate` (infrastructure versus model quality), resume safety (no
  overwrite, no repeat, lock file, settings must match), the Novita budget ledger with 8 calls at once, scoring through R.
- `shtest.sh` (a few minutes per part): the Redhawk job scripts with fake `nvidia-smi`, `module`, `scontrol` and
  `llama-server`: GPU, weights, template and flag checks, the stage gates, the memory summary, queue wait, mandatory
  validation, and an incomplete main run followed by a deliberate resume.

**Run them** (from the repository root, in Git Bash):
```
python code/tests/qwen_deployment_test/test_suite.py
bash code/tests/qwen_deployment_test/shtest.sh /tmp/ott_sh 1
bash code/tests/qwen_deployment_test/shtest.sh /tmp/ott_sh 2
```
Each prints PASS or FAIL per check and ends with a count. They clean up after themselves (including the review copies
that `score` would otherwise leave in `results/open_teacher_test/`).

**What a pass does not prove.** The fake programs only imitate the real ones. Real `nvidia-smi` output, Slurm options,
module names, the llama.cpp build, flash attention on a V100 and real speed can only be checked on Redhawk, which is
what the GPU smoke tests are for.
