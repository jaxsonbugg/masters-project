# How the Pythia Models Behave, and What That Means for the Project

Prepared 2026-10-06 (the data files carry the UTC stamp 2026-10-07_0015Z). Based on one run of `code/evaluation/pythia_probe.py` (192 generations, results in `results/pythia_probe/`) plus outside research. Cost: $0.00 (local CPU, no API calls). Every number below was recomputed from the data file; every source link was opened (the few exceptions are marked "search snippet").

## Recommendation (the short version)

The four Pythia students are **text continuers, not question answerers**. Given a question, they write something that looks like the next part of a web page, and they never stop on their own: in all 192 generations, not one ended with the end-of-text token. So most of the project's design has to be about *teaching a format*, and the data show that format, not knowledge, is the first thing fine-tuning must fix. Concretely:

1. **Train on one fixed template and always end every answer with the end-of-text token** (`<|endoftext|>`, token id 0), with the loss counted only on the answer and that final token. Without that last token the fine-tuned model will keep rambling just like the untrained ones. For the 1B model, set the id explicitly, because its own config points at the wrong token (Section 3.2).
2. **Keep teacher answers short** (a few sentences, or a short rationale ending in a clearly marked final answer). Long answers are not something these models can imitate well, and they are also what makes teacher data expensive. Section 5 shows how much this could shrink the API bill, as a hypothesis to measure in the pilot.
3. **Grade the benchmark on short, checkable answers** (numbers, multiple choice, R code run against tests), and cut the model's output at a stop rule (first blank line or `Question:`) before grading. Free-text explanations from a 70M model are not something we can grade meaningfully.
4. **Expect the 70M model to score near zero on knowledge-heavy items** and make sure the benchmark has easy items and "well-formed answer" metrics, so differences between sizes are visible. This is a real risk to the 70% retained-accuracy tier at the smallest sizes; the project can still answer its question as a curve.
5. **Do the evaluation on the GPU cluster.** On this CPU the 1B model produced about 9.5 tokens per second, so scoring a 1,000-question benchmark at 64 tokens each would take roughly 2 hours.

## 1. What a "base model" is, and how Pythia was trained

A language model is a program that, given some text, predicts a probability for every possible next token (a token is a short chunk of text, about three quarters of a word on average). To generate text, you pick one token, add it to the text, and ask again, over and over. A **base model** is what you get when you train only on that one task over a huge pile of text. It is never taught to answer questions, follow instructions, or stop. An **instruction-tuned** model (like ChatGPT or Claude) gets extra training on examples of questions paired with good answers.

Pythia is a base-model suite from EleutherAI. According to [the Pythia GitHub repository](https://github.com/EleutherAI/pythia) (read in full for this document), every model uses a 2,048-token context, trains on about 300 billion tokens at 2,097,152 tokens per step for 143,000 steps, and the "deduped" versions we use saw a de-duplicated copy of the Pile data for about 1.5 passes. The [70M model card](https://huggingface.co/EleutherAI/pythia-70m-deduped) states that the model "has not been fine-tuned for downstream contexts in which language models are commonly deployed", will not respond to a prompt "the way a product like ChatGPT does", and should never be relied on for factual output. Its tokenizer is the same as GPT-NeoX-20B's. The [Pythia paper](https://arxiv.org/abs/2304.01373) describes the suite as 16 models, 70M to 12B, trained on the same public data in the same order, built for research on how models change with scale, which is exactly why it suits a size-comparison project. The Pile itself is described as [22 diverse subsets, many of academic or professional origin](https://arxiv.org/abs/2101.00027).

This means our students start with some world knowledge and a lot of fluency, but no concept of "a question deserves exactly one answer and then silence". Fine-tuning (continuing the training on our own examples) is where they learn that.

## 2. What we ran

The script asked each of the four models 16 questions, each in three prompt formats:

- **raw**: just the question (for example `What is a p-value?`).
- **qa**: `Question: <question>` then a new line `Answer:`.
- **fewshot**: three unrelated solved examples in the qa pattern, then our question.

The 16 questions: 2 general knowledge, 3 arithmetic, 1 word problem, 1 logic, 2 definitions, 3 statistics, 3 R code, 1 "answer with only a number". Decoding was **greedy** (always take the single most likely next token), at most 128 new tokens, weights loaded as `float16`, CPU only, one run. That is 4 models x 16 questions x 3 formats = 192 generations, all completed without an error. Limits of this design are in Section 7.

## 3. What the data show

### 3.1 The headline result: they never stop, and they loop

| Model | Generations ending with end-of-text | Hit the 128-token limit | Flagged as repeating (same 4 tokens at least 3 times) |
|---|---|---|---|
| 70M | 0 of 48 | 48 | 48 of 48 |
| 160M | 0 of 48 | 48 | 45 of 48 |
| 410M | 0 of 48 | 48 | 44 of 48 |
| 1B | 0 of 48 | 48 | 46 of 48 |

Even when a model gets the answer right, it keeps going. 1B on `Question: What is the capital of France?`, qa format:

> ` Paris.\nQuestion: What is the capital of the United States?\nAnswer: Washington.\nQuestion: What is the capital of the United Kingdom?\nAnswer: Londo` (cut at 150 characters here)

It answered, then invented the next quiz question itself, and would have gone on. In the qa and fewshot formats, the share of generations that contain a new `Question:` or `A:` block after the first line is high, and for 160M, 410M and 1B it reaches 16 of 16 with few-shot prompting:

| Model | raw | qa | fewshot |
|---|---|---|---|
| 70M | 3 of 16 | 7 of 16 | 7 of 16 |
| 160M | 2 of 16 | 11 of 16 | 16 of 16 |
| 410M | 1 of 16 | 11 of 16 | 16 of 16 |
| 1B | 6 of 16 | 14 of 16 | 16 of 16 |

**What it means:** the first line is the answer; everything after it is the model continuing a document. A tool that reads the whole output would score garbage. Both the benchmark runner and (above all) the training data must handle this: training must teach "answer, then end-of-text", and evaluation must cut the output.

### 3.2 The 1B model has a misconfigured stop token (a real trap)

All four models share the same vocabulary, where token id 0 is `<|endoftext|>` and id 2 is the exclamation mark `!`. The 70M, 160M and 410M configs correctly say the end-of-sequence token is id 0. The **1B config says `eos_token_id: 2`, which is `!`**, and its tokenizer defines no end-of-sequence token at all (`eos_token` is `None`). The tokenizer files for 1B also differ from the others at the file level (already noted in `docs/model_versions.md`), though the text we tested tokenized identically (Section 3.6). Consequences:

- If the 1B model is run with its default settings, generation would stop at the first `!` and never at end-of-text.
- A training script that asks the tokenizer for its end-of-sequence token would get nothing for 1B, and could silently train it without any stop token.

My first run of the probe hit exactly this: I stopped on the tokenizer's end token, which was `None` for 1B, so 1B was not being checked for stops correctly. I fixed the script to look up `<|endoftext|>` by name (always id 0) and reran everything; the table above is from the corrected run. **Project rule that follows:** in all training and evaluation code, set the end token explicitly to id 0 for all four sizes, and assert it.

### 3.3 The prompt format decides what kind of "document" the model writes

The same question produced very different continuations depending on format:

- **raw** drifts into other document types. Examples from the data: `What is 17 + 25?` made the 70M model write a stream of puzzle-style questions (`What is the next term in -1 + -1 - -1 - -1?`), the 410M and 1B models did the same with `In base 5, what is...` (the style of a machine-generated mathematics question set). `Write R code to compute the mean...` made the 160M and 1B models write C++ (`#include <iostream>`). Forum-style `A:` answers (like Stack Exchange) appear often. These are consistent with a web-scale training mix that includes forums, code and math exercise sets (the model card lists internet, prose, dialogue and academic sources; I did not verify the exact list of Pile subsets, so treat the "which subset" part as a guess).
- **qa** gives a short first line most of the time (mean first-line length 5.9 to 14.6 words, the 160M model the longest), then keeps going.
- **fewshot** produces the shortest, cleanest first lines (mean 1.1 to 5.9 words), because the model copies the pattern of short answers. But it also copies the *content* of the examples. Example, 160M: `Question: What is 17 + 25?` got ` White` (the colour answer from the example) and 70M answered `What is 144 divided by 12?` with `The sky is the same as the sky.` The model is imitating the surface form, not reading the question.

**What it means:** we should not leave the format to chance. Fine-tuning on one fixed template removes this sensitivity, which is also a fairness point: all students and the untrained baselines need to be compared under a fixed, pre-declared format.

### 3.4 Size helps fluency and recall, not arithmetic or reasoning

For the 8 prompts with a short unambiguous answer (two general knowledge, three arithmetic, one word problem, one logic, one "7 days"), I counted how often the correct answer appeared in the first line of the output. This is a rough tally (n = 8 per cell, simple text matching, a few matches are lucky copies), so read it only as a trend:

| Model | raw | qa | fewshot |
|---|---|---|---|
| 70M | 0 of 8 | 1 of 8 | 0 of 8 |
| 160M | 1 of 8 | 1 of 8 | 2 of 8 |
| 410M | 3 of 8 | 2 of 8 | 3 of 8 |
| 1B | 4 of 8 | 3 of 8 | 3 of 8 |

- **70M** fails nearly everything. Its output is mostly loops (`A:\n\nAnswer:\n\nAnswer:...`, `I have no idea.`).
- **410M and 1B** know simple facts. 410M and 1B both answered ` Paris` in the fewshot format; 1B wrote `The play was written by William Shakespeare` and `William Shakespeare`.
- **Arithmetic is wrong at every size.** `What is 17 + 25?`: 410M wrote `17 + 25 = 35`, 1B wrote `17 + 25 = 36` (the answer is 42). `What is 12 times 8?` produced `12` from 410M and 1B. Papers on Pythia find the same kind of pattern: per-digit accuracy improves smoothly with scale while exact multi-digit answers appear abruptly (one of the [search results](https://arxiv.org/pdf/2505.11004), snippet only, not read in full).
- **Statistics definitions are fluent but hollow.** 410M: `A p-value is a measure of statistical significance.` then repeated `The p-value is a measure of the probability that the null hypothesis is true.` (that is a common misconception, not the definition). 1B on the standard deviation versus standard error question: `Standard deviation is the standard error of the mean.` (incorrect). 1B on the 95% confidence interval: `It means that the probability of the event occurring is 95% of the time.` (incorrect). 70M's raw-format p-value answer was `A p-value is a p-value.`, repeated.
- **R code.** Only 2 of the 18 R-prompt generations at the two larger sizes (410M and 1B, both on the mean question in qa format) contained a correct-looking R call at all, and no generation anywhere contained `lm(`. 410M, qa format: `x <- c(4, 8, 15, 16, 23, 42)\nmean(x)\n#[1] 4.0`. The code is right, the printed result is wrong (the mean is 18), and 1B had the same kind of error (`mean(c(4, 8, 15, 16, 23, 42))\n\n#[1] 4.0 8.0 15.0 16.0 23.0 42.0`). For the typo-fix prompt (`mena(c(1, 2, 3))`), 1B treated `mena` as a real function (`You can use the function mena to get the number of elements in a list.`) instead of fixing the typo. For the regression prompt, 160M, 410M and 1B built long lists of numbers (`df <- data.frame(x = c(1,2,3,...`) and never reached `lm(`.

**What it means:** the models have patterns of code and text from pretraining, but no ability to compute. A 1,000-example fine-tune is not going to teach a 70M model to do multi-step statistics. What it can plausibly teach is the answer format and some surface patterns. That matters for how we read the research question (Section 6).

### 3.5 Speed and memory on this PC (CPU, `float16`, one sequence at a time)

| Model | Mean speed (tokens per second) | Peak memory (MB) |
|---|---|---|
| 70M | 172 | 771 |
| 160M | 75 | 1,101 |
| 410M | 31 | 1,623 |
| 1B | 9.5 | 3,441 |

`float16` loaded and ran on the CPU for all four sizes without errors. At 64 new tokens per question, a 1,000-question benchmark is about 6 minutes for 70M, 14 minutes for 160M, 34 minutes for 410M and 1.9 hours for 1B on this CPU, one question at a time (batching and a GPU will be much faster). These timings are only for planning; they say nothing about quality.

### 3.6 Facts the probe settled from `docs/model_versions.md`

- **Parameter counts match** the official counts exactly for all four sizes (difference 0). That includes the 1B (1,011,781,632), so the 512-value discrepancy seen in the Hugging Face API listing does not appear in the loaded model.
- **Stored dtype of the files** (read from the `.safetensors` headers): 70M, 160M and 410M are stored as 32-bit floats (F32); **1B is stored as 16-bit (F16)**. All four loaded as `torch.float16` as required. The Pythia repository says the 1B was trained in bf16 because of a loss spike in fp16, which is worth remembering for the fine-tuning precision choice on Redhawk's V100 GPUs (no native bf16).
- **Tokenizers:** the same eight test strings (plain text, a p-value sentence, three R snippets, numbers, the end-of-text string, whitespace and a tab) became **identical token sequences for all four sizes**, including 1B. One caveat: the 1B tokenizer config sets `clean_up_tokenization_spaces=True`, and the library printed a warning that this setting is destructive for this tokenizer type and was ignored. We should check once that decoding 1B output matches the others when we build the evaluation code.
- **R code costs few tokens:** the 3-line R snippet `model <- lm(y ~ x1 + x2, data = df)\nsummary(model)` is 22 tokens and a 3-line loop is 19, so answers with some R code fit easily in the 2,048-token window.

## 4. What outside research adds

- **Fine-tuning mechanics.** In [Hugging Face's TRL documentation](https://huggingface.co/docs/trl/sft_trainer) (read in full), supervised fine-tuning on prompt-completion pairs computes the loss on the completion only by default, which is what we want. The same page warns that the end-of-sequence token must match the format "to ensure the model's responses terminate correctly", the issue we found for 1B.
- **How little data teaches format.** [LIMA](https://arxiv.org/abs/2305.11206) fine-tuned a 65B model on only 1,000 curated examples and argued that "almost all knowledge in large language models is learned during pretraining, and only limited instruction tuning data is necessary to teach models to produce high quality output." That supports our 1,000-example pilot as a test of *format learning*. It also warns us: the idea assumes the pretrained model already holds the knowledge. At 70M, the data above suggest little knowledge is there to unlock, so distillation gains at the smallest sizes will come mostly from format and surface patterns.
- **How to score base models.** The EleutherAI evaluation write-up, [Lessons from the Trenches on Reproducible Evaluation](https://arxiv.org/abs/2405.14782) (the PDF text was only partly readable, so this is a summary), and an overview found by search (snippet only) describe two scoring styles: **likelihood scoring** (compare the probability the model gives to each multiple-choice option, with no free generation) and **generation scoring** (let the model write an answer and check it). Likelihood scoring suits small or base models that cannot be trusted to generate cleanly, but it is sensitive to how the question is formatted, needs length normalization when options differ in length, and does not always agree with generation-based results.
- **Reported Pythia scores** (from one search snippet of the Pythia paper, not independently checked): on zero-shot tests, scores rise from the 70M to 1B models, for example LAMBADA 0.185, 0.328, 0.516, 0.562 and SciQ 0.601, 0.741, 0.811, 0.840 for 70M, 160M, 410M, 1B. This matches the direction of what we saw: bigger is better at recalling and completing, which are likelihood-style tasks.

## 5. How this should change the project

### 5.1 Training data design (Phase 4 and Phase 6)

- **One template**, for example `Question: <text>\nAnswer: <text><|endoftext|>`, used for every example and every size. Loss only on the answer and the end token (TRL's prompt-completion mode does this by default).
- **Short answers with a marked final answer**, for example a one- to three-sentence explanation ending in `Final answer: 18`. The base models above could not hold a train of thought longer than a sentence or two, and a clear last line makes grading simple. Ask the teacher for this format explicitly in the prompt and have the script check each example for it.
- **Token budget:** keep the whole example (question, answer, end token) well below 300 tokens. The 2,048 limit is not the constraint; the 70M model's capacity is.
- **End token id 0, set explicitly** in the training code for all four sizes (Section 3.2).
- **Include simple items on purpose.** Easy facts and arithmetic are where 410M and 1B showed signal; the smallest models need some tasks they can win.

### 5.2 Benchmark design (Phase 3)

- Give every question an **answer type** (number, multiple choice, short text, R code with test cases) and a **canonical short answer** of at most about 20 tokens. Grade by exact or tolerance match after cutting the output at the first blank line, the first `Question:`, or the end token.
- Keep free-text conceptual questions to a clearly separate, optional slice. A grader cannot give a 70M model's loop a meaningful score, and the examples in Section 3.4 show that fluent text can be wrong.
- **Consider a multiple-choice slice scored by likelihood.** It is the one measurement every student, including the untrained baselines, can be scored on without generation noise. Report it separately from generation accuracy, because the two do not always agree.
- **Pre-declare one evaluation protocol** (prompt format, stop rule, max new tokens, greedy decoding) and use it for baselines, fine-tuned students and, where possible, the teacher. The untrained baselines will look worse under any format they were not trained on, so say so in the write-up.

### 5.3 Cost implication for the teacher (Phase 4 and the budget request)

The current estimate (`docs/cost_estimate.md`) assumes 300 input tokens and 600 output tokens plus up to 2,000 thinking tokens per example, which is $0.0133 per example at Batch prices. Most of that cost is output tokens, which the student never sees, because thinking tokens are billed but not stored in the training example. If the training answers are short and the teacher runs at lower effort, the cost per example could fall a lot. Sensitivity, Sonnet 5.5 Batch ($1 per million input tokens, $5 per million output tokens, cost = (input x $1 + output x $5) / 1,000,000):

| Scenario | Input tokens | Output tokens incl. thinking | Cost per example | 50k examples | 200k examples |
|---|---|---|---|---|---|
| Current high case | 300 | 2,600 | $0.0133 | $665 | $2,660 |
| Short answer, no thinking | 300 | 200 | $0.0013 | $65 | $260 |
| Short answer, 1,000 thinking tokens | 300 | 1,200 | $0.0063 | $315 | $1,260 |

This is arithmetic on assumptions, not a forecast. The pilot will measure the real token counts; until then the funding request should still use the safe high case. The check to run in the pilot: generate the same 50 questions at two effort levels and compare both the cost and how many answers pass verification, since cheaper answers are only a saving if they are still correct.

### 5.4 Evaluation compute (Phase 4 and Phase 5)

Run baselines and evaluations on Redhawk's GPUs with batching. This PC is fine for development and for the 70M and 160M models.

## 6. How the models work: determination

1. **Mechanism.** All four models are next-token predictors trained on web-scale text. A prompt is not an instruction; it is the start of a document, and the model writes whatever such a document would plausibly say next.
2. **Format cues dominate.** The same question becomes a forum post, a code file, a math drill or a quiz depending on how it is framed. Few-shot examples make the first line short and well-formed, but the models copy the examples' content too.
3. **They do not stop.** Stopping is something that has to be taught (end-of-text token plus consistent training data), and the 1B config has the wrong stop token.
4. **Scale buys recall and fluency, not computation.** At 410M and 1B simple facts appear; every size gets two-digit arithmetic wrong; definitions of statistical ideas read well and are frequently wrong or circular; the smallest model cannot hold a topic for more than a phrase.
5. **Greedy decoding loops.** Almost every output (183 of 192) repeated a phrase, which is a known property of always picking the top token; sampling would change that, but it would also make evaluation noisier.

**For the research question:** the primary question is how small a student can be while retaining useful capability. These data suggest the accuracy curve will rise steeply between 70M and 410M on easy items, and that the 70M student will struggle to reach the 60% absolute-accuracy floor on harder content regardless of how good the teacher data is. That is a legitimate finding, not a failure, provided the benchmark has enough easy items to show the curve. It also suggests being careful about promising the 70% "Useful" tier at 70M.

## 7. Limits of this analysis

- **Small and single-run:** 16 questions, 3 formats, greedy decoding, one seed, 128 tokens. The tallies in Section 3.4 are rough text matches over only 8 questions per cell and should not be quoted as accuracy.
- **Different from the final setup:** these are untrained models, run on CPU in `float16`, with prompts I wrote. A fine-tuned model will behave differently, and that is what the pilot tests.
- **No sampling run** (the script has a `--sampling` option that was not used), so the looping result applies to greedy decoding only.
- **Outside sources:** two were only seen as search snippets (the Pythia benchmark numbers and the arithmetic-scaling paper) and one PDF (the evaluation write-up) was only partly readable. Treat those three as leads to verify before they go in the final report.
- **Guesses marked as guesses:** the link between odd output styles and specific Pile subsets was not verified.

## 8. Files and sources

Data: `results/pythia_probe/2026-10-07_0015Z_probe.jsonl` (one record per generation, including full prompt and output), `..._summary.csv` (per model and format), `..._model_info.json` (parameter counts, dtypes, tokenizer comparison). Script: `code/evaluation/pythia_probe.py`. Environment: `environment/requirements.txt`, `recovery/python_env.md`.

Read in full: [Pythia model card (70M deduped)](https://huggingface.co/EleutherAI/pythia-70m-deduped), [Pythia GitHub repository](https://github.com/EleutherAI/pythia), [Pythia paper abstract](https://arxiv.org/abs/2304.01373), [The Pile abstract](https://arxiv.org/abs/2101.00027), [LIMA abstract](https://arxiv.org/abs/2305.11206), [TRL SFT trainer documentation](https://huggingface.co/docs/trl/sft_trainer). Partly read or snippet only: [Lessons from the Trenches](https://arxiv.org/abs/2405.14782), the Pythia benchmark scores and the [arithmetic emergence paper](https://arxiv.org/pdf/2505.11004).
