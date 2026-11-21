# Recovery: teacher outputs (raw replies) and the benchmark collection files

**What it is:** Every reply the teacher (Qwen3.6-27B, BF16, thinking on) wrote for a slot, every attempt, with its thinking text, as saved by `code/generation/generate_set.py run` (stage G on Talon), plus the files made from them on the PC: the collected items (`collect --r-keys`), the repaired items (`apply-repairs`) and the filled position lists (`fill-bench`).
**Location:**
- Raw replies on the PC: `teacher_outputs` in `configs/paths.yaml` (`C:\masters_project_large\data\teacher_outputs\`), one dated folder per run and shard, for example `2026-11-21_qwen3-6-27b-talon-bf16_benchmark_benchmark-v8_d5897ee2_shard1of4\` (`responses.jsonl`, `done_index.jsonl`, `run_log.json`), and the job logs in `2026-11-21_stageG_bm-dv-tv_jobs299-309_logs\`.
- The same raw folders on Talon: `/home/buggjm/talon_project/teacher_outputs/` (a second copy until Talon is cleaned up).
- Collection files: `benchmark_work` in `configs/paths.yaml` (`C:\masters_project_large\data\benchmark_work\2026-11-21_collection\`).
**Approx. size:** 2026-11-21 benchmark, development and TV runs: about 31 MB of raw replies (4 benchmark shards 5.0 to 6.1 MB each, development 4.4 MB, TV 3.0 MB); collection files about 7 MB. Smoke runs 2026-11-20 and 2026-11-21: under 1 MB each.
**Backed up?** Partly: the raw folders exist on the PC and on Talon. Not in Git (too large and not needed there). The decisions and reports that shape the benchmark ARE in Git (`data/slots/`, `data/verification_logs/`).

## Why this matters
Raw replies **cost GPU-hours and are not deterministic**: the teacher samples at temperature 1.0, so generating the same slots again gives different questions. The 2026-11-21 benchmark, development and TV runs (Talon jobs 299 to 309) used about 4.85 GPU-hours. Losing the raw folders before the benchmark is frozen means generating again (new questions, a new audit); after the freeze, the frozen benchmark file is the instrument and the raw replies are its provenance.

## How to rebuild the collection files (deterministic, from the raw folders)
Everything after generation is deterministic given the raw replies, the slot files and the decisions file, and R in the sandbox:
```
P=C:/masters_project_large/envs/probe/Scripts/python.exe; D=C:/masters_project_large/data/teacher_outputs; W=C:/masters_project_large/data/benchmark_work/2026-11-21_collection
$P code/generation/generate_set.py collect --runs $D/2026-11-21_qwen3-6-27b-talon-bf16_benchmark_* --out $W/benchmark_items.jsonl --r-keys
$P code/generation/generate_set.py apply-repairs --items $W/benchmark_items.jsonl --decisions data/verification_logs/2026-11-21_benchmark_check_repairs/decisions.json --out $W/benchmark_items_repaired.jsonl
$P code/generation/generate_set.py fill-bench --items $W/benchmark_items_repaired.jsonl --manifest data/slots/benchmark_slots.manifest.json --primary 1000 --out $W/benchmark_filled.jsonl
```
(the same for the development set with `dev_` files, `--primary 200`). The R sandbox (`recovery/r_sandbox.md`) must pass its self-test first.

## How to rebuild the raw replies (only if both copies are lost)
Deal nothing new: the slot files in `data/slots/` are frozen. Submit stage G again for the same slot file and shards (`docs/clusters/talon_setup.md` Section 8). The result is a NEW set of questions (sampling), so every later step (collection, repairs, the Codex screen, the audit) must be redone, and the change is logged. Expected cost: about 3 GPU-hours per 1,000 benchmark questions.

## Versions, seeds, and settings
- Model `Qwen/Qwen3.6-27B` @ `6a9e13bd`, BF16, vLLM 0.32.0, context 20,480, output limit 16,384, thinking on (temperature 1.0, top_p 0.95, top_k 20), up to 3 attempts per slot.
- Prompts: benchmark v8 `0ba834e2...`, training v2 `412d1eb4...` (smoke runs also v7 `980f5570...` and training v1 `db9ca660...`).
- Slot files and seeds: `data/slots/*.manifest.json` (seeds `<set>-2026-11-20`).

## Verification
- Each run folder: `python code/generation/generate_set.py validate --run <folder> --slots data/slots/<set>_slots.jsonl` must say `infra=PASS` with the counts recorded in `docs/logs/compute_log.md` (entry 19 for jobs 299-309).
- The collected files' SHA-256 values are in the progress log entry of 2026-11-21.

## If it is lost
Raw folders: copy them back from Talon if they are still there (`scp -r talon:~/talon_project/teacher_outputs/<folder> ...`); otherwise regenerate as above, knowing the questions will differ. Collection files: rebuild with the commands above (minutes, free).

## Last updated
2026-11-21
