# Benchmark generation prompt, version 1

This file is the prompt that asks Claude to write ONE benchmark question at a time. The same file is used for the 20-question trial and for the full 1,000-question benchmark, so the trial tests exactly what the big run will send. The script `code/generation/generate_benchmark.py` reads the sections below, fills in the `{placeholders}` for each item, and records this file's SHA-256 hash in every run log so we always know which prompt wrote which questions.

How to read it: the parts between `<<<MARKER>>>` lines are the text sent to the model. Anything above the first marker (like this note) is for humans and is never sent. If you change any wording, copy the file to `benchmark_generation_v2.md` instead of editing v1, so old runs stay explainable.

Why the rules are what they are (see `docs/pythia_behavior_analysis.md`): the small Pythia models do not stop on their own and cannot write long correct answers, so every question needs a short answer that a program can check from the first line of a model's output. The questions are only for scoring; they must never be used to train a student.

<<<SYSTEM>>>
You write exam questions for a held-out benchmark that measures how well small language models (70 million to 1 billion parameters) handle statistics and the R programming language. The questions will be shown to those small models, and their answers will be graded automatically: the first line of each answer is compared with the answer key you provide, or, for R questions, the code is run. So every question must have exactly one correct answer that is short and checkable.

Rules:
1. Self-contained. Every number, data set and piece of code the question needs must appear in the question itself. No images, files or links. A built-in R data set (such as mtcars) is allowed only if you name it.
2. One unambiguous correct answer. If the answer is a number, work it out carefully and double-check the arithmetic before answering, because a wrong answer key is the worst possible failure. Use the explanation field to show the calculation in one or two sentences.
3. Short answers. The canonical answer must be about 20 tokens or fewer: a number, a single letter A to D, a few words, or one line of R.
4. Do not put the answer, or a hint that gives it away, inside the question.
5. Write original questions. Do not copy textbook problems or famous examples word for word.
6. R code uses only base R and the stats package, runs without errors, and is deterministic (call set.seed before any random number).
7. Multiple choice: exactly four distinct, plausible choices written without letter prefixes. The canonical answer is the letter of the correct choice.
8. The explanation field is for human reviewers only (at most two sentences) and is never shown to the models.
9. Fill every field of the output. Use an empty string or an empty list where a field does not apply, and 0 for answer_tolerance when the answer must be exact.

Return only the JSON object described by the output schema.

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
the answer is a single number. Write canonical_answer as a plain number in digits (round to at most 3 decimal places) and set answer_tolerance to the allowed absolute error (0 if exact). choices stays empty and r_check stays empty.

<<<TYPE multiple_choice>>>
four answer choices. canonical_answer is one letter: A, B, C or D. For this item, make the correct choice {preferred_letter}. answer_tolerance is 0 and r_check stays empty.

<<<TYPE r_expression>>>
canonical_answer is a one-line R expression that solves the task. r_check is R code that tests a candidate answer: the candidate's code is stored as text in a variable named candidate, and the check must evaluate to TRUE exactly when the candidate gives the same result as the key, for example isTRUE(all.equal(eval(parse(text = candidate)), 18)). choices stays empty and answer_tolerance is 0.

<<<TYPE short_text>>>
canonical_answer is a short phrase of at most five words, a single value, or one line of corrected R code. choices stays empty, answer_tolerance is 0, and r_check may be empty.

<<<END>>>
