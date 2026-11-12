# Model Versions

Exact model versions used in the project. Written 2026-10-01; teacher and cluster sections rewritten 2026-11-07 for the Qwen3.6-27B teacher. Pythia facts come from the linked sources, accessed 2026-09-30 and 2026-10-01 (the date each file was downloaded and hash-checked is in the table below).

## Reproducibility rule

> Preserve the original pinned checkpoints exactly as distributed; standardize all four student models to FP16 model weights when loaded for baseline experiments; verify the actual loaded dtype and parameter count; and document the final mixed-precision training recipe separately once the training environment is finalized.

## 1. Students: Pythia deduped, final `step143000` checkpoint

All four students are the **deduped** variants (trained on the globally deduplicated Pile). The standard variants (repo ids without `-deduped`) are not used anywhere. Each is pinned to the commit SHA of the `step143000` branch, not to `main`.

| Size | Repo ID | Pinned revision | Commit SHA | Official total params | License | Date retrieved |
|---|---|---|---|---|---|---|
| 70M | [EleutherAI/pythia-70m-deduped](https://huggingface.co/EleutherAI/pythia-70m-deduped) | `step143000` | `9a7c847e93250c8f24d4b7e7134dbf369e8fc9cb` | 70,426,624 | Apache-2.0 | 2026-10-01 |
| 160M | [EleutherAI/pythia-160m-deduped](https://huggingface.co/EleutherAI/pythia-160m-deduped) | `step143000` | `c54a0e0b28cc667b6f278803024438d57f847b5d` | 162,322,944 | Apache-2.0 | 2026-10-01 |
| 410M | [EleutherAI/pythia-410m-deduped](https://huggingface.co/EleutherAI/pythia-410m-deduped) | `step143000` | `c66f7467608ffee8fca0d28cf1f46a7574b53cec` | 405,334,016 | Apache-2.0 | 2026-10-01 |
| 1B | [EleutherAI/pythia-1b-deduped](https://huggingface.co/EleutherAI/pythia-1b-deduped) | `step143000` | `d1988145ec1cf1e76d786cd05af9f53e8b1c95cc` | 1,011,781,632 | Apache-2.0 | 2026-10-01 |

Sources:
- Commit SHAs: `https://huggingface.co/api/models/EleutherAI/pythia-<size>-deduped/refs` (branch `step143000`), read 2026-09-30.
- Parameter counts and architecture: the "Naming convention and parameter count" table on each model card, for example the [160M card](https://huggingface.co/EleutherAI/pythia-160m-deduped).
- License: the model cards and the Hugging Face API tags (`apache-2.0`).
- Training setup (Pile deduplicated, 143,000 steps, 2,097,152-token batches, 154 checkpoints): [Pythia GitHub README](https://github.com/EleutherAI/pythia) and the paper, [arXiv 2304.01373](https://arxiv.org/abs/2304.01373).

Architecture (same sources):

| Size | Layers | Model dim | Heads | Non-embedding params |
|---|---|---|---|---|
| 70M | 6 | 512 | 8 | 18,915,328 |
| 160M | 12 | 768 | 12 | 85,056,000 |
| 410M | 24 | 1024 | 16 | 302,311,424 |
| 1B | 16 | 2048 | 8 | 805,736,448 |

**Context length: 2,048 tokens for all four sizes.** `max_position_embeddings` is 2048 in each pinned `step143000/config.json` (read 2026-11-11 from the local copies). The model has learned positions only up to 2,048 tokens, so this is a **hard limit** for training and evaluation:
- **Training:** every example (prompt, working, `Final answer:` line and end token) must fit. An over-length example is rejected or deliberately shortened, never silently truncated.
- **Evaluation:** the prompt plus the maximum number of new tokens must stay within 2,048 (`docs/methodology/workflow.md` Phase 4).
(The 2048 in the 1B row above is a different number: the 1B model's hidden size.)

Notes:
- The Hugging Face API reports the 1B repo as 1,011,782,144 F16 plus 67,108,864 U8 entries. This differs by 512 from the model card's 1,011,781,632. The cause is not known; the model card number is used as the official count and the difference is to be checked when the models are loaded.
- The model cards for 70M and 1B say "branch `143000`", which appears to be a typo for `step143000`.

## 2. Why the `step143000` commit and not `main`

For every size the `main` and `step143000` commit SHAs differ. EleutherAI states that `step143000` corresponds exactly to the final model checkpoint on `main` ([Pythia README](https://github.com/EleutherAI/pythia) and the model cards), but the later differences between the branch SHAs have not yet been fully inspected; therefore the pinned `step143000` SHA is used for reproducibility. The files below were downloaded with the `step143000` SHA in the URL.

| Size | `main` SHA at retrieval (not used) |
|---|---|
| 70M | `e93a9faa9c77e5d09219f6c868bfc7a1bd65593c` |
| 160M | `582159a2dfe3e712a8d47ae83dec95ae3bde8e7e` |
| 410M | `c4fc8d586d62df497f1f9b69d66d3ca419992d3e` |
| 1B | `7199d8fc61a6d565cd1f3c62bf11525b563e13b2` |

Open check: inspect the commit history between `step143000` and `main` on each repo's Hugging Face page and record what changed.

## 3. Precision and dtype

Three separate concepts. Never merge them in docs, configs or code comments.

| Concept | Meaning | Status |
|---|---|---|
| 1. Checkpoint storage dtype | How the original Hugging Face weights are serialized on disk | Observed, not chosen. Files are kept exactly as downloaded: no conversion, no re-saving, no modification |
| 2. Runtime load dtype | The dtype weights are loaded into for baseline evaluation | `torch.float16` for all four sizes, passed explicitly in every load call. Not taken from `config.json` |
| 3. Training precision configuration | AMP/mixed precision, gradient precision, optimizer-state precision, loss scaling, BF16 or FP16 | **Decided 2026-11-11, for all sizes:** load the model in **float32** for training and use BF16 mixed precision (`bf16=True` in the Hugging Face `Trainer`). Master weights, gradients and AdamW states stay float32; matrix math runs in BF16 under autocast; no loss scaling (BF16 does not need it). Loading in float16 and then using `bf16=True` would keep weights, gradients and optimizer states in float16, which is not real mixed precision. Runs on the Talon H100s (BF16 is supported); the Redhawk V100s lack BF16, so a fallback run there would need FP16 with loss scaling, a logged deviation |

Fine-tuning is **not** described as "pure FP16 training". Only the loading of model weights in FP16 is decided.

### Per-model precision record

| Size | Checkpoint storage dtype / observed serialized dtype | Experimental runtime load dtype | `config.json` `torch_dtype` (metadata only) |
|---|---|---|---|
| 70M | **F32** for all 76 tensors (read from the safetensors header 2026-10-06). `model.safetensors` is 281,715,176 bytes | `torch.float16` (verified loaded: only `torch.float16`) | float16 |
| 160M | **F32** for all 148 tensors. 649,308,728 bytes | `torch.float16` (verified) | float16 |
| 410M | **F32** for all 292 tensors. 1,621,370,224 bytes | `torch.float16` (verified) | float16 |
| 1B | **F16** for all 196 tensors. 2,023,586,192 bytes. (EleutherAI says the 1B was trained in bf16 because of a loss spike in fp16.) | `torch.float16` (verified) | float16 |

Cautions:
- The file-size observation is only an approximate consistency check (official parameters x 4 or x 2, plus a small header). It is not proof of the stored dtype of every tensor, and it says nothing about the dtype used after loading. The direct read of the tensor dtypes from each safetensors header was done on 2026-10-06 (status paragraph below); the dtypes in the table above come from that read, not from the file sizes.
- Repository size, checkpoint size, config metadata, buffers and other non-parameter tensors, and duplicate serialization formats (the repos also hold `pytorch_model.bin`, which was not downloaded, and the 1B repo also holds a 12.2 GB `optimizer.pt`, not downloaded) are separate from the dtype used after loading.
- All four `config.json` files say `float16`, while the 70M, 160M and 410M safetensors files are approximately 4 bytes per official parameter. The `torch_dtype` metadata does not by itself establish the dtype of every tensor stored in the checkpoint file. The experiment does not rely on it and sets the dtype itself.
- V100 GPUs (Redhawk) have no native BF16 support and H100 GPUs (Talon) do. This is noted as a hardware fact only; no training-precision choice is made here.

### Load and dtype verification (to do once Python and the libraries are installed)

For each of the four sizes, in order:
1. Load from the pinned local folder (or the Hub repo with `revision=<commit SHA>`), explicitly passing `torch_dtype=torch.float16`.
2. Count parameters and compare with the official total in section 1. Record any difference instead of ignoring it.
3. Verify the in-memory dtype: `{p.dtype for p in model.parameters()}` equals `{torch.float16}`.
4. Confirm that all four baseline models report `torch.float16`.
5. Record any exception or mismatch here and stop. Do not silently coerce the dtype or ignore the error.
6. Read the tensor dtypes from each safetensors header (concept 1) and record them in the table above.
7. Re-run the SHA-256 check to confirm the files are unchanged.
8. Fill in the environment table below.

Status (updated 2026-10-06): steps 1 to 6 are done for all four sizes by `code/evaluation/pythia_probe.py` on this PC's CPU (results in `results/pythia_probe/2026-10-07_0015Z_probe_model_info.json`). Parameter counts match the official counts exactly (difference 0 for all four, including the 1B, so the 512-value gap in the Hugging Face API listing does not show up in the loaded model). Every loaded parameter is `torch.float16`. The stored tensor dtypes are in the table above (F32 for 70M, 160M, 410M; F16 for 1B). No errors loading in `float16` on CPU. Step 7 (re-hashing the files) and the Redhawk-side check are not done. Python 3.11.9 is at `C:\Users\Buggb\AppData\Local\Programs\Python\Python311\`; the probe runs in the venv `C:\masters_project_large\envs\probe` (recipe: `recovery/python_env.md`). This PC has no NVIDIA GPU.

**Found by the probe: the 1B stop token is misconfigured.** In the shared vocabulary id 0 is `<|endoftext|>` and id 2 is `!`. The 70M, 160M and 410M configs say `eos_token_id: 0` and their tokenizers define `<|endoftext|>` as the end token. The **1B config says `eos_token_id: 2` (`!`)** and its tokenizer defines no end token (`eos_token` is `None`). Rule: set the end-of-text id explicitly to 0 (found by name `<|endoftext|>`) in all training and evaluation code and assert it, for all four sizes. See `docs/models/pythia_behavior_analysis.md` section 3.2.

## 4. Files and hashes

Local location: `C:\masters_project_large\models\pythia\pythia-<size>-deduped\step143000\` (outside the repository, not backed up; see `recovery/pythia_base_models.md`). Downloaded 2026-10-01 from `https://huggingface.co/EleutherAI/pythia-<size>-deduped/resolve/<commit SHA>/<file>`. The `model.safetensors` SHA-256 values below equal the Hugging Face file listing (`https://huggingface.co/api/models/EleutherAI/pythia-<size>-deduped/tree/step143000`) for every size, and the byte counts match. The other files have no published hash; the values below are computed locally.

### 70M (`9a7c847e93250c8f24d4b7e7134dbf369e8fc9cb`)
| File | Bytes | SHA-256 |
|---|---|---|
| model.safetensors | 281,715,176 | `9d70830dfb5bc582679707fafd5e998651498b57d033371a274685c96e526d64` |
| config.json | 567 | `002050231a9b1ec3ac77aa6b9b3bbdc4d923f4068a7dd33b8da72a9bd6ad9a43` |
| tokenizer.json | 2,113,710 | `c24618a1b3e6a38167beff1c72cffd126c3a66254347304b50547d12c5f25624` |
| tokenizer_config.json | 396 | `70e38394e494931c6f773ba41e19460dd4436526b852207367f04341b4066d3f` |
| special_tokens_map.json | 99 | `6f50ab5a5a509a1c309d6171f339b196a900dc9c99ad0408ff23bb615fdae7ad` |

### 160M (`c54a0e0b28cc667b6f278803024438d57f847b5d`)
| File | Bytes | SHA-256 |
|---|---|---|
| model.safetensors | 649,308,728 | `38efddf97ab820b9483302e2e4c104f794cef518a291b249e2be1d26e2ae50c9` |
| config.json | 569 | `76eb275107220e450d31258f792a2efcbee109d8b62ae0088260057dec06362f` |
| tokenizer.json | 2,113,710 | `c24618a1b3e6a38167beff1c72cffd126c3a66254347304b50547d12c5f25624` |
| tokenizer_config.json | 396 | `70e38394e494931c6f773ba41e19460dd4436526b852207367f04341b4066d3f` |
| special_tokens_map.json | 99 | `6f50ab5a5a509a1c309d6171f339b196a900dc9c99ad0408ff23bb615fdae7ad` |

### 410M (`c66f7467608ffee8fca0d28cf1f46a7574b53cec`)
| File | Bytes | SHA-256 |
|---|---|---|
| model.safetensors | 1,621,370,224 | `e5130ca26aa649f69035269bfb00a25afc4704d11ff4385ae368e6eed4ad530a` |
| config.json | 570 | `d4c11e84a59c8af4d88446bba53b718f7aef740daa070ded08fd6a9a3aca4fc6` |
| tokenizer.json | 2,113,710 | `c24618a1b3e6a38167beff1c72cffd126c3a66254347304b50547d12c5f25624` |
| tokenizer_config.json | 396 | `70e38394e494931c6f773ba41e19460dd4436526b852207367f04341b4066d3f` |
| special_tokens_map.json | 99 | `6f50ab5a5a509a1c309d6171f339b196a900dc9c99ad0408ff23bb615fdae7ad` |

### 1B (`d1988145ec1cf1e76d786cd05af9f53e8b1c95cc`)
| File | Bytes | SHA-256 |
|---|---|---|
| model.safetensors | 2,023,586,192 | `3e51dc49d75de37ec6674b4a01cd0b45d058917c6eb82c610a68d09b05b90755` |
| config.json | 677 | `5f273a0b89f10727f638fe3134c6f718a9b6a991569453a9446e898c40bb6312` |
| generation_config.json | 111 | `0c6190f4b464ae6d6062068bb719baf8fff2bedc261c09852b86a3c85630b8b3` |
| tokenizer.json | 2,113,738 | `3cf430678137c8491ca82fb7092ee49e44ad38857fffe1e4a4a5ed860139a5b8` |
| tokenizer_config.json | 4,643 | `84f28e3ab5abb48724a3e678ad5de5f6f920b4948dc01814503bd34b00823e3c` |
| special_tokens_map.json | 3 | `ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356` |

### Tokenizer: open check
The 70M, 160M and 410M tokenizer files are byte-identical (same hashes). The 1B tokenizer files (`tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`) differ from the smaller models at the file level, and the 1B `config.json` has a different `eos_token_id` (2, versus 0 in the 70M config) and extra fields. **Tested 2026-10-06:** eight test strings (plain text, a p-value sentence, three R snippets, numbers, the `<|endoftext|>` string, whitespace and a tab) encode to **identical token ids for all four sizes, including 1B**, and `<|endoftext|>` is the single id 0 in all of them. The 1B differences that remain are in the configuration: no defined end/pad/bos tokens in the tokenizer, `eos_token_id: 2` in the config (see section 3), and a `clean_up_tokenization_spaces=True` setting that the library warns is destructive for this tokenizer type and ignores. Still to check once, when the evaluation code is written: that decoded 1B text matches the others for text with spaces before punctuation.

## 5. Environment versions

Filled in 2026-10-06 from the local probe environment (`C:\masters_project_large\envs\probe`; exact pins in `environment/requirements.txt`, rebuild steps in `recovery/python_env.md`).

| Component | Version |
|---|---|
| Python | 3.11.9 on this PC. Clusters (checked by read-only probes, no training environment built yet): Redhawk `/software/python/anaconda3-2023-python3.10/bin/python` = 3.10.9; Talon system Python 3.9, plus module `miniforge3-python3.12` = 3.12.5 |
| PyTorch | 2.14.1+cpu (CPU build, local only) |
| Transformers | 5.19.0 |
| safetensors | 0.8.0 |
| tokenizers | 0.23.2 |
| Hugging Face Hub | 1.33.0 (installed as a dependency; the model files were downloaded with `curl`, not this library) |
| CUDA | none locally. Redhawk has the module `cuda-12.2` (used to build llama.cpp). The Talon CUDA version is not recorded here yet. The training environment on Talon (primary) or Redhawk (fallback) will need a CUDA build of PyTorch and its own record |

## 6. Teacher: Qwen3.6-27B

**What and why.** The teacher is Qwen3.6-27B, an open-weight reasoning model with about 27 billion parameters, released under the Apache 2.0 license, which allows training other models on its outputs. It was decided on 2026-11-06, after Anthropic confirmed that Claude outputs may not be used to train the students; the earlier Claude teacher is archived (`docs/methodology/workflow.md` Section 2.2). Because the weights are public, we download them and run the model on Miami's GPUs, so every part of the setup can be pinned: the exact weight files, the program that runs them, the chat template and the sampling settings. If one of these changes, the teacher's outputs can change, so each is recorded below and any change is logged in `docs/progress_update.md`.

**Two deployments.** *Talon (primary)* runs the full BF16 weights. BF16 is a 16-bit number format, about 2 bytes per parameter, so the model runs as released, without compression. *Redhawk (fallback)* runs a 4-bit compressed copy (a GGUF file, the format used by the llama.cpp engine), which stores roughly half a byte per parameter so the model fits on two 16 GB V100 GPUs. Worked example of the size difference: the BF16 weights are about 53,011 MiB (55.6 GB), while the 4-bit file is 16,817,244,384 bytes (16.8 GB), about 30% of the size. Compression can cost some accuracy, which is why a 4-bit vs BF16 comparison is planned, both on Talon so the hardware is the same (the Talon 4-bit backend is not built yet; `docs/methodology/workflow.md` Section 2.1).

### Talon (primary): BF16 weights served by vLLM

| Item | Value |
|---|---|
| Repository | [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) |
| Pinned revision (commit SHA) | `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9` |
| Weights | 29 files, about 53,011 MiB in total (read 2026-11-06; the download step records the real total) |
| Engine | vLLM, the program that loads the model onto the GPUs and answers requests. **Version to be pinned**; the model card requires vLLM 0.19.0 or later |
| Python for the engine | module `miniforge3-python3.12` (Python 3.12.5); Talon's system Python 3.9 is too old for vLLM |
| Settings file | `configs/talon/talon_settings.sh`, explained in `docs/clusters/talon_setup.md` |

### Redhawk (fallback): 4-bit GGUF served by llama.cpp

| Item | Value |
|---|---|
| Engine | llama.cpp tag `b11960`, which must resolve to commit `8642541b255bfb5dc39cd351a178be09013a55d6` |
| Weights repository | `unsloth/Qwen3.6-27B-GGUF` at revision `82d411acf4a06cfb8d9b073a5211bf410bfc29bf` |
| File | `Qwen3.6-27B-Q4_K_M.gguf`, 16,817,244,384 bytes |
| File SHA-256 | `5ed60d0af4650a854b1755bd392f9aef4872643dc25a254bc68043fa638392a0` |
| Chat template | Qwen's own `chat_template.jinja` from `Qwen/Qwen3.6-27B` at revision `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9` (the same commit as the Talon weights), so the template does not come from the third-party GGUF file. Its SHA-256 is computed at download and stored next to the model on the cluster (`chat_template.sha256`) |
| Pins file | `configs/redhawk/common.sh` |

A **chat template** is the small text recipe that turns a list of messages (system prompt, user question) into the exact token sequence the model was trained to read, including the markers that start and end its thinking. A wrong template can quietly change the answers, which is why it is pinned to Qwen's own repository.

### Sampling and limits (identical on both clusters)

These are the model card's recommended settings for thinking mode. *Temperature* 1.0 keeps the model's own word probabilities unchanged; *top_p* 0.95 means it picks only from the most likely words that together make up 95% of the probability; *top_k* 20 limits that to at most the 20 most likely words; *min_p* 0 and *presence penalty* 0 switch two further filters off.

| Setting | Value |
|---|---|
| temperature | 1.0 |
| top_p | 0.95 |
| top_k | 20 |
| min_p | 0 |
| presence_penalty | 0 |
| Maximum output per call | 16,384 tokens, thinking included |
| Context per sequence | 20,480 tokens (a comparison setting, not the model's maximum; `docs/clusters/talon_setup.md` Section 7) |
| Benchmark prompt | `data/prompts/benchmark_generation_v6.md`, SHA-256 `348db6ff84da29d22b2fcdeec9c13191df9d828b6af64b61146f2794b1888cc4` |

Worked example of the limits: if Qwen thinks for 9,000 tokens and then writes a 600-token answer, the call used 9,600 of its 16,384 output tokens; a reply that needs more than 16,384 tokens of thinking plus answer is cut off and cannot be used. Because sampling at temperature 1.0 is random, rerunning the same slot gives a different question; that is why teacher outputs are never overwritten.

**Fallback if the teacher underperforms.** If teacher accuracy on the benchmark is below 80%, or the Phase 7 pass rate is poor, the first step is the same Qwen model at a higher precision or with more thinking, not a different model (`docs/methodology/workflow.md` Section 2.1).

**Recording rule.** Every batch of teacher outputs is recorded with the UTC date and time generated, the cluster and job ID, the model repository and revision, the weight format (BF16 or the 4-bit file), the engine and its version, the chat template, the sampling settings, the prompt file and its SHA-256, and the files produced. Put the date in the file or folder name. Never overwrite a dated batch. Cluster jobs and their GPU time go in `docs/logs/compute_log.md`; storage locations are in `docs/methodology/workflow.md` Section 8.

## 7. Cluster notes (public documentation checked 2026-10-01; read-only probes 2026-11-04 on Redhawk and 2026-11-06 on Talon)

This section only records the facts that matter for the model versions above. The full cluster facts, with how each was observed, are in `docs/clusters/cluster_selection.md` (Redhawk, and why each cluster is used) and `docs/clusters/talon_setup.md` (Talon). Every cluster job is recorded in `docs/logs/compute_log.md`.

Public sources: [Redhawk cluster page](https://www.miamioh.edu/research/research-computing-support/services/hpc-cluster), [Slurm](https://miamioh.edu/research-innovation/research-computing-support/slurm-resource-manager.html), [batch usage](https://miamioh.edu/research-innovation/research-computing-support/batch-cluster-usage.html), [interactive usage](https://miamioh.edu/research-innovation/research-computing-support/interactive-cluster-usage.html), [Talon news](https://miamioh.edu/news/2026/06/new-talon-cluster-a-major-leap-forward-in-accelerated-computing-ai-technology-infrastructure-at-miami.html), [resource overview](https://miamioh.teamdynamix.com/TDClient/1813/Portal/KB/ArticleDet?ID=169669).

- **Which cluster.** Talon is the primary cluster for teacher generation, fine-tuning and evaluation; Redhawk is the fallback. Both are free to use; their cost is GPU time and queue waits.
- **Talon:** Slurm partition `talon`; 4 nodes, each with 4 NVIDIA H100 NVL GPUs, 64 CPU cores and 515 GB of RAM. Nodes are shared between jobs, so a job asks for GPUs rather than a whole node. Jobs may run at most 3 days. Slurm accounting is off, so the scheduler keeps no job history (numbers come from the jobs' own logs). System Python is 3.9; module `miniforge3-python3.12` gives Python 3.12.5. The login node reaches Hugging Face and PyPI through the university proxy. The account is active and was probed read-only on 2026-11-06.
- **Redhawk:** Slurm partition `gpu` with 4 V100 nodes (`mualhpcp38` to `mualhpcp41`), each with 2 NVIDIA V100 16 GB GPUs. There is no per-GPU request, so a job takes a whole node with `--exclusive`. Jobs may run at most 3 days; accounting is off. Python `/software/python/anaconda3-2023-python3.10/bin/python` is 3.10.9; the modules used are `cuda-12.2`, `gcc-12.2.0` and `cmake-3.31.2`. The public pages also list partitions `batch` and `bigmem`, about 120 TB of shared storage, and a rule that login nodes should not be used for work over 1 hour of CPU time or 10 GB of memory.
- **Storage.** Redhawk and Talon share one home folder, `/home/buggjm`, with a 500 GB hard and 480 GB soft quota (about 17 GB used on 2026-11-06). The two clusters work in separate subfolders (`docs/methodology/workflow.md` Section 8).
- **Precision hardware fact.** V100 GPUs (Redhawk) have no native BF16 support and H100 GPUs (Talon) do. Together with memory (about 53,011 MiB of BF16 weights cannot fit in a Redhawk node's 2 x 16 GB), this is why the BF16 teacher runs on Talon and Redhawk uses the 4-bit file.
- **Student sizes against GPU memory.** The four Pythia checkpoints total about 4.6 GB for the downloaded safetensors, small against the home quota. FP16 weights are about 0.14, 0.32, 0.81 and 2.02 GB for 70M, 160M, 410M and 1B, so baseline evaluation fits even in one 16 GB V100. The planned approach does not need internet on the compute nodes: model files are downloaded on a login node or copied from this PC with `scp`, then re-checked with `sha256sum`.
- Training memory depends on the training precision recipe (concept 3). With float32 weights and AdamW, that is roughly 16 bytes per parameter before activations, about 1.1 GB for 70M and about 16 GB for 1B. This is an estimate; the pilot measures peak memory.
