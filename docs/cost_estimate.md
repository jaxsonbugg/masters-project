# Cost estimate

Date: 2026-10-01. Status: desk estimate, to be replaced by measured token counts in the Phase 3 pilot.

## 1. Summary

Student training on Redhawk is free with sponsorship (see `cluster_selection.md`). The only real cash cost is Claude API usage for teacher data and teacher evaluation.

| Scenario | Training-set size | Teacher | Estimated cost |
|---|---|---|---|
| Minimum (README Section 9, 50k first) | 50k | Sonnet 5.5, Batch | **$165 to $665** |
| Mid | 100k | Sonnet 5.5, Batch | $330 to $1,330 |
| Full | 200k | Sonnet 5.5, Batch | **$660 to $2,660** |
| Fallback (teacher below 80% on benchmark) | 50k / 200k | Opus 5.5, Batch | $1,330 / $5,320 (upper case) |

The low end of each range assumes no thinking tokens (Base: 300 in / 600 out per example). The high end adds 2,000 thinking tokens per example. Sonnet 5.5 thinks adaptively, so the real figure is likely between the two. The pilot will pin it down.

## 2. Basis

- Prices (USD per million tokens, checked against the Anthropic pricing table on 2026-10-01): Sonnet 5.5 $2 input / $10 output; Opus 5.5 $4 / $20. The Batch API is 50% off both. Thinking tokens bill as output.
- Per-example token assumptions and the full price grid are in `teacher_selection.md` Section 2. Figures here are the Batch rows of that grid.
- Training sets are nested (1k within 10k within 50k and so on), so the data cost is the cost of the **largest** set generated, not the sum of all sizes.

| Size | Sonnet 5.5 Batch, Base | Sonnet 5.5 Batch, Base + 2k thinking | Opus 5.5 Batch, Base + 2k thinking |
|---|---|---|---|
| 1k (pilot) | $3 | $13 | $27 |
| 10k | $33 | $133 | $266 |
| 50k | $165 | $665 | $1,330 |
| 100k | $330 | $1,330 | $2,660 |
| 200k | $660 | $2,660 | $5,320 |

## 3. Other line items

| Item | Estimate | Note |
|---|---|---|
| Teacher on the frozen ~1k benchmark (Phase 5) | about $15 to $30 | Same per-example cost as the 1k row, plus a dev set. |
| Over-generation for items that fail verification | add 10 to 25% to the data cost | Assumption. The Phase 7 pass rate is unknown until the pilot. |
| Verifier model (Phase 7, high-effort ChatGPT) | not priced | Free if run by hand through a subscription at small scale. Needs API pricing if run at 50k+ scale. |
| Redhawk / Talon compute | $0 | Free with sponsorship. |

## 4. What to ask for

- **Minimum request: about $750.** Covers 50k examples on Sonnet 5.5 with thinking ($665) plus benchmark and dev-set runs, with a small buffer.
- **Full-grid request: about $3,000.** Covers 200k on Sonnet 5.5 with thinking ($2,660), benchmark runs, and a 10% buffer.
- **Contingency if the teacher must switch to Opus 5.5:** the figures double. Do not request this up front. The README triggers it only if teacher accuracy on the dev set is below 80%.

## 5. Ways to cut cost

- Cap the largest set (the README already allows this) and report the size curve up to the cap.
- Use the Batch API for all bulk generation (already assumed above).
- Use medium effort on Sonnet 5.5 rather than high. Anthropic's guidance for Sonnet is Medium or High, and the pilot should compare them.
- Check whether the department or university has an Anthropic API credit or a research allocation before spending personal money.

## 6. Limits of this estimate

- Token counts per example are assumptions. The pilot (Phase 3) should generate about 1k examples, record `usage` from the API responses, and update this file.
- Prices change. Re-check the pricing page before the large run.
- The verifier cost depends on a model and plan not yet chosen.
