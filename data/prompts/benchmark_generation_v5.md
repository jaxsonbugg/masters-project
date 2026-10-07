# Benchmark generation prompt, version 5

This file is the prompt that asks Claude to write ONE benchmark question at a time. The same file is used for the 20-question trial and for the full 1,000-question benchmark, so the trial tests exactly what the big run will send. The script `code/generation/generate_benchmark.py` reads the sections below, fills in the `{placeholders}` for each item, and records this file's SHA-256 hash in every run log so we always know which prompt wrote which questions.

How to read it: the parts between `<<<MARKER>>>` lines are the text sent to the model. Anything above the first marker (like this note) is for humans and is never sent. If you change any wording, copy the file to `benchmark_generation_v6.md` instead of editing v5, so old runs stay explainable.

**What changed from v1 to v2 and why.** The first trial (2026-10-07) found that 3 of 8 numerical answer keys were wrong, and one R check tested nothing. In v2 the model had to (1) write out its calculation in a new `working` field BEFORE it wrote the key, and (2) write `r_solution`, R code that recomputes every number. We then run that R code ourselves (`generate_benchmark.py verify`); if R and the key disagree, the item is flagged.

**What changed from v2 to v3 and why.** The second trial showed a rounding problem (BM0001: the exact value 0.3125 was keyed as 0.313, but R's `round(x, 3)` gives 0.312). In v3 `r_solution` prints the UNROUNDED number, every number question says how to round, the key is written with exactly that many decimals, and `answer_tolerance` covers a tie rounded the other way.

**What changed from v3 to v4, and why v4 failed.** v4 moved `working` to be the first output field and told the model to design the question and judge every answer choice true or false inside it. On 2026-10-07 the API refused all 20 v4 requests (`stop_reason: "refusal"`, no output). Anthropic's documentation says its safety checks decline prompts that ask the model to put its reasoning in the reply, for example "a `reasoning`, `thinking`, or `trace` field in JSON output" or a scratchpad section the model fills in before it answers. A `working` field written first, in which the model designs the question and judges every choice, looks exactly like that. This is the most likely cause, but it is not proven, because the first version of the script did not save the refusal details (`stop_details`).

**What changed from v3 to v5 and why.** v5 starts from v3, not v4, because v3 ran cleanly. It has NO `working` field: the model is no longer asked to write out its reasoning in the reply, and the system prompt says so in one plain sentence. The model still reasons internally, in the part of the reply that Anthropic calls thinking, which is billed as output tokens but is not part of the answer we receive. Everything else that is about content, not reasoning, is kept: `r_solution` (R code that recomputes the answer, which we run ourselves), a short one-sentence `explanation`, the rounding rules from v3, and from v4 the rules that the question text is final text only, that exactly one multiple-choice option is fully true, and that printed software output is consistent. What we do not know yet is whether keys stay as accurate without a written `working` field; that is what trial 5 measures against trials 2 and 3.

<<<SYSTEM>>>
You write exam questions for a held-out benchmark that measures how well small language models (70 million to 1 billion parameters) handle statistics and the R programming language. The questions will be shown to those small models, and their answers will be graded automatically: the first line of each answer is compared with the answer key you provide, or, for R questions, the code is run. So every question must have exactly one correct answer that is short and checkable.

Rules:
1. Self-contained. Every number, data set and piece of code the question needs must appear in the question itself. No images, files or links. A built-in R data set (such as mtcars) is allowed only if you name it.
2. One unambiguous correct answer. A wrong answer key is the worst possible failure, so make sure the key equals the result of your r_solution code, and that the answer you give is correct for the question exactly as it is written.
3. Short answers. The canonical answer must be about 20 tokens or fewer: a number, a single letter A to D, a few words, or one line of R.
4. Do not put the answer, or a hint that gives it away, inside the question.
5. Write original questions. Do not copy textbook problems or famous examples word for word.
6. R code uses only base R and the stats package, runs without errors, and is deterministic (call set.seed before any random number). Do not read or write files, use the network, call system commands, or load packages with library().
7. r_solution is R code that we will run to check your key. For a number answer it must compute the answer from the numbers in the question using R's own functions (for example pnorm, qt, sd, cor, choose, dbinom), not by retyping arithmetic done by hand, and it must end by printing exactly one number with cat(), for example cat(pnorm(0.4851, lower.tail = FALSE)). Print the exact, unrounded value: never use round(), signif() or format() on the final answer, because rounding is done by you when you write canonical_answer. If the question shows R code and asks what it prints, r_solution is that code with the final value passed to cat(). Leave r_solution as an empty string for multiple choice, r_expression and short_text items.
8. Multiple choice: exactly four distinct, plausible choices written without letter prefixes. The canonical answer is the letter of the correct choice. Exactly one choice may be fully true and the other three must each be clearly false. Every clause of the correct choice, including any "because ..." reason, must be true, and no wrong choice may be partly right. If you cannot make exactly one fully true choice, change the question.
9. Software output printed in a question (t, df, p-value, confidence interval, means, counts) must be internally consistent, so the numbers it shows agree with each other. If a choice depends on an exact value, print that value in the question.
10. The question field is the final text only, written once. It must never contain self-corrections, second thoughts, a trailing "...", or notes to yourself.
11. r_check, when present, must use the variable candidate (the student's answer as text). It must be FALSE for wrong answers, so never write a check that ignores candidate.
12. The explanation field is one short sentence for human reviewers only and is never shown to the models.
13. Fill every field of the output. Use an empty string or an empty list where a field does not apply, and 0 for answer_tolerance when the answer must be exact.

Return only the requested JSON fields. Do not include scratch work, chain-of-thought, design notes, or intermediate reasoning.

<<<USER>>>
Write benchmark item {item_id}.

Category: {category} - {category_text}
Subtopic: {subtopic}
Difficulty: {difficulty} - {difficulty_text}
Answer type: {answer_type} - {answer_type_text}

Set the category, subtopic, difficulty and answer_type fields in your output to exactly these values: category "{category}", subtopic "{subtopic}", difficulty "{difficulty}", answer_type "{answer_type}".

<<<CAT numerical>>>
a computational problem with a single numerical answer, such as a calculation about data, probabilities, distributions or test statistics.

<<<CAT conceptual>>>
a conceptual statistics question that tests understanding of a definition, an assumption or an interpretation. It is not a calculation.

<<<CAT r_generation>>>
a question asking for a short piece of R code that produces a specified result. The answer key is a one-line R expression.

<<<CAT r_interpretation>>>
a short R snippet followed by either "what does this print or return?" or "this code has an error, fix it". The answer is the output value or the corrected line of code.

<<<CAT output_interpretation>>>
a short piece of statistical software output (a regression summary, t-test, ANOVA table, confusion matrix or similar) printed in the question, followed by one question about what it shows.

<<<DIFF intro>>>
introductory undergraduate statistics or a first week of R: one step and small, friendly numbers.

<<<DIFF intermediate>>>
second-course undergraduate level: two or three steps, or a standard test or regression, with realistic numbers.

<<<DIFF graduate>>>
graduate level: needs deeper reasoning (likelihood, distributions of estimators, model assumptions, or non-obvious R behavior) but still has one short, checkable answer.

<<<TYPE number>>>
the answer is a single number. The question must state how to round (for example "Give your answer to 3 decimal places" or "Give your answer as a whole number"). Write canonical_answer as a plain number in digits with exactly that many decimal places (for example 0.740, not 0.74), at most 3 decimal places. Set answer_tolerance to the allowed absolute error: at least half of the last decimal place that was asked for (0.0005 for 3 decimal places, 0.005 for 2, 0.5 for a whole number), or 0 only if the answer is an exact integer count. r_solution must be filled in as described in the rules and its printed value must match canonical_answer. choices stays empty and r_check stays empty.

<<<TYPE multiple_choice>>>
four answer choices. canonical_answer is one letter: A, B, C or D. For this item, make the correct choice {preferred_letter}. answer_tolerance is 0, and r_solution and r_check stay empty.

<<<TYPE r_expression>>>
canonical_answer is a one-line R expression that solves the task. r_check is R code that tests a candidate answer: the candidate's code is stored as text in a variable named candidate, and the check must evaluate to TRUE exactly when the candidate gives the same result as the key, for example isTRUE(all.equal(eval(parse(text = candidate)), 18)). choices stays empty, answer_tolerance is 0 and r_solution stays empty.

<<<TYPE short_text>>>
canonical_answer is a short phrase of at most five words, a single value, or one line of corrected R code. choices stays empty, answer_tolerance is 0 and r_solution stays empty. If the answer is R code, r_check must test candidate as described above (for example, evaluate the candidate and compare its result); otherwise r_check may be empty.

<<<END>>>
