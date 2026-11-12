# Recovery: Qwen3.6-27B BF16 weights and the vLLM environment on Talon

**What it is:** two things:
- **The teacher model's weights:** Qwen3.6-27B in BF16, the full-precision release, pinned to one commit.
- **The Python environment that serves them:** a virtual environment ("venv", a private folder of installed Python packages) with vLLM 0.32.0. vLLM is the inference engine that loads the model onto the GPUs and answers requests.

Every Talon teacher job reads both. Before loading the weights, each job re-hashes them against the manifest below.

**Location:** on Talon, inside the home folder that Talon shares with Redhawk (`configs/paths.yaml`: `talon_root`, `talon_models`):
- weights: `/home/buggjm/talon_project/models/Qwen3.6-27B/`, with the manifest `models/weights_manifest.sha256`, plus `models/model_revision.txt` and `models/weights_total_mib.txt`;
- environment: `/home/buggjm/talon_project/venv/`, with the package list `venv_pip_freeze.txt` and the install log `fetch_talon.log`, both in `/home/buggjm/talon_project/`.

**Approx. size:** the weights take 52 GB on disk (`du`; 53,220 MiB counted by the manifest step). The environment takes 8.5 GB.

**Backed up?** No. Only this recipe and the scripts are in the repository. Both items can be rebuilt exactly, because the weights are pinned and hash-checked and the environment's package list is recorded.

## How to rebuild

Do this from the PC in Git Bash, with the Miami VPN on if you are off campus. It is the same procedure that built them on 2026-11-12.

1. **Copy the committed repository to Talon.** Build it in `repo_new` and only then swap it in, so the existing copy is untouched until every step has passed. Keep the probe files from job 196, which the submit script needs:
   ```bash
   cd /c/dev/masters-project
   git archive --format=tar HEAD | ssh talon 'set -e; cd ~/talon_project; test ! -e repo_new; mkdir repo_new; tar -x -C repo_new; cp repo/talon_probe_job.txt repo/qt_talon_probe_196.log repo_new/; cd repo_new; bash configs/talon/probe_talon_part2.sh record > /dev/null; cd ..; mv repo repo_old_$(date -u +%Y%m%dT%H%M%SZ); mv repo_new repo; echo REFRESHED'
   ```
   `git archive` on this PC writes text files with Windows line endings, which is what the v6 prompt's pinned SHA-256 (`348db6ff...`) was computed on. Shell scripts get Unix line endings, because `.gitattributes` forces that.
2. **Run the preparation script.** It checks the copied files, then starts the install and download in the background on the login node:
   ```bash
   ssh talon 'cd ~/talon_project/repo && QT_CONFIRM_STORAGE=yes QT_ALLOW_HOME=yes bash -l configs/talon/prep_talon.sh'
   ```
   - `QT_CONFIRM_STORAGE=yes` confirms the storage after reading the free space and quota.
   - `QT_ALLOW_HOME=yes` allows the home folder (Research Computing said the 500 GB home quota is ours to use).
   - Add `QT_PREP_AGAIN=yes` if a `prep_state.txt` from an earlier attempt exists.

   The background part (`configs/talon/fetch_talon.sh`) then:
   - creates the venv from `/software/miniforge3-python3.12/bin/python3.12`;
   - installs `vllm==0.32.0`;
   - checks the installed version from Python's package records (not `vllm --version`, which crashes on a node without a GPU);
   - saves `pip freeze --all`;
   - downloads `Qwen/Qwen3.6-27B` at the pinned commit;
   - verifies every file against the sizes and SHA-256 hashes Hugging Face publishes for that commit;
   - writes the manifest.
3. **Watch it:** `ssh talon 'tail -n 15 ~/talon_project/fetch_talon.log'`. It is done when the last line is `OK: weights verified`.

## Versions, seeds, and settings
- **Model:** `Qwen/Qwen3.6-27B`, revision `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9` (2026-04-24), BF16, 29 files.
  - A newer head, `8f33b98937c6031bb49e713dee3e8e185aafd26f` (2026-11-07), changes only the chat template files. It is known and **not adopted**, so do not download `main`.
- **Engine:** `vllm==0.32.0`. The installed environment (recorded 2026-11-12T05:32:27Z) has Python 3.12.5, `torch==2.13.0` (CUDA 13.0 build, `2.13.0+cu130`), `transformers==5.19.0` and `flashinfer_python==0.7.0.post1`, 199 packages in all.
- **Settings:** `configs/talon/talon_settings.sh` (reviewed by Jaxson Bugg, 2026-11-12) and `configs/paths.yaml`.
- **Random seeds:** none. Downloading and installing involve no randomness.
- **Package versions:** `venv_pip_freeze.txt` on Talon holds the complete list. The repository's `environment/requirements.txt` covers only the local CPU environment.

## Verification
- **Expected file count and size:** 29 weight files, 53,220 MiB by the manifest step (52 GB with `du`). `WEIGHTS_MIB` in the settings is 53,011, a 0.4% difference that is normal for disk accounting and left unchanged.
- **Expected checksums:**
  - **the weights manifest** (`weights_manifest.sha256`, one SHA-256 per file): its own SHA-256 is `8e3e1fc0103c85a66c1516343b645a80d667e47a8152b8b38a24e67e218d1d33`;
  - **the package list** (`venv_pip_freeze.txt`): SHA-256 `96977b7fd97d9e886930fa2c2a423e64651bf0354bbe892646e6ab27f4f9867a`.
- **Quick sanity check, on the login node:**
  ```bash
  ssh talon 'cd ~/talon_project; sha256sum models/weights_manifest.sha256 venv_pip_freeze.txt; cat models/model_revision.txt; venv/bin/python -c "import importlib.metadata as m; print(m.version(\"vllm\"))"'
  ```
  The two hashes and the commit must match the values above, and the version must be `0.32.0`.
  - Do not use `venv/bin/vllm --version` on the login node: it crashes with "Failed to infer device type" because there is no GPU.
  - Every Stage A, T or main job re-hashes all weight files against the manifest before loading them.

## If it is lost
Re-run the two steps above.
- **Time:** on 2026-11-12 the 54 GB download took about 82 seconds; the package install and the hash check add some minutes, which were not timed.
- **Cost:** no GPU-hours and no money, because everything runs on the login node.
- **Storage:** about 61 GB of the home quota.

The rebuild is exact as long as Hugging Face keeps the pinned commit and PyPI keeps `vllm==0.32.0` and its dependencies. If a dependency version has disappeared, compare the new `venv_pip_freeze.txt` with the recorded hash. Record any difference as a deviation in `docs/progress_update.md`, because the engine environment must be identical for all teacher generation.

## Last updated
2026-11-12 (first build)
