# Embedding check, 2026-11-20

**What this is.** The check that the project's embedding code (`code/verification/decontaminate.py`, class `Embedder`) gives the same vectors as the official `sentence-transformers` package for the pinned model `sentence-transformers/all-MiniLM-L6-v2` @ `1110a243...`, and how fast it runs on the PC's CPU. Decontamination uses these vectors to find reworded copies of benchmark and development questions, so a wrong implementation would shift every similarity score. Method: `code/verification/embedding_check.py`; model: `recovery/embedding_model.md`.

**Files.**
- `verify_texts.json`: the 100 sample texts, built deterministically from the taxonomy and the context deck; 4 of them are longer than the model's 256-word-piece limit.
- `reference_environment.json`: the throwaway environment that produced the reference vectors (sentence-transformers 6.3.0; modules Transformer, Pooling, Normalize; maximum length 256). The environment was deleted afterwards.
- `verify_result.json`: the comparison. Lowest cosine 0.99999988 (the requirement was at least 0.9999), largest difference in any number 9e-8. **PASS.**
- `cpu_benchmark.json`: 5,000 training-like texts, 38.7 texts per second on 14 CPU threads, peak memory 867 MB; about 112 minutes projected for 260,000 texts. No GPU job is needed.

**What it does not show.** That the model's similarity scores separate copies from distinct problems. That is measured separately, with hand-labeled pairs from development data (`docs/guides/decontamination_labeling_guide.md`).
