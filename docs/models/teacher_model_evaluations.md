# Teacher Model Evaluations: How Qwen3.6-27B Was Chosen as the Teacher

Prepared 2026-11-03 as desk research; updated 2026-11-07 after the teacher decision. No API calls, paid or free, and no cluster jobs were run for this research. Everything below comes from public pages (model cards, license files, provider price pages and terms, engine documentation), all accessed 2026-11-03, plus arithmetic that is shown. Facts marked **[S]** come from a secondary source or a search snippet and should be re-checked before they are relied on. Unmarked facts were read on a primary source (the model's own Hugging Face card, its LICENSE file, its tech report, or the provider's own page).

The research was written while the project still expected to use Claude Sonnet 5.5 as the teacher and only feared that Anthropic would not allow it. Anthropic has since said no, and the first choice of this document, Qwen3.6-27B, became the teacher. The text has been edited so it reads as the record of that choice: the license, quality and hardware findings are kept as they were found, and the parts that only made sense next to the Claude API (feature mapping, price and score comparisons with Sonnet) were removed. The full story of the Claude period, and how to recover its files, is in `docs/methodology/workflow.md` Section 2.2 and under the Git tag `pre-cleanup-claude-era`.

---

## Decision (2026-11-06)

**What was decided.** The teacher is **Qwen3.6-27B** (Alibaba, Apache 2.0 license). Anthropic support confirmed that Claude outputs may not be used to train the Pythia students, because Anthropic's Commercial Terms forbid using the service "to train competing AI models". Claude therefore no longer writes any training data or benchmark questions, and the open-weight evaluation below became the basis for the new teacher.

**Why Qwen3.6-27B.** It was ranked first here (Section 2) for three reasons: its license puts no limit on using its outputs to train other models, its published math, science and code scores are the highest of any candidate that fits our hardware, and it can run on Miami's own clusters, so the teacher costs no money and its exact weights can be pinned.

**How it runs.**
- **Talon (primary, for everything):** Miami's Talon cluster has 4 nodes, each with 4 NVIDIA H100 NVL GPUs. The teacher runs there in vLLM (an inference engine, Section 3) with the full **BF16** weights, meaning the model is used as released, without compression. The weights are pinned to repository `Qwen/Qwen3.6-27B`, revision `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9`. The Talon account has been active since 2026-11-06, when a read-only probe of the cluster was done. Talon costs nothing.
- **Redhawk (fallback):** if Talon is unavailable, the teacher runs on Redhawk's V100 GPUs through llama.cpp tag `b11960` with the 4-bit `Q4_K_M` GGUF file (Section 5 explains why llama.cpp and not vLLM).

**Planned deployment comparison.** Before the full run, the same development questions will be answered twice on Talon, once with the BF16 weights and once with a 4-bit version, to see whether compressing the teacher changes the quality of its questions and how much faster it is. Both runs use Talon, so the hardware is the same and only the precision differs. The Talon 4-bit backend is not built yet. Details are in `docs/methodology/workflow.md` Section 2.1; this comparison replaces the shortlist test proposed in Section 11.

**If the teacher underperforms.** The first remedy is the same Qwen3.6-27B at a higher precision or with more thinking, not a different model. DeepSeek V4-Flash and gpt-oss-120b (Section 2) stay documented as alternatives only.

**What could go wrong, and what this decision does not tell us.** Public benchmark scores do not test statistics or R, so the choice rests on proxies. Whether Qwen is good enough on our own questions is measured later, on the frozen benchmark in Phase 5 (a teacher below 80% is a red flag, `docs/methodology/workflow.md` Section 1.1). Paid calls, if any ever happen, are logged in `docs/logs/cost_log.md`; cluster jobs and GPU time are logged in `docs/logs/compute_log.md`.

---

## 1. Why this document exists

The project's original plan was to have Claude Sonnet 5.5 act as the **teacher**: it writes answers to statistics and R questions, and those answers become the training data that the small Pythia **students** learn from. Training a small model on a big model's outputs is called **distillation**: the knowledge of the big model is "distilled" into the small one.

Anthropic's Commercial Terms say the service may not be used "to build a competing product or service, including to train competing AI models". Training Pythia students on Claude's answers might fall under that sentence. Jaxson asked Anthropic support, and at the time of writing (2026-11-03) a "no" looked likely. Support has since confirmed the "no" (see the Decision above and `docs/methodology/workflow.md` Section 2.2). The project therefore needed a different teacher, and that teacher had to be **open-weight**.

**Open-weight** means the model's trained numbers (its "weights") are published, so anyone can download the model and run it on their own computer or cluster. This differs from Claude or ChatGPT, which can only be reached through the company's API. Open-weight models come with a license that says what you may do with them. That license is the main thing that decides whether we may use the model's outputs to train Pythia.

This document evaluates the six models Jaxson listed and a set of newer open-weight models, and ends with a recommendation that was adopted on 2026-11-06.

---

## 2. Recommendation (written 2026-11-03, adopted 2026-11-06)

**First choice, now the teacher: Qwen3.6-27B** (Alibaba, April 2026, Apache 2.0 license).
- It is the only strong candidate that can plausibly run on **Redhawk** (compressed to 4-bit across the two 16 GB V100 GPUs of one node), and it runs at full BF16 precision on Talon's H100s. Its license has no restriction on outputs.
- Its published math, science and code scores (GPQA Diamond 87.8, AIME 2026 94.1, LiveCodeBench v6 83.9) are far above every one of the six originally listed models.
- It has a thinking mode that can be switched on and off, and works with JSON-schema output in the usual inference engines.

**Runner-up, documented alternative: DeepSeek V4-Flash** (DeepSeek, April 2026, MIT license).
- It has the **clearest distillation permission of anything found**. The MIT license lets you do anything with the model, and DeepSeek's own API terms explicitly list "training other models (such as model distillation)" as a permitted use of outputs.
- It scores about as high as Qwen3.6-27B (GPQA 88.1, LiveCodeBench 91.6 in its highest thinking setting), and in 2026-11-03 prices it was the cheapest strong model to call through a hosted API (Section 6).
- It is too large for Redhawk, so it could only be used through a hosted API or on a bigger cluster such as Talon or OSC, and even on Talon its weight format needs checking (Section 9.2). It is not the plan.

**Third, documented alternative: gpt-oss-120b** (OpenAI, August 2025, Apache 2.0).
- It has a three-level "reasoning effort" setting (low/medium/high), which gives finer control over how long it thinks than Qwen's on/off switch.
- It fits on a single 80 GB H100, so it would be self-hostable on Talon or OSC, though not on Redhawk. Its scores (GPQA 80.1 [S]) are a step below the first two. It is not the plan.

**Best of the six originally listed models: Qwen3-32B.** If the decision had to come from that list alone, this is the one. It has an Apache 2.0 license, fits Redhawk at 4-bit, and has a thinking toggle. Its scores (GPQA 68.4, AIME 2025 72.9) are clearly below the 2026 models, though, so there is little reason to choose it over Qwen3.6-27B, which is from the same family and has the same license and nearly the same size.

**Shortlist proposed for a hands-on test (Section 11, superseded):** Qwen3.6-27B, DeepSeek V4-Flash, gpt-oss-120b, with Qwen3-32B as an optional fourth. The test was never run; the 2026-11-06 decision replaced it with the Talon 4-bit vs BF16 deployment comparison.

**Ruled out, one line each:**
- **DeepSeek-R1 (671B):** good scores in 2025, but it is now retired from DeepSeek's own API and from Together and Fireworks. It is far too large to self-host, very verbose (about 12,000 to 23,000 thinking tokens per hard math problem), and has weak structured output. DeepSeek V4-Flash replaces it with the same license, better scores and a lower price.
- **DeepSeek-R1-Distill-Qwen-32B:** clean license, but it has lower scores than Qwen3-32B on every benchmark, no hosted provider sells it, and it needs awkward prompting (no system prompt, forced `<think>`).
- **Mistral Small 3.1 24B:** clean license, but it has no reasoning mode and scores far too low for a statistics teacher (MATH 69.3, GPQA 46). Its reasoning sibling Magistral Small 1.2 is better but still well behind the 2026 models.
- **OLMo 3 / 3.1 32B Think:** the most "open" model of all (its training data is public too), with a clean license. Its scores trail (GPQA 57.5), and almost no hosted API sells it. Keep it in mind only if Dr. Lee values full openness for the report.
- **Qwen3-8B:** too small to be a strong teacher (GPQA 62.0). It also does not fit on one V100 at full precision, and no major host sells it.
- **Gemma 3** and **Llama 4:** their licenses put conditions on models trained with their outputs (Section 9), so they fail the "clearly allows distillation" test.

The most important caveat: **public benchmarks are not our task.** No source reports statistics- or R-specific scores for any of these models. The scores rank the candidates against each other, but only the Phase 5 teacher evaluation on our own frozen benchmark shows whether Qwen3.6-27B is good enough on our kind of questions.

---

## 3. Terms used in this document

**Parameters.** The adjustable numbers inside a model. More parameters usually mean a more capable model, and also more memory and compute. "32B" means about 32 billion parameters. Pythia 1B has about 1 billion.

**Dense vs. mixture-of-experts (MoE).** A dense model uses all of its parameters for every word it writes. An MoE model is split into many smaller "experts" and uses only a few of them for each word. DeepSeek V4-Flash, for example, has 284B parameters in total, but only 13B are **active** for any one token. MoE models are cheap to run per word (only the active part does work) but still need memory for all of their parameters, so they are hard to self-host.

**Tokens.** Models read and write in tokens, pieces of words about three-quarters of an English word long on average. Hosted providers quote prices per million tokens (MTok), separately for **input** (what we send) and **output** (what the model writes). On our own GPUs a token costs GPU time instead of money.

**Thinking (reasoning) tokens.** Many current models first write a hidden or marked-off "scratchpad" of reasoning (often between `<think>` and `</think>`), then the final answer. Those thinking tokens take time to generate like any other output (and are billed as output by hosted providers), so a model that thinks for 5,000 tokens takes about ten times as long as one that answers in 500.

**Quantization (FP16, BF16, 8-bit, 4-bit).** Each parameter is stored as a number. At **FP16** ("16-bit floating point") each parameter takes 2 bytes. **BF16** is another 16-bit format, also 2 bytes per parameter; newer GPUs such as the H100 support it in hardware and the V100 does not. The teacher runs at BF16 on Talon, meaning without compression. **8-bit** takes 1 byte. **4-bit** takes half a byte. Shrinking the numbers like this is called quantization. It lets a big model fit on a small GPU at the cost of a small loss of accuracy, usually minor at 8-bit and noticeable but often acceptable at 4-bit. Common 4-bit file formats are **GPTQ**, **AWQ** and **GGUF** (the format used by llama.cpp; "Q4_K_M" is a popular 4-bit GGUF variant, and the one used for the Redhawk fallback).

*Worked example.* Qwen3-32B has about 32.8 billion parameters. At FP16 that is 32.8 billion × 2 bytes = about **65 GB**. One Redhawk node has two V100 GPUs with 16 GB each, **32 GB** in total, so the full-precision model does not fit. At 4-bit, the official AWQ file is **19.3 GB**, which fits in 32 GB and leaves about 7 to 9 GB for working memory. A 4-bit model also has some overhead for scaling factors, which is why 32.8 × 0.5 = 16.4 GB becomes about 19 GB in practice.

**KV cache.** While a model writes, it keeps a memory of every token so far (the "keys and values" of its attention layers). This memory grows with the length of each response and with how many requests are processed at once. On Qwen2.5-32B it is about 256 KB per token, so one 3,000-token conversation needs about 0.8 GB. The space left after the weights decides how many questions the GPU can work on at the same time, and that largely decides speed.

**Inference engine.** The software that runs a downloaded model: **vLLM** (the most common for large batch jobs, and the engine used on Talon), **SGLang**, **llama.cpp** (runs GGUF files, very portable, and the engine used on Redhawk), and others.

**Structured output / constrained (guided) decoding.** Our generation script asks for answers as a JSON object that matches a schema (a list of required fields and their types). With open-weight models the engine can *force* this. At every step it only allows tokens that keep the output valid against the schema. In vLLM this is done by a component such as xgrammar. In llama.cpp it is done with a grammar.

**Hosted API provider.** A company that runs open-weight models on its own GPUs and sells access per token, for example DeepInfra, Together, Fireworks, Groq or OpenRouter (OpenRouter is a marketplace that routes requests to many such providers). The project does not use one: the teacher runs on Talon. Their terms are still summarized here (Section 13), because they would matter if that ever changed.

**License vs. terms of service.** The *license* comes with the model weights and governs the model itself. A hosted provider's *terms of service* govern the use of its service. When we use a hosted provider, both apply. When we run the weights ourselves, only the license applies.

---

## 4. How the candidates were judged

The criteria are in order of importance. The first two are **gates**: a model that fails one is out, however good it is otherwise.

**Gate 1: the license must clearly allow training other models on its outputs** (Jaxson's "distillation guidelines" requirement). Three levels were found:
- *Explicit permission.* The DeepSeek models are MIT-licensed, and their model cards and API terms name distillation as allowed. This is the strongest position.
- *No restriction.* Apache 2.0 (Qwen, Mistral, OLMo, gpt-oss, Gemma 4) and plain MIT say nothing at all about outputs, so outputs are simply ours to use. That is legally clean but not as explicit.
- *Restriction.* Gemma 3's terms, Llama's naming clause, and custom licenses (Kimi K3, MiniMax) place conditions on models trained with their outputs. These fail the gate.

**Gate 2: it must be runnable somewhere we can reach and afford**: Redhawk, a hosted API at a sensible price, or Talon or OSC. (On 2026-11-03 Talon access was not yet confirmed; it has been active since 2026-11-06.)

**Scored factors:**
1. *Quality for statistics, math and R.* Measured by published math (AIME, MATH-500), graduate science (GPQA Diamond) and code (LiveCodeBench) scores. These are proxies; none tests statistics or R directly.
2. *Fit with our prompts and pipeline.* Can it follow a long rule list, produce schema-valid JSON, take a system prompt, switch thinking on or off, and be run in big batches? (Section 7.)
3. *Cost* for 50,000 examples (Section 6). This mattered while a hosted API was a likely route. With the teacher on Talon, generation costs no money, so this factor no longer affects the decision.
4. *Hardware fit and time* on Redhawk, or on Talon or OSC (Section 5).
5. *Reproducibility.* With open weights we can pin an exact file and its checksum, which is better than an API model that can be changed or retired. Retirement is a real risk: DeepSeek-R1 has already disappeared from most APIs.
6. *Output style for Pythia.* The students have a 2,048-token context and need short answers with a marked final answer (`docs/models/pythia_behavior_analysis.md`). A very verbose teacher takes more GPU time, and its long reasoning would have to be cut or summarized before it is used as training data.
7. *Support and ecosystem.* Quantized versions, engine support, documentation.

---

## 5. Hardware: what Redhawk can and cannot do

This section explains the hardware limits once, because they shape every model's verdict. Redhawk is now the fallback cluster, so these limits matter only if Talon is unavailable.

**What Redhawk has.** 4 GPU nodes, each with 2 NVIDIA V100 GPUs of 16 GB (so 32 GB per node, 8 GPUs shared by the whole campus). The V100 is a 2017 design (NVIDIA "compute capability 7.0"). It can compute in FP16 but has no hardware support for the newer BF16 or FP8 number formats (`docs/clusters/cluster_selection.md`).

**Problem 1: current vLLM no longer supports the V100.** vLLM's installation page now requires "compute capability 7.5 or higher". A change merged on 2026-04-23 (pull request #39878) removed the V100 from vLLM's builds when it moved to CUDA 13 and PyTorch 2.11, and vLLM 0.20.0 (2026-04-27) shipped that change. Users report that vLLM 0.18.x and earlier still run on V100 [S]. 0.19 is untested. So on Redhawk we would have to **pin an older vLLM (0.18 or earlier) built with CUDA 12.x**. The risk is that an old vLLM may not know how to run the newest model designs. Qwen3.6-27B uses a new hybrid attention design (introduced with Qwen3.5 in February 2026), and its model card requires vLLM 0.19.0 or later (`docs/methodology/workflow.md` Section 2.1). Community forks of vLLM with V100 patches exist [S] but are not official. **Resolution:** the Redhawk fallback does not use vLLM; it uses llama.cpp (below).

**Problem 2: some 4-bit formats do not work on the V100.** In vLLM on Volta, GPTQ, GGUF and bitsandbytes work, but AWQ and the fast "Marlin" kernels do not (they need newer GPUs). FlashAttention, the fast attention code most engines use, does not support the V100 either. vLLM falls back to a slower Triton attention backend.

**The reliable fallback is llama.cpp, and it is what the project uses on Redhawk.** It supports the V100 well (a December 2025 change added fast attention kernels for V100 tensor cores), runs GGUF 4-bit files, and can force JSON-schema output. It must be built with CUDA 12.x, because CUDA 13 dropped the V100. It is generally slower than vLLM for big batches, but far easier to get working on old GPUs. The Redhawk fallback is pinned to llama.cpp tag `b11960` with the Qwen3.6-27B `Q4_K_M` GGUF file (`configs/redhawk/common.sh`, `docs/methodology/workflow.md` Section 2.1).

**Problem 3: an 8B model at FP16 does not fit on one 16 GB V100.** 8.2 billion × 2 bytes = 16.4 GB, more than the card's 16 GB before any working memory. It needs either both GPUs of a node or an 8-bit version.

**How much fits, worked example (estimate).** A 32B model at 4-bit on one node: 32 GB total; usable at 90% is about 28.8 GB. Subtract about 19.5 GB of weights and about 2 GB of engine overhead, and about 7 GB is left for the KV cache, which is about 27,000 tokens. Each example is about 300 tokens in plus 600 out, so about 29 examples can be in progress at once. If the teacher thinks for an extra 2,000 tokens per example, that drops to about 9. Fewer examples at once means slower total throughput.

**Time on Redhawk for 50,000 examples (estimates, least certain number in this document).** I found no published speed for a 32B 4-bit model on V100s, so these are scaled from related measurements (V100 memory bandwidth of 900 GB/s, measured 8B and 14B speeds on V100s) and shown so they can be replaced by a real measurement:

| Setup | 600 output tokens each (30M tokens) | 2,600 output tokens each (130M tokens) |
|---|---|---|
| 32B (or 27B) at 4-bit on one node (2 V100s), about 150 to 250 tokens/s in total | about 33 h, or **67 GPU-hours** (range 42 to 111) | about 241 h (10 days), or **480 GPU-hours** (range 290 to 720) |
| 8B at FP16 across 2 V100s, about 800 to 1,500 tokens/s | about 5.6 h, or **11 GPU-hours** | about 45 h, or **90 GPU-hours** |

How the first cell is computed: 50,000 × 600 = 30 million output tokens; 30,000,000 ÷ 250 tokens per second = 120,000 s = 33 hours; × 2 GPUs = 67 GPU-hours. Redhawk is free, but 10 days of one node is a big share of 8 GPUs that the whole campus shares, and queue waits come on top. Running on all 4 nodes would cut the wall-clock time to about 2.5 days if they were free.

**Talon and OSC.** When this was written, access to **Talon** (4 nodes with 4 H100 GPUs each) was unconfirmed. The account has been active since 2026-11-06 (a read-only probe was done that day), and Talon is now the primary cluster for generation, training and evaluation, at no cost. On Talon the teacher runs at full BF16 precision in a current vLLM, so none of the V100 problems above apply there. **OSC** was noted as a realistic alternative and is kept here as background. Its Cardinal cluster has nodes with 4 H100 94 GB GPUs. The Ohio academic rate is listed at $0.09 per GPU-hour, and every Ohio academic faculty member gets an automatic $1,000 credit per fiscal year (FY27 confirmed). The project lead must be faculty, so Dr. Lee would have to set it up. Whether the $0.09 rate applies to H100s should be confirmed with OSC. NSF ACCESS (a graduate student can lead a small "Explore" allocation, with the advisor as co-PI) and the NAIRR Pilot (compute and model-access credits for US researchers) are other routes.

**What this means overall:** Redhawk can run a 24B to 32B model at 4-bit, but slowly, on an old software stack, and with real setup risk. Anything larger (DeepSeek R1 or V4, gpt-oss-120b) cannot run on Redhawk at all. With Talon available, the teacher runs there at full precision, and Redhawk stays a no-cost fallback through llama.cpp.

---

## 6. Hosted API cost for 50,000 examples (historical, 2026-11-03 prices)

**Why this section is kept.** When this research was done, a hosted API was a likely way to run an open-weight teacher, so price was one of the factors. Since the decision, the teacher runs on Talon, which costs no money; what generation costs now is GPU time, which is recorded in `docs/logs/compute_log.md`. The table is kept as a short record of why money stopped being a deciding factor. Prices change often, so re-check them if a hosted provider is ever considered again.

The token assumptions were the project's planning figures at the time:
- **Base:** 300 input and 600 output tokens per example, which means 15M input and 30M output tokens for 50,000.
- **Base + 2k thinking:** the same, plus 2,000 thinking tokens, so 130M output tokens.

Formula: cost = (input tokens × input price + output tokens × output price) ÷ 1,000,000.

*Worked example, DeepSeek V4-Flash on DeepInfra ($0.09 in / $0.18 out per million):* Base = 15 × 0.09 + 30 × 0.18 = 1.35 + 5.40 = **$6.75**. With thinking = 1.35 + 130 × 0.18 = 1.35 + 23.40 = **$24.75**.

| Model | Cheapest primary-source price (in / out per MTok) | 50k, Base | 50k, Base + 2k thinking |
|---|---|---|---|
| DeepSeek V4-Flash (DeepInfra) | $0.09 / $0.18 | $7 | $25 |
| DeepSeek `deepseek-flash` on DeepSeek's own API, off-peak (serves V4.1-Flash) | $0.15 / $0.60 (half of the $0.30 / $1.20 peak price) | $20 | $80 |
| gpt-oss-120b (cheapest OpenRouter provider; Together) | $0.03 / $0.15; Together $0.15 / $0.60 | $5; Together $20 | $20; Together $80 |
| Qwen3.6-27B (Chutes; DeepInfra) | $0.25 / $2.00; DeepInfra $0.32 / $3.20 | $64; DeepInfra $101 | $264; DeepInfra $421 |
| Qwen3-32B (DeepInfra) | $0.08 / $0.28 | $10 | $38 |
| DeepSeek-R1-0528 (DeepInfra) | $0.50 / $2.15 | $72 | $287 |
| OLMo 3.1 32B Think (secondary-source price only) [S] | $0.15 / $0.50 | $17 | $67 |
| Mistral Small 3.1 (Cloudflare via OpenRouter) | $0.351 / $0.555 | $22 | n/a (no thinking mode) |
| Qwen3-8B, R1-Distill-Qwen-32B | no hosted provider found | Redhawk only | Redhawk only |
| Any model self-hosted on Talon or Redhawk | $0 in money | GPU-hours, see Section 5 | GPU-hours, see Section 5 |

How to read this:
- **Even hosted, every option cost at most a few hundred dollars for 50k examples.** Money was never the deciding factor. Quality, time and the license are what matter.
- **Thinking length is the biggest unknown, and it still matters on Talon.** The 2,000-token figure is a planning assumption, not a measurement. Reasoning models often think much longer: DeepSeek-R1-0528 averages about 23,000 thinking tokens on a hard AIME problem, and Qwen3.8-27B used about 1.7 times the median number of tokens on the Artificial Analysis test suite. Our questions are much easier than AIME, so the real figure is probably lower, but the pilot must measure it. On our own GPUs each extra 1,000 thinking tokens per example means 50,000 × 1,000 = 50 million more tokens to generate for 50k examples, which is GPU time rather than dollars.
- **Batch discounts and prices varied by provider** (Fireworks and Groq offered 50% off batch jobs, DeepInfra 20%, DeepSeek off-peak half price, OpenRouter no batch API), and several prices changed or models were withdrawn during 2026.

---

## 7. Notes on running Qwen (and the alternatives) with our prompt and pipeline

Our generation script (`code/generation/generate_benchmark.py`, with `data/prompts/benchmark_generation_v6.md`) needs a handful of things from any teacher. This section records what was found about each, for Qwen3.6-27B first and the documented alternatives where they differ.

1. **A system prompt plus a user prompt.** The v6 system prompt is a numbered list of 11 rules. Qwen accepts a system prompt, as does every model here *except the original DeepSeek-R1 and R1-Distill models*, whose cards say to put everything in the user turn. Long rule lists are a test of instruction following. Where reported, OLMo 3.1 scores 93.8 on IFEval (an instruction-following benchmark). The other cards mostly do not report it.
2. **Structured output (a JSON schema).** The script needs a valid JSON object back. How the engines force it:
   - *vLLM (Talon):* `response_format` with a JSON schema, which forces valid output. Importantly, when a reasoning parser is enabled (there are ones for `qwen3`, `deepseek_r1`, `gemma4` and others), vLLM lets the model think freely and only enforces the schema after the end of the thinking block. Known bugs: Gemma 4 with thinking turned off silently skips the schema; DeepSeek V3.2/V4 on vLLM 0.20 put the JSON inside the reasoning field [S]; and the old `guided_json` field was removed, so a script that still sends it gets *unchecked* output without any error [S].
   - *llama.cpp (Redhawk):* `json_schema` or `response_format`. The schema is only used to force output and is *not* shown to the model, so the prompt must describe the fields too (ours already does). Thinking tokens count against the output limit, so long thinking can use up the budget before the JSON starts.
   - *Hosted providers (not used, recorded for completeness):* OpenRouter supports strict JSON schemas, but only on some providers. Setting `require_parameters: true` stops it from silently sending the request to a provider that only treats the schema "as a strong hint". Fireworks turns *off* reasoning when a JSON schema is used. Together supports JSON schema mode.
   - The DeepSeek-R1 paper itself says R1's "structural output capabilities ... remain suboptimal", another reason to drop it.
3. **Control over thinking.**
   - Qwen3 and Qwen3.6: thinking on or off (`enable_thinking`), with no in-between level. Qwen3.5 and later dropped the `/think` and `/no_think` switches. "More thinking" for Qwen3.6-27B (the fallback remedy in the Decision) therefore means a larger output budget with thinking on, not a different setting.
   - gpt-oss: reasoning effort low/medium/high.
   - DeepSeek V4: Non-think/High/Max modes.
   - OLMo 3 Think, R1 and R1-Distill: always think.
   - Mistral Small 3.1: never thinks.
4. **Batching.** On our own GPUs, vLLM's offline batch mode or a queue of requests to its server lets many questions be answered at once, which is what makes 50k or more examples practical.
5. **Output limit and cut-off detection.** Every engine has an output limit and reports whether the output was cut off, so the script's "cut off at the limit" check carries over directly. Reasoning models need a much higher limit than a non-thinking model: Qwen recommends 32,768 tokens. The project uses 16,384 tokens per call, thinking included (`docs/methodology/workflow.md` Section 2.1), and every cut-off is recorded.
6. **Sampling settings.** Open models let us set temperature and the related settings, and their cards give firm recommendations. *Temperature* controls how random the choice of each next token is (0 means always the most likely token, "greedy"); *top_p*, *top_k* and *min_p* limit which tokens can be chosen at all; a *presence penalty* discourages repeating words already used. Qwen3 in thinking mode: temperature 0.6, top_p 0.95, top_k 20, and never greedy decoding. R1: temperature 0.6. For Qwen3.5/3.6 the card read on 2026-11-03 was noted as temperature 1.0 with presence penalty 1.5. The settings the project actually uses are the card's thinking-mode recommendations listed in `docs/methodology/workflow.md` Section 2.1: temperature 1.0, top_p 0.95, top_k 20, min_p 0, presence penalty 0. If the two ever seem to disagree, the card and `docs/methodology/workflow.md` are the reference. On Qwen3 the card warns that a high presence penalty can cause language mixing (Chinese and English in one answer), so watch for that in any run that raises it. Being able to set and record exact sampling settings is a gain for reproducibility; they go in every run log (Section 12).

**One unchanged strength.** The v6 design takes number answer keys from R's own output instead of trusting the model's typed number, and it regenerates items that fail the checks. That protection does not depend on which model writes the questions, so it carries over to Qwen unchanged.

---

## 8. The six originally listed models

### 8.1 DeepSeek-R1 (671B) and its May 2025 update R1-0528

**What it is.** DeepSeek's first big open reasoning model (January 2025): a mixture-of-experts model with 671B total parameters (37B active), 128K context, that always thinks before answering. The May 2025 update `DeepSeek-R1-0528` improved it considerably.

**License.** MIT. The model card says the series supports "commercial use, allow[s] for any modifications and derivative works, including, but not limited to, distillation for training other LLMs." This is the explicit distillation permission Jaxson is looking for.

**Quality.** Original R1: AIME 2024 79.8, MATH-500 97.3, GPQA Diamond 71.5, LiveCodeBench 65.9. R1-0528: AIME 2024 91.4, AIME 2025 87.5, GPQA 81.0, LiveCodeBench 73.3. These were very strong numbers for 2025.

**Hardware.** Impossible on Redhawk. Even an aggressive 4-bit GGUF file of R1-0528 is 405 GB, and the full-precision version is 1.34 TB. It would not run comfortably on one Talon node either.

**Cost and availability.** This is the problem. DeepSeek no longer serves R1 on its own API, and Together and Fireworks do not list it. R1-0528 is still sold by DeepInfra and a few OpenRouter providers at about $0.50 / $2.15 per MTok, so $72 to $287 for 50k. It is also extremely verbose: about 12,000 (R1) to 23,000 (R1-0528) thinking tokens per AIME problem, so the real cost would likely be above the $287 figure.

**Fit with our prompts.** Weak. The original R1 should get no system prompt and needs its reply forced to start with `<think>`. The paper reports language mixing (Chinese and English), worse results with examples in the prompt, overthinking on simple questions, and "suboptimal" structured output. R1-0528 fixes the system-prompt issue.

**Verdict: ruled out.** It has a great license, but it is being retired by hosts, cannot be self-hosted, and is verbose. DeepSeek V4-Flash (Section 9.2) has the same license and is better on every count.

### 8.2 DeepSeek-R1-Distill-Qwen-32B

**What it is.** A 32B dense model: Alibaba's Qwen2.5-32B fine-tuned by DeepSeek on about 800,000 reasoning examples written by R1. It is itself a distilled model.

**License.** The DeepSeek side is MIT. The base model, Qwen2.5-32B, is Apache 2.0 (checked in its LICENSE file; some other Qwen2.5 sizes use a more restrictive Qwen license, but the 32B does not). So the whole chain is permissive.

**Quality.** AIME 2024 72.6, MATH-500 94.3, GPQA 62.1, LiveCodeBench 57.2. That is below Qwen3-32B on every benchmark.

**Hardware.** It fits Redhawk at 4-bit (GGUF Q4_K_M is 19.85 GB). Its older Qwen2.5 design is well supported by older vLLM versions, which is a small plus on the V100s.

**Cost.** No hosted provider among the five checked sells it, so it would be self-hosted only (Section 5 times).

**Fit with our prompts.** It has the same awkwardness as the original R1: no system prompt, forced `<think>`, temperature 0.6.

**Verdict: ruled out.** Qwen3-32B is the same size, stronger, more flexible and actually hosted.

### 8.3 Qwen3-32B

**What it is.** Alibaba's 32.8B dense model from April 2025, with 32K context (131K with an extension). It can think or answer directly.

**License.** Apache 2.0, with no clause about outputs, so they are ours to use.

**Quality.** In thinking mode: MATH-500 97.2, AIME 2024 81.4, AIME 2025 72.9, GPQA 68.4, LiveCodeBench 65.7. In non-thinking mode the scores fall sharply (AIME 2025 20.2, GPQA 54.6), so it would need to run with thinking on.

**Hardware.** It fits Redhawk at 4-bit (official AWQ file 19.33 GB, official GGUF Q4_K_M 19.76 GB). Note that AWQ does not run in vLLM on V100s, so a GPTQ or GGUF version would be needed there. Its design is older and well supported, so an old pinned vLLM or llama.cpp should handle it.

**Cost.** Very cheap hosted at 2026-11-03 prices: $0.08 / $0.28 on DeepInfra, so about **$10 to $38** for 50k.

**Fit with our prompts.** Good. It takes a system prompt, has a clean on/off thinking switch (`enable_thinking`), works with vLLM's `qwen3` reasoning parser for JSON, and has published sampling settings. No JSON reliability data was found.

**Verdict: best of the six, but superseded.** If only the original six were allowed, choose this one. Since its newer sibling Qwen3.6-27B is the same family, the same license and nearly the same size with much higher scores, it is kept only as a documented comparison point.

### 8.4 Mistral Small 3.1 24B

**What it is.** Mistral's 24B dense model (March 2025), 128K context, which also reads images. It is a plain instruction model with **no thinking mode**.

**License.** Apache 2.0. Mistral's commercial terms appear to restrict only *image* outputs from being used to build competing products [S]. That does not affect us, but the primary text was not verified.

**Quality.** MATH 69.3, GPQA Diamond 45.96. It is the weakest of the six by a wide margin. The June 2025 update (Small 3.2) barely changes this (MATH 69.4, GPQA 46.1) but cuts repetitive-output failures from 2.11% to 1.29%.

**Hardware.** It is the best fit for Redhawk. At 4-bit it is only 14.3 GB, which leaves about 13 GB of working memory on one node, so many examples could be processed at once.

**Cost.** About $22 for 50k (Cloudflare via OpenRouter), or less through Mistral's own API, which offers 50% off batch.

**Fit with our prompts.** It has native JSON output and function calling, but no thinking at all.

**Related models.** Magistral Small 1.2 (September 2025, 24B, Apache 2.0) is Mistral's *reasoning* version: AIME 2025 77.3, GPQA 70.1, LiveCodeBench 70.9, about $0.50 / $1.50 per MTok. It is much better, and still well behind the 2026 options. Mistral Small 4 (March 2026, 119B MoE) is too big for Redhawk, and the only score found for it is GPQA 71.2.

**Verdict: ruled out.** It is easy to run and cleanly licensed, but too weak to be the statistics teacher.

### 8.5 OLMo 3 32B Think (and OLMo 3.1 32B Think)

**What it is.** The Allen Institute for AI's 32B dense reasoning model (OLMo 3 in November 2025; OLMo 3.1 in December 2025 with three more weeks of reinforcement-learning training). It always thinks. It is unusual because **everything is open**: weights, training code and training data.

**License.** Apache 2.0, "intended for research and educational use in accordance with Ai2's Responsible Use Guidelines". Those guidelines list harmful uses to avoid (fraud, malicious code, academic dishonesty and so on) but **say nothing against training other models on outputs**. Its reasoning training data was itself written by DeepSeek R1 (MIT).

**Quality (3.1).** AIME 2024 80.6, AIME 2025 78.1, MATH 96.2, GPQA 57.5, LiveCodeBench 83.3, IFEval 93.8. Strong on math and instruction following, weak on GPQA (graduate-level science questions), which is the closest proxy for conceptual statistics.

**Hardware.** It fits Redhawk at 4-bit (GGUF Q4_K_M 19.5 GB). It needs a recent Hugging Face transformers version (4.57+), and an old pinned vLLM may not support it. That needs checking.

**Cost.** Only secondary sources list a price (about $0.15 / $0.50 per MTok). Artificial Analysis says there is "no publicly available API", and the OpenRouter page is gone. In practice it is self-hosted only.

**Fit with our prompts.** Always thinks, takes a system prompt, temperature 0.6. Its card contains small errors (a template typo and 7B dataset names on the 32B card), which suggests less polish.

**Verdict: ruled out as the main teacher, kept as a "fully open" option.** A fully open teacher would make the report's story very clean (every step reproducible from public data). If Dr. Lee values that above raw quality, OLMo 3.1 is the choice. Otherwise its GPQA score and lack of hosting put it behind.

### 8.6 Qwen3-8B

**What it is.** The 8.2B sibling of Qwen3-32B, with the same license (Apache 2.0) and the same thinking switch.

**Quality.** In thinking mode: MATH-500 97.4, AIME 2025 67.3, GPQA 62.0, LiveCodeBench 57.5. It is impressive for its size, but clearly a step down from the 32B. A DeepSeek-distilled version (`DeepSeek-R1-0528-Qwen3-8B`, MIT) scores a bit higher (AIME 2025 76.3, GPQA 61.1).

**Hardware.** At FP16 it needs 16.4 GB, which does *not* fit on one 16 GB V100. It needs both GPUs of a node (fast: an estimated 11 to 90 GPU-hours for 50k) or an 8-bit version (8.7 GB GGUF).

**Cost.** No major host sells it (Fireworks only as an embedding model; the OpenRouter page did not resolve, so that is unconfirmed). It would be self-hosted only.

**Verdict: ruled out as the teacher.** The whole point of the teacher is to be much stronger than the students. An 8B model is only 8 times larger than Pythia 1B and far below the 2026 candidates. It is fast enough on Redhawk to be a possible cheap ablation (a "weak teacher" comparison for the report) if that becomes interesting later.

---

## 9. Newer open-weight models (released since mid-2025)

### 9.1 Qwen3.6-27B: first choice, now the teacher

- **What:** a dense 27B model from Alibaba (April 2026), 262K context, with thinking on by default and switchable off (`enable_thinking: false`). It is part of the Qwen3.5/3.6 generation, which uses a new hybrid attention design (Gated DeltaNet layers mixed with normal attention). That design keeps the working memory small on long outputs, but it is also why support on old software had to be checked.
- **License:** Apache 2.0.
- **Quality:** AIME 2026 94.1, GPQA Diamond 87.8, LiveCodeBench v6 83.9, HMMT February 2025 93.8 (vendor-reported). These are the highest scores of any model in this document that can fit on Redhawk. The earlier Qwen3.5-27B (February 2026) scores GPQA 85.5 and LiveCodeBench v6 80.7.
- **Hardware:** on Talon it runs at full BF16 precision in vLLM (repository `Qwen/Qwen3.6-27B`, revision `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9`). At 4-bit it is about 17 to 21 GB, so it fits one Redhawk node; the Redhawk fallback uses llama.cpp tag `b11960` with the `Q4_K_M` GGUF file, because current vLLM no longer supports the V100 (Section 5).
- **Cost:** on Talon, no money; the cost is GPU time (`docs/logs/compute_log.md`). At 2026-11-03 hosted prices it was the most expensive of the shortlist per output token ($0.25 / $2.00 on Chutes to $0.32 / $3.20 on DeepInfra; Section 6), which no longer matters.
- **Prompt fit:** system prompt, thinking switch, vLLM `qwen3` reasoning parser for JSON after thinking. Sampling settings are in Section 7, item 6.
- **Risks:** verbosity on our questions is unknown until the pilot measures it; its sibling Qwen3.8-27B (below) was measured as very verbose, so the family may lean toward long outputs. Accuracy at 4-bit versus BF16 is unknown until the Talon deployment comparison is run.

### 9.2 DeepSeek V4-Flash (and V4.1-Flash): runner-up, documented alternative

- **What:** a DeepSeek mixture-of-experts model (April 2026), 284B total and 13B active parameters, with selectable thinking (Non-think / High / Max). DeepSeek's own API now serves the newer **V4.1-Flash** (released 2026-09-10, updated 2026-10-17), currently the top open-weight model on the Artificial Analysis Intelligence Index v5 (score 33 [S]).
- **License:** MIT for V4-Flash. V4.1-Flash is reported as MIT [S], but the license of the October update was not checked. DeepSeek's API terms (effective 2026-04-29) say: "We assign any rights, title, and interests—if any—in the Outputs of the Services to you", and list permitted uses including "training other models (such as model distillation)". **No other provider or model has a clearer statement.**
- **Quality (V4-Flash, highest thinking mode):** GPQA 88.1, LiveCodeBench 91.6, HMMT February 2026 94.8 (vendor-reported). V4.1-Flash: GPQA 90.9.
- **Hardware:** not possible on Redhawk. The weights are about 160 GB in a mix of FP4 and FP8 [S], so a 4×H100 node might hold it, but H100s have no FP4 hardware and engine support would need checking.
- **Cost (2026-11-03, hosted):** DeepInfra (V4-Flash) $0.09 / $0.18, so $7 to $25 for 50k. DeepSeek's own API (V4.1-Flash) $0.30 / $1.20 at peak, half price off-peak (peak is weekdays 01:00 to 04:00 and 06:00 to 10:00 UTC), so $20 to $80 off-peak.
- **Prompt fit:** system prompt, JSON output supported on DeepSeek's API, and three thinking modes, which give finer control than Qwen's on/off switch. One known vLLM bug (JSON landing in the reasoning field on V4 [S]) only matters if we self-host.
- **Risks:**
  - **Model churn.** DeepSeek's own API has remapped its model names several times in 2026 (R1 to V3.1 to V3.2 to V4-Flash to V4.1-Flash), so a fixed model version must be pinned through a provider that serves exact weights, or every run's model ID must be recorded.
  - **Data handling.** DeepSeek's own API is hosted in China. Our prompts are synthetic statistics questions with no personal data, but it is worth checking whether Miami University has any policy on DeepSeek services. Using the MIT-licensed weights through a US host such as DeepInfra avoids the question, though then the host's terms apply instead of DeepSeek's explicit distillation clause (DeepInfra's terms say third-party models are governed by their own license, which here is MIT).
- **Status:** documented alternative only. Under the 2026-11-06 decision, if Qwen underperforms the first remedy is Qwen at higher precision or with more thinking, not this model.

### 9.3 gpt-oss-120b: third, documented alternative

- **What:** OpenAI's open-weight mixture-of-experts model (August 2025), 117B total and 5.1B active parameters, with reasoning effort low/medium/high.
- **License:** Apache 2.0. The usage policy only asks users to follow applicable law, with no restriction on outputs.
- **Quality:** AIME 2025 92.5, GPQA 80.1 at high effort without tools [S] (from a secondary source quoting OpenAI's model card).
- **Hardware:** it fits on one 80 GB H100 in its native MXFP4 format, so it is self-hostable on Talon or OSC but not on Redhawk. Its small sibling **gpt-oss-20b** (21B, GPQA 58.6) runs "within 16 GB", but whether its MXFP4 format works on V100s is unverified, and its scores are too low to be the teacher.
- **Cost (2026-11-03, hosted):** $0.03 / $0.15 (cheapest OpenRouter providers) to $0.15 / $0.60 (Together), so about $5 to $80 for 50k.
- **Prompt fit:** the three-level effort setting gives the finest control over thinking of any candidate. It uses OpenAI's "harmony" chat format, which the engines handle.
- **Risks:** below the first two on GPQA, and the scores come from a secondary source. Those numbers should be read on OpenAI's card if it is ever reconsidered.
- **Status:** documented alternative only.

### 9.4 Others considered

- **Qwen3.8-27B** (August 2026, Apache 2.0): GPQA 89.2, LiveCodeBench v6 90.3. It is even stronger on paper than Qwen3.6-27B, but Artificial Analysis found it **very verbose** (about 130M tokens to run its test suite against a median of 78M), and it scored 20 on that index. Its long outputs would make it slow and, hosted, expensive ($0.50 / $3.00). At the time it looked like a reasonable swap if 3.6 proved not good enough; under the 2026-11-06 decision the fallback is the same Qwen3.6-27B at higher precision or with more thinking, so 3.8 stays a documented alternative only. The Qwen3.8 *flagship* (not the 27B) is reported to use a custom license [S], so check the license of the exact model if it is ever used.
- **Gemma 4 31B** (Google, April 2026, Apache 2.0, unlike Gemma 3): AIME 2026 89.2, GPQA 84.3, LiveCodeBench v6 80.0. It is a solid alternative of about the same size as Qwen3.6-27B. It was not shortlisted because of the known vLLM bug where JSON schemas are silently ignored when thinking is turned off, and because it adds no advantage over Qwen3.6-27B.
- **Qwen3-30B-A3B-Thinking-2507** (Apache 2.0, 30.5B total and 3.3B active): GPQA 73.4. It is fast because so few parameters are active, but it thinks very long (32K to 81K output tokens recommended) and has been overtaken by Qwen3.6.
- **Phi-4-reasoning-plus** (Microsoft, 14B, MIT): GPQA 68.9. Microsoft says it is "tested for math reasoning only", and it is too small.
- **GLM-4.5-Air / GLM-5** (MIT), **Kimi K2.x**, **DeepSeek V4-Pro**: too large to self-host on anything we have. Kimi K2's modified MIT license requires very large products to display "Kimi K2", which is irrelevant at our scale. DeepSeek V4-Pro has been retired on DeepSeek's API. None beats the shortlist on price and quality together.
- **Ruled out on license:**
  - **Gemma 3:** Google's terms count a model trained on "synthetic data Outputs by Gemma" as a "Model Derivative", which must carry Google's restrictions. Our Pythia students would inherit them.
  - **Llama 4:** a model trained on Llama outputs and then distributed must have "Llama" at the start of its name.
  - **Kimi K3:** custom license with a separate-agreement clause.
  - **MiniMax M2.x, Nemotron 3:** license text unverified or reportedly non-commercial in later versions.

---

## 10. Summary tables

These tables summarize Sections 8 and 9. Benchmark scores are vendor-reported with thinking on, and "n/r" means not reported.

**Quality and license**

| Model | Size (total / active) | License; may outputs train other models? | AIME (year) | GPQA Diamond | LiveCodeBench |
|---|---|---|---|---|---|
| Qwen3.6-27B (the teacher) | 27B dense | Apache 2.0; yes, no restriction | 94.1 (2026) | 87.8 | 83.9 (v6) |
| DeepSeek V4-Flash | 284B / 13B | MIT plus explicit "distillation" in API terms; yes | n/r (HMMT 94.8) | 88.1 | 91.6 |
| gpt-oss-120b | 117B / 5.1B | Apache 2.0; yes | 92.5 (2025) [S] | 80.1 [S] | n/r |
| DeepSeek-R1-0528 | 685B / 37B | MIT plus explicit "distillation"; yes | 87.5 (2025) | 81.0 | 73.3 |
| Qwen3-32B | 32.8B dense | Apache 2.0; yes | 72.9 (2025) | 68.4 | 65.7 (v5) |
| OLMo 3.1 32B Think | 32B dense | Apache 2.0 plus use guidelines; yes | 78.1 (2025) | 57.5 | 83.3 (v3) |
| R1-Distill-Qwen-32B | 32B dense | MIT plus Apache 2.0; yes | 72.6 (2024) | 62.1 | 57.2 |
| Qwen3-8B | 8.2B dense | Apache 2.0; yes | 67.3 (2025) | 62.0 | 57.5 (v5) |
| Mistral Small 3.1 | 24B dense | Apache 2.0; yes | n/r (MATH 69.3) | 46.0 | n/r |

LiveCodeBench versions differ (v3, v5, v6 use different problem sets), so those numbers are only roughly comparable.

**Practicality**

| Model | Redhawk (2×V100 16 GB)? | Talon/OSC (H100)? | Hosted 50k cost at 2026-11-03 prices, Base to +2k thinking (historical) | Thinking control |
|---|---|---|---|---|
| Qwen3.6-27B (the teacher) | Yes at 4-bit via llama.cpp `b11960` (`Q4_K_M` GGUF); the fallback | Yes, full BF16 in vLLM on Talon; the primary | $64 to $421 | On / off |
| DeepSeek V4-Flash | No | Maybe (about 160 GB FP4/FP8) | $7 to $80 | Non-think / High / Max |
| gpt-oss-120b | No | Yes, one H100 | $5 to $80 | Low / medium / high |
| DeepSeek-R1-0528 | No | No | $72 to $287+ (very verbose) | Always on |
| Qwen3-32B | Yes at 4-bit (GPTQ/GGUF) | Yes | $10 to $38 | On / off |
| OLMo 3.1 32B Think | Yes at 4-bit (check engine support) | Yes | Self-hosted only (about $17 to $67 if a host appears) | Always on |
| R1-Distill-Qwen-32B | Yes at 4-bit | Yes | Self-hosted only | Always on |
| Qwen3-8B | Yes, needs both GPUs or 8-bit | Yes | Self-hosted only | On / off |
| Mistral Small 3.1 | Yes, best fit (14 GB at 4-bit) | Yes | about $22 | None |

---

## 11. The proposed shortlist test (superseded) and what replaced it

**Status.** This test was proposed on 2026-11-03 and never run. The 2026-11-06 decision chose Qwen3.6-27B directly, and the test's role is now filled by the **Talon 4-bit vs BF16 deployment comparison** described in `docs/methodology/workflow.md` Section 2.1. The original proposal is kept in short form because its measurements are still the right ones to look at.

**What was proposed, and why.** Public benchmarks cannot tell us how well a model writes *statistics and R* questions and answers in *our* format. A small test can. The idea was to give each shortlisted model (Qwen3.6-27B, DeepSeek V4-Flash, gpt-oss-120b, optionally Qwen3-32B) the same 20 slot descriptions (category, subtopic, difficulty, answer type) with **new item IDs, kept in a separate dev folder that never becomes part of the benchmark**, run each with thinking on and its card's recommended sampling settings, and compare them on the free checks already in `generate_benchmark.py`:
- share of replies that are valid JSON on the first try
- share of number keys R agrees with
- multiple-choice keys found wrong by hand check
- thinking and output tokens per item (this replaces the 2,000-token guess in Section 6)
- questions that "think aloud" or contain their own answer
- near-duplicates

No existing or future benchmark question was to be shown to any model, and that rule still holds.

**What replaced it: the Talon 4-bit vs BF16 comparison.**
- *What and why.* The question is no longer "which model?" but "does compressing Qwen3.6-27B to 4 bits hurt it?". A 4-bit model is faster and smaller, but may write slightly worse questions or wrong keys more often. If 4-bit is as good, it could speed up large generation runs; if it is worse, BF16 stays.
- *How it works.* The same development slots (IDs `BM9001` and up, never part of the benchmark) are answered twice on Talon: once with the BF16 weights in vLLM and once with a 4-bit version. Because both runs use the same cluster and GPU type, the only difference is the precision of the weights. The comparison looks at the share of usable questions and correct keys (measures like the list above) and at speed. Which 4-bit format and engine to use, which slots, and which measures decide it are still open (`docs/methodology/workflow.md` Section 10.2).
- *Worked example (hypothetical numbers).* Suppose 20 slots are answered both ways. BF16 gives 18 usable questions with R-verified keys and 4-bit gives 17. A difference of one question in 20 is well within chance at this size, so the result would read "no clear difference", not "4-bit is worse". If 4-bit gave 12 of 20, that would be a clear warning.
- *What could go wrong.* Twenty items gives wide error bars, so the comparison can reveal a clearly bad setup but cannot separate two close ones. The 4-bit backend is not built yet, so its setup could itself introduce problems that are not caused by the compression. Thinking might run past the output limit; the limit is set high and every cut-off is recorded.
- *What it tells us.* Whether the 4-bit teacher is good enough to use and how much time it saves. It does not tell us how good the final students will be; only the Phase 4 pilot and later phases do that.

Talon jobs cost no money, so nothing goes in `docs/logs/cost_log.md`; the GPU time of each run is recorded in `docs/logs/compute_log.md`.

---

## 12. Effects on the rest of the project plan

- **The teacher in the method.** Done: `docs/methodology/workflow.md` Section 2 and Section 2.1 now name Qwen3.6-27B. The Claude-era record (trials, prompts v1 to v5, the Claude-only docs) is archived under the Git tag `pre-cleanup-claude-era`, summarized in `docs/methodology/workflow.md` Section 2.2.
- **The benchmark.** Claude can no longer write benchmark questions either, so Qwen3.6-27B writes both the benchmark and the training data. The Claude-era trial questions (BM0001 to BM0120) were never part of the frozen benchmark. Because one teacher now writes both, the safeguards in `docs/methodology/workflow.md` Section 4 (separate prompts and IDs, freeze first, decontamination, independent verification) carry the weight that a second model family would otherwise have carried.
- **The verifier.** The verifier is still to be decided (`docs/methodology/workflow.md` Section 10.2), most likely ChatGPT or Claude used only as a checker, never as a source of training text. With a Qwen teacher, either is a different model family, so the independence ladder holds. If gpt-oss-120b had been the teacher, a ChatGPT verifier would have been from the same company (OpenAI), which is less independent; that was one reason it ranked third.
- **Success criterion 4 (efficiency).** With an open-weight teacher, size, memory and speed can be compared directly on the same GPUs. Criterion 4 was revised on 2026-11-06 into a size part (4a) and a measured-efficiency part (4b); see `docs/methodology/workflow.md` Section 1.2. Qwen3.6-27B, for example, is 27 times the size of Pythia 1B.
- **The 80% teacher red flag (`docs/methodology/workflow.md` Section 1.1).** It still applies. Qwen3.6-27B must reach 80% on the frozen benchmark, measured in Phase 5. If it does not, the first remedy is the same model at higher precision or with more thinking (`docs/methodology/workflow.md` Section 2.1).
- **Logging.** Every run log should record: provider (or "self-hosted", which is now always the case), exact weights repo and revision (or provider model ID), quantization, engine and version, temperature, top_p, top_k, min_p, presence penalty and thinking setting. Paid calls, if any, go in `docs/logs/cost_log.md`; cluster jobs and GPU time go in `docs/logs/compute_log.md`.
- **Reproducibility gain.** Open weights can be pinned by exact file and checksum, so the teacher can be re-run years later, which a closed API model cannot guarantee. A `recovery/` doc should describe how to fetch the exact weights.

---

## 13. Limitations

- All scores are vendor-reported or third-party proxies. None tests statistics or R. Settings differ between vendors (number of samples, thinking budget, tools). The scores rank the open-weight candidates against each other; only the Phase 5 teacher evaluation on our own benchmark says how good Qwen3.6-27B is at our task.
- Redhawk speed figures are estimates scaled from other GPUs and model sizes. No 32B 4-bit V100 benchmark was found.
- Whether old vLLM or llama.cpp supports OLMo 3's design on V100 is unverified. For Qwen3.6-27B the Redhawk fallback is pinned to llama.cpp `b11960`.
- Prices and model availability change quickly. Several models were withdrawn from APIs during 2026.
- Hosted providers' terms add to the model license. Fireworks' terms (Section 2.2(c), dated 2026-07-10) forbid using "any content available on or via the Service ... for any machine learning and/or artificial intelligence training", which may or may not be meant to cover your own outputs. **Do not use Fireworks for training data without asking them in writing.** Together and Groq forbid building a *competing service* (we are not), and DeepInfra and OpenRouter defer to the model's own license. Running the weights on Talon or Redhawk avoids provider terms entirely; only the Apache 2.0 license applies.
- This is not legal advice. Apache 2.0 and MIT are widely understood to put no limits on outputs, but if Dr. Lee or the university wants certainty, the license texts are short and can go to university counsel.

---

## 14. Sources (all accessed 2026-11-03)

**Model cards, licenses and reports**
- DeepSeek-R1: https://huggingface.co/deepseek-ai/DeepSeek-R1 ; paper https://arxiv.org/abs/2501.12948 ; R1-0528 https://huggingface.co/deepseek-ai/DeepSeek-R1-0528
- DeepSeek-R1-Distill-Qwen-32B: https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B ; Qwen2.5-32B license https://huggingface.co/Qwen/Qwen2.5-32B/blob/main/LICENSE
- Qwen3-32B: https://huggingface.co/Qwen/Qwen3-32B ; Qwen3-8B https://huggingface.co/Qwen/Qwen3-8B ; Qwen3 tech report https://arxiv.org/html/2505.09388v1
- Qwen3.5-27B: https://huggingface.co/Qwen/Qwen3.5-27B ; Qwen3.6-27B https://huggingface.co/Qwen/Qwen3.6-27B ; Qwen3.8-27B https://huggingface.co/Qwen/Qwen3.8-27B ; Qwen3-30B-A3B-Thinking-2507 https://huggingface.co/Qwen/Qwen3-30B-A3B-Thinking-2507
- Mistral Small 3.1: https://huggingface.co/mistralai/Mistral-Small-3.1-24B-Instruct-2503 ; 3.2 https://huggingface.co/mistralai/Mistral-Small-3.2-24B-Instruct-2506 ; Magistral Small 1.2 https://huggingface.co/mistralai/Magistral-Small-2509 ; Small 4 https://huggingface.co/mistralai/Mistral-Small-4-119B-2603
- OLMo 3.1 32B Think: https://huggingface.co/allenai/Olmo-3.1-32B-Think ; Ai2 Responsible Use Guidelines https://allenai.org/responsible-use ; Dolci-Think-SFT https://huggingface.co/datasets/allenai/Dolci-Think-SFT-32B
- DeepSeek V4-Flash: https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash ; V4-Pro https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro
- gpt-oss: https://huggingface.co/openai/gpt-oss-120b ; usage policy https://huggingface.co/openai/gpt-oss-120b/blob/main/USAGE_POLICY ; https://huggingface.co/openai/gpt-oss-20b ; model card PDF https://arxiv.org/pdf/2508.10925
- Gemma 4 31B: https://huggingface.co/google/gemma-4-31B-it ; Gemma terms https://ai.google.dev/gemma/terms
- Llama 4 license: https://dev.meta.ai/llama/llama4/license/ ; Kimi K2 Thinking license https://huggingface.co/moonshotai/Kimi-K2-Thinking/blob/main/LICENSE ; GLM-4.5-Air https://huggingface.co/zai-org/GLM-4.5-Air ; Phi-4-reasoning-plus https://huggingface.co/microsoft/Phi-4-reasoning-plus
- Quantized files: https://huggingface.co/unsloth/DeepSeek-R1-0528-GGUF ; https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF ; https://huggingface.co/unsloth/Mistral-Small-3.1-24B-Instruct-2503-GGUF ; https://huggingface.co/unsloth/Olmo-3.1-32B-Think-GGUF

**Prices and provider terms**
- DeepSeek pricing https://api-docs.deepseek.com/quick_start/pricing ; changelog https://api-docs.deepseek.com/updates ; Open Platform terms https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html
- OpenRouter model pages (e.g. https://openrouter.ai/qwen/qwen3-32b , https://openrouter.ai/qwen/qwen3.6-27b , https://openrouter.ai/openai/gpt-oss-120b , https://openrouter.ai/deepseek/deepseek-v4-flash , https://openrouter.ai/deepseek/deepseek-r1-0528 , https://openrouter.ai/mistralai/mistral-small-3.1-24b-instruct ); terms https://openrouter.ai/terms ; structured outputs https://openrouter.ai/docs/guides/features/structured-outputs
- DeepInfra pricing https://deepinfra.com/pricing ; terms https://deepinfra.com/terms ; batch https://docs.deepinfra.com/batch/introduction
- Together pricing https://www.together.ai/pricing ; terms https://www.together.ai/terms-of-service ; batch https://docs.together.ai/docs/inference/batch/overview.md ; JSON mode https://docs.together.ai/docs/json-mode
- Fireworks pricing https://fireworks.ai/pricing ; terms https://fireworks.ai/terms-of-service ; batch https://docs.fireworks.ai/guides/batch-inference ; structured output https://docs.fireworks.ai/structured-responses/structured-response-formatting
- Groq services agreement https://console.groq.com/docs/legal/services-agreement ; batch https://console.groq.com/docs/batch
- Mistral pricing https://mistral.ai/pricing
- Artificial Analysis: https://artificialanalysis.ai/models/open-source ; https://artificialanalysis.ai/models/qwen3-8-27b ; https://artificialanalysis.ai/articles/deepseek-r1-update

**Engines and hardware**
- vLLM GPU requirements https://docs.vllm.ai/en/latest/getting_started/installation/gpu.html ; PR #39878 https://github.com/vllm-project/vllm/pull/39878 ; v0.20.0 release https://github.com/vllm-project/vllm/releases/tag/v0.20.0 ; quantization support https://docs.vllm.ai/en/stable/features/quantization/ ; reasoning outputs and structured output https://docs.vllm.ai/en/latest/features/reasoning_outputs.html
- V100 forum thread [S] https://discuss.vllm.ai/t/support-for-v100-sm-70-on-vllm-0-20/2605 ; V100 forks [S] https://github.com/1CatAI/1Cat-vLLM , https://github.com/humanjesse/vllm-v100
- llama.cpp Volta attention PR https://github.com/ggml-org/llama.cpp/pull/17505 ; grammars and JSON schema https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md
- FlashAttention https://github.com/Dao-AILab/flash-attention ; TGI maintenance mode https://huggingface.co/docs/text-generation-inference/en/index.md
- V100 throughput benchmarks [S] https://www.databasemart.com/blog/vllm-gpu-benchmark-v100-3 ; https://docs.apolo.us/index/apolo-console/apps/available-apps/llm-inference/multi-gpu-benchmarks-report ; V100 datasheet https://images.nvidia.com/content/technologies/volta/pdf/volta-v100-datasheet-update-us-1165301-r5.pdf

**Academic compute**
- OSC fee model https://www.osc.edu/book/export/html/4887 ; FAQ https://www.osc.edu/content/academic_fee_model_faq ; Cardinal https://www.osc.edu/resources/technical_support/supercomputers/cardinal
- NSF ACCESS policy https://allocations.access-ci.org/allocations-policy ; NAIRR Pilot https://nairrpilot.org/nairr-pilot-proposal-instructions

**Project documents:** `docs/methodology/workflow.md` (Sections 1.1, 1.2, 2.1, 2.2, 4, 10.2), `docs/clusters/cluster_selection.md`, `docs/models/pythia_behavior_analysis.md`, `docs/logs/compute_log.md`, `configs/redhawk/common.sh`, `code/generation/generate_benchmark.py`, `data/prompts/benchmark_generation_v6.md`. The 2026-11-03 version of this document also cited Claude-era documents that are now archived under the Git tag `pre-cleanup-claude-era` (`docs/methodology/workflow.md` Section 2.2).
