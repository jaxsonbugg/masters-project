# Talon setup: what it is, what we know, and how the Talon scripts work

Written 2026-11-05, before any Talon login. Everything about Talon that has not been confirmed is marked **UNVERIFIED**.

## 1. What Talon is and why we want it

**Talon** is Miami University's newer GPU cluster. A *cluster* is a set of shared computers (nodes) that people use by submitting *jobs* to a
scheduler (Slurm) instead of logging in and running things by hand. Miami's pages say Talon has 4 GPU nodes with 4 NVIDIA H100 GPUs each (16 GPUs
in all) and 20 high-density CPU nodes. A GPU is the chip that does the heavy arithmetic for language models. The H100 is much newer and much larger
than the V100s on Redhawk: an H100 has about 80 GB of memory per card (the exact variant, 80 GB or 94 GB, is **UNVERIFIED**), a V100 only 16 GB.

Why it matters to this project: the project now includes generating **200,000 teacher examples** with Qwen3.6-27B. On Redhawk that cannot work (a
27-billion-parameter model barely fits on two small V100s even squeezed to 4 bits, and it runs at about 35 tokens per second). Talon's H100s can hold
the full-precision model and serve many requests at once. **TOLD BY RESEARCH COMPUTING (meeting, 2026-11-06; verbal, not yet in writing):** using Talon costs
us nothing, one job may run at most 3 days, and we have 500 GB of storage (more must be requested). How many GPU-hours we may use in total is **UNVERIFIED**.

The Redhawk test (pipeline job 2511641) continues independently and stays the baseline: **nothing under `configs/redhawk/` was changed**.

## 2. What is known and what is not

### How to read the status labels (used here, in the settings file and in the probe output)
Four labels say HOW we know something. A weaker source never promotes something to a stronger label:
- **OBSERVED**: seen directly by a command (the login works, an operating-system release, a disk size, an HTTP status). Independent of the scheduler's settings.
- **SLURM-REPORTED**: what the scheduler's *configuration* says (a partition's time limit, a node's `Gres=gpu:h100:4`, billing weights, QOS limits, reservations). It tells us what is
  *configured*. It does **not** prove that a particular GPU request is accepted, that a GPU works, or what Miami's policy is. Example: a `Gres=gpu:h100:4` line does not make
  "`--gres=gpu:h100:N` works" verified; only a scheduler acceptance test or a real job can.
- **TOLD BY RESEARCH COMPUTING**: stated in a message from Research Computing, with date and channel; we have not checked it ourselves yet.
- **UNVERIFIED**: everything else. It needs a test, a GPU job or an email.

| Topic | What we have | Status (as of 2026-11-06, before the first probe) |
|---|---|---|
| Hardware | 4 GPU nodes x 4 H100, plus 20 CPU nodes | documented (Miami IT news, Nov 2025); not observed by us |
| Login (head) node | `mualhphp01.hpc.miamioh.edu` | **TOLD BY RESEARCH COMPUTING** 2026-11-05 (message to Jaxson); port 22 answers on the Miami VPN (**OBSERVED**); no login yet |
| GPU partition name | `talon` (`--partition=talon`) | **TOLD BY RESEARCH COMPUTING** 2026-11-05; not yet seen in `sinfo` |
| Choosing a node | `--nodelist=mualhpgp01.mpi` lands a job on GPU node 1 | **TOLD BY RESEARCH COMPUTING** 2026-11-05: a confirmed option, not a requirement (see "Choosing a node") |
| Other GPU node names (`mualhpgp02` to `04`) | guessed from the naming pattern | **UNVERIFIED** |
| VPN and Duo needed? | port 22 answered only with the Miami VPN on | VPN: **OBSERVED** 2026-11-05 and **TOLD** 2026-11-06 (needed off campus). Duo method: **UNVERIFIED** until the first login |
| H100 memory variant | 80 GB or 94 GB | **UNVERIFIED** (only `nvidia-smi` inside a job shows it) |
| Account process | Students use "Research Cluster Account Sponsorships" (faculty sponsor, expiry date) | documented |
| Same account and home folder as Redhawk? | same account and user name (`buggjm`) | account: **TOLD BY RESEARCH COMPUTING** 2026-11-06 (meeting, verbal); shared home folder: **UNVERIFIED** (probe section 1b makes it OBSERVED) |
| Time limits, whole-node jobs, GPU resource string | one job may run at most 3 days; Research Computing's example asks for `--gres=gpu:2` | **TOLD BY RESEARCH COMPUTING** 2026-11-06 (verbal); the scheduler's own values will be SLURM-REPORTED (probe 5b/5e); whole-node rules **UNVERIFIED** |
| Accepted GPU request syntax (`--gres=gpu:N`, typed, `--gpus=N`) | the example from Research Computing uses `--gres=gpu:2` | **UNVERIFIED**: still needs `sbatch --test-only` (no job) or a job; the example makes `--gres` the likely answer |
| Modules, OS, glibc, Python, containers (login node) | a module `miniforge3-python3.12` (conda) was named; own software and conda environments are allowed | **TOLD BY RESEARCH COMPUTING** 2026-11-06; everything else **UNVERIFIED** (probe sections 2-4 make them OBSERVED) |
| Driver, CUDA, NVLink, internet from compute nodes | not known | **UNVERIFIED**: needs a job on a GPU node |
| Storage (paths, quotas, purge rules) | 500 GB limit for us; more must be requested; all of it is ours to use; a display of used and total space exists | limit and display: **TOLD BY RESEARCH COMPUTING** 2026-11-06 (verbal); paths, the display command and purge rules: **UNVERIFIED** (probe section 6 makes paths and quotas OBSERVED) |
| Pricing and charges | using Talon costs us nothing | **TOLD BY RESEARCH COMPUTING** 2026-11-06 (verbal, not yet in writing); billing weights may show as SLURM-REPORTED; the credit and any allocation are **UNVERIFIED** |
| Allocation (total GPU-hours), GPU quotas, per-user limits | no figure given | **UNVERIFIED** (limits configured in Slurm would be SLURM-REPORTED, not policy) |
| Access requirements and policies (usage, data) | the meeting said nothing changes without written notice to Jaxson, and that the planned use is fine | **TOLD BY RESEARCH COMPUTING** 2026-11-06 (verbal); nothing is in writing, so the policies themselves stay **UNVERIFIED** |
| Contact | Dr. Mueller (Research Computing) | **TOLD** 2026-11-06 |
| Maintenance window and availability | all four GPU nodes are reported up now | **TOLD BY RESEARCH COMPUTING** 2026-11-06; **UNVERIFIED** until probe section 5c shows Slurm's node states and reservations |

Every Talon script prints the unverified list (pricing, allocation, limits, policies) so it cannot be forgotten, and nothing in the code assumes an
answer to any of them. Because the meeting answers were verbal, a short email asking Dr. Mueller to confirm them in writing (no cost, the 500 GB limit and how to ask for
more, the 3-day job limit, no changes without written notice) is the way to turn "told" into a documented fact.

### The lines Research Computing gave us, in plain language
Research Computing supplied four commands. None of them is run by us now (the first one reserves GPUs, so it is not a read-only action).
- `salloc -N 1 -n 32 -c 2 -J interactive -p talon --gres=gpu:2 --x11 -t 72:00:00 /usr/bin/srun --pty /bin/bash` asks Slurm (the scheduler, the program that hands out the
  computers) for an *interactive* session. `-N 1` means one machine; `-n 32 -c 2` means 32 tasks with 2 CPU cores each, so 64 cores; `-J interactive` is just a name; `-p talon`
  is the GPU partition (a partition is a group of machines); `--gres=gpu:2` asks for two GPUs ("gres" means a generic resource); `--x11` lets windows appear on your PC, which we do
  not need; `-t 72:00:00` is the longest allowed time, 72 hours = the 3 days we were told; the last part opens a command line on the machine you were given. While that session
  exists you are holding two GPUs even if you do nothing, so you leave it (type `exit`) when finished. Our scripts use *batch* jobs instead: a job script runs by itself and
  frees the GPUs the moment it ends.
- `module load miniforge3-python3.12` switches on a prepared software package for this session only: Miniforge, which provides the `conda` program, with Python 3.12. Clusters keep
  software behind "modules" so that many people can use different versions without clashing.
- `conda create -y -n my-conda-env` makes an *environment*: a private folder of Python packages, so that what we install (vLLM, the program that serves the model) cannot disturb
  anyone else's software and vice versa. `-y` answers "yes" to its questions automatically. `conda activate my-conda-env` switches the session into that folder. The environment
  lives in our home area and counts toward the 500 GB. Our draft `fetch_talon.sh` builds an ordinary Python `venv` (a similar private folder); after the probe we decide
  whether to switch to a conda environment.
- **Storage example with real numbers:** the model weights are about 54 GB, a vLLM environment is perhaps 15 to 20 GB, caches (pip, conda, Hugging Face) are kept inside our project
  folder so we can see them, and the outputs of the 100-question test are only megabytes (200,000 examples would be a few GB). That is roughly 80 to 100 GB of the 500 GB. Two copies
  of the model (for example the BF16 and an FP8 copy of about 27 GB) would still fit. The risk is not the size of one run but forgetting old copies, which is why the download
  script will check the projected use against the limit.

### Logging in without typing a password each time (key pair)
A *key pair* is two files created together. The *private key* stays on this PC and is never shared. The *public key* is one line of text that we copy into `~/.ssh/authorized_keys`
on Talon. When we connect, Talon sends a puzzle that only the private key can solve, so it recognises us without a password. The procedure and its risks are in
`recovery/talon_ssh_access.md`. It does not change what we are allowed to do; it only removes the typing. If Talon still asks for Duo with a key, that is the cluster's own rule
and we simply keep approving the Duo prompt (the probe is a single login either way). The host key was accepted on trust at the first connection (Jaxson's decision of
2026-11-06); `accept-new` makes ssh refuse the connection later if the server's key ever changes.

### Questions to send to Miami Research Computing (ResComp@MiamiOH.edu), in ONE email
1. What is the login host, and do I need the VPN and Duo? Is the account the same as my Redhawk account?
2. Which partition(s) hold the H100 nodes, what is the maximum job time, and how do I request GPUs (`--gres=gpu:N`, `--gpus=N`, a type name)? May a job take a whole node?
3. Is there a charge account or allocation to name in jobs? What does GPU time cost, and does a sponsored student draw on the faculty sponsor's research credit? What are the limits per user (GPUs, jobs, GPU-hours)?
4. Where should large files go (home, project, scratch), with what quotas and purge rules? Is downloading about 55 GB from Hugging Face acceptable, from a login node or from a compute node? Do compute nodes have internet?
5. Which modules exist (CUDA, Python), may I use pip/uv virtual environments, and are Apptainer containers available?
6. Which H100 variant are the nodes (memory per GPU)? When does Talon come back from maintenance?
7. **Before the first login:** what are the SHA256 fingerprints of the SSH host keys of `mualhphp01.hpc.miamioh.edu` (ED25519, ECDSA and RSA; on the node: `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` and the equivalents)? They are needed to verify the server before typing a password.

(Items 1 and 2 are partly answered by Research Computing's message of 2026-11-05: head node `mualhphp01.hpc.miamioh.edu`, partition `talon`, `--nodelist=mualhpgp01.mpi` for GPU node 1. Those stay
"told by Research Computing" until the probe observes them; the rest of the list still applies, and the probe will settle some of it first.)

(The 2026-11-06 meeting answered more of these, verbally: item 1 (same account, VPN needed off campus), item 2 (a job may run 3 days; the example uses `--gres=gpu:2`; the scheduler
may choose the node), item 3 (no cost; no allocation figure was given), item 4 (500 GB limit, more on request), item 5 (own software and conda environments are allowed) and the
availability part of item 6 (all four nodes available). Item 7 is no longer needed: Jaxson decided to trust the server without comparing fingerprints. Still open: GPU-hours in
total, the H100 memory variant, whether compute nodes have internet, and the written policies.)

### Choosing a node: `--nodelist=mualhpgp01.mpi` or no node at all
Research Computing confirmed that `--nodelist=mualhpgp01.mpi` places a job on GPU node 1. That is a **confirmed way to choose a node, not a requirement** for every job.
Without it, the scheduler may start a job on any free GPU node of the partition. That is usually better: a job is not held back because node 1 happens to be busy, drained or
reserved, and it does not depend on node 1 staying available. Pinning a node helps when (a) every benchmark run must use identical hardware, so throughput numbers are comparable,
(b) only that node is usable by us for now, or (c) a problem is being debugged on one node. The probe lists all nodes of the partition side by side (section 5b) with their state
and any reservation (5c), so we can see whether the nodes look identical. The default is therefore **no node pinned** (`TALON_NODELIST` is blank in `talon_settings.sh`); it is
set only if the probe shows the nodes differ or only one is usable. In the 2026-11-06 meeting Research Computing also said to let the scheduler choose, and that all four
nodes are available.

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
| llama.cpp, a 4-bit GGUF file (16.8 GB) | vLLM serving the BF16 safetensors weights (about 54 GB) | Qwen's model page recommends vLLM or SGLang; H100s have the memory for 16-bit weights, which keeps the model as it was released. BF16 = 16-bit "brain floating point", the full-precision format the model was released in. |
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
  must not be called comparable to the Redhawk run.
- peak GPU memory per GPU, if the job saved it.

**Worked example (illustration only).** Suppose 2 GPUs finish 32 successful examples in half an hour. That is 64 examples per hour. GPU-hours per
1,000 = 2 GPUs x 0.5 h / 32 x 1,000 = 31.25. For 200,000 examples that is 31.25 x 200 = 6,250 GPU-hours. If 16 GPUs were all available at once that would
be 6,250 / 16 = 390 hours, about 16 days. These numbers are made up to show the arithmetic; the real ones come from stage T.

**What the projection is not.** It uses 32 questions of one prompt family. The real 200,000 questions may be longer or shorter, jobs lose time to queue
waits and time limits, model loading repeats per job, and failed examples must be re-asked. Treat it as a planning estimate with a wide error bar. The
"if N GPUs were available" lines are arithmetic only; Talon's allocation and GPU quota are **UNVERIFIED**.

## 7. The 20,480-token context is a comparison setting, not the model's best

Qwen3.6-27B natively handles 262,144 tokens, and its model card advises keeping at least 128K tokens of context to preserve its thinking quality. The
Talon comparison uses **20,480 tokens per sequence** (3,000 for the prompt, 16,384 for the output, headroom) only so that it matches the Redhawk
run. The scripts print this note, and the checks above look for truncation and reasoning exhaustion. If the throughput benchmark shows
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
2. **Check reachability and verify the host key, then connect.** Run `Test-NetConnection mualhphp01.hpc.miamioh.edu -Port 22` (connect the Miami VPN if it times out). **Do not
   just type "yes" at the first SSH prompt:** display the server's host-key fingerprints, get Research Computing's own fingerprints by email or phone, compare them, and only then
   accept the key once (the procedure is in `recovery/talon_ssh_access.md`). Record the host, VPN yes/no and Duo method there.
3. **Run the read-only probe** with the local wrapper (`bash configs/talon/run_probe_local.sh` in Git Bash): it sends the probe through ssh without copying anything to Talon, keeps ssh's
   exit status, records the output and diagnostics under `~/talon_probe/`, and calls the result COMPLETE only if `END OF PROBE` and every section are present. Paste the output to me. I
   fill `talon_settings.sh` and the `talon_*` keys in `configs/paths.yaml` from it, mark each fact with its evidence label, correct the test fakes with the real facts, and rerun the tests.
4. **Part 2 of the probe**: first only the checks (no job). Then, after your separate approval, `QT_SUBMIT=yes` (one 5-minute GPU job, which may use
   allocation), then `... record`.
5. **Review** `talon_settings.sh` together, then set `SETTINGS_REVIEWED=yes`.
6. **`prep_talon.sh`** (installs vLLM, downloads and verifies about 54 GB; needs `QT_CONFIRM_STORAGE=yes`; separate approval).
7. **Stage A** (`submit_pipeline.sh smoke_a`): read it before anything else. This is also where the real vLLM log and reply fields replace the fakes.
8. **Stage T** for each layout (1 GPU, 2 GPUs, ...), then `throughput_report.py`; choose the layout together.
9. **Stage B and the main run** (or `pipeline`) with the chosen layout: the second comparison point (Redhawk 4-bit versus Talon BF16).
10. A **new plan** for the 200,000-example work, using the measured GPU-hours.

## 10. What could go wrong

- **vLLM cannot be installed** (no internet on the nodes, no wheel for the operating system, no pip allowed). The probe tests it. Fallbacks: a wheel
  directory downloaded on the login node, an Apptainer container, SGLang (the model card's other engine), or llama.cpp as on Redhawk.
- **One H100 cannot hold BF16 with enough cache**: stage T records it as a result. FP8 (`Qwen/Qwen3.6-27B-FP8`, about half the size, "nearly identical" quality per
  the model card) is a possible third layout if the probe shows it is allowed; it would be a different precision and must be labelled so.
- **The reasoning field has a different name** in the real vLLM: both `reasoning_content` and `reasoning` are accepted, and stage A shows which arrives.
- **The error-word list is wrong**: a harmless warning could fail a stage. Stage results print the matching lines so a person can judge in seconds.
- **The first GPU job uses allocation** we do not know about: ask first (email, question 3).
