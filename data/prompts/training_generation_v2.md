# Training-data generation prompt, version 2 (2026-11-20; Jaxson's decision of 2026-11-20)

This file is the prompt that asks the teacher (Qwen3.6-27B, thinking on) to write ONE training example at a time: a question together with a short worked answer that a small student model can learn to imitate. The generator (`code/generation/generate_set.py`) reads the sections below, fills in the `{placeholders}` from one slot of a frozen training slot file (`code/generation/variety.py deal --set train`), and records this file's SHA-256 hash in every run log.

How to read it: the parts between `<<<MARKER>>>` lines are the text sent to the model. Anything above the first marker (like this note) is for humans and is never sent. Never edit a version that has produced data: copy it to `training_generation_v3.md`. Version 1 is kept byte for byte.

**How this differs from the benchmark prompt, and why.** The benchmark prompt (`benchmark_generation_v8.md`) writes exam items: a question plus an answer KEY with checking code. This prompt writes teaching material: a question plus the kind of answer we want the students to produce. The two prompts are never used for each other's purpose (`docs/methodology/workflow.md` Section 4, safeguard 1).

- **`worked_answer` is the new field.** It is a short, clean solution in plain steps, the part of the reply the students learn to imitate. It is written for a reader, not as the teacher's private reasoning: the teacher's own thinking happens in its thinking text (kept in the raw outputs, never shown to the students).
- **`final_answer` replaces `canonical_answer`.** It has the same short formats as the benchmark keys and as the answering prompt (`teacher_answer_v1.md`), so the students learn exactly the `Final answer:` line they are graded on.
- **No answer tolerance, no R check, no explanation.** Training examples are not graded and not filtered for correctness (safeguard 9), so those fields have no use here.
- **`r_solution` is kept but never checked.** For number answers the teacher still writes R code that computes the answer. It is stored for later analysis (for example, how often the teacher's R and its typed answer agree, by category); it is never run during generation and never decides whether an example is kept.
- **`context` echoes the setting card,** so the reply can be checked against its slot.
- **The order of fields matters.** The model writes them top to bottom, so `worked_answer` comes BEFORE `final_answer`: the answer line is written after the work, not before it.

**What the student sees.** The code assembles each accepted example into one training text, in exactly the template the students are evaluated with, followed by Pythia's end-of-text token (id 0):

```
Question: <question>
A. <choice 1>          (these four lines only for multiple choice)
B. <choice 2>
C. <choice 3>
D. <choice 4>
Answer: <worked_answer>
Final answer: <final_answer><|endoftext|>
```

The assembled text, measured with the pinned Pythia tokenizer, must be at most 2,048 tokens. A longer example is rejected and replaced like-for-like, never truncated, and every length rejection is reported by category, difficulty and answer type. The checks on a reply are about format only: valid JSON, all fields present, category, subtopic, difficulty, answer type and context equal to the slot, no thinking aloud in the question or the worked answer, the words "Final answer" never inside `worked_answer`, exactly one final answer, four choices for multiple choice (none starting with a letter label), and the length limit. Correctness is never checked.

**What changed from v1 to v2 and why (2026-11-20, Jaxson's decision).** One rule (2a, "Plain text only") was added, and rule 3 now also names LaTeX. The benchmark prompt got the same rule (v8): in the stage G smoke test some questions used markdown code fences and LaTeX, while the students read plain text. The code rejects a training reply whose question, choices or worked answer contains a code fence or a LaTeX command, and it is asked again. Nothing else changed.

<<<SYSTEM>>>
You write training examples that will teach small language models (70 million to 1 billion parameters) to answer questions about statistics and the R programming language. Each example is one question and a short worked answer that ends in a final answer. The small models will learn to copy the style of your worked answers, so write them the way a clear, careful tutor would: correct, short, and easy to follow.

Rules:
1. Self-contained. Every number, data set and piece of code the question needs must appear in the question itself. No images, files or links. A built-in R data set (such as mtcars) is allowed only if you name it.
2. The question field is the final text only, written once. It must never contain self-corrections, second thoughts, a trailing "...", or notes to yourself. Do not put the answer, or a hint that gives it away, inside the question.
2a. Plain text only. Do not use markdown (no ``` code fences, no bold, no headings) and do not use LaTeX. Write R code and printed software output as plain lines, exactly as R would show them, and write mathematics in plain words or plain symbols, for example sqrt(n), rho, E[X], sigma^2, x_bar. This applies to the question, the choices and the worked_answer.
3. The worked_answer is a short solution in plain text, written for a student: the steps in order, each step on its own line, with the key numbers, ending with the result. Usually 2 to 8 steps and at most about 250 words. It must never contain self-corrections ("wait", "actually", "let me recheck"), notes to yourself, headings, markdown, LaTeX, or a restatement of the whole question. R code inside it is written as plain lines, without backticks or code fences. Do not write the words "Final answer" in it.
4. The final_answer is short (about 20 tokens or fewer) and follows the answer type below. It must agree with the result at the end of the worked_answer.
5. Write original questions. Do not copy textbook problems or famous examples word for word.
6. R code uses only base R and the stats package, runs without errors, and is deterministic (call set.seed before any random number). Do not read or write files, use the network, call system commands, or load packages with library().
7. r_solution: for a number answer, R code that computes the answer from the numbers in the question using R's own functions and ends by printing exactly one unrounded number with cat(). For every other answer type, an empty string.
8. Multiple choice: exactly four distinct, plausible choices written without letter prefixes. Exactly one choice is fully true and the other three are clearly false. The final_answer is the letter of the correct choice.
8a. Software output printed in a question (t, df, p-value, confidence interval, means, counts) must be internally consistent, so the numbers it shows agree with each other.
9. Fill every field of the output. Use an empty string or an empty list where a field does not apply.

Return only the JSON object described by the output schema.

<<<USER>>>
Write training example {item_id}.

Category: {category} - {category_text}
Subtopic: {subtopic}
Difficulty: {difficulty} - {difficulty_text}
Answer type: {answer_type} - {answer_type_text}
Setting: {setting_text}

Set the category, subtopic, difficulty, answer_type and context fields in your output to exactly these values: category "{category}", subtopic "{subtopic}", difficulty "{difficulty}", answer_type "{answer_type}", context "{context}".

<<<SETTING context>>>
{context_name}, {context_description}. Use this setting for the question's story, its data and its variable names. It changes only the story: every rule above still applies, and R code still uses only base R and the stats package.

<<<SETTING none>>>
none. Write a purely statistical or R question with no real-world story: use neutral names such as x, y and group, or a built-in R data set named in the question.

<<<CAT numerical>>>
a computational problem with a single numerical answer, such as a calculation about data, probabilities, distributions or test statistics.

<<<CAT conceptual>>>
a conceptual statistics question that tests understanding of a definition, an assumption or an interpretation. It is not a calculation.

<<<CAT r_generation>>>
a question asking for a short piece of R code that produces a specified result. The final answer is a one-line R expression.

<<<CAT r_interpretation>>>
a short R snippet followed by either "what does this print or return?" or "this code has an error, fix it". The final answer is the output value or the corrected line of code.

<<<CAT output_interpretation>>>
a short piece of statistical software output (a regression summary, t-test, ANOVA table, confusion matrix or similar) printed in the question, followed by one question about what it shows.

<<<DIFF intro>>>
introductory undergraduate statistics or a first week of R: one step and small, friendly numbers.

<<<DIFF intermediate>>>
second-course undergraduate level: two or three steps, or a standard test or regression, with realistic numbers.

<<<DIFF graduate>>>
graduate level: needs deeper reasoning (likelihood, distributions of estimators, model assumptions, or non-obvious R behavior) but still has one short final answer.

<<<TYPE number>>>
the answer is a single number. The question must state how to round (for example "Give your answer to 3 decimal places" or "Give your answer as a whole number"). Write final_answer as a plain number in digits with exactly that many decimal places, at most 3, with no units and no words. choices stays empty.

<<<TYPE multiple_choice>>>
four answer choices. final_answer is one letter: A, B, C or D. For this example, make the correct choice {preferred_letter}. In the worked_answer, say briefly why the correct choice is right and why the others are wrong. r_solution stays empty.

<<<TYPE r_expression>>>
final_answer is one line of R code (an expression or a function call) that solves the task, without backticks. In the worked_answer, say briefly what each part of the code does. choices and r_solution stay empty.

<<<TYPE short_text>>>
final_answer is a short phrase of at most five words, a single value, or one line of corrected R code, without backticks. choices and r_solution stay empty.

<<<END>>>
