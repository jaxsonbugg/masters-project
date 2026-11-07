# Recovery: Python probe environment (virtual environment)

**What it is:** A Python virtual environment ("venv", a private folder of installed Python packages so this project's versions do not clash with anything else on the PC) holding PyTorch (CPU build), Transformers, and a few helpers. It runs `code/evaluation/pythia_probe.py`, the free checks in `code/generation/generate_benchmark.py` (with R), and the local test suites in `code/tests/` (set `OTT_TEST_PYTHON` to this venv's `python.exe`).
**Location:** `C:\masters_project_large\envs\probe` (`envs` in `configs/paths.yaml`)
**Approx. size:** about 1 GB
**Backed up?** No. Only this recipe and `environment/requirements.txt` are in the repository.

## How to rebuild
1. Create the venv with the Python that is installed on this PC (the plain `python` command in some shells hits a Windows Store stub, so use the full path):
   ```powershell
   & "C:\Users\Buggb\AppData\Local\Programs\Python\Python311\python.exe" -m venv C:\masters_project_large\envs\probe
   ```
2. Install the CPU build of PyTorch, then the other packages (exact versions, from `environment/requirements.txt`):
   ```powershell
   $p = "C:\masters_project_large\envs\probe\Scripts\python.exe"
   & $p -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
   & $p -m pip install transformers==5.19.0 safetensors==0.8.0 PyYAML==6.0.3 psutil==7.2.2 httpx==0.28.1
   ```
3. Run the probe:
   ```powershell
   & $p C:\dev\masters-project\code\evaluation\pythia_probe.py
   ```

## Versions, seeds, and settings
- Source / model revision / API model + version: the probe loads the pinned Pythia checkpoints from `C:\masters_project_large\models\pythia` (see `recovery/pythia_base_models.md`); it uses no API. `httpx` is the HTTP client `code/generation/open_teacher_test.py` uses to talk to the Qwen server on a cluster. (The existing venv also still contains the `anthropic` package from the Claude era; it is no longer needed, and a rebuilt venv does not install it.)
- Random seeds: 1234 (only matters if `--sampling` is used; the default greedy decoding is deterministic).
- Key hyperparameters or config file: `--dtype float16 --device cpu --max-new-tokens 128` (defaults).
- Package versions: `environment/requirements.txt` (Python 3.11.9, torch 2.14.1+cpu, transformers 5.19.0, safetensors 0.8.0).
- This is a CPU-only environment for local work. The cluster environments are separate: vLLM on Talon is installed by `configs/talon/prep_talon.sh` (`docs/talon_setup.md`), and the training environment with a CUDA build of PyTorch is set up and recorded during the pilot (Talon, with Redhawk as the fallback).

## Verification
- Expected file count / size: not meaningful (many small package files).
- Expected checksum: none.
- Quick sanity check: `& $p -c "import torch, transformers; print(torch.__version__, transformers.__version__)"` prints `2.14.1+cpu 5.19.0`. Running the probe with `--models 70m --limit-prompts 2 --out-dir <temp folder>` should finish in under a minute.

## If it is lost
Re-run the steps above. It needs internet and takes about 5 minutes. Costs nothing. If a pinned version has been removed from PyPI or the PyTorch index, install the closest version and record the change in `docs/model_versions.md` section 5, because generation behavior can differ slightly between versions.

## Last updated
2026-11-06 (Claude API client removed; httpx listed for the Qwen client)
