# CLAUDE.md

Masters project (Jaxson Bugg, Miami University): distilling a large open-weight teacher (Qwen3.6-27B, run on Miami's Talon cluster, with Redhawk as the fallback) into small Pythia students (70M, 160M, 410M, 1B) for statistics and R.

Where things are:
- **`README.md`** is the short technical overview: research question, design, status and repository map. Keep it general, keep it technically written, and keep project history out of it.
- **`docs/workflow.md`** is the source of truth for specifics: success criteria (including the dated criterion 4 deviation), design, phase checklists, safeguards, metrics, statistics, storage, risks and open decisions. Read it at the start of a session. Update it when work is completed or a decision changes.
- **`docs/progress_update.md`** is the dated history. Never rewrite past entries; add new ones.

The rules below are the working notes for every session.

## Explain everything (standing rule)

The project owner must understand every step of this project. Whenever you write or update anything that describes a process (a file in `docs/`, comments in pipeline scripts, or a summary in chat), explain it in plain language instead of only listing steps or results. For each process, cover:

- **What it is** and **why** it is being done.
- **How it works**, step by step.
- **What every term and number means.** Define jargon the first time it appears (for example distillation, fine-tuning, tokens, thinking tokens, BF16, quantization, decontamination, bootstrap confidence interval, GPU-hour).
- **A small worked example** with real numbers where possible.
- **What could go wrong**, and what the result tells us or does not tell us.

Prefer short explanatory paragraphs plus an example over dense tables or bare bullet lists. Tables are fine as a summary after the explanation, not as a replacement for it. The README is the exception: it is a concise technical overview, and the explanations live in `docs/`.

Write in American English (artifact, behavior, analyze).

## Record every compute run and every cost (standing rule)

- **Compute log (`docs/compute_log.md`).** Every cluster job (Redhawk or Talon), every scheduler test, and every measured local run is recorded in the same session. The entry is detailed enough that anyone can reproduce or audit it:
  - UTC submit, start and end times; cluster, partition, node and job ID;
  - purpose and stage; GPUs (count and type); engine and version; model, revision and quantization;
  - key settings; queue wait, wall time and GPU-hours; peak GPU memory;
  - output folder; outcome; and the related progress entry.

  A job that has not been reviewed yet is still logged, marked as such.
- **Cost log (`docs/cost_log.md`).** Every paid call (for example a ChatGPT or Claude verifier, even a test call) is recorded with UTC time, purpose, service and model, mode, tokens, dollars and the running total. State the expected cost before a paid run and compare the actual afterward. Never make a paid call without logging it. Cluster time is free and goes only in the compute log.

## Working rules

- **Progress log.** Every change to the project goes in `docs/progress_update.md` in the same session, with the date, what was done and why. This covers decisions, completed steps, new, moved or deleted files, threshold or plan changes, and deviations.
- **Dated outputs.** Every batch of teacher or verifier outputs is recorded with:
  - the UTC date and time;
  - the exact model and revision, engine and version, quantization or precision;
  - the thinking mode, the sampling settings and max tokens;
  - the cluster and job ID;
  - the files it produced.

  Put the date in the folder name (for example `teacher_outputs/2026-11-10_qwen3.6-27b-bf16_talon_benchmark01/`) and in the log entry. Never overwrite a dated batch; start a new one.
- **Current Pythia labels only.** Use the current names 70M, 160M, 410M and 1B. Never use the old names for the students, except in this table or in a quotation of an old source. Repo ids always end in `-deduped`.

  | Use (current) | Never use (old) |
  |---|---|
  | 70M | 19M |
  | 160M | 125M |
  | 410M | 350M |
  | 1B | 800M |
- **Model precision.** Keep three things separate:
  1. *Checkpoint storage dtype:* how the original files are serialized. Observed, never changed.
  2. *Runtime load dtype:* `torch.float16` for all four students, passed explicitly in every load call and not taken from `config.json`.
  3. *Training precision recipe:* decided in Phase 8.

  Preserve the pinned checkpoints exactly as distributed, verify the loaded dtype and parameter count, and document the final mixed-precision recipe once the training environment is set. The teacher's precision (BF16 on Talon, 4-bit on the Redhawk fallback) is always stated with its results.
- **Benchmark isolation.** Never use benchmark questions in any training, prompting or tuning step. Benchmark and training data use separate prompts, separate IDs and decontamination (`docs/workflow.md` Section 4).
- **Consistency.** Keep procedures identical across student sizes unless a deviation is logged. Log all model versions, seeds, hyperparameters and job IDs so runs are reproducible. Flag any deviation from the plan or any surprising result rather than silently working around it.
- **Clusters.** Never submit a job, download to a cluster, or change cluster files without the owner's approval for that step. Talon scripts stay drafts until `SETTINGS_REVIEWED=yes`. Redhawk scripts (`configs/redhawk/`) are the tested fallback; do not change them without a reason that is logged.
- **Recovery docs.** Anything stored outside the repository (models, datasets, caches, environments, large logs) needs a file in `recovery/`, written from `recovery/_TEMPLATE.md` when the step is done. Include the source, exact commands, versions, seeds, expected size and checksum, and what to do if it is lost. Teacher outputs cost GPU-hours and are not deterministic, so their recovery doc says so, and a compressed backup of the verified 50k set is kept.
- **Paths.** Read every storage location from `configs/paths.yaml`; never hardcode paths in code.
- **Git.**
  - Commit every change with a clear message and push it to GitHub.
  - Never commit secrets or API keys, model weights, or anything from `C:\masters_project_large\`.
  - Command notes are in `docs/github_notes.md`.
  - The Claude-era material (the original teacher, ruled out by Anthropic's terms) is archived under the tag `pre-cleanup-claude-era`; see `docs/workflow.md` Section 2.2.
