# Talon setup: what it is, what we know, and how the Talon scripts work

Written 2026-11-05, before any Talon login. Everything about Talon that has not been confirmed is marked **UNVERIFIED**.

## 1. What Talon is and why we want it

**Talon** is Miami University's newer GPU cluster. A *cluster* is a set of shared computers (nodes) that people use by submitting *jobs* to a
scheduler (Slurm) instead of logging in and running things by hand. Miami's pages say Talon has 4 GPU nodes with 4 NVIDIA H100 GPUs each (16 GPUs
in all) and 20 high-density CPU nodes. A GPU is the chip that does the heavy arithmetic for language models. The H100 is much newer and much larger
than the V100s on Redhawk: an H100 has about 80 GB of memory per card (the exact variant, 80 GB or 94 GB, is **UNVERIFIED**), a V100 only 16 GB.

Why it matters to this project: the project now includes generating **200,000 teacher examples** with Qwen3.6-27B. On Redhawk that cannot work (a
27-billion-parameter model barely fits on two small V100s even squeezed to 4 bits, and it runs at about 35 tokens per second); on Novita it would cost
thousands of dollars (docs/teacher_model_evaluations.md). Talon's H100s can hold the full-precision model and serve many requests at once, and its
cost to us is, as far as we know, GPU time from an allocation rather than dollars. How much allocation we get is **UNVERIFIED**.

The Redhawk test (pipeline job 2511641) continues independently and stays the baseline: **nothing under `configs/redhawk/` was changed**.

## 2. What is known and what is not

| Topic | What we know | Status |
|---|---|---|
| Hardware | 4 GPU nodes x 4 H100, plus 20 CPU nodes | documented (Miami IT news, Nov 2025) |
| H100 memory variant | 80 GB or 94 GB | **UNVERIFIED** |
| Account process | Students use "Research Cluster Account Sponsorships" (faculty sponsor, expiry date) | documented |
| Login host, VPN, Duo, web portal | not published | **UNVERIFIED** |
| Scheduler and partitions | Slurm very likely; partition names, time limits, GPU request syntax, whether a whole node can be requested | **UNVERIFIED** |
| Modules, OS, driver, CUDA, containers, internet from the nodes | not published | **UNVERIFIED** |
| Storage (paths, quotas, purge rules) | not published | **UNVERIFIED** |
| Pricing and charges | a PI credit of $1,000 per year was seen only in a search snippet | **UNVERIFIED** |
| Allocation, GPU quotas, per-user limits, maximum job length | not published | **UNVERIFIED** |
| Access requirements and policies (usage, data), whether Redhawk and Talon accounts are separate | not published | **UNVERIFIED** |
| Maintenance window and return date | not published; Talon is in maintenance | **UNVERIFIED** |

Every Talon script prints the unverified list (pricing, allocation, GPU quota, access) so it cannot be forgotten, and nothing in the code assumes an
answer to any of them.

### Questions to send to Miami Research Computing (ResComp@MiamiOH.edu), in ONE email
1. What is the login host, and do I need the VPN and Duo? Is the account the same as my Redhawk account?
2. Which partition(s) hold the H100 nodes, what is the maximum job time, and how do I request GPUs (`--gres=gpu:N`, `--gpus=N`, a type name)? May a job take a whole node?
3. Is there a charge account or allocation to name in jobs? What does GPU time cost, and does a sponsored student draw on the faculty sponsor's research credit? What are the limits per user (GPUs, jobs, GPU-hours)?
4. Where should large files go (home, project, scratch), with what quotas and purge rules? Is downloading about 55 GB from Hugging Face acceptable, from a login node or from a compute node? Do compute nodes have internet?
5. Which modules exist (CUDA, Python), may I use pip/uv virtual environments, and are Apptainer containers available?
6. Which H100 variant are the nodes (memory per GPU)? When does Talon come back from maintenance?

## 3. Why every Talon script is a draft

The first Redhawk pipeline job stopped in its first minute because a check was written against my *guess* about what a program would print, not what it
printed (the log format differed). The cost was a new queue wait. For Talon, almost everything would be a guess, so the design is:

1. **All guesses live in one file**, `configs/talon/talon_settings.sh`, each marked UNVERIFIED.
2. **The first login runs a probe** (`probe_talon.sh`, read-only, then `probe_talon_part2.sh`, one 5-minute GPU job) whose real output replaces the guesses.
3. **The scripts refuse to run** until a person reads the settings file and changes `SETTINGS_REVIEWED=no` to `yes`. The flag is read from the file itself,
   so an environment variable cannot switch it on by accident (a test checks this).
4. **No pass or fail depends on the wording of a log.** The scripts decide from HTTP answers, exit codes and measured GPU memory. Error *words* in the
   vLLM log can only fail a stage, never pass one, and the word list is a draft to be adjusted after the first real log.

## 4. What changed compared with Redhawk (and why)

| Redhawk | Talon | Why |
|---|---|---|
| llama.cpp, a 4-bit GGUF file (16.8 GB) | vLLM serving the BF16 safetensors weights (about 54 GB) | Qwen's model page recommends vLLM or SGLang; H100s have the memory for 16-bit weights, which also matches what Novita advertises. BF16 = 16-bit "brain floating point", the full-precision format the model was released in. |
| Compile llama.cpp on a CPU node (about 30 minutes) | No compile: `pip install vllm==<pinned version>` | vLLM is a Python package. |
| `-sm layer -ts 1,1`: split by layer across exactly 2 GPUs | `--tensor-parallel-size N`: split each layer's arithmetic across N GPUs | Tensor parallelism (TP) is how vLLM uses several GPUs for one model copy. |
| Context set with `-c` and divided among parallel slots | `--max-model-len` is **per sequence** | The two engines count context differently; 20,480 per sequence keeps the same per-question room as Redhawk's stage A. |
| Flash-attention crash retry ladder | none | That risk was specific to the V100 and llama.cpp. |
| Free-memory gates (3 GB / 1 GiB) | none; memory is recorded only | vLLM reserves a fixed share (by default 90%) of each GPU at start, so "free memory" is almost constant and says little. Out-of-memory shows up as a failed start instead. |
| `--exclusive --nodes=1` (no GPU resource defined on Redhawk), partition `gpu`, an excluded node | the submit script builds the request from the settings (`--gres=gpu:N` or `--gpus=N`, partition, account, wall time) | Slurm sites differ; `#SBATCH` lines cannot hold variables. |
| Weights check: one file's size and SHA-256 | a manifest with the SHA-256 of every file, checked against the hashes Hugging Face publishes for the pinned **commit** | The weights are about 15 files; the revision is a commit hash, never a branch name. |
| Exactly 2 GPUs of 16 GB | `GPU_COUNT` GPUs of at least `GPU_MIN_TOTAL_MIB` each | The layout is a setting. |
| Stage A, Stage B, main (with a fallback setting) | Stage A, B, **T (throughput)**, main; no fallback setting | The layout is chosen BEFORE the pipeline, from stage T. |

The Redhawk scripts and tests, the prompt (v6, hash `348db6ff...`), the sampling settings, the slot rules, the two failure kinds (infrastructure vs
model quality), mandatory validation and the stage result files are reused unchanged in meaning.

## 5. The GPU layout has no preferred default

Four numbers describe how the model is spread over GPUs, and all four are blank until chosen:
- `GPU_COUNT`: GPUs the job gets. `TENSOR_PARALLEL`: GPUs one copy of the model is split across. `REPLICAS`: independent copies side by side. They must satisfy
  `GPU_COUNT = TENSOR_PARALLEL x REPLICAS` (a check enforces it). `REPLICAS` must be 1 for now (see section 8).
- `MAX_NUM_SEQS`: how many sequences the *server* decodes at once. `CLIENT_CONCURRENCY`: how many requests the *client* keeps in flight.

**Why not assume 2 GPUs or 8 at once?** The BF16 weights are about 54 GB. On one 80 GB card that leaves roughly 20 GB (before vLLM's own overhead) for
the "KV cache", the memory that holds the text each running sequence has produced so far; that may allow few sequences at once, or fail. Two GPUs leave
much more cache but use twice the GPU-hours per example, and splitting a model across GPUs adds communication cost. Which layout gives the most examples
per GPU-hour is a measurement, not an argument: that is stage T.

## 6. The throughput stage (T) and its report

**What it is.** A small benchmark: the same 32 development questions (slot set T, BM9101-BM9132; development slots, never benchmark questions) are sent
to the model under a chosen GPU layout, once for each client concurrency in `SWEEP_CONCURRENCY` (default 1, 4, 8, 16), on one server start. You run it
once per layout you want to compare, for example 1 GPU and 2 GPUs at BF16.

**What is measured.** For each run, `code/generation/throughput_report.py` reads the run folder and reports:
- **successful example**: HTTP 200, the model stopped by itself (not cut off), and the answer is a JSON object. Anything else is counted but is not an example.
- **successful examples per hour** = successes / hours of client time (model loading time is reported separately: it is paid once per job).
- **GPU-hours per 1,000 successful examples** = GPUs used x hours / successes x 1,000.
- **truncation rate** (finish reason `length`, or prompt plus output reached the context limit) and **reasoning-exhaustion rate** (the model produced
  reasoning but no usable answer, often because thinking used up the output budget); both are printed as findings above 5% (editable) and then the layout
  must not be called comparable to the Redhawk and Novita runs.
- peak GPU memory per GPU, if the job saved it.

**Worked example (illustration only).** Suppose 2 GPUs finish 32 successful examples in half an hour. That is 64 examples per hour. GPU-hours per
1,000 = 2 GPUs x 0.5 h / 32 x 1,000 = 31.25. For 200,000 examples that is 31.25 x 200 = 6,250 GPU-hours. If 16 GPUs were all available at once that would
be 6,250 / 16 = 390 hours, about 16 days. These numbers are made up to show the arithmetic; the real ones come from stage T.

**What the projection is not.** It uses 32 questions of one prompt family. The real 200,000 questions may be longer or shorter, jobs lose time to queue
waits and time limits, model loading repeats per job, and failed examples must be re-asked. Treat it as a planning estimate with a wide error bar. The
"if N GPUs were available" lines are arithmetic only; Talon's allocation and GPU quota are **UNVERIFIED**.

## 7. The 20,480-token context is a comparison setting, not the model's best

Qwen3.6-27B natively handles 262,144 tokens, and its model card advises keeping at least 128K tokens of context to preserve its thinking quality. The
Talon comparison uses **20,480 tokens per sequence** (3,000 for the prompt, 16,384 for the output, headroom) only so that it matches the Redhawk and
Novita runs. The scripts print this note, and the checks above look for truncation and reasoning exhaustion. If the throughput benchmark shows
truncation at 20,480, a run at a longer `MAX_MODEL_LEN` is the next experiment; the report can compare the two.

## 8. What the 200,000-example generation will need (documented, NOT built)

`open_teacher_test.py` is a tool for comparing deployments of the model on 100 fixed question slots. It deliberately lacks what a 200,000-example run
needs, and these get their own plan and approval later:
- **A far richer question generator.** The current blueprint has only 138 distinct slot combinations (category, subtopic, difficulty, answer type);
  200,000 examples need much more variety, or the data will repeat itself.
- **Sharding into chunks** sized to the job time limit, with **checkpoint and resume at scale** and no double-spending of GPU time.
- **Several server replicas side by side and job arrays** to use all 16 GPUs (this draft supports `REPLICAS=1` only).
- **A deduplication and decontamination pass** against the benchmark, so no benchmark question can leak into training data.
- **Verification by sampling** (R answer checks and hand review of a sample), and a policy for rejected examples.
- **An answer-length and thinking-budget policy**, because thinking tokens dominate cost and time.
- **Output format and storage size** (200,000 examples of thousands of tokens each is gigabytes).
- **GPU-hour accounting against the allocation** (UNVERIFIED), and a way to stop safely at the limit.

## 9. After your Talon account is activated: exact steps

Each step that touches the cluster needs your approval first, as for Redhawk.
1. **Email** the questions in section 2 (you may already have). Until answered, pricing, allocation, quotas and access limits stay UNVERIFIED.
2. **Connect** (VPN/Duo as needed), add the `talon` alias, and record the host and findings in `recovery/talon_ssh_access.md`.
3. **Copy the Talon files** and run the read-only probe (the command is at the top of `configs/talon/probe_talon.sh`). Paste the output to me. I
   fill `talon_settings.sh` and the `talon_*` keys in `configs/paths.yaml` from it, correct the test fakes with the real facts, and rerun the tests.
4. **Part 2 of the probe**: first only the checks (no job). Then, after your separate approval, `QT_SUBMIT=yes` (one 5-minute GPU job, which may use
   allocation), then `... record`.
5. **Review** `talon_settings.sh` together, then set `SETTINGS_REVIEWED=yes`.
6. **`prep_talon.sh`** (installs vLLM, downloads and verifies about 54 GB; needs `QT_CONFIRM_STORAGE=yes`; separate approval).
7. **Stage A** (`submit_pipeline.sh smoke_a`): read it before anything else. This is also where the real vLLM log and reply fields replace the fakes.
8. **Stage T** for each layout (1 GPU, 2 GPUs, ...), then `throughput_report.py`; choose the layout together.
9. **Stage B and the main run** (or `pipeline`) with the chosen layout: the third comparison point (Redhawk 4-bit, Talon BF16, Novita BF16).
10. A **new plan** for the 200,000-example work, using the measured GPU-hours.

## 10. What could go wrong

- **vLLM cannot be installed** (no internet on the nodes, no wheel for the operating system, no pip allowed). The probe tests it. Fallbacks: a wheel
  directory downloaded on the login node, an Apptainer container, SGLang (the model card's other engine), or llama.cpp as on Redhawk.
- **One H100 cannot hold BF16 with enough cache**: stage T records it as a result. FP8 (`Qwen/Qwen3.6-27B-FP8`, about half the size, "nearly identical" quality per
  the model card) is a possible third layout if the probe shows it is allowed; it would be a different precision and must be labelled so.
- **The reasoning field has a different name** in the real vLLM: both `reasoning_content` and `reasoning` are accepted, and stage A shows which arrives.
- **The error-word list is wrong**: a harmless warning could fail a stage. Stage results print the matching lines so a person can judge in seconds.
- **The first GPU job uses allocation** we do not know about: ask first (email, question 3).
