# Recovery: Pythia deduped base models (step143000)

**What it is:** The four student base checkpoints, Pythia 70M, 160M, 410M and 1B deduped, final `step143000` revision, exactly as distributed on Hugging Face.
**Location:** `C:\masters_project_large\models\pythia\pythia-<size>-deduped\step143000\` (`models_pythia` in `configs/paths.yaml`)
**Approx. size:** about 4.6 GB (0.28 + 0.65 + 1.62 + 2.02 GB of safetensors, plus small config and tokenizer files)
**Backed up?** No (only this recipe is in the repository). Exact versions and hashes are in `docs/model_versions.md`.

## How to rebuild
1. Create the folders and download each file from the pinned commit (Git Bash; `curl` is resumable with `-C -`). A 404 on the optional `generation_config.json` removes that file and continues; any other response that is not 200 or 206 deletes the bad file and stops the script:
   ```bash
   cd /c/masters_project_large/models/pythia
   declare -A SHA=( [70m]=9a7c847e93250c8f24d4b7e7134dbf369e8fc9cb [160m]=c54a0e0b28cc667b6f278803024438d57f847b5d [410m]=c66f7467608ffee8fca0d28cf1f46a7574b53cec [1b]=d1988145ec1cf1e76d786cd05af9f53e8b1c95cc )
   for s in 70m 160m 410m 1b; do
     d="pythia-$s-deduped/step143000"; mkdir -p "$d"
     for f in config.json tokenizer.json tokenizer_config.json special_tokens_map.json generation_config.json model.safetensors; do
       url="https://huggingface.co/EleutherAI/pythia-$s-deduped/resolve/${SHA[$s]}/$f"
       code=$(curl -sS -L -C - -w '%{http_code}' -o "$d/$f" "$url")
       if [ "$code" = "200" ] || [ "$code" = "206" ]; then
         echo "$s $f ok ($code)"
       elif [ "$code" = "404" ] && [ "$f" = "generation_config.json" ]; then
         rm -f "$d/$f"; echo "$s $f not present (optional), skipped"
       else
         rm -f "$d/$f"; echo "ERROR: $s $f returned HTTP $code; bad file deleted, stopping" >&2; exit 1
       fi
     done
   done
   ```
2. Compare the hashes with `docs/model_versions.md` (section 4): `cd <folder> && sha256sum *`.
3. Do not download `pytorch_model.bin` or the 12.2 GB `optimizer.pt` of the 1B repo.
4. Do not convert, re-save or edit any file. The load dtype (`torch.float16`) is set in code at load time, never by changing the files.
5. Optional: set the files read-only (`attrib +R <folder>\* /S` in a Windows prompt).

## Versions, seeds, and settings
- Source / model revision / API model + version: Hugging Face `EleutherAI/pythia-<size>-deduped`, branch `step143000`, commit SHAs as above. Always use the commit SHA, never `main` (the `main` SHAs are different).
- Random seeds: none (download only).
- Runtime load setting: `torch.float16`, passed explicitly at load time.
- Package versions (see environment/): none used for the download (curl only); curl 8.21.0 (Git for Windows).

## Verification
- Expected file count / size: 5 files per model (6 for 1B, which also has `generation_config.json`). `model.safetensors` sizes: 281,715,176 / 649,308,728 / 1,621,370,224 / 2,023,586,192 bytes.
- Expected checksum: `model.safetensors` SHA-256 values are in `docs/model_versions.md` and match the Hugging Face file listing.
- Quick sanity check: once Python exists, load each model with `torch_dtype=torch.float16`, check the parameter count and that every parameter dtype is `torch.float16` (procedure in `docs/model_versions.md`, section 3).

## If it is lost
Re-run step 1 and check the hashes. About 4.6 GB, a few minutes, no cost. If a hash does not match, stop and compare against the Hugging Face file listing for the pinned commit before using the file. If Hugging Face removes a repo, the SHAs and hashes recorded here identify the exact files to look for elsewhere.

## Last updated
2026-10-01
