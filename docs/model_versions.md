# Model Versions

Exact model versions used in the project. Written 2026-10-01. Facts come from the linked sources, accessed 2026-09-30 and 2026-10-01 (the date each file was downloaded and hash-checked is in the table below).

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
| 3. Training precision configuration | AMP/mixed precision, gradient precision, optimizer-state precision, loss scaling, BF16 or FP16 | Not decided. Set and documented separately in Phase 8, once the cluster/GPU environment (Redhawk V100 or Talon H100) is known |

Fine-tuning is **not** described as "pure FP16 training". Only the loading of model weights in FP16 is decided.

### Per-model precision record

| Size | Checkpoint storage dtype / observed serialized dtype | Experimental runtime load dtype | `config.json` `torch_dtype` (metadata only) |
|---|---|---|---|
| 70M | Not read from the tensor header yet. `model.safetensors` is 281,715,176 bytes, approximately consistent with 4 bytes per official parameter | `torch.float16` | float16 |
| 160M | Not read from the tensor header yet. 649,308,728 bytes, approximately consistent with 4 bytes per official parameter | `torch.float16` | float16 |
| 410M | Not read from the tensor header yet. 1,621,370,224 bytes, approximately consistent with 4 bytes per official parameter | `torch.float16` | float16 |
| 1B | Not read from the tensor header yet. 2,023,586,192 bytes, approximately consistent with 2 bytes per official parameter | `torch.float16` | float16 |

Cautions:
- The file-size observation is only an approximate consistency check (official parameters x 4 or x 2, plus a small header). It is not proof of the stored dtype of every tensor, and it says nothing about the dtype used after loading. A direct read of the tensor dtypes in each safetensors header is still to be done once Python is available.
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

Status: not done (Python is not installed yet).

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
The 70M, 160M and 410M tokenizer files are byte-identical (same hashes). The 1B tokenizer files (`tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`) differ from the smaller models at the file level, and the 1B `config.json` has a different `eos_token_id` (2, versus 0 in the 70M config) and extra fields. Whether this changes actual tokenization behavior will be tested before Phase 5 (encode the same text with each tokenizer, including special tokens, and record any difference). Not done yet (needs Python).

## 5. Environment versions

Filled in the first time the check in section 3 is run.

| Component | Version |
|---|---|
| Python | not yet installed |
| PyTorch | not yet installed |
| Transformers | not yet installed |
| Hugging Face Hub | not yet installed |
| CUDA | not yet known (depends on the cluster) |

## 6. Teacher

| Item | Value | Source |
|---|---|---|
| Model | Claude Sonnet 5.5 | [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview) |
| API model ID | `claude-sonnet-5-5` (Anthropic states every Claude model ID is a pinned snapshot, including dateless IDs) | same page |
| Knowledge cutoff | Jun 2026 (reliable and training data) | same page |
| Retirement | Not sooner than September 28, 2027 | same page |
| Fallback | `claude-opus-5-5` | same page; decision in `docs/teacher_selection.md` |
| Effort and thinking mode | Not yet used. Record the values actually used for each generation run | `docs/teacher_selection.md` plans medium or high |

Every batch of teacher outputs must be recorded with the UTC date and time generated, the API model ID, effort level, thinking mode, sampling settings, and the files produced. Put the date in the file or folder name. Never overwrite a dated batch. The rule is in README Section 12.

## 7. Cluster notes (public documentation, checked 2026-10-01)

Sources: [Redhawk cluster page](https://www.miamioh.edu/research/research-computing-support/services/hpc-cluster), [Slurm](https://miamioh.edu/research-innovation/research-computing-support/slurm-resource-manager.html), [batch usage](https://miamioh.edu/research-innovation/research-computing-support/batch-cluster-usage.html), [interactive usage](https://miamioh.edu/research-innovation/research-computing-support/interactive-cluster-usage.html), [Talon news](https://miamioh.edu/news/2026/06/new-talon-cluster-a-major-leap-forward-in-accelerated-computing-ai-technology-infrastructure-at-miami.html), [resource overview](https://miamioh.teamdynamix.com/TDClient/1813/Portal/KB/ArticleDet?ID=169669).

- Redhawk: Slurm; partitions `batch`, `gpu`, `bigmem`; 4 GPU nodes with 2x NVIDIA Tesla V100-PCIE-16GB each; about 120 TB shared storage; login nodes should not be used for work over 1 hour of CPU time or 10 GB of memory.
- Talon: 4 GPU nodes with 4x NVIDIA H100 each. No public documentation of its partitions, login or storage.
- The four checkpoints total about 4.6 GB for the downloaded safetensors, small against the cluster storage. FP16 weights are about 0.14, 0.32, 0.81 and 2.02 GB for 70M, 160M, 410M and 1B, so baseline evaluation fits in 16 GB of GPU memory.
- Not documented publicly (to ask rescomp@miamioh.edu): outbound internet from login and compute nodes, home and scratch quotas, available Python/PyTorch/CUDA modules, which cluster to use. The planned approach does not need cluster internet: the files are downloaded here and copied with `scp`, then re-checked with `sha256sum`.
- Training memory depends on the training precision recipe (concept 3), which is not decided here.
