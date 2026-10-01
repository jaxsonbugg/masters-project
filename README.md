# Masters Project: Distilling a Frontier LLM into Small Domain-Specialized Models for Statistics and R

> This project will investigate how effectively knowledge from a large frontier language model can be distilled into much smaller, domain-specialized language models for statistics and R programming. The goal is to quantify the tradeoff between model size, domain-specific performance, and computational efficiency to determine how small a specialized model can become while still retaining useful capability.

**Author:** Jaxson Bugg (buggjm@miamioh.edu)

**Advisor:** Dr. Donghyung Lee

**Institution:** Miami University

**Duration:** Two semesters

**Status:** Planning (README created 2026-09-29)

This file is the living guide for the project. Update it as decisions are made, and keep the checklists current. The dated change history is in `docs/progress_update.md`.

---

## 1. Research Question

**Primary question:** How small can a specialized language model be, distilled from a frontier teacher, and still retain useful capability in statistics and R programming?

**Sub-questions**
1. How does post-distillation accuracy change with student size (70M, 160M, 410M, 1B)?
2. How does accuracy change with the amount of distillation data (e.g., 1k to 200k examples)?
3. Is there a "knee" in the size-performance curve where shrinking the model causes substantial loss?
4. What are the efficiency gains (memory, latency, throughput, training cost) relative to the teacher, and what does each unit of accuracy cost?
5. Are the differences between models statistically significant?

**Definition of success (pre-registered 2026-09-29):** A student (model size, data size) is a successful specialization if it meets **all four** criteria below. Thresholds were fixed before any student results exist; any later change must be logged in `docs/progress_update.md` with a reason.

1. **Retained accuracy.** Ratio = student accuracy / teacher accuracy on the frozen benchmark. The lower bound of the bootstrap 95% CI of the ratio must reach the tier: **Useful >= 70%**, **Strong >= 85%**, **Near-parity >= 95%**. Accuracy is macro-averaged across benchmark categories, and R code items are graded by execution. Results are reported at all three tiers.
   - *Weak-teacher safeguard:* always report teacher and student absolute accuracies with CIs next to every ratio. A student must also reach an **absolute accuracy floor of 60%** to earn any tier. A teacher below **80%** on the benchmark is a red flag: pause and review benchmark difficulty and teacher choice (using the dev set, not the frozen benchmark) before distillation.
2. **Real gain over own baseline.** Significantly better than the same student untrained (McNemar's test, Holm correction across model pairs).
3. **Usable output.** Minimum share of well-formed, parseable responses and minimum share of R code that runs. Starting value 90% each; confirm in the Phase 3 pilot and log any change before Phase 5 results.
4. **At least 10x cheaper/smaller than the teacher.** Compared on measured inference cost per query and latency (the teacher is API-only, so parameter count and memory are not directly comparable). Also report training GPU-hours, memory, and throughput. The exact measurement protocol is fixed in the pilot. At these student sizes this criterion is a guard more than a differentiator; the accuracy tiers carry the analysis.

**Answer to the primary question:** the smallest (size, data size) pair that reaches each tier. The Phase 12 knee analysis shows where accuracy falls off below it. No general-purpose small-model comparator is used unless an open-weight model matching the Pythia sizes in parameter count and purpose is found.

---

## 2. Experimental Design at a Glance

| Factor | Levels |
|---|---|
| Teacher | Claude Sonnet 5.5 (fallback: Opus 5.5); see `docs/teacher_selection.md` |
| Student size | Pythia 70M, 160M, 410M, 1B (deduped variants, final `step143000` checkpoints; see `docs/model_versions.md`) |
| Distillation set size | 1k, 10k, 50k, 100k, 200k (stretch); **50k is the fallback single size** |
| Verifier | A different frontier model (high-effort ChatGPT model) |
| Benchmark | Frozen held-out set, ~1k statistics/R questions |

**Conditions per student:** untrained baseline plus one fine-tuned model per training-set size. The full grid is 4 sizes x up to 5 data sizes = 20 fine-tuned models, plus 4 baselines and the teacher. If compute is limited, run all 4 sizes at 50k first, then expand the data-size axis.

**Why Pythia:** All Pythia sizes are trained on the same data in the same order and are designed for controlled scaling experiments, so differences between students are attributable to size rather than to training-data differences. This project uses the deduped variants only (all four sizes saw the same globally deduplicated Pile in the same order), never the standard variants.

**Design principles**
- Same benchmark, same training data, same hyperparameter recipe across all student sizes.
- Training sets are nested where possible (the 1k set is a subset of the 10k set, and so on) so data-size effects are not confounded by content.
- Use multiple random seeds per condition if compute allows, so seed variance can be estimated.

---

## 3. Workflow and Checklists

### Phase 1: Define the research question
- [x] Domain: statistics and R programming (final)
- [x] Define "successful specialization": four criteria (retained accuracy tiers, gain over baseline, usable output, >=10x cheaper) (see Section 1)
- [x] Pre-register the success thresholds and primary metrics (see Section 1; dated 2026-09-29)

### Phase 2: Choose teacher and student models
- [x] Teacher: Claude Sonnet 5.5 selected from desk research (Opus 5.5 is the fallback if the Phase 5 teacher accuracy is below 80% or the Phase 7 pass rate is poor); see `docs/teacher_selection.md`
- [x] Students: Pythia 70M, 160M, 410M, 1B (deduped variants only)
- [x] Record exact model checkpoints/revisions used: deduped, final `step143000` checkpoints pinned by commit SHA; see `docs/model_versions.md`

### Phase 3: Pilot at small scale
- [x] Confirm cluster access: Redhawk login works (password + Duo), confirmed 2026-10-01; the `redhawk` command logs in; cluster choice analysis in `docs/cluster_selection.md`
- [ ] Run a few test jobs (environment, GPU allocation, job scheduler)
- [ ] Do a short training run on a tiny dataset to validate the full pipeline end to end
- [ ] Estimate time and cost per training run to plan the full grid

### Phase 4: Create the evaluation benchmark
- [ ] Build a held-out set of about 1k statistics/R questions
- [ ] Cover a balanced mix (see Benchmark Design)
- [ ] **Freeze** the benchmark (hash it, store read-only) before any training
- [ ] Guarantee these exact questions, and near-duplicates, are never used in distillation data

### Phase 5: Measure baseline performance
- [ ] Evaluate each pretrained student before specialization
- [ ] Evaluate the teacher on the same benchmark
- [ ] Record correctness, response validity, runtime, memory use, and other efficiency measures

### Phase 6: Create the distillation training set
- [ ] Generate a large pool of domain-specific prompts/questions
- [ ] Have the teacher generate answers, explanations, and/or R code
- [ ] Deduplicate and decontaminate against the frozen benchmark
- [ ] Use the same verified set for every student size
- [ ] Build nested subsets (1k, 10k, 50k, 100k, 200k as feasible; 50k minimum)

### Phase 7: Verify teacher-generated data
- [ ] Have a different frontier model (high-effort ChatGPT) grade the teacher outputs
- [ ] Objective numerical answers must be verified correct; R code should be improved where needed
- [ ] Execute R code where possible to check that it runs and produces the stated output
- [ ] Score answers, then manually review the ones flagged wrong to understand why (error taxonomy)
- [ ] Fix or drop failing items; record the pass rate and error categories

### Phase 8: Specialize the student models
- [ ] Fine-tune each Pythia student on the verified dataset
- [ ] Keep training procedure consistent across sizes (optimizer, schedule, epochs, sequence length, seeds)
- [ ] Optionally compare training-set sizes

### Phase 9: Re-evaluate specialized students
- [ ] Run the same frozen benchmark
- [ ] Compare each student before vs. after specialization
- [ ] Compare students with each other and with the teacher

### Phase 10: Measure computational efficiency
- [ ] Record parameter count, model file size, RAM/VRAM usage, inference speed, and training cost (GPU-hours)
- [ ] Analyze performance gained or lost as a function of model size and data amount

### Phase 11: Statistical analysis
- [ ] Apply appropriate tests to determine whether differences are significant (see Statistical Analysis)

### Phase 12: Identify the size-performance tradeoff
- [ ] Locate any point where shrinking the model causes substantial performance loss
- [ ] Assess whether very small specialized models retain useful capability relative to the teacher

### Phase 13: Report results
- [ ] Written report: methodology, verification process, statistical analysis, efficiency results
- [ ] Presentation
- [ ] Discussion of practical implications of small specialized models vs. large general-purpose ones

---

## 4. Benchmark Design

- **Size:** about 1,000 questions, held out and frozen.
- **Content mix (proposed):** conceptual statistics, numerical/computational problems with a single correct answer, R code generation, R code interpretation/debugging, and interpretation of statistical output.
- **Difficulty:** span introductory to graduate level, tagged per question so results can be sliced.
- **Ground truth:** numeric and multiple-choice items get exact or tolerance-based auto-grading. R code items are graded by executing the code against test cases where possible. Free-text explanations use rubric or LLM-judge grading, spot-checked by hand.
- **Integrity rules**
  - Freeze before training; store a checksum in `benchmark/`.
  - Never generate teacher data from benchmark prompts or paraphrases.
  - Run n-gram/embedding similarity decontamination between the benchmark and every training set.
  - Do not tune hyperparameters on the benchmark; if tuning is needed, carve out a separate small dev set.

---

## 5. Metrics

**Quality**
- Accuracy / correctness (primary; macro-averaged across categories), broken down by category and difficulty
- Retained fraction of teacher accuracy, using the lower bound of the bootstrap 95% CI, judged against the 70/85/95% tiers (Section 1)
- Response validity (well-formed, parseable, R code that runs)
- Optional: pass@k for code tasks

**Efficiency**
- Parameter count and on-disk model size
- RAM/VRAM at inference
- Inference latency and tokens/second
- Training cost (GPU-hours, wall-clock)
- Derived: accuracy per parameter, accuracy per GPU-hour, retained fraction of teacher accuracy

**Data quality**
- Verifier pass rate and error-type breakdown for teacher-generated data

---

## 6. Statistical Analysis

Planned approach (refine with Dr. Lee's input):
- Paired comparisons on the same benchmark items: **McNemar's test** for binary correctness between two models.
- **Bootstrap confidence intervals** for accuracy and for differences in accuracy.
- Mixed-effects / logistic regression of correctness on model size and data size (with question as a random effect) to model the size-performance relationship.
- Multiple-comparison correction (Holm or Benjamini-Hochberg) across model pairs.
- Seed-to-seed variance where multiple seeds are run.
- Curve fitting (e.g., log-size vs. accuracy) and changepoint/knee analysis to identify the tradeoff point.

---

## 7. Storage Layout

Storage is split in two. **Small, important items live in the project repository** at `C:\dev\masters-project`, the main working copy, which is backed up to the private GitHub repository `jaxsonbugg/masters-project`. **Large items live outside the repository** so they stay out of Git; because they are not backed up, each one must be reproducible from a recovery doc kept in the repository (see Section 12).

### 7.1 Project repository: `C:\dev\masters-project\` (backed up on GitHub)

```
masters-project/
├── README.md
├── recovery/               # one md per item stored outside the repository; _TEMPLATE.md
├── docs/
├── benchmark/
├── data/
│   ├── prompts/
│   └── verification_logs/
├── code/
│   ├── generation/
│   ├── verification/
│   ├── training/
│   ├── evaluation/
│   └── analysis/
├── configs/                # includes paths.yaml
├── environment/
├── results/
└── report/
```

| Folder | Purpose |
|---|---|
| `recovery/` | Rebuild instructions for everything stored outside the repository, one md file per item, written from `_TEMPLATE.md` |
| `docs/` | Notes, advisor meeting notes, decision details, report drafts |
| `benchmark/` | Frozen ~1k question benchmark, its checksum, and grading scripts |
| `data/prompts/` | Generated domain prompts used to query the teacher |
| `data/verification_logs/` | Verifier scores and error analysis of teacher outputs |
| `code/generation/` | Teacher prompting scripts |
| `code/verification/` | Verifier prompting and R code execution |
| `code/training/` | Fine-tuning code |
| `code/evaluation/` | Benchmark runners and metrics |
| `code/analysis/` | Statistics and plots |
| `configs/` | Hyperparameters, cluster job scripts, and `paths.yaml` (defines the large-storage locations; code reads paths from it) |
| `environment/` | Requirements or conda export so the environment can be rebuilt |
| `results/` | Metrics, tables, figures, and small logs |
| `report/` | Final paper and slides |

### 7.2 Outside the repository: `C:\masters_project_large\` (NOT backed up)

```
masters_project_large/
├── WHERE_TO_RECOVER.txt    # points back to recovery/ in the repository
├── models/
│   ├── pythia/
│   └── finetuned/
├── data/
│   ├── teacher_outputs/
│   └── verified/
├── cache/
├── logs/
└── envs/
```

| Folder | Purpose |
|---|---|
| `models/pythia/` | Downloaded base checkpoints (70M, 160M, 410M, 1B deduped, `step143000`), one folder per model; files kept exactly as distributed |
| `models/finetuned/` | Specialized student checkpoints, by size and data size |
| `data/teacher_outputs/` | Raw teacher generations |
| `data/verified/` | Verified training sets (1k to 200k) |
| `cache/` | Hugging Face and pip caches |
| `logs/` | Large raw training and evaluation logs |
| `envs/` | Python virtual environment(s) |

Adjust as the project evolves.

---

## 8. Proposed Timeline (two semesters)

| Period | Focus |
|---|---|
| Semester 1, early | Finalize design, choose teacher, cluster access, Phase 3 pilot |
| Semester 1, mid | Build and freeze benchmark; baselines for students and teacher |
| Semester 1, late | Generate and verify distillation data (50k first) |
| Semester 2, early | Fine-tune all students; re-evaluate; expand data-size axis if feasible |
| Semester 2, mid | Efficiency measurements, statistical analysis, tradeoff analysis |
| Semester 2, late | Report and presentation |

Dates are placeholders; replace with real deadlines from the program.

---

## 9. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Cluster access or queue times limit training runs | Pilot early; prioritize the 50k run across all four sizes; expand only if time allows |
| Teacher API cost for 200k examples | Estimate token cost in the pilot; cap the largest set if needed |
| Pythia models are base (not instruction-tuned) and have a 2048-token context | Use a consistent prompt/answer format in fine-tuning; keep teacher responses within length limits |
| Very small models may score near zero, hiding differences | Include easier items and partial-credit / validity metrics |
| Benchmark contamination | Strict decontamination, checksum freeze, separate dev set |
| Verifier (ChatGPT) errors or shared blind spots with the teacher | Execute R code, spot-check by hand, review flagged disagreements manually |
| Teacher-as-judge bias | Benchmark grading uses objective answers and code execution wherever possible |
| Confounded comparisons across sizes | Identical recipe, data, seeds, and evaluation for all students |

---

## 10. Open Decisions

- [ ] Exact question-format mix and difficulty distribution of the benchmark
- [ ] Grading method for free-text answers
- [ ] Which ChatGPT model and reasoning effort to use as verifier
- [ ] Fine-tuning approach: full fine-tune vs. LoRA (full fine-tune is cleaner for small models)
- [ ] Number of seeds per condition
- [ ] Exact validity thresholds (default 90% well-formed and 90% R code runs), to be confirmed in the pilot
- [ ] Efficiency measurement protocol for the 10x criterion (cost per query, latency), to be set in the pilot
- [ ] Which data sizes to run beyond 50k, based on pilot cost estimates
- [ ] Cluster specifics (scheduler, GPU type, allocation limits)
- [ ] Talon (H100 GPUs) access request, as the fallback for the 1B student if the pilot memory measurement shows Redhawk's 16 GB V100s are too small
- [ ] Pilot measurement of actual peak GPU memory for all four sizes, to decide how to train 1B (sharding, gradient checkpointing, 8-bit optimizer, LoRA, or a larger GPU)
- [ ] Cluster policy: outbound internet from login/compute nodes, home and scratch quotas, available Python/PyTorch/CUDA modules (ask rescomp@miamioh.edu; see `docs/model_versions.md`)
- [ ] Phase 8 training precision recipe (AMP/mixed precision, gradient and optimizer-state precision, BF16 or FP16), to be decided and documented once the GPU environment is known

---

## 11. Progress Updates

The dated history of all project changes and decisions lives in `docs/progress_update.md`, not here, to keep this README short. See Section 12 for the rule on keeping it current.

---

## 12. Working Notes for Claude

- Treat this README as the source of truth for project scope; update the checklists when work is completed or decisions change.
- **Progress log:** every change added to the project (decisions, completed steps, new or moved files, threshold or plan changes, deviations) must be recorded in `docs/progress_update.md` with the date and information about what was done and why. Add the entry in the same session as the change. Do not keep change history in this README.
- **Dated outputs:** every batch of teacher outputs (generation, verification, or re-generation) must be recorded with the UTC date and time it was generated, the exact API model ID, effort level, thinking mode, temperature/sampling settings, and the file(s) it produced. Put the date in the output file or folder name (for example `teacher_outputs/2026-10-15_sonnet-5-5_batch01/`) and also in the log entry. Never overwrite a dated batch; start a new dated one. The same applies to verifier runs, with the verifier model name and settings recorded.
- **Current Pythia labels only:** use the current names 70M, 160M, 410M, 1B. Never use the old names (19M, 125M, 350M, 800M) for the students, except in the table below or in a quotation of an old source. Repo ids always end in `-deduped`.

  | Use (current) | Never use (old) |
  |---|---|
  | 70M | 19M |
  | 160M | 125M |
  | 410M | 350M |
  | 1B | 800M |
- **Model precision:** keep three things separate: (1) checkpoint storage dtype, how the original files are serialized, observed and never changed; (2) runtime load dtype, `torch.float16` for all four students, passed explicitly in every load call and not taken from `config.json`; (3) training precision recipe, decided in Phase 8. Rule: preserve the original pinned checkpoints exactly as distributed; standardize all four student models to FP16 model weights when loaded for baseline experiments; verify the actual loaded dtype and parameter count; and document the final mixed-precision training recipe separately once the training environment is finalized.
- Never use benchmark questions in any training, prompting, or tuning step.
- Keep procedures identical across student sizes unless a deviation is logged.
- Log all model versions, seeds, hyperparameters, and job IDs in `results/` so runs are reproducible.
- Flag any deviation from the plan or any surprising result rather than silently working around it.
- **Recovery docs:** any step or artifact stored outside the repository (models, datasets, caches, environments, large logs) must have an md file in `recovery/` that says how to recreate it if it is lost or removed. Write it from `recovery/_TEMPLATE.md` when the step is done, and update it if the procedure changes. Include the source, exact commands, versions, seeds, expected size and checksum, and what to do if it is lost. Do not create these docs before the corresponding step exists.
- Teacher outputs cost API money and are not deterministic, so their recovery doc should note this and suggest keeping a compressed backup of the verified 50k set.
- Read all storage locations from `configs/paths.yaml`; never hardcode paths in code.
- **Git:** commit every change with a clear message and push it to GitHub. Never commit secrets or API keys, model weights, or anything from `C:\masters_project_large\`. Command notes are in `docs/github_notes.md`.
