# Cost Log

The running record of every dollar spent on this project. Add a row in the same session as any paid Claude API call (see README Section 12 and `CLAUDE.md`). Redhawk and Talon cluster time is free with sponsorship, so the Claude API is the only cash cost.

## How to read and fill in a row

**Tokens.** The API does not charge by words. It charges by *tokens*, which are small chunks of text, roughly three quarters of an English word each. You pay separately for tokens you send (input) and tokens the model writes back (output).

**Thinking tokens.** Sonnet 5.5 can "think" before it answers, writing hidden reasoning. That reasoning is billed at the output price, which is the expensive side, so a thinking-heavy answer costs several times more than a short one. In the log, put thinking tokens inside the output-token column and note it.

**Batch API.** Anthropic gives a 50% discount if you submit requests as a batch and accept results within about 24 hours instead of instantly. All bulk generation here uses Batch. Sonnet 5.5 prices (USD per million tokens, source `teacher_selection.md`): standard $2 input / $10 output; Batch $1 input / $5 output.

**How the cost column is computed.**

cost = (input tokens x input price + output tokens x output price) / 1,000,000

Worked example (Batch, from `cost_estimate.md`): one benchmark question with 300 input tokens and 600 output tokens costs (300 x $1 + 600 x $5) / 1,000,000 = $0.0033. If the model also uses 2,000 thinking tokens, output becomes 2,600 and the cost is (300 x $1 + 2,600 x $5) / 1,000,000 = $0.0133. For 1,000 questions that is $3.30 and $13.30. The real token counts come from the `usage` field the API returns with every response; copy those numbers in rather than estimating.

## Ledger

| UTC date/time | Purpose (phase) | Model ID | Effort / thinking | Batch or standard | Input tokens | Output tokens (incl. thinking) | Cost (USD) | Running total (USD) | Output folder | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-06 | Setup, no API calls yet | n/a | n/a | n/a | 0 | 0 | 0.00 | 0.00 | n/a | Teacher selection and cost estimates were desk research from public pages, not API spend. Subscription seats not purchased. |
| 2026-10-07 (UTC, about 02:00) | Phase 3 prompt trial: 20 benchmark questions (`benchmark_generation_v1`), 20 separate calls | `claude-sonnet-5-5` | effort medium; adaptive thinking (API default); sampling = API defaults | Standard (not Batch) | 28,850 | 7,017 (incl. any thinking) | 0.1279 | 0.13 | `C:\masters_project_large\data\teacher_outputs\2026-10-07_sonnet-5-5_benchmark-trial01\` (review copy in `results/benchmark_trial/`) | Cap was $3.00; worst case was $1.05; estimate was about $0.35, actual was a third of that. Prices: $2 / $10 per million tokens. 20 of 20 items parsed; 3 answer keys were wrong (see below). |
| 2026-10-07 (UTC, later the same day) | Phase 3 prompt trial 2: the same 20 slots with `benchmark_generation_v2` (adds `working` and `r_solution`), 20 separate calls | `claude-sonnet-5-5` | effort medium; adaptive thinking (API default); sampling = API defaults | Standard (not Batch) | 35,767 | 10,492 (incl. any thinking) | 0.1765 | 0.30 | `C:\masters_project_large\data\teacher_outputs\2026-10-07_sonnet-5-5_benchmark-trial02\` (review copy in `results/benchmark_trial/`) | Stated before the run: expected about $0.15 to $0.25, cap $1.50 (worst case $1.06). Actual $0.1765, inside the expected range. 20 of 20 parsed; R then verified the keys (see below). |
| 2026-10-07 00:15 UTC | Pythia base-model probe (Phase 2, `code/evaluation/pythia_probe.py`) | n/a (no Claude call; local Pythia models) | n/a | n/a | 0 | 0 | 0.00 | 0.00 | `results/pythia_probe/2026-10-07_0015Z_probe.*` | Ran on this PC's CPU, so $0. Recorded here because it is a measured pilot-related step. An earlier run the same evening had a stop-token bug for the 1B model and was replaced. |

## First measured numbers: the 20-question trial (2026-10-07)

How the cost was worked out, with real numbers: the 20 calls used 28,850 input tokens and 7,017 output tokens. Input: 28,850 x $2 / 1,000,000 = $0.0577. Output: 7,017 x $10 / 1,000,000 = $0.0702. Total $0.1279, which is about **$0.0064 per question** at standard prices.

| | Estimate before the trial | Measured |
|---|---|---|
| Input tokens per question | about 1,200 | about 1,440 (the system prompt and JSON schema are bigger than I guessed) |
| Output tokens per question (including thinking) | about 1,500 | about 350 (at medium effort the model barely thinks for these short questions) |
| Cost per question, standard | about $0.0174 | **$0.0064** |
| Forecast for 1,000 questions, **Batch** (half price) | about $8.70 | **about $3.20** |
| Forecast for 1,000 questions, standard | about $17.40 | about $6.40 |

What this does and does not tell us: it is only 20 questions at medium effort, the questions are short, and the average will move if we change the prompt, the effort level, or ask for longer questions. It also says nothing about the cost of the second step (the blind re-solve check on each question), which is likely a similar amount, or about the teacher run on the finished benchmark. Still, a benchmark generation run of a few dollars, not the $13 high case, is now the working assumption. Re-measure after any prompt change.

**Trial 2 (prompt v2) cost, with the same arithmetic:** 35,767 input tokens x $2 / 1,000,000 = $0.0715, plus 10,492 output tokens x $10 / 1,000,000 = $0.1049, total **$0.1765**, or about **$0.0088 per question**. That is about 38% more than v1 ($0.0064) because every reply now also contains a written calculation and R code (about 520 output tokens per question instead of 350, and about 1,790 input tokens instead of 1,440 because the prompt is longer). Updated forecast for 1,000 questions: about **$4.40 on Batch** (half of $8.80 standard). Running R to check the keys costs nothing.

**The cheap cost hid an expensive problem:** by the numbers, 3 of the 8 numerical answer keys were wrong (see `docs/pilot_plan.md` Step 1 and the progress log). The money was not the risk; the correctness of the keys is.

## Pilot budget versus actual

Expected cost of the Phase 3 and Phase 4 pilot, using the desk figures in `cost_estimate.md` (Sonnet 5.5, Batch; the low end assumes no thinking, the high end adds 2,000 thinking tokens per item):

| Pilot step | Expected | Actual | Difference |
|---|---|---|---|
| Phase 3: 20-question prompt trial (standard prices) | about $0.35 | $0.1279 | $0.22 less |
| Phase 3: second 20-question trial with prompt v2 (standard prices) | about $0.15 to $0.25 | $0.1765 | within range |
| Phase 3: generate about 1k benchmark questions with answer keys | $3 to $13 (now forecast about $4.40 on Batch from trial 2) | not yet run | |
| Phase 3: blind re-solve of each benchmark question by a fresh call (key check) | $3 to $13 | not yet run | |
| Phase 4: generate about 1k training questions and teacher answers | $3 to $13 | not yet run | |
| Phase 4: run the teacher on the benchmark (for the teacher accuracy baseline) | $3 to $13 | not yet run | |
| Over-generation for items that fail checks (10 to 25% of one generation run) | up to about $3 | not yet run | |
| **Pilot total** | **about $13 to $57 (likely lower; see the trial numbers above)** | **$0.30 so far** | |

**Possible savings to test in the pilot (not yet a forecast):** the Pythia probe (`pythia_behavior_analysis.md` section 5.3) suggests the student can only imitate short answers, so the teacher does not need to write long ones. At Batch prices, 300 input tokens plus 200 output tokens costs $0.0013 per example, and 300 in plus 1,200 out (with some thinking) costs $0.0063, against $0.0133 for the current high case. So the real cost per 1k examples might be $1.30 to $6.30 instead of $13.30. The pilot should generate a small sample at two effort levels and record both the cost and the share of answers that pass verification, because a cheaper answer only saves money if it is still correct.

The point of the pilot is to replace these guesses with measured token counts. After the pilot, update `cost_estimate.md` with the measured cost per item and re-project the 50k, 100k and 200k costs. If the measured cost per item differs a lot from $0.0033 to $0.0133, that changes the size of the funding request.
