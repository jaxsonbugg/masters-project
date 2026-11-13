# Cost Log

This file records every dollar the project spends and every use of a metered service, including test calls. Cluster time on Talon and Redhawk is free and goes in `docs/logs/compute_log.md` instead.

**When a paid or metered call happens:**
1. Before the run, state the expected cost or usage and a hard cap.
2. Afterwards, add one row here in the same session.
3. Compare the actual cost or usage with the expected one in the note.

**The service now planned (decided 2026-11-12): Codex, the grader** (`docs/methodology/workflow.md` Section 2.3). It screens the benchmark questions and grades the benchmark answers. It runs through the Codex command-line tool on the owner's **workspace subscription**, so it is not billed per call like an API. That does not make it free:
- its use counts against the plan's included allowance;
- work beyond the allowance may need purchased credits.

**How a Codex batch is logged:**
- one row per batch, with the purpose, the Codex CLI version and model, the reasoning setting, and the input and output tokens if Codex reports them;
- the share of the allowance used, if the plan shows it;
- in the cost column, **$0.00 when the batch stayed within the included allowance**, or the dollars of any credits used.

A usage pilot on development items (about 100 screened questions and 100 graded answers) comes first, to measure usage per judgment and project the full runs.

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

**Total spent to date: $1.44.** Every row above is a Claude-era benchmark trial. Claude is no longer the teacher (`docs/methodology/workflow.md` Section 2.2), and those outputs are archived under the Git tag `pre-cleanup-claude-era`, where the original detailed version of this file, with per-trial arithmetic and the old pilot budget, can also be read.
