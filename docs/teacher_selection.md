# Teacher Model Selection (desk research, no API spend)

Prepared 2026-09-30. Candidates: Claude Opus 5.5, Claude Sonnet 5.5, Claude Fable 5.1, Claude Haiku 4.5. No API calls were made; everything below comes from public pages (accessed 2026-09-30) and arithmetic.

## Recommendation

**Use Claude Sonnet 5.5 as the teacher.** Keep Claude Opus 5.5 as the pre-agreed fallback. Fable 5.1 is dominated (about 2.5x Opus 5.5's price with a lower independent quality score). Haiku 4.5 is cheapest but is a previous-generation model without published evidence that it is a strong enough teacher.

Use it at `medium` or `high` effort, not `max` (see Cost notes). Sonnet 5.5 defaults to `high`; Opus 5.5 defaults to `medium`.

## 1. Public facts

Prices are USD per million tokens (MTok) from the [Anthropic pricing page](https://platform.claude.com/docs/en/about-claude/pricing). Model specs are from the [models overview](https://platform.claude.com/docs/en/about-claude/models/overview).

| | Fable 5.1 | Opus 5.5 | Sonnet 5.5 | Haiku 4.5 |
|---|---|---|---|---|
| Input / output | $10 / $50 | $4 / $20 | $2 / $10 | $1 / $5 |
| Batch API (50% off) | $5 / $25 | $2 / $10 | $1 / $5 | $0.50 / $2.50 |
| Cache read | $0.25 | $0.20 | $0.20 | $0.10 |
| Context / max output | 1M / 128K | 1M / 128K | 1M / 128K | 200K / 64K |
| Thinking | Adaptive, always on | Adaptive, always on | Adaptive | Extended (manual) |
| Default effort | high | medium | high | not supported |
| Knowledge cutoff (reliable) | Jun 2026 | Jun 2026 | Jun 2026 | Feb 2025 |
| Latency (relative) | Slower | Moderate | Fast | Fastest |

Notes: thinking tokens bill as output tokens. Models from 4.7 onward use a tokenizer that produces about 30% more tokens for the same text than Haiku 4.5's tokenizer. Anthropic's own guidance is to start with Opus 5.5 for most workloads and reserve Fable 5.1 for demanding reasoning or when Opus 5.5 at higher effort still falls short.

### Published quality evidence

None of these sources reports statistics/R-specific scores, so general reasoning, science and coding benchmarks are used as proxies.

| Measure | Fable 5.1 | Opus 5.5 | Sonnet 5.5 | Haiku 4.5 | Source |
|---|---|---|---|---|---|
| Artificial Analysis Intelligence Index | 53 | 58 | 56 | not listed | [kingy.ai (Sonnet)](https://kingy.ai/blog/claude-sonnet-5-5-specs-benchmarks-pricing/), [kingy.ai (Opus)](https://kingy.ai/blog/claude-opus-5-5-specs-benchmarks-pricing-comparison/) |
| Humanity's Last Exam, with tools (vendor-reported) | 65.6 | 67.7 | 64.5 | n/a | [Anthropic](https://www.anthropic.com/claude-opus-5-5), [kingy.ai](https://kingy.ai/blog/claude-sonnet-5-5-specs-benchmarks-pricing/) |
| Terminal-Bench-Science 0.1 | 52.6 | 58.7 | not reported | n/a | [Anthropic](https://www.anthropic.com/claude-opus-5-5) |
| Terminal-Bench 4.0 (coding/agentic) | 55.8 | 66.4 | 70.6 | n/a | as above |
| SWE-Bench Pro | not reported | 89.9 | 81.3 | n/a | [kingy.ai](https://kingy.ai/blog/claude-sonnet-5-5-specs-benchmarks-pricing/) |
| GDPval-AA v2.1 (Elo) | 1735 | 1846 | 1844 | n/a | as above |
| GPQA Diamond / AIME 2025 | n/a | n/a | n/a | 73% / 80.7% | [Anthropic Haiku 4.5](https://www.anthropic.com/news/claude-haiku-4-5) via search snippet |

Caveats: vendor-reported and third-party numbers use different settings (for example, Opus 5.5 HLE is 67.7 as reported by Anthropic and 61.4 in Artificial Analysis's run). Sonnet 5.5 and Haiku 4.5 have no head-to-head data on several benchmarks. Haiku 4.5 is an October 2025 model with a Feb 2025 knowledge cutoff, and its scores come from a different (older) generation of benchmarks.

## 2. Cost model

Assumptions (per example, tokens): Low 200 in / 400 out; Base 300 in / 600 out; High 500 in / 1,200 out; and a Base+thinking case adding 2,000 thinking tokens to the output. Haiku 4.5 token counts are scaled by 1/1.3 for its older tokenizer, and it runs without thinking. Fable 5.1 and Opus 5.5 always think, so the "Base+2k thinking" row is closest to their real use; Sonnet 5.5 thinks adaptively. Prompt caching is ignored because the shared instruction prefix is small; it would only lower input cost.

**Cost to generate the raw examples, standard pricing (Batch API halves every figure):**

| Scenario | Model | Per example | 1k | 10k | 50k | 100k | 200k |
|---|---|---|---|---|---|---|---|
| Low | Fable 5.1 | $0.0220 | $22 | $220 | $1,100 | $2,200 | $4,400 |
| Low | Opus 5.5 | $0.0088 | $9 | $88 | $440 | $880 | $1,760 |
| Low | Sonnet 5.5 | $0.0044 | $4 | $44 | $220 | $440 | $880 |
| Low | Haiku 4.5 | $0.0017 | $2 | $17 | $85 | $169 | $338 |
| Base | Fable 5.1 | $0.0330 | $33 | $330 | $1,650 | $3,300 | $6,600 |
| Base | Opus 5.5 | $0.0132 | $13 | $132 | $660 | $1,320 | $2,640 |
| Base | Sonnet 5.5 | $0.0066 | $7 | $66 | $330 | $660 | $1,320 |
| Base | Haiku 4.5 | $0.0025 | $3 | $25 | $127 | $254 | $508 |
| High | Fable 5.1 | $0.0650 | $65 | $650 | $3,250 | $6,500 | $13,000 |
| High | Opus 5.5 | $0.0260 | $26 | $260 | $1,300 | $2,600 | $5,200 |
| High | Sonnet 5.5 | $0.0130 | $13 | $130 | $650 | $1,300 | $2,600 |
| High | Haiku 4.5 | $0.0050 | $5 | $50 | $250 | $500 | $1,000 |
| Base + 2k thinking | Fable 5.1 | $0.1330 | $133 | $1,330 | $6,650 | $13,300 | $26,600 |
| Base + 2k thinking | Opus 5.5 | $0.0532 | $53 | $532 | $2,660 | $5,320 | $10,640 |
| Base + 2k thinking | Sonnet 5.5 | $0.0266 | $27 | $266 | $1,330 | $2,660 | $5,320 |

Formula: cost = (input tokens x input price + output tokens x output price) / 1,000,000. The 10k and 100k columns are the 1k and 50k figures scaled.

**Cost per verified-correct example** is cost divided by the share of examples that pass verification. Pass rates are not published for this task, so I use the break-even form instead of guessing: a pricier model is cheaper per verified example only if its pass rate is higher by at least its price ratio.
- Opus 5.5 vs. Sonnet 5.5: Opus costs 2x per token, so its pass rate would need to be 2x Sonnet's. That is impossible (it would exceed 100% for any Sonnet rate above 50%).
- Fable 5.1 vs. Opus 5.5: Fable costs 2.5x, so it would need 2.5x the pass rate.
- Sonnet uses more tokens than Opus at `max` effort (Artificial Analysis: about 193K vs. 119K output tokens per task, roughly 1.6x). Sonnet's per-token output price is half of Opus's, so at 1.6x tokens its cost is 0.8x Opus's, still cheaper. It would only lose if it emitted more than 2x Opus's tokens.
- Sonnet 5.5 costs about $7.60 per task vs. $5.98 for Opus 5.5 at `max` effort in that same run, so avoid `max` for Sonnet. Its own guidance is to run Medium or High.

## 3. Decision rule and result

Rule (from the plan, with the primary quality score named here):
1. Drop any model with no published evidence of strong math/statistics and code performance.
2. Among the rest, treat models within 3 points of the best on the Artificial Analysis Intelligence Index as equivalent on quality (it is the broadest single independent score; the other benchmarks are tie-breakers).
3. Choose the cheapest equivalent-quality model by cost per verified-correct example.
4. If only the top model clears the bar, choose it unless the 50k cost is out of budget.

Result:
- **Haiku 4.5: dropped by rule 1.** Older generation, no head-to-head evidence, lower GPQA (73%) than comparable earlier Sonnet models, and the oldest knowledge cutoff (Feb 2025). It is very cheap ($63 to $250 for 50k with Batch), so it is worth reconsidering only if the budget becomes the binding constraint.
- **Fable 5.1: dominated.** Index 53 vs. 58 for Opus 5.5 and 56 for Sonnet 5.5, at 2.5x Opus's price and 5x Sonnet's. No published result shows it ahead of Opus 5.5 on the measures relevant here.
- **Opus 5.5 vs. Sonnet 5.5:** Index 58 vs. 56, which is within the 3-point band, so they are equivalent on quality by the rule. Sonnet is about half the cost, so **Sonnet 5.5 wins**.

Edge case to be aware of: Opus 5.5 leads Sonnet 5.5 by 3.2 points on HLE with tools (67.7 vs. 64.5) and by 8.6 on SWE-Bench Pro, though Sonnet leads on Terminal-Bench 4.0 and ties on GDPval-AA. These are the strongest arguments for Opus, but neither measures statistics or R directly.

Absolute cost at the README's minimum size (50k examples, Batch API, Base + 2k thinking): about **$665 for Sonnet 5.5 vs. $1,330 for Opus 5.5**. The difference is roughly $665 at 50k and about $2,660 at 200k.

## 4. Limitation and safeguard

Public benchmarks are proxies for statistics/R quality. The free safeguard is already in the plan: the chosen teacher's accuracy on the frozen benchmark is measured in Phase 5. If it is below the 80% red-flag level (README Section 1), or the verifier pass rate in Phase 7 is poor, switch the teacher to Opus 5.5 before generating the full set. Because the verifier filters bad items, teacher errors cost money more than they damage the final data.

Open input still needed: the total API budget for teacher generation. Without it the decision stands on the projections above.

## 5. Sources (accessed 2026-09-30)

- [Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Introducing Claude Opus 5.5](https://www.anthropic.com/claude-opus-5-5)
- [Introducing Claude Fable 5.1](https://www.anthropic.com/claude-fable-and-mythos-5-1)
- [Claude Sonnet 5.5 specs, benchmarks and cost per task (kingy.ai)](https://kingy.ai/blog/claude-sonnet-5-5-specs-benchmarks-pricing/)
- [Claude Opus 5.5 specs and comparison (kingy.ai)](https://kingy.ai/blog/claude-opus-5-5-specs-benchmarks-pricing-comparison/)
- [Introducing Claude Haiku 4.5](https://www.anthropic.com/news/claude-haiku-4-5)
