# Cost Log

This file records every dollar the project spends and every use of a metered service, including test calls. Cluster time on Talon and Redhawk is free and goes in `docs/logs/compute_log.md` instead.

**When a paid or metered call happens:**
1. Before the run, state the expected cost or usage and a hard cap.
2. Afterwards, add one row here in the same session.
3. Compare the actual cost or usage with the expected one in the note.

**Codex, the grader, is not logged here (owner's decision, 2026-11-21).** It screens the benchmark questions and grades the benchmark answers (`docs/methodology/workflow.md` Section 2.3) on a workspace account provided through OpenAI to professors, at no cost to the project. Its scientific usage and provenance (CLI version, model, reasoning setting, SHA-256 values, times, token counts, exit status) are recorded with each batch in `run.json` and in `results/codex/` instead. (Until 2026-11-21 this file planned one row per Codex batch and a usage pilot on development items; both were dropped.)

The verifier planned earlier (an external model checking the training data) was retired on 2026-11-12 and never made a call (`docs/archive/retired_verification_2026-11-12.md`).

**How a row's cost is computed for a per-token API** (as in the Claude-era rows below). API providers charge per *token* (a chunk of text, about three quarters of a word), with separate prices for tokens sent (input) and tokens written (output, including any hidden "thinking" tokens):

cost = (input tokens x input price + output tokens x output price) / 1,000,000

For example, a call with 1,500 input and 400 output tokens, at $2 and $10 per million tokens, costs (1,500 x 2 + 400 x 10) / 1,000,000 = $0.007. Take the token counts from the usage numbers the service reports; do not estimate them. For Codex on the workspace plan the dollars are $0.00 unless credits are bought, but the tokens are still recorded, because they are what uses up the allowance.

## Ledger

| UTC date | Purpose | Service / model | Mode | Input tokens | Output tokens | Cost (USD) | Running total (USD) | Note |
|---|---|---|---|---|---|---|---|---|
| 2026-10-07 | Benchmark trial 1, 20 questions (prompt v1) | Claude API, `claude-sonnet-5-5` | standard, effort medium | 28,850 | 7,017 | 0.1279 | 0.13 | Expected ~$0.35 |
| 2026-10-07 | Benchmark trial 2, 20 questions (v2) | Claude API, `claude-sonnet-5-5` | standard, effort medium | 35,767 | 10,492 | 0.1765 | 0.30 | Expected $0.15 to $0.25 |
| 2026-10-07 | Benchmark trial 3, 20 questions (v3) | Claude API, `claude-sonnet-5-5` | standard, effort medium | 37,675 | 10,465 | 0.1800 | 0.48 | Expected $0.15 to $0.22 |
| 2026-10-07 | Benchmark trial 4, 20 questions (v4) | Claude API, `claude-sonnet-5-5` | standard, effort medium | 43,375 | 0 | 0.0867 | 0.57 | All calls refused; input still billed |
| 2026-10-07 | Trial 5, 1-question probe (v5) | Claude API, `claude-sonnet-5-5` | standard | 0 | 0 | 0.0000 | 0.57 | HTTP 403 `model_access_suspended`; nothing billed |
| 2026-10-07 | Trial 6, 1-question probe (v5) | Claude API, `claude-sonnet-5-5` | standard, effort medium | 2,119 | 227 | 0.0065 | 0.58 | Expected ~$0.01 |
| 2026-10-07 | Benchmark trial 7, 20 questions (v5) | Claude API, `claude-sonnet-5-5` | standard, effort medium | 41,355 | 7,959 | 0.1623 | 0.74 | Expected ~$0.18 |
| 2026-10-15 | Trial 8a, 1-question probe (v6) | Claude API, `claude-sonnet-5-5` | standard, effort medium | 2,130 | 279 | 0.0070 | 0.75 | Expected ~$0.01 |
| 2026-10-15 | Benchmark trial 8, 20 questions (v6, R keys) | Claude API, `claude-sonnet-5-5` | standard, effort medium | 41,575 | 10,531 | 0.1885 | 0.94 | Expected $0.19 to $0.22 |
| 2026-10-15 | 2-question test batch (v6) | Claude API, `claude-sonnet-5-5` | Batch, effort medium | 4,141 | 828 | 0.0083 | 0.94 | Expected ~$0.01 |
| 2026-10-15 | 100-question batch BM0021 to BM0120 (v6) | Claude API, `claude-sonnet-5-5` | Batch, effort medium | 207,947 | 52,032 | 0.4681 | 1.41 | Expected ~$0.47 |
| 2026-10-15 | 3 regeneration calls for that batch | Claude API, `claude-sonnet-5-5` | standard, effort medium | 6,098 | 1,464 | 0.0268 | 1.44 | Expected $0.03 to $0.09 |
| 2026-11-25 05:23-05:25 | Key-check pilot, 25 benchmark questions: C1, C2, C3 and the variants agent (4 runs) | Claude Code CLI 2.1.330, `claude-opus-5-5`, **Team subscription login** (not the API) | `-p`, no tools; key source "none" | 28,882 (incl. cache writes) | 18,781 | 0.0000 | 1.44 | Subscription usage, no dollars. Plan windows before and after: five-hour 18-19%, seven-day 13%. Expected about 4 x 10k in, 4 x 15-40k out; actual output lower. The Anthropic API is never used (owner's rule, 2026-11-25). |
| 2026-11-25 05:38-05:40 | Key-check pilot 2 (v2 instructions): C1 and C2 (2 runs) | Claude Code CLI 2.1.330, `claude-opus-5-5`, Team subscription login | `-p`, no tools; key source "none" | 18,209 | 11,145 | 0.0000 | 1.44 | Subscription usage, no dollars. |
| 2026-11-25 05:47-06:01 | Key-check full run: C1, C2, C3 and variants for 975 questions (155 run attempts, incl. retries and about 56 attempts refused at the usage limit, which used no tokens) | Claude Code CLI 2.1.330, `claude-opus-5-5`, Team subscription login | `-p`, no tools, 4 at a time; key source "none" | 895,345 | 384,813 | 0.0000 | 1.44 | Five-hour window full at 06:00 UTC (from about 26%); expected far less (the projection from the pilot was wrong). Seven-day window 22%. |
| 2026-11-25 22:03-22:27 | Key-check resume: 20 C3 and 8 variants batches, then 9 adjudicator-brief batches (38 run attempts incl. 1 retry) | Claude Code CLI 2.1.330, `claude-opus-5-5`, Team subscription login | `-p`, no tools, 2 at a time; key source "none" | 370,635 | 209,746 | 0.0000 | 1.44 | Five-hour window 23% -> 54%, seven-day 25% -> 29%. Expected about 20-25% plus 10-15% for briefs; actual about 31 points. |

**Total spent to date: $1.44.** Every row above is a Claude-era benchmark trial. Claude is no longer the teacher (`docs/methodology/workflow.md` Section 2.2), and those outputs are archived under the Git tag `pre-cleanup-claude-era`, where the original detailed version of this file, with per-trial arithmetic and the old pilot budget, can also be read.
