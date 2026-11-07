# configs/talon - job scripts for Miami's Talon cluster (DRAFT, written before any Talon login)

This folder is the Talon twin of `configs/redhawk/`. It was **copied and adapted, not shared**, so nothing in it can break the
working Redhawk scripts (`configs/redhawk/` was not touched). Read `docs/clusters/talon_setup.md` first: it explains in plain language what
Talon is, what is known and unknown about it, why every script is a draft, and the exact steps after the account is activated.

**Every file here is a draft.** The scripts refuse to run until a person has changed `SETTINGS_REVIEWED=no` to `yes` in
`talon_settings.sh` (read from the file itself; an environment variable cannot override it). The only scripts that run before
that are the two probes, because they are how the real values are found.

| File | What it does | Runs when |
|---|---|---|
| `talon_settings.sh` | The ONLY place with Talon guesses (partition, account, GPU request style, modules, Python, vLLM version, model revision, GPU layout, wall times). Every line is UNVERIFIED until the probe confirms it. Also lists the unverified Talon facts (pricing, allocation, quotas, access). | edited once, after the probe |
| `common.sh` | Helpers (twin of the Redhawk one): paths from the `talon_*` keys of `configs/paths.yaml`, the review guard, layout checks, sbatch option builder, Slurm time parser, GPU memory checks. | sourced by every script |
| `run_probe_local.sh` | Runs the probe FROM THE PC through ssh's standard input (nothing is copied to Talon), keeps ssh's exit status, records `.out`, `.err` and `.diag` under `~/talon_probe/`, and says COMPLETE only if `END OF PROBE` and all 13 sections are present. Uses `StrictHostKeyChecking=yes`: verify the host key first (`recovery/talon_ssh_access.md`). | first login |
| `probe_talon.sh` | READ-ONLY look at Talon (sent by the wrapper): who/where, shared-home check, OS, tools, modules, Slurm in general, the `talon` partition and every node of it, maintenance and reservations, queue, limits and billing weights, storage and quotas, internet, and the model/vLLM versions to pin. Every section header carries an evidence label (OBSERVED or SLURM-REPORTED). Tests enforce that it submits, installs and writes nothing. | via the wrapper |
| `probe_talon_part2.sh` + `probe_gpu_job.sbatch` | Asks the scheduler which GPU request forms it accepts (`--test-only`, no job), then (with `QT_SUBMIT=yes`, needs your separate approval) runs ONE 5-minute GPU job, then `record` writes `talon_verified.txt`. | first login, after `probe_talon.sh` |
| `prep_talon.sh` + `fetch_talon.sh` | Checks the copied files, then installs the pinned vLLM into a Python environment and downloads and verifies the pinned BF16 weights (about 54 GB) in the background. Needs `QT_CONFIRM_STORAGE=yes` from you. | after review, once |
| `submit_pipeline.sh <kind>` | Checks everything is ready, builds the sbatch options from the settings, shows the scheduler's start estimate, and (with `QT_SUBMIT=yes`) submits one job. Kinds: `smoke_a`, `smoke_b`, `throughput`, `pipeline`, `main`. | for every job |
| `serve_and_run.sh` | The stage runner inside a job: checks, starts `vllm serve`, runs the client, mandatory validation, PASS or FAIL. Stages A, B, T, main. | inside jobs |
| `talon_smoke_a.sbatch`, `talon_smoke_b.sbatch` | Stage A (2 questions, one at a time) and Stage B (2 questions at the main run's concurrency). | via `submit_pipeline.sh` |
| `talon_throughput.sbatch` | Stage T, the throughput benchmark: 32 development questions once per concurrency in `SWEEP_CONCURRENCY`, for one GPU layout. Read the runs with `code/generation/throughput_report.py`. | once per layout |
| `talon_pipeline.sbatch` | One job running Stage A, Stage B and the main run (BM0021-BM0120) with one layout. | via `submit_pipeline.sh pipeline` |
| `talon_test.sbatch` | The main run alone (to resume or repeat it). | via `submit_pipeline.sh main` |

## Order on day 1 (each cluster action needs your approval, as with Redhawk)
1. Check reachability, **verify the host key with Research Computing**, connect once by hand, record the findings in `recovery/talon_ssh_access.md`.
2. `bash configs/talon/run_probe_local.sh` (read-only; it checks its own completeness). Paste the output into the chat.
3. Fill the values into `talon_settings.sh`; set the `talon_*` keys in `configs/paths.yaml`.
4. `probe_talon_part2.sh` (checks), then, after approval, `QT_SUBMIT=yes ...`, then `... record`.
5. Read `talon_settings.sh` end to end; only then set `SETTINGS_REVIEWED=yes`.
6. `prep_talon.sh` (download), then `submit_pipeline.sh smoke_a`, read it, then `throughput` for each layout, then the pipeline.

## What is deliberately NOT here
- The 200,000-example generation (see `docs/clusters/talon_setup.md`, section "What the 200,000-example generation will need").
- Several server replicas side by side (`REPLICAS` must be 1 for now) and container mode (`TALON_ENGINE_MODE=venv` only).
- Any preferred GPU layout: GPU count, tensor parallelism, sequences and concurrency are left blank until the throughput benchmark.

## Tests
`code/tests/talon_deployment_test/` (fake `nvidia-smi`, Slurm commands and `vllm`; the fakes are placeholders and no check depends
on log wording). The Redhawk tests in `code/tests/qwen_deployment_test/` must keep passing unchanged.
