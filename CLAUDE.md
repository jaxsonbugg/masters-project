# CLAUDE.md

Masters project (Jaxson Bugg, Miami University): distilling Claude into small Pythia models for statistics and R. `README.md` is the source of truth for scope, phases and working rules; read Section 12 ("Working Notes for Claude") at the start of a session. The rules below are repeated from there because they are the ones most likely to be missed.

## Explain everything (standing rule)

The project owner must understand every step of this project. Whenever you write or update anything that describes a process (a README section, a file in `docs/`, comments in pipeline scripts, or a summary in chat), explain it in plain language instead of only listing steps or results. For each process, cover:

- **What it is** and **why** it is being done.
- **How it works**, step by step.
- **What every term and number means.** Define jargon the first time it appears (for example distillation, fine-tuning, tokens, thinking tokens, Batch API, decontamination, bootstrap confidence interval).
- **A small worked example** with real numbers where possible.
- **What could go wrong**, and what the result tells us or does not tell us.

Prefer short explanatory paragraphs plus an example over dense tables or bare bullet lists. Tables are fine as a summary after the explanation, not as a replacement for it.

## Record every cost (standing rule)

Every Claude API call batch (benchmark, training data, re-solve checks, teacher evaluation, verification, even a test call) is recorded in `docs/cost_log.md` in the same session: UTC time, purpose, model ID, effort, Batch or standard, input/output/thinking tokens, dollars, and the running total. State the expected cost before a paid run and compare the actual afterward. Never make a paid call without logging it.

## Other rules to keep in mind

- Log every project change in `docs/progress_update.md` with the date and why.
- Never use benchmark questions in any training, prompting, or tuning step.
- Never commit secrets or API keys. Read paths from `configs/paths.yaml`.
- Commit and push changes (see README Section 12 and `docs/github_notes.md`).
