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

## Pilot budget versus actual

Expected cost of the Phase 3 and Phase 4 pilot, using the desk figures in `cost_estimate.md` (Sonnet 5.5, Batch; the low end assumes no thinking, the high end adds 2,000 thinking tokens per item):

| Pilot step | Expected | Actual | Difference |
|---|---|---|---|
| Phase 3: generate about 1k benchmark questions with answer keys | $3 to $13 | not yet run | |
| Phase 3: blind re-solve of each benchmark question by a fresh call (key check) | $3 to $13 | not yet run | |
| Phase 4: generate about 1k training questions and teacher answers | $3 to $13 | not yet run | |
| Phase 4: run the teacher on the benchmark (for the teacher accuracy baseline) | $3 to $13 | not yet run | |
| Over-generation for items that fail checks (10 to 25% of one generation run) | up to about $3 | not yet run | |
| **Pilot total** | **about $13 to $57** | **$0.00 so far** | |

The point of the pilot is to replace these guesses with measured token counts. After the pilot, update `cost_estimate.md` with the measured cost per item and re-project the 50k, 100k and 200k costs. If the measured cost per item differs a lot from $0.0033 to $0.0133, that changes the size of the funding request.
