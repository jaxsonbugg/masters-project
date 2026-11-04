# Teacher Model Evaluations: Open-Weight Alternatives to Claude Sonnet 5.5 (desk research, no spend)

Prepared 2026-11-03. No API calls, paid or free, and no cluster jobs were run. Everything below comes from public pages (model cards, license files, provider price pages and terms, engine documentation), all accessed 2026-11-03, plus arithmetic that is shown. Facts marked **[S]** come from a secondary source or a search snippet and should be re-checked before they are relied on. Unmarked facts were read on a primary source (the model's own Hugging Face card, its LICENSE file, its tech report, or the provider's own page).

---

## 1. Why this document exists

The project's plan is to have Claude Sonnet 5.5 act as the **teacher**: it writes answers to statistics and R questions, and those answers become the training data that the small Pythia **students** learn from. Training a small model on a big model's outputs is called **distillation**: the knowledge of the big model is "distilled" into the small one.

Anthropic's Commercial Terms say the service may not be used "to build a competing product or service, including to train competing AI models" (flagged earlier in `docs/teacher_subscription_feasibility.md`, Section 1.4). Training Pythia students on Claude's answers might fall under that sentence. Jaxson has asked Anthropic support, and as of today a "no" looks likely. If the answer is no, the project needs a different teacher, and that teacher should be **open-weight**.

**Open-weight** means the model's trained numbers (its "weights") are published, so anyone can download the model and run it on their own computer or cluster. This differs from Claude or ChatGPT, which can only be reached through the company's API. Open-weight models come with a license that says what you may do with them. That license is the main thing that decides whether we may use the model's outputs to train Pythia.

This document evaluates the six models Jaxson listed and a set of newer open-weight models, and ends with a recommendation and a short list worth testing.

---

## 2. Recommendation (read this first)

**First choice: Qwen3.6-27B** (Alibaba, April 2026, Apache 2.0 license).
- It is the only strong candidate that can plausibly run on **Redhawk** (compressed to 4-bit across the two 16 GB V100 GPUs of one node), is also sold cheaply by hosted API providers, and has a license with no restriction on outputs.
- Its published math, science and code scores (GPQA Diamond 87.8, AIME 2026 94.1, LiveCodeBench v6 83.9) are far above every one of the six originally listed models.
- It has a thinking mode that can be switched on and off, and works with JSON-schema output in the usual inference engines.

**Runner-up, and the best hosted-only option: DeepSeek V4-Flash** (DeepSeek, April 2026, MIT license).
- It has the **clearest distillation permission of anything found**. The MIT license lets you do anything with the model, and DeepSeek's own API terms explicitly list "training other models (such as model distillation)" as a permitted use of outputs.
- It scores about as high as Qwen3.6-27B (GPQA 88.1, LiveCodeBench 91.6 in its highest thinking setting) and is the cheapest strong model to call: about **$7 to $25 for 50,000 examples** on DeepInfra, against about $165 to $665 for Sonnet 5.5 through the Batch API.
- It is too large for Redhawk, so it can only be used through a hosted API, or on a bigger cluster such as Talon or OSC.

**Third, for testing: gpt-oss-120b** (OpenAI, August 2025, Apache 2.0).
- Its "reasoning effort" setting (low/medium/high) maps directly onto the `effort` setting our Claude scripts already use.
- It is very cheap through hosted APIs (about $5 to $80 for 50,000 examples, depending on the provider).
- It fits on a single 80 GB H100, so it would be self-hostable on Talon or OSC, though not on Redhawk. Its scores (GPQA 80.1 [S]) are a step below the first two.

**Best of the six originally listed models: Qwen3-32B.** If the decision had to come from that list alone, this is the one. It has an Apache 2.0 license, fits Redhawk at 4-bit, costs about $10 to $38 for 50,000 examples on DeepInfra, and has a thinking toggle. Its scores (GPQA 68.4, AIME 2025 72.9) are clearly below the 2026 models, though, so there is little reason to choose it over Qwen3.6-27B, which is from the same family and has the same license and nearly the same size.

**Shortlist for the hands-on test (Section 11):** Qwen3.6-27B, DeepSeek V4-Flash, gpt-oss-120b. Qwen3-32B can be added as a fourth, cheap "best of the original list" comparison if you want the report to show that the newer models really are better on our own questions.

**Ruled out, one line each:**
- **DeepSeek-R1 (671B):** good scores in 2025, but it is now retired from DeepSeek's own API and from Together and Fireworks. It is far too large to self-host, very verbose (about 12,000 to 23,000 thinking tokens per hard math problem), and has weak structured output. DeepSeek V4-Flash replaces it with the same license, better scores and a lower price.
- **DeepSeek-R1-Distill-Qwen-32B:** clean license, but it has lower scores than Qwen3-32B on every benchmark, no hosted provider sells it, and it needs awkward prompting (no system prompt, forced `<think>`).
- **Mistral Small 3.1 24B:** clean license, but it has no reasoning mode and scores far too low for a statistics teacher (MATH 69.3, GPQA 46). Its reasoning sibling Magistral Small 1.2 is better but still well behind the 2026 models.
- **OLMo 3 / 3.1 32B Think:** the most "open" model of all (its training data is public too), with a clean license. Its scores trail (GPQA 57.5), and almost no hosted API sells it. Keep it in mind only if Dr. Lee values full openness for the report.
- **Qwen3-8B:** too small to come close to Sonnet 5.5 (GPQA 62.0). It also does not fit on one V100 at full precision, and no major host sells it.
- **Gemma 3** and **Llama 4:** their licenses put conditions on models trained with their outputs (Section 9), so they fail the "clearly allows distillation" test.

The most important caveat: **public benchmarks are not our task.** No source reports statistics- or R-specific scores for any of these models, and the scores above cannot be put on the same scale as Sonnet 5.5's numbers in `docs/teacher_selection.md` (Section 6.4 explains why). The small hands-on test in Section 11 is what will show how close each one gets on our own kind of questions.

---

## 3. Terms used in this document

**Parameters.** The adjustable numbers inside a model. More parameters usually mean a more capable model, and also more memory and compute. "32B" means about 32 billion parameters. Pythia 1B has about 1 billion.

**Dense vs. mixture-of-experts (MoE).** A dense model uses all of its parameters for every word it writes. An MoE model is split into many smaller "experts" and uses only a few of them for each word. DeepSeek V4-Flash, for example, has 284B parameters in total, but only 13B are **active** for any one token. MoE models are cheap to run per word (only the active part does work) but still need memory for all of their parameters, so they are hard to self-host.

**Tokens.** Models read and write in tokens, pieces of words about three-quarters of an English word long on average. Prices are quoted per million tokens (MTok), separately for **input** (what we send) and **output** (what the model writes).

**Thinking (reasoning) tokens.** Many current models first write a hidden or marked-off "scratchpad" of reasoning (often between `<think>` and `</think>`), then the final answer. Those thinking tokens are billed as output and take time to generate, so a model that thinks for 5,000 tokens costs and takes about ten times as long as one that answers in 500.

**Quantization (FP16, 8-bit, 4-bit).** Each parameter is stored as a number. At **FP16** ("16-bit floating point") each parameter takes 2 bytes. **8-bit** takes 1 byte. **4-bit** takes half a byte. Shrinking the numbers like this is called quantization. It lets a big model fit on a small GPU at the cost of a small loss of accuracy, usually minor at 8-bit and noticeable but often acceptable at 4-bit. Common 4-bit file formats are **GPTQ**, **AWQ** and **GGUF** (the format used by llama.cpp; "Q4_K_M" is a popular 4-bit GGUF variant).

*Worked example.* Qwen3-32B has about 32.8 billion parameters. At FP16 that is 32.8 billion × 2 bytes = about **65 GB**. One Redhawk node has two V100 GPUs with 16 GB each, **32 GB** in total, so the full-precision model does not fit. At 4-bit, the official AWQ file is **19.3 GB**, which fits in 32 GB and leaves about 7 to 9 GB for working memory. A 4-bit model also has some overhead for scaling factors, which is why 32.8 × 0.5 = 16.4 GB becomes about 19 GB in practice.

**KV cache.** While a model writes, it keeps a memory of every token so far (the "keys and values" of its attention layers). This memory grows with the length of each response and with how many requests are processed at once. On Qwen2.5-32B it is about 256 KB per token, so one 3,000-token conversation needs about 0.8 GB. The space left after the weights decides how many questions the GPU can work on at the same time, and that largely decides speed.

**Inference engine.** The software that runs a downloaded model: **vLLM** (the most common for large batch jobs), **SGLang**, **llama.cpp** (runs GGUF files, very portable), and others.

**Structured output / constrained (guided) decoding.** Our Claude scripts ask for answers as a JSON object that matches a schema (a list of required fields and their types). With open-weight models the engine can *force* this. At every step it only allows tokens that keep the output valid against the schema. In vLLM this is done by a component such as xgrammar. In llama.cpp it is done with a grammar.

**Hosted API provider.** A company that runs open-weight models on its own GPUs and sells access per token, for example DeepInfra, Together, Fireworks, Groq or OpenRouter (OpenRouter is a marketplace that routes requests to many such providers). It is the open-weight equivalent of Anthropic's API.

**License vs. terms of service.** The *license* comes with the model weights and governs the model itself. A hosted provider's *terms of service* govern the use of its service. When we use a hosted provider, both apply.

---

## 4. How the candidates were judged

The criteria are in order of importance. The first two are **gates**: a model that fails one is out, however good it is otherwise.

**Gate 1: the license must clearly allow training other models on its outputs** (Jaxson's "distillation guidelines" requirement). Three levels were found:
- *Explicit permission.* The DeepSeek models are MIT-licensed, and their model cards and API terms name distillation as allowed. This is the strongest position.
- *No restriction.* Apache 2.0 (Qwen, Mistral, OLMo, gpt-oss, Gemma 4) and plain MIT say nothing at all about outputs, so outputs are simply ours to use. That is legally clean but not as explicit.
- *Restriction.* Gemma 3's terms, Llama's naming clause, and custom licenses (Kimi K3, MiniMax) place conditions on models trained with their outputs. These fail the gate.

**Gate 2: it must be runnable somewhere we can reach and afford**: Redhawk, a hosted API at a sensible price, or (if granted) Talon or OSC.

**Scored factors:**
1. *Quality for statistics, math and R.* Measured by published math (AIME, MATH-500), graduate science (GPQA Diamond) and code (LiveCodeBench) scores. These are proxies; none tests statistics or R directly.
2. *Fit with our prompts and pipeline.* Can it follow a long rule list, produce schema-valid JSON, take a system prompt, switch thinking on or off, and be run in big batches? (Section 7.)
3. *Cost* for 50,000 examples (Section 6).
4. *Hardware fit and time* on Redhawk, or on Talon or OSC (Section 5).
5. *Reproducibility.* With open weights we can pin an exact file and its checksum, which is better than an API model that can be changed or retired. Retirement is a real risk: DeepSeek-R1 has already disappeared from most APIs.
6. *Output style for Pythia.* The students have a 2,048-token context and need short answers with a marked final answer (`docs/pythia_behavior_analysis.md`). A very verbose teacher costs more, and its long reasoning would have to be cut or summarized before it is used as training data.
7. *Support and ecosystem.* Quantized versions, engine support, documentation.

---

## 5. Hardware: what Redhawk can and cannot do

This section explains the hardware limits once, because they shape every model's verdict.

**What Redhawk has.** 4 GPU nodes, each with 2 NVIDIA V100 GPUs of 16 GB (so 32 GB per node, 8 GPUs shared by the whole campus). The V100 is a 2017 design (NVIDIA "compute capability 7.0"). It can compute in FP16 but has no hardware support for the newer BF16 or FP8 number formats (`docs/cluster_selection.md`).

**Problem 1: current vLLM no longer supports the V100.** vLLM's installation page now requires "compute capability 7.5 or higher". A change merged on 2026-04-23 (pull request #39878) removed the V100 from vLLM's builds when it moved to CUDA 13 and PyTorch 2.11, and vLLM 0.20.0 (2026-04-27) shipped that change. Users report that vLLM 0.18.x and earlier still run on V100 [S]. 0.19 is untested. So on Redhawk we would have to **pin an older vLLM (0.18 or earlier) built with CUDA 12.x**. The risk is that an old vLLM may not know how to run the newest model designs. Qwen3.6-27B uses a new hybrid attention design (introduced with Qwen3.5 in February 2026), and **whether vLLM 0.18 supports it must be checked before relying on Redhawk**. Community forks of vLLM with V100 patches exist [S] but are not official.

**Problem 2: some 4-bit formats do not work on the V100.** In vLLM on Volta, GPTQ, GGUF and bitsandbytes work, but AWQ and the fast "Marlin" kernels do not (they need newer GPUs). FlashAttention, the fast attention code most engines use, does not support the V100 either. vLLM falls back to a slower Triton attention backend.

**The reliable fallback is llama.cpp.** It supports the V100 well (a December 2025 change added fast attention kernels for V100 tensor cores), runs GGUF 4-bit files, and can force JSON-schema output. It must be built with CUDA 12.x, because CUDA 13 dropped the V100. It is generally slower than vLLM for big batches, but far easier to get working on old GPUs.

**Problem 3: an 8B model at FP16 does not fit on one 16 GB V100.** 8.2 billion × 2 bytes = 16.4 GB, more than the card's 16 GB before any working memory. It needs either both GPUs of a node or an 8-bit version.

**How much fits, worked example (estimate).** A 32B model at 4-bit on one node: 32 GB total; usable at 90% is about 28.8 GB. Subtract about 19.5 GB of weights and about 2 GB of engine overhead, and about 7 GB is left for the KV cache, which is about 27,000 tokens. Each example is about 300 tokens in plus 600 out, so about 29 examples can be in progress at once. If the teacher thinks for an extra 2,000 tokens per example, that drops to about 9. Fewer examples at once means slower total throughput.

**Time on Redhawk for 50,000 examples (estimates, least certain number in this document).** I found no published speed for a 32B 4-bit model on V100s, so these are scaled from related measurements (V100 memory bandwidth of 900 GB/s, measured 8B and 14B speeds on V100s) and shown so they can be replaced by a real measurement:

| Setup | 600 output tokens each (30M tokens) | 2,600 output tokens each (130M tokens) |
|---|---|---|
| 32B (or 27B) at 4-bit on one node (2 V100s), about 150 to 250 tokens/s in total | about 33 h, or **67 GPU-hours** (range 42 to 111) | about 241 h (10 days), or **480 GPU-hours** (range 290 to 720) |
| 8B at FP16 across 2 V100s, about 800 to 1,500 tokens/s | about 5.6 h, or **11 GPU-hours** | about 45 h, or **90 GPU-hours** |

How the first cell is computed: 50,000 × 600 = 30 million output tokens; 30,000,000 ÷ 250 tokens per second = 120,000 s = 33 hours; × 2 GPUs = 67 GPU-hours. Redhawk is free, but 10 days of one node is a big share of 8 GPUs that the whole campus shares, and queue waits come on top. Running on all 4 nodes would cut the wall-clock time to about 2.5 days if they were free.

**Talon and OSC.** Talon (4 H100s per node) is unconfirmed. **OSC** is a realistic alternative worth knowing about. Its Cardinal cluster has nodes with 4 H100 94 GB GPUs. The Ohio academic rate is listed at $0.09 per GPU-hour, and every Ohio academic faculty member gets an automatic $1,000 credit per fiscal year (FY27 confirmed). The project lead must be faculty, so Dr. Lee would have to set it up. Whether the $0.09 rate applies to H100s should be confirmed with OSC. If it does, the credit covers far more GPU time than this project needs. NSF ACCESS (a graduate student can lead a small "Explore" allocation, with the advisor as co-PI) and the NAIRR Pilot (compute and model-access credits for US researchers) are other routes.

**What this means overall:** Redhawk can run a 24B to 32B model at 4-bit, but slowly, on an old software stack, and with real setup risk. Anything larger (DeepSeek R1 or V4, gpt-oss-120b) cannot run on Redhawk at all and must be hosted or run on Talon or OSC. For the full 50k run, a hosted API is likely faster and cheaper in practice than wrestling with V100s, and Redhawk stays useful for the pilot and as a no-cost fallback.

---

## 6. Cost for 50,000 examples

The token assumptions are the same as `docs/teacher_selection.md`, so the numbers compare directly with the Sonnet 5.5 plan:
- **Base:** 300 input and 600 output tokens per example, which means 15M input and 30M output tokens for 50,000.
- **Base + 2k thinking:** the same, plus 2,000 thinking tokens, so 130M output tokens.

Formula: cost = (input tokens × input price + output tokens × output price) ÷ 1,000,000.

*Worked example, DeepSeek V4-Flash on DeepInfra ($0.09 in / $0.18 out per million):* Base = 15 × 0.09 + 30 × 0.18 = 1.35 + 5.40 = **$6.75**. With thinking = 1.35 + 130 × 0.18 = 1.35 + 23.40 = **$24.75**.

| Model | Cheapest primary-source price (in / out per MTok) | 50k, Base | 50k, Base + 2k thinking |
|---|---|---|---|
| **Claude Sonnet 5.5, Batch API (current plan)** | $1.00 / $5.00 | $165 | $665 |
| DeepSeek V4-Flash (DeepInfra) | $0.09 / $0.18 | $7 | $25 |
| DeepSeek `deepseek-flash` on DeepSeek's own API, off-peak (serves V4.1-Flash) | $0.15 / $0.60 (half of the $0.30 / $1.20 peak price) | $20 | $80 |
| gpt-oss-120b (cheapest OpenRouter provider; Together) | $0.03 / $0.15; Together $0.15 / $0.60 | $5; Together $20 | $20; Together $80 |
| Qwen3.6-27B (Chutes; DeepInfra) | $0.25 / $2.00; DeepInfra $0.32 / $3.20 | $64; DeepInfra $101 | $264; DeepInfra $421 |
| Qwen3-32B (DeepInfra) | $0.08 / $0.28 | $10 | $38 |
| DeepSeek-R1-0528 (DeepInfra) | $0.50 / $2.15 | $72 | $287 |
| OLMo 3.1 32B Think (secondary-source price only) [S] | $0.15 / $0.50 | $17 | $67 |
| Mistral Small 3.1 (Cloudflare via OpenRouter) | $0.351 / $0.555 | $22 | n/a (no thinking mode) |
| Qwen3-8B, R1-Distill-Qwen-32B | no hosted provider found | Redhawk only | Redhawk only |
| Any model self-hosted on Redhawk | $0 in money | GPU-hours, see Section 5 | GPU-hours, see Section 5 |

How to read this:
- **Every open-weight option is cheaper than Sonnet 5.5**, most of them by 5 to 30 times. Money stops being the deciding factor. Quality, time and the license are what matter.
- **Thinking length is the biggest unknown.** The 2,000-token figure is our planning assumption, not a measurement. Reasoning models often think much longer: DeepSeek-R1-0528 averages about 23,000 thinking tokens on a hard AIME problem, and Qwen3.8-27B used about 1.7 times the median number of tokens on the Artificial Analysis test suite. Our questions are much easier than AIME, so the real figure is probably lower, but the pilot must measure it. For Qwen3.6-27B, whose output price is relatively high ($2 to $3.20 per MTok), each extra 1,000 thinking tokens per example adds about $100 to $160 at 50k.
- **Batch discounts exist but are uneven.** Fireworks and Groq offer 50% off batch jobs, DeepInfra 20% off. Together advertises "up to 50%" but lists only a speech model as discounted. DeepSeek offers off-peak half price instead. OpenRouter has no batch API.
- **Prices change often.** Several prices here changed during 2026, and some models were withdrawn. Re-check them on the day of any paid run.

---

## 7. How well each model can use the prompts we already wrote

Our current generation script (`code/generation/generate_benchmark.py`, with `data/prompts/benchmark_generation_v6.md`) relies on six features of the Claude API. Each one needs an equivalent on an open-weight model:

1. **A system prompt plus a user prompt.** The v6 system prompt is a numbered list of 11 rules. Every model here accepts a system prompt *except the original DeepSeek-R1 and R1-Distill models*, whose cards say to put everything in the user turn. Long rule lists are a test of instruction following. Where reported, OLMo 3.1 scores 93.8 on IFEval (an instruction-following benchmark). The other cards mostly do not report it.
2. **Structured output (a JSON schema).** We send a schema through `output_config.format` and get back a valid JSON object. The equivalents are:
   - *vLLM:* `response_format` with a JSON schema, which forces valid output. Importantly, when a reasoning parser is enabled (there are ones for `qwen3`, `deepseek_r1`, `gemma4` and others), vLLM lets the model think freely and only enforces the schema after the end of the thinking block. Known bugs: Gemma 4 with thinking turned off silently skips the schema; DeepSeek V3.2/V4 on vLLM 0.20 put the JSON inside the reasoning field [S]; and the old `guided_json` field was removed, so a script that still sends it gets *unchecked* output without any error [S].
   - *llama.cpp:* `json_schema` or `response_format`. The schema is only used to force output and is *not* shown to the model, so the prompt must describe the fields too (ours already does). Thinking tokens count against the output limit, so long thinking can use up the budget before the JSON starts.
   - *Hosted providers:* OpenRouter supports strict JSON schemas, but only on some providers. Setting `require_parameters: true` stops it from silently sending the request to a provider that only treats the schema "as a strong hint". Fireworks turns *off* reasoning when a JSON schema is used. Together supports JSON schema mode.
   - The DeepSeek-R1 paper itself says R1's "structural output capabilities ... remain suboptimal", another reason to drop it.
3. **An `effort` level and adaptive thinking.** Claude lets us set how hard it thinks. The open equivalents:
   - gpt-oss: reasoning effort low/medium/high, the closest match.
   - DeepSeek V4: Non-think/High/Max modes.
   - Qwen3 and Qwen3.6: thinking on or off (`enable_thinking`), with no in-between level. Qwen3.5 and later dropped the `/think` and `/no_think` switches.
   - OLMo 3 Think, R1 and R1-Distill: always think.
   - Mistral Small 3.1: never thinks.
4. **The Batch API.** On our own GPUs, vLLM's offline batch mode or a queue of requests to its server does the same job. Hosted batch APIs exist on Fireworks, Groq, DeepInfra and Together.
5. **`max_tokens` and `stop_reason`.** Every engine and provider has an output limit and reports whether the output was cut off. The script's "cut off at max_tokens" check carries over directly. Reasoning models need a much higher limit than our current 5,000 tokens (Qwen recommends 32,768), so the cost guard in the script must be rethought.
6. **Sampling settings.** Claude Sonnet 5.5 does not let us set temperature. Open models *do*, and their cards give firm recommendations: Qwen3 thinking mode at temperature 0.6, top_p 0.95, top_k 20, and never greedy decoding; Qwen3.5/3.6 at temperature 1.0 with presence penalty 1.5; R1 at temperature 0.6. This is an improvement for reproducibility, because we can now record exact sampling settings in every run log as README Section 12 requires.

**One unchanged strength.** The v6 design takes number answer keys from R's own output instead of trusting the model's typed number, and it regenerates items that fail the checks. That protection does not depend on which teacher writes the questions, so it carries over to any open-weight teacher.

**One prompt change to expect.** The v4 prompt was refused by Claude, most likely because it looked like a request to reveal reasoning. Open-weight models have no such refusal behavior, so the earlier `working`-field-first design (v4) could be tried again. Whether it works better is a question for the test, not something to assume.

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

**Cost.** No hosted provider among the five checked sells it, so it would be Redhawk only (Section 5 times).

**Fit with our prompts.** It has the same awkwardness as the original R1: no system prompt, forced `<think>`, temperature 0.6.

**Verdict: ruled out.** Qwen3-32B is the same size, stronger, more flexible and actually hosted.

### 8.3 Qwen3-32B

**What it is.** Alibaba's 32.8B dense model from April 2025, with 32K context (131K with an extension). It can think or answer directly.

**License.** Apache 2.0, with no clause about outputs, so they are ours to use.

**Quality.** In thinking mode: MATH-500 97.2, AIME 2024 81.4, AIME 2025 72.9, GPQA 68.4, LiveCodeBench 65.7. In non-thinking mode the scores fall sharply (AIME 2025 20.2, GPQA 54.6), so it would need to run with thinking on.

**Hardware.** It fits Redhawk at 4-bit (official AWQ file 19.33 GB, official GGUF Q4_K_M 19.76 GB). Note that AWQ does not run in vLLM on V100s, so a GPTQ or GGUF version would be needed there. Its design is older and well supported, so an old pinned vLLM or llama.cpp should handle it.

**Cost.** Very cheap hosted: $0.08 / $0.28 on DeepInfra, so about **$10 to $38** for 50k.

**Fit with our prompts.** Good. It takes a system prompt, has a clean on/off thinking switch (`enable_thinking`), works with vLLM's `qwen3` reasoning parser for JSON, and has published sampling settings. No JSON reliability data was found.

**Verdict: best of the six, but superseded.** If only the original six were allowed, choose this one. Since its newer sibling Qwen3.6-27B is the same family, the same license and nearly the same size with much higher scores, it is better used as a cheap comparison point in the test.

### 8.4 Mistral Small 3.1 24B

**What it is.** Mistral's 24B dense model (March 2025), 128K context, which also reads images. It is a plain instruction model with **no thinking mode**.

**License.** Apache 2.0. Mistral's commercial terms appear to restrict only *image* outputs from being used to build competing products [S]. That does not affect us, but the primary text was not verified.

**Quality.** MATH 69.3, GPQA Diamond 45.96. It is the weakest of the six by a wide margin. The June 2025 update (Small 3.2) barely changes this (MATH 69.4, GPQA 46.1) but cuts repetitive-output failures from 2.11% to 1.29%.

**Hardware.** It is the best fit for Redhawk. At 4-bit it is only 14.3 GB, which leaves about 13 GB of working memory on one node, so many examples could be processed at once.

**Cost.** About $22 for 50k (Cloudflare via OpenRouter), or less through Mistral's own API, which offers 50% off batch.

**Fit with our prompts.** It has native JSON output and function calling, but no thinking at all.

**Related models.** Magistral Small 1.2 (September 2025, 24B, Apache 2.0) is Mistral's *reasoning* version: AIME 2025 77.3, GPQA 70.1, LiveCodeBench 70.9, about $0.50 / $1.50 per MTok. It is much better, and still well behind the 2026 options. Mistral Small 4 (March 2026, 119B MoE) is too big for Redhawk, and the only score found for it is GPQA 71.2.

**Verdict: ruled out.** It is easy to run and cheaply licensed, but too weak to stand in for Sonnet 5.5 on statistics.

### 8.5 OLMo 3 32B Think (and OLMo 3.1 32B Think)

**What it is.** The Allen Institute for AI's 32B dense reasoning model (OLMo 3 in November 2025; OLMo 3.1 in December 2025 with three more weeks of reinforcement-learning training). It always thinks. It is unusual because **everything is open**: weights, training code and training data.

**License.** Apache 2.0, "intended for research and educational use in accordance with Ai2's Responsible Use Guidelines". Those guidelines list harmful uses to avoid (fraud, malicious code, academic dishonesty and so on) but **say nothing against training other models on outputs**. Its reasoning training data was itself written by DeepSeek R1 (MIT).

**Quality (3.1).** AIME 2024 80.6, AIME 2025 78.1, MATH 96.2, GPQA 57.5, LiveCodeBench 83.3, IFEval 93.8. Strong on math and instruction following, weak on GPQA (graduate-level science questions), which is the closest proxy for conceptual statistics.

**Hardware.** It fits Redhawk at 4-bit (GGUF Q4_K_M 19.5 GB). It needs a recent Hugging Face transformers version (4.57+), and an old pinned vLLM may not support it. That needs checking.

**Cost.** Only secondary sources list a price (about $0.15 / $0.50 per MTok). Artificial Analysis says there is "no publicly available API", and the OpenRouter page is gone. In practice it is Redhawk-only.

**Fit with our prompts.** Always thinks, takes a system prompt, temperature 0.6. Its card contains small errors (a template typo and 7B dataset names on the 32B card), which suggests less polish.

**Verdict: ruled out as the main teacher, kept as a "fully open" option.** A fully open teacher would make the report's story very clean (every step reproducible from public data). If Dr. Lee values that above raw quality, OLMo 3.1 is the choice. Otherwise its GPQA score and lack of hosting put it behind.

### 8.6 Qwen3-8B

**What it is.** The 8.2B sibling of Qwen3-32B, with the same license (Apache 2.0) and the same thinking switch.

**Quality.** In thinking mode: MATH-500 97.4, AIME 2025 67.3, GPQA 62.0, LiveCodeBench 57.5. It is impressive for its size, but clearly a step down from the 32B. A DeepSeek-distilled version (`DeepSeek-R1-0528-Qwen3-8B`, MIT) scores a bit higher (AIME 2025 76.3, GPQA 61.1).

**Hardware.** At FP16 it needs 16.4 GB, which does *not* fit on one 16 GB V100. It needs both GPUs of a node (fast: an estimated 11 to 90 GPU-hours for 50k) or an 8-bit version (8.7 GB GGUF).

**Cost.** No major host sells it (Fireworks only as an embedding model; the OpenRouter page did not resolve, so that is unconfirmed). It would be Redhawk only.

**Verdict: ruled out as the teacher.** The whole point of the teacher is to be much stronger than the students. An 8B model is only 8 times larger than Pythia 1B and is far from Sonnet 5.5. It is fast enough on Redhawk to be a possible cheap ablation (a "weak teacher" comparison for the report) if that becomes interesting later.

---

## 9. Newer open-weight models (released since mid-2025)

### 9.1 Qwen3.6-27B: first choice

- **What:** a dense 27B model from Alibaba (April 2026), 262K context, with thinking on by default and switchable off (`enable_thinking: false`). It is part of the Qwen3.5/3.6 generation, which uses a new hybrid attention design (Gated DeltaNet layers mixed with normal attention). That design keeps the working memory small on long outputs, but it is also why support on old software must be checked.
- **License:** Apache 2.0.
- **Quality:** AIME 2026 94.1, GPQA Diamond 87.8, LiveCodeBench v6 83.9, HMMT February 2025 93.8 (vendor-reported). These are the highest scores of any model in this document that can fit on Redhawk. The earlier Qwen3.5-27B (February 2026) scores GPQA 85.5 and LiveCodeBench v6 80.7.
- **Hardware:** at 4-bit about 17 to 21 GB, so it fits one Redhawk node, *if* the pinned vLLM 0.18 or llama.cpp supports the Qwen3.5/3.6 design. **This is the first thing to check on Redhawk.** On an H100 it runs at full BF16 precision.
- **Cost:** $0.25 / $2.00 (Chutes) to $0.32 / $3.20 (DeepInfra), so about **$64 to $101 for 50k at Base and $264 to $421 with 2k thinking**. It is the most expensive of the shortlist per output token, because its output price is high. Still below Sonnet 5.5.
- **Prompt fit:** system prompt, thinking switch, vLLM `qwen3` reasoning parser for JSON after thinking. Its card recommends temperature 1.0 and presence penalty 1.5. Presence penalty discourages repeating words; on Qwen3 the card warns that high values can cause language mixing, so watch for that in the test.
- **Risks:** verbosity unknown on our questions; vLLM-on-V100 support for the new design is unverified; its sibling Qwen3.8-27B (below) was measured as very verbose, so the family may lean toward long outputs.

### 9.2 DeepSeek V4-Flash (and V4.1-Flash): runner-up, hosted

- **What:** a DeepSeek mixture-of-experts model (April 2026), 284B total and 13B active parameters, with selectable thinking (Non-think / High / Max). DeepSeek's own API now serves the newer **V4.1-Flash** (released 2026-09-10, updated 2026-10-17), currently the top open-weight model on the Artificial Analysis Intelligence Index v5 (score 33 [S]).
- **License:** MIT for V4-Flash. V4.1-Flash is reported as MIT [S], but the license of the October update was not checked. DeepSeek's API terms (effective 2026-04-29) say: "We assign any rights, title, and interests—if any—in the Outputs of the Services to you", and list permitted uses including "training other models (such as model distillation)". **No other provider or model has a clearer statement.**
- **Quality (V4-Flash, highest thinking mode):** GPQA 88.1, LiveCodeBench 91.6, HMMT February 2026 94.8 (vendor-reported). V4.1-Flash: GPQA 90.9.
- **Hardware:** not possible on Redhawk. The weights are about 160 GB in a mix of FP4 and FP8 [S], so a 4×H100 node might hold it, but H100s have no FP4 hardware and engine support would need checking.
- **Cost:** DeepInfra (V4-Flash) $0.09 / $0.18, so **$7 to $25 for 50k**. DeepSeek's own API (V4.1-Flash) $0.30 / $1.20 at peak, half price off-peak (peak is weekdays 01:00 to 04:00 and 06:00 to 10:00 UTC), so $20 to $80 off-peak. There is no batch discount, but off-peak pricing does a similar job.
- **Prompt fit:** system prompt, JSON output supported on DeepSeek's API, and thinking modes that map well onto Claude's effort levels. One known vLLM bug (JSON landing in the reasoning field on V4 [S]) only matters if we self-host.
- **Risks:**
  - **Model churn.** DeepSeek's own API has remapped its model names several times in 2026 (R1 to V3.1 to V3.2 to V4-Flash to V4.1-Flash), so a fixed model version must be pinned through a provider that serves exact weights, or every run's model ID must be recorded.
  - **Data handling.** DeepSeek's own API is hosted in China. Our prompts are synthetic statistics questions with no personal data, but it is worth checking whether Miami University has any policy on DeepSeek services. Using the MIT-licensed weights through a US host such as DeepInfra avoids the question, though then the host's terms apply instead of DeepSeek's explicit distillation clause (DeepInfra's terms say third-party models are governed by their own license, which here is MIT).

### 9.3 gpt-oss-120b: third

- **What:** OpenAI's open-weight mixture-of-experts model (August 2025), 117B total and 5.1B active parameters, with reasoning effort low/medium/high.
- **License:** Apache 2.0. The usage policy only asks users to follow applicable law, with no restriction on outputs.
- **Quality:** AIME 2025 92.5, GPQA 80.1 at high effort without tools [S] (from a secondary source quoting OpenAI's model card).
- **Hardware:** it fits on one 80 GB H100 in its native MXFP4 format, so it is self-hostable on Talon or OSC but not on Redhawk. Its small sibling **gpt-oss-20b** (21B, GPQA 58.6) runs "within 16 GB", but whether its MXFP4 format works on V100s is unverified, and its scores are too low to be the teacher.
- **Cost:** $0.03 / $0.15 (cheapest OpenRouter providers) to $0.15 / $0.60 (Together), so about **$5 to $80 for 50k**.
- **Prompt fit:** the effort setting is the closest match to our Claude scripts. It uses OpenAI's "harmony" chat format, which the engines handle.
- **Risks:** below the first two on GPQA, and the scores come from a secondary source. Those numbers should be read on OpenAI's card before the test.

### 9.4 Others considered

- **Qwen3.8-27B** (August 2026, Apache 2.0): GPQA 89.2, LiveCodeBench v6 90.3. It is even stronger on paper than Qwen3.6-27B, but Artificial Analysis found it **very verbose** (about 130M tokens to run its test suite against a median of 78M), and it scored 20 on that index. At $0.50 / $3.00 its long outputs make it expensive. It is a reasonable swap for Qwen3.6-27B if the test shows 3.6 is not good enough. The Qwen3.8 *flagship* (not the 27B) is reported to use a custom license [S], so check the license of the exact model used.
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
| Qwen3.6-27B | 27B dense | Apache 2.0; yes, no restriction | 94.1 (2026) | 87.8 | 83.9 (v6) |
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

| Model | Redhawk (2×V100 16 GB)? | Talon/OSC (H100)? | 50k cost, Base to +2k thinking | Thinking control |
|---|---|---|---|---|
| Qwen3.6-27B | Yes at 4-bit, if old vLLM or llama.cpp supports its design (check) | Yes, full precision | $64 to $421 | On / off |
| DeepSeek V4-Flash | No | Maybe (about 160 GB FP4/FP8) | $7 to $80 | Non-think / High / Max |
| gpt-oss-120b | No | Yes, one H100 | $5 to $80 | Low / medium / high |
| DeepSeek-R1-0528 | No | No | $72 to $287+ (very verbose) | Always on |
| Qwen3-32B | Yes at 4-bit (GPTQ/GGUF) | Yes | $10 to $38 | On / off |
| OLMo 3.1 32B Think | Yes at 4-bit (check engine support) | Yes | Redhawk only (about $17 to $67 if a host appears) | Always on |
| R1-Distill-Qwen-32B | Yes at 4-bit | Yes | Redhawk only | Always on |
| Qwen3-8B | Yes, needs both GPUs or 8-bit | Yes | Redhawk only | On / off |
| Mistral Small 3.1 | Yes, best fit (14 GB at 4-bit) | Yes | about $22 | None |

---

## 11. Proposed next step: a small hands-on test of the shortlist only

**What and why.** Public benchmarks cannot tell us how well a model writes *statistics and R* questions and answers in *our* format. A small, cheap test can. Following Jaxson's instruction, only models that could plausibly be chosen are tested: Qwen3.6-27B, DeepSeek V4-Flash, gpt-oss-120b, and optionally Qwen3-32B as the best of the original six.

**How it would work.**
1. Use the v6 prompt and the existing free checks in `generate_benchmark.py` (JSON parse, field rules, thinking-aloud check, R verification of number keys, `dupcheck`), adapted to call an OpenAI-compatible endpoint instead of the Claude API.
2. Give each model the same 20 slot descriptions (category, subtopic, difficulty, answer type) with **new item IDs, kept in a separate dev folder that never becomes part of the benchmark**. No existing or future benchmark question is shown to any model.
3. Run each model with thinking on, at its card's recommended sampling settings, with JSON schema enforcement.
4. Measure, per model:
   - share of replies that are valid JSON on the first try
   - share of number keys R agrees with
   - multiple-choice keys found wrong by hand check
   - thinking and output tokens per item (this replaces the 2,000-token guess in Section 6)
   - questions that "think aloud" or contain their own answer
   - near-duplicates
   - cost
5. Compare with Sonnet 5.5's trial 8 and the 100-question batch on exactly the same checks.

**Expected cost (estimate).** Assume a generous 6,000 output tokens per item, including thinking. Then 20 items × 6,000 = 120,000 output tokens per model. At the highest shortlisted output price ($3.20 per MTok, Qwen3.6-27B on DeepInfra) that is about $0.38 per model, so **under $2 for all four**. This would be the project's first paid non-Claude call. The CLAUDE.md cost rule is written for Claude calls, but these should be logged in `docs/cost_log.md` the same way (time, purpose, model ID, provider, settings, tokens, dollars, running total). Stating the expected cost before the run and comparing actual against it afterwards applies too.

**What could go wrong.**
- A provider might silently ignore the JSON schema. Use providers that enforce it, and on OpenRouter set `require_parameters: true`.
- Thinking might run past the output limit. Set a high limit and record cut-offs.
- Twenty items gives wide error bars, so the test can rule out a clearly bad model but cannot separate two close ones with confidence.
- The hand check would again be done by a Claude model, which shares blind spots with Claude. That matters less now that the generator is a different model family.

**What it tells us.** Whether each shortlisted model can follow our prompt and produce correct, checkable keys, and what it really costs per item. It does not tell us how good the final students will be. Only the Phase 4 pilot does that.

---

## 12. Effects on the rest of the project plan

- **The teacher row in README Section 2 and the Phase 2 checklist.** These change only once Anthropic answers and a teacher is chosen. `docs/teacher_selection.md` stays as the record of the original decision.
- **The benchmark.** The benchmark trials (BM0001 to BM0120) and the planned 1,000-question benchmark were written or are being written by Claude. A benchmark is not training data, so the "train competing models" clause may not apply to it, but **the same Anthropic support thread should be asked about it explicitly.** If benchmark generation also has to move, the same shortlist applies. A different model family writing the benchmark and the training data would also reduce the "shared blind spots" risk in README Section 9.
- **The verifier.** The plan uses a ChatGPT model as the verifier. With a Qwen or DeepSeek teacher, the verifier is still a different model family, so the independence ladder holds. If gpt-oss-120b were the teacher, the verifier would be from the same company (OpenAI). That is less independent, and another reason it ranks third.
- **Success criterion 4 (at least 10 times cheaper or smaller than the teacher).** This becomes easier to measure: with an open-weight teacher, parameter count, memory and speed can be compared directly. Qwen3.6-27B, for example, is 27 times the size of Pythia 1B.
- **The 80% teacher red flag (README Section 1).** It still applies. The chosen open-weight teacher must reach 80% on the frozen benchmark, measured in Phase 5. A weaker teacher than Sonnet 5.5 makes this check more important, not less.
- **Logging.** Every run log should record, as well as what is logged now: provider (or "self-hosted"), exact weights repo and revision (or provider model ID), quantization, engine and version, temperature, top_p, top_k, presence penalty and thinking setting. The README's dated-output rule applies unchanged.
- **Reproducibility gain.** Open weights can be pinned by exact file and checksum, so the teacher can be re-run years later, which Sonnet 5.5 could not guarantee. A `recovery/` doc should describe how to fetch the exact weights once a teacher is chosen.

---

## 13. Limitations

- All scores are vendor-reported or third-party proxies. None tests statistics or R. Settings differ between vendors (number of samples, thinking budget, tools).
- **The Sonnet 5.5 numbers cannot be put side by side with these.** `docs/teacher_selection.md` used the Artificial Analysis Intelligence Index *before* its version 5. Version 5 uses a different scale (the top open model scores 33), and older models now show "N/A". GPQA for Sonnet 5.5 was not recorded in our docs. So this document can rank the open-weight candidates against each other, but cannot say from public data how far below Sonnet 5.5 each one is. The test in Section 11 and the Phase 5 teacher evaluation answer that.
- Redhawk speed figures are estimates scaled from other GPUs and model sizes. No 32B 4-bit V100 benchmark was found.
- Whether vLLM 0.18 or llama.cpp supports Qwen3.6's and OLMo 3's designs on V100 is unverified.
- Prices and model availability change quickly. Several models were withdrawn from APIs during 2026.
- Hosted providers' terms add to the model license. Fireworks' terms (Section 2.2(c), dated 2026-07-10) forbid using "any content available on or via the Service ... for any machine learning and/or artificial intelligence training", which may or may not be meant to cover your own outputs. **Do not use Fireworks for training data without asking them in writing.** Together and Groq forbid building a *competing service* (we are not), and DeepInfra and OpenRouter defer to the model's own license.
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

**Project documents:** `README.md`, `docs/teacher_selection.md`, `docs/teacher_subscription_feasibility.md`, `docs/cluster_selection.md`, `docs/pythia_behavior_analysis.md`, `code/generation/generate_benchmark.py`, `data/prompts/benchmark_generation_v6.md`.
