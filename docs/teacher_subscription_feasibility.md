# Can Teacher Generation Run on a Claude Team Subscription? (desk research, no spend)

Prepared 2026-10-04. Question: can the teacher data generation step (Sonnet 5.5, see [teacher_selection.md](teacher_selection.md)) run through a Claude Team plan using Claude Code instead of the pay-per-token API priced in [cost_estimate.md](cost_estimate.md)? Compares the Standard seat ($20 version) with the Premium seat ($100 version). No subscription or API money was spent; everything below comes from public pages (accessed 2026-10-04) and arithmetic.

## Recommendation

**Yes, it is feasible, but only as a one-shot, scripted, throttled run, not as an open-ended continuous process, and the capacity numbers are extrapolations that must be measured before committing.**

1. **Run the ~1k pilot on the subscription first** (about 3 Standard-seat sessions at the optimistic estimate). Read the usage meter (Settings > Usage) before and after to get the real percent-of-limit per example. This replaces every capacity guess in this document, the same way the Phase 4 pilot is meant to replace the token assumptions in cost_estimate.md.
2. **If the measured burn supports it, do the 50k minimum on 2 Standard seats on monthly billing** (about $50 to $250 total, versus $165 to $665 on the Batch API). Choose **Premium only if the pilot shows Standard would take more than about 3 months**: Premium costs about the same per example but finishes 5x faster, with a $250/month floor.
3. **Keep the API as the fallback and for the pieces the subscription is bad at:** benchmark and teacher evaluation runs that need pinned settings, any top-up that must be reproducible, and the whole job if Anthropic's paused change to programmatic limits takes effect (Section 1.3). If that change lands, Standard becomes unusable for this (about 33 months for 50k) and Premium marginal (about 7 months).
4. **Do not plan on 200k via subscription,** and do not use Opus on it (Sonnet and Opus draw on different weekly buckets, and Opus burns faster).

Headline caveat: Anthropic publishes no token or message counts for any plan. Every capacity figure here is scaled from a third-party measurement on a different plan and a different (coding-agent) workload. Treat the scenario table as a range, not a forecast.

## 1. Public facts

### 1.1 Plan comparison, side by side

| | Team Standard seat | Team Premium seat |
|---|---|---|
| Price per seat | $20/mo billed annually, $25 billed monthly | $100/mo billed annually, $125 billed monthly |
| Minimum seats | 2 (max 150) | 2 (max 150) |
| Real floor, annual / monthly | $40 / $50 per month | $200 / $250 per month |
| Usage per 5-hour session | 1.25x Pro | 6.25x Pro |
| Usage pools | Per member, not shared | Per member, not shared |
| Weekly cap | Yes, across all models, plus a separate Sonnet-only weekly cap; resets at a fixed per-account time (see Settings > Usage) | Same structure, higher |
| Claude Code | Included | Included |
| Extra usage | Admin can buy usage credits | Same |
| API-equivalent value per 5h session (scaled estimate) | about $9 | about $46 |
| API-equivalent weekly ceiling per seat (scaled estimate) | about $310 | about $1,550 |
| Sonnet 5.5 examples per session at $0.0266 each (estimate) | about 350 | about 1,740 |
| Sonnet 5.5 examples per week per seat (upper bound) | about 11,700 | about 58,300 |
| If the paused programmatic credit (1.3) takes effect | $20/mo, about 750 examples | $100/mo, about 3,760 examples |
| Value per dollar of seat fee | Same as Premium (about 54x API-equivalent per monthly dollar, estimate) | Same as Standard |

Sources: seat prices, multipliers, minimum seats and pool structure are from Anthropic's [Team plan page](https://support.claude.com/en/articles/9266767-what-is-the-team-plan) (fetched). API-equivalent values are scaled as described in 1.2.

### 1.2 How the capacity estimate was built (and why it is soft)

- Anthropic states no token count. Usage is metered as a share of a rolling 5-hour session plus a weekly cap, and depends on conversation length, model and features.
- The only measurement found: [finopsllm](https://finopsllm.com/research/claude-pro-max-tokens-limit) analysed 60 days of real Claude Code logs. A **Max 5x** session is about **39M tokens, or about $37 of API-priced usage**; the weekly ceiling on Max 5x is at least 1.3B tokens. Pro (about 8M tokens) and Max 20x are projected, not measured.
- Scaling: Pro per session is $37 / 5 = about $7.40. Standard is 1.25x = **$9.25**; Premium is 6.25x = **$46.25**. Weekly: 1.3B tokens at about 1.05M tokens per dollar is about $1,240 for Max 5x, so Pro is about $248, Standard about **$310**, Premium about **$1,550**.
- Caveats: (a) 96% of those measured tokens were cache reads, which are cheap, whereas teacher generation is output-heavy (about 2,600 output tokens per example, mostly thinking), so the dollar-weighted limit may not translate one-for-one; (b) the weekly figure is a lower bound for Max 5x; (c) Anthropic doubled Claude Code's five-hour limits for these plans on 2026-05-06 and can change them again at any time; (d) the weekly ceiling of about 33 full sessions per week is roughly the number of 5-hour windows in a week (33.6), so reaching it means running 24/7.
- A reality adjustment is built into the scenarios below: **Optimistic = 100%** of the scaled figure, **Conservative = 25%**, **Pessimistic = 10%**.

### 1.3 Programmatic use: what is allowed, and a pending change

- Claude Code's non-interactive mode (`claude -p`) and the Agent SDK **currently draw from the subscription's usage limits.** On 2026-06-15 Anthropic planned to move them to a separate monthly credit (Standard $20, Premium $100, Max 5x $100, Max 20x $200) and then **paused the change**, saying it is working on a better plan ([Agent SDK and your Claude plan](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan), fetched; [summary](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026), search snippet only).
- If it is revived as announced, scripted generation would be capped at $20 or $100 per seat per month of API-priced usage. At $0.0266 per example that is **about 750 examples per Standard seat per month** (two seats: about 1,500/month, so 50k takes about 33 months) or **about 3,760 per Premium seat per month** (two seats: about 7,500/month, so 50k takes about 6.6 months).
- Third-party tools that borrow subscription login tokens are not allowed (enforcement began in January 2026 and was tightened 2026-04-04; [Engineer's Codex](https://www.engineerscodex.com/anthropic-claude-subscription-switcharoo), fetched; other search snippets agree). Running Anthropic's own Claude Code CLI on your own machine for personal or local work is described as fine; sources conflict on whether the Agent SDK itself is subscription-eligible, so this plan uses only `claude -p`.
- Setting `ANTHROPIC_API_KEY` in the environment makes Claude Code bill the API instead of the subscription ([Claude Code with Pro/Max](https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan), fetched). The generation script must make sure that variable is unset.

### 1.4 Terms to confirm

- Team plans fall under Anthropic's [Commercial Terms](https://www.anthropic.com/legal/commercial-terms) (fetched). The customer owns the outputs, and Anthropic may not train on Customer Content. The same document bars using the Services "to build a competing product or service, including to train competing AI models". Whether a Pythia-based statistics tutor counts as "competing" is a question for the advisor or university counsel. **It applies equally to the API route**, so it does not change the subscription-vs-API choice, but it should be settled before generating 50k examples either way.

## 2. Project requirements (from this repo)

| Requirement | Value | Source |
|---|---|---|
| Training examples | 1k pilot, 50k minimum, 100k, 200k stretch; nested sets | README.md, cost_estimate.md |
| Over-generation | 10 to 25% extra for verification failures | cost_estimate.md |
| Tokens per example | Base 300 in / 600 out; Base + thinking adds 2,000 | teacher_selection.md |
| Cost per example, Sonnet 5.5, standard pricing | $0.0066 (Base), $0.0266 (Base + 2k thinking) | teacher_selection.md |
| Shape of the work | One-shot dated batches, not recurring | README.md |
| Provenance logging | Model ID, effort, thinking mode, sampling settings per batch | README.md |
| Timeline | Generate in Semester 1 late; fine-tune Semester 2 early (dates are placeholders) | README.md |

Capacity in Section 1 is metered at standard (non-Batch) prices, so the right per-example yardstick is $0.0266, and the right API comparison for cash cost is the Batch API at half of that.

## 3. Time and cost model

Examples per week: Standard 11,654/seat, Premium 58,271/seat at 100%; scenarios scale this by 100%, 25%, 10%. All rows use the minimum 2 seats and monthly billing (1 month = 4.33 weeks, rounded up to whole months). Targets are raw examples; add 10 to 25% for verification failures (50k verified needs up to 62.5k generated).

**Weeks to reach the target (2 seats)**

| Target | Standard: Opt / Cons / Pess | Premium: Opt / Cons / Pess |
|---|---|---|
| 1k pilot | 0.04 / 0.17 / 0.43 (about 0.3 / 1.2 / 3 days) | under 1 day in all cases |
| 50k | 2.1 / 8.6 / 21.4 | 0.4 / 1.7 / 4.3 |
| 100k | 4.3 / 17.2 / 42.9 | 0.9 / 3.4 / 8.6 |
| 200k | 8.6 / 34.3 / 85.8 | 1.7 / 6.9 / 17.2 |

**Seat cost to finish (monthly billing, 2 seats) versus the API Batch**

| Target | Standard Opt / Cons / Pess | Premium Opt / Cons / Pess | API Batch, Sonnet 5.5 (Base to Base + 2k thinking) |
|---|---|---|---|
| 50k | $50 / $100 / $250 | $250 / $250 / $250 | $165 to $665 |
| 100k | $50 / $200 / $500 | $250 / $250 / $500 | $330 to $1,330 |
| 200k | $100 / $400 / $1,000 | $250 / $500 / $1,000 | $660 to $2,660 |

Reading the tables:

- **Per dollar, Standard and Premium are the same value** (both about 54x the seat fee in API-equivalent usage per month, on the scaled estimate). Premium buys speed and headroom, not savings. It costs more only through its $250/month floor and when you would not otherwise have used the capacity.
- Under these numbers the subscription is cheaper than the API at every size in the Optimistic and Conservative scenarios, and only the Pessimistic scenario at 100k and above erodes the advantage on Standard. The relevant comparison for 50k is **about $100 versus about $665** in the Conservative case. The saving is real but small in absolute terms (a few hundred dollars), and it is bought with risk (Section 4).
- Annual billing would lock in $480 (Standard) or $2,400 (Premium) for 2 seats. That is the wrong shape for a one-shot job. **Use monthly billing and cancel after the run.**
- Mixed seats (for example 1 Standard + 1 Premium) are plausible but not confirmed on the plan page; check before relying on it.
- Optimistic time assumes the cap is the only limit. In practice a script that runs 8 to 12 hours a day touches 2 to 3 sessions per day, which is roughly 40 to 60% of the weekly ceiling, so the Optimistic column is a floor on time, not a typical value.

## 4. Frictions specific to this project

| Issue | Effect | Mitigation |
|---|---|---|
| Per-call overhead of Claude Code (system prompt, tools) | Inflates tokens per example versus the raw API | Pack 10 to 20 prompts per `claude -p` call; disable unneeded tools |
| No sampling control (temperature, top_p), limited effort and thinking control | Conflicts with the README's provenance fields | Log the `--model` flag, CLI version and effort actually used; note that sampling is not controllable; consider this when deciding whether benchmark runs stay on the API |
| Default model is not Sonnet (Opus is the default on Pro and Team Standard in recent Claude Code versions) | Wrong teacher and faster limit burn | Always pass `--model claude-sonnet-5-5` and verify in the output metadata |
| No Batch discount, no queue | Slower per example and no 24h batch workflow | Run unattended, throttled |
| Hitting the 5-hour and weekly limits | Jobs stall mid-run | Script must detect the limit message, sleep until the window resets, and resume from a manifest of finished prompt IDs |
| Shared pool with interactive use | Running Claude Code on the project eats the same budget | Dedicate the seats (or schedule generation outside working hours) |
| Policy drift (Section 1.3) | The route can get 5 to 50x worse overnight | Keep the API path working and budgeted as fallback |
| Reproducibility | Outputs are non-deterministic either way, but a CLI run records less metadata than an API response (no `usage` block per call) | Save the raw CLI JSON output (`--output-format json`) and the usage meter readings per batch |
| Verification | The ChatGPT verifier step in Phase 7 is separate and is not covered by this analysis | n/a |

## 5. Decision rule and result

Rule: use the subscription for the 50k minimum only if all hold:
1. Scripted `claude -p` use is permitted and still counts against subscription limits on the day generation starts.
2. The pilot's measured burn projects 50k raw examples within the Semester 1 late window (use the Conservative figure, not the Optimistic one).
3. The expected saving versus the Batch API is meaningful (at least a few hundred dollars).
4. The per-batch provenance fields in the README can still be recorded.

Result today: (1) holds at the time of writing but is explicitly unstable; (2) cannot be decided until the pilot; (3) holds under every scenario except Pessimistic at 100k+; (4) holds with the mitigations above, except sampling settings, which are not recorded because they cannot be set. So the decision is **conditional on the pilot, with Standard as the default and Premium as the schedule lever**:

- Pilot burn implies 50k fits in about 3 months on 2 Standard seats: use Standard (about $100 to $250).
- Pilot implies more than that: pay for Premium for one or two months (about $250 to $500) and cancel.
- Policy change lands, or the pilot shows far worse burn than the Pessimistic case: fall back to the Batch API ($165 to $665 for 50k).

## 6. Limitations

- The capacity numbers rest on one third-party dataset for a different plan and workload, scaled by Anthropic's multipliers. They could be off by several times in either direction. The measurable correction is the pilot.
- Pricing, multipliers and limits changed during 2026 (doubled five-hour limits on 2026-05-06; the programmatic-credit plan announced and paused in June) and can change again.
- The two-seat minimum and monthly-billing figures come from the Team plan page; whether a university or department can purchase Team seats this way, and whether you are allowed to use personal accounts for this, is not covered here.
- This document does not assess whether using subscription outputs for training is acceptable under the Commercial Terms clause (1.4); that applies to the API as well.

## 7. Sources (accessed 2026-10-04)

Fetched and read:
- [What is the Team plan?](https://support.claude.com/en/articles/9266767-what-is-the-team-plan) (Anthropic)
- [Use the Claude Agent SDK with your Claude plan](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan) (Anthropic)
- [Using Claude Code with your Pro or Max plan](https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan) (Anthropic)
- [Commercial Terms](https://www.anthropic.com/legal/commercial-terms) (Anthropic)
- [How many tokens do you get with Claude Pro and Max? We counted them](https://finopsllm.com/research/claude-pro-max-tokens-limit) (finopsllm)
- [How Claude Team Plan Usage Limits Really Work in 2026](https://dejaflow.com/blog/2026/05/04/how-claude-team-plan-usage-limits-work/) (Dejaflow)
- [Anthropic's Confusing Claude Subscription Policy, Explained](https://www.engineerscodex.com/anthropic-claude-subscription-switcharoo) (Engineer's Codex)

Search snippets only (page not read in full; the fetch of morphllm returned HTTP 429):
- [Claude Credit Overhaul 2026: Anthropic Pauses the June 15 Change](https://www.digitalapplied.com/blog/anthropic-claude-credit-overhaul-june-15-2026)
- [Claude Code Usage Limits (2026)](https://www.morphllm.com/claude-code-usage-limits)
- [Claude Code Limits](https://claudelog.com/claude-code-limits/)

Project documents: [teacher_selection.md](teacher_selection.md), [cost_estimate.md](cost_estimate.md), README.md.
