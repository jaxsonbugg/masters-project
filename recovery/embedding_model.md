# Recovery: sentence-embedding model for decontamination (all-MiniLM-L6-v2)

**What it is:** The small sentence-embedding model that `code/verification/decontaminate.py` uses to turn each question into 384 numbers summarizing its meaning, so reworded copies of benchmark or development questions can be found (`docs/methodology/workflow.md` Section 4, safeguard 5). It is never trained and never part of the students.
**Location:** `models_embedding` in `configs/paths.yaml`: `C:\masters_project_large\models\embeddings\all-MiniLM-L6-v2\1110a243fdf4706b3f48f1d95db1a4f5529b4d41`
**Approx. size:** 91.6 MB (90.9 MB of weights plus small configuration and tokenizer files)
**Backed up?** No. It is a public model and is downloaded again in a minute.

## How to rebuild
1. With the project environment's Python (`recovery/python_env.md`), download the pinned commit only, never `main`:
   ```
   C:\masters_project_large\envs\probe\Scripts\python.exe -c "from huggingface_hub import hf_hub_download; rev='1110a243fdf4706b3f48f1d95db1a4f5529b4d41'; [hf_hub_download('sentence-transformers/all-MiniLM-L6-v2', f, revision=rev, local_dir=r'C:\masters_project_large\models\embeddings\all-MiniLM-L6-v2\1110a243fdf4706b3f48f1d95db1a4f5529b4d41') for f in ['config.json','tokenizer.json','tokenizer_config.json','vocab.txt','special_tokens_map.json','model.safetensors','sentence_bert_config.json','modules.json','1_Pooling/config.json','config_sentence_transformers.json']]"
   ```
2. Check the hashes below.
3. Re-run the verification (below) if the project environment's `transformers` or `torch` version changed since 2026-11-20.

## Versions, seeds, and settings
- Source: Hugging Face `sentence-transformers/all-MiniLM-L6-v2`, commit `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` (the `main` commit on 2026-11-20).
- How it is run (the model card's own configuration, read from `modules.json`, `1_Pooling/config.json` and `sentence_bert_config.json`): text cut at 256 word pieces; mean pooling over the attention mask; L2 normalization; float32 on the CPU. Implemented in `decontaminate.Embedder` with `transformers` 5.19.0 and `torch` 2.14.1+cpu (the project environment); `sentence-transformers` itself is NOT installed in the project environment.
- No random seeds (inference only, deterministic).

## Verification
- Expected SHA-256 values (computed 2026-11-20; the weights value equals Hugging Face's own listing):
  - `model.safetensors` `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db` (90,868,376 bytes)
  - `tokenizer.json` `be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037`
  - `vocab.txt` `07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3`
  - `config.json` `953f9c0d463486b10a6871cc2fd59f223b2c70184f49815e7efbcab5d8908b41`
  - `modules.json` `84e40c8e006c9b1d6c122e02cba9b02458120b5fb0c87b746c41e0207cf642cf`
  - `1_Pooling/config.json` `4be450dde3b0273bb9787637cfbd28fe04a7ba6ab9d36ac48e92b11e350ffc23`
  - `sentence_bert_config.json` `fc1993fde0a95c24ec6c022539d41cf6e2f7c9721e5415d6fb6897472a9cd4b7`
- **Our implementation matches the reference** (`code/verification/embedding_check.py`, 2026-11-20). In a throwaway virtual environment (sentence-transformers 6.3.0, torch 2.15.0+cpu, transformers 5.23.0; deleted afterwards), the official package embedded 100 sample texts; our code embedded the same texts in the project environment. Lowest cosine 0.99999988 (required at least 0.9999), largest difference in any number 9e-8; 4 of the 100 texts were longer than 256 word pieces and were cut the same way. The record is in `data/verification_logs/2026-11-20_embedding_check/`.
  To repeat it: `python embedding_check.py texts --out t.json`; in a new throwaway environment (`py -3.11 -m venv X; X\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cpu; X\Scripts\pip install sentence-transformers`) run `X\Scripts\python embedding_check.py reference --texts t.json --model-folder <folder> --out ref.npy`; then `python embedding_check.py verify --texts t.json --reference ref.npy`; delete X.
- **CPU speed** (`embedding_check.py bench`, 2026-11-20, this PC, 14 threads): 38.7 texts per second on 5,000 training-like texts (some longer than 256 word pieces), peak memory 867 MB; about 112 minutes projected for 260,000 texts, and 381 MB of vectors. No GPU job is needed.

## If it is lost
Download it again (step 1) and check the hashes: about a minute, no cost. If Hugging Face removed the repository, the commit id and hashes above identify the exact files to look for in a mirror; any other model or revision would change every similarity score, so the decontamination thresholds would have to be calibrated again.

## Last updated
2026-11-20
