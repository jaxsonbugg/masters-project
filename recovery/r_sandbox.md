# Recovery: the R sandbox (WSL2 Ubuntu 24.04 + bubblewrap + R 4.3.1)

**What it is:** a sealed place on this PC where model-written R code runs: the teacher's `r_solution` and `r_check`, and later the students' R answers. It has no network, cannot see the C: drive, the repository or the Linux home folder, and enforces limits on memory, CPU time, wall time, file size, `/tmp` size, processes and output. Why and how: `docs/methodology/workflow.md` Section 4, safeguard 10, and the docstring of `code/generation/r_sandbox.py`.
**Location:** the WSL distribution `Ubuntu-24.04` on this PC (Windows keeps its disk in the user's local app data). Settings are in `configs/paths.yaml`, block `r_sandbox`.
**Approx. size:** about 2–3 GB (Ubuntu plus R).
**Backed up?** No. It holds no project data and is rebuilt from the steps below in about 15 minutes.

## How to rebuild
1. **WSL2 and Ubuntu.** In PowerShell as administrator, run `wsl --install -d Ubuntu-24.04`. When asked, create a Linux user; the one used here is `buggb`. No restart was needed on 2026-11-12. CPU virtualization must be on; Task Manager, then Performance, then CPU shows "Virtualization: Enabled".
2. **Internet for the setup.** The setup needs internet inside Ubuntu. With the Cisco AnyConnect VPN connected, WSL2's default network cannot reach the internet (seen 2026-11-12), so either disconnect the VPN for steps 3 and 4, or put `[wsl2]` and `networkingMode=mirrored` in `%USERPROFILE%\.wslconfig` and run `wsl --shutdown`.
3. **bubblewrap**, in Ubuntu: `sudo apt update && sudo apt install -y bubblewrap curl ca-certificates`, then `bwrap --version`. This gave `bubblewrap 0.9.0`.
4. **R 4.3.1 with rig**, in Ubuntu:
   ```bash
   curl -Ls https://github.com/r-lib/rig/releases/download/latest/rig-linux-$(arch)-latest.tar.gz | sudo tar xz -C /usr/local
   sudo rig add 4.3.1
   /opt/R/4.3.1/bin/Rscript -e 'cat(R.version.string, "\n")'
   ```
   The expected output is `R version 4.3.1 (2023-06-16)`.
5. **Cut Ubuntu off from Windows.**
   - In Ubuntu, write `/etc/wsl.conf`. It keeps the two settings Ubuntu creates itself and adds the two locks:
     ```bash
     printf '[boot]\nsystemd=true\n\n[user]\ndefault=buggb\n\n[automount]\nenabled=false\nmountFsTab=false\n\n[interop]\nenabled=false\nappendWindowsPath=false\n' | sudo tee /etc/wsl.conf
     ```
     Replace `buggb` with the Linux user from step 1.
   - Then, in PowerShell, run `wsl --shutdown`.
   - **Effect:** `/mnt/c` is empty inside Ubuntu (the C: drive is not mounted), and Linux cannot start Windows programs. Windows can still start Linux and pass it text, which is all the runner needs.
6. **Check.** Reconnect the VPN if you like; nothing below needs the internet. From the repository, run:
   ```
   C:\masters_project_large\envs\probe\Scripts\python.exe code\generation\r_sandbox.py selftest
   ```
   It must end with `13 passed, 0 failed`.

## Versions, seeds, and settings
- **WSL:** 3.0.5.0, kernel 6.18.58.1-1, Windows 10.0.26200.9974 (`wsl --version`, 2026-11-12).
- **Ubuntu and its tools:** Ubuntu 24.04 LTS; bubblewrap 0.9.0 (Ubuntu package `0.9.0-1ubuntu0.1`); rig (latest release on 2026-11-12).
- **R:** R 4.3.1 (2023-06-16) at `/opt/R/4.3.1`, the same version as the Windows R that computed the earlier keys.
- **Limits per run** (`configs/paths.yaml`):

  | Limit | Value |
  |---|---|
  | Memory (address space) | 4096 MB |
  | CPU time | 10 s |
  | Wall time | 20 s |
  | Output | 1,000,000 bytes each for standard output and standard error |
  | Largest file written | 16 MB |
  | `/tmp` in total | 64 MB |
  | Processes | 256 |

  R 4.3.1 hangs at startup under a 2048 MB address-space limit, because its math library reserves address space per thread; 4096 MB starts normally.
- **Seeds:** none. The sandbox is deterministic.

## Verification
- `r_sandbox.py selftest` must show 13 checks passing:
  - **Positive controls:** BM9001's calculation prints 0.2304, and R is 4.3.1.
  - **Each forbidden action fails:** opening a URL, opening a socket, reading a canary file planted in the Linux home folder, seeing `/mnt/c`, writing outside `/tmp`, allocating beyond the memory limit, an endless loop, a background process outliving the run, too much output, and an inherited environment.
- `code/tests/benchmark_core_regression/test_regression.py` must pass. Its snapshot was recorded with the Windows R, so a pass shows the sandbox gives identical R results.
- **Every command that runs R** (`generate_benchmark.py verify`, `open_teacher_test.py score`) runs the self-test first and refuses to run any R if it fails.

## If it is lost
Rebuild with the steps above, in about 15 minutes, at no cost. Nothing in it needs restoring: it holds no data. Until it is rebuilt, the scripts refuse to run R (fail closed), so nothing unsafe happens. If R 4.3.1 can no longer be installed with rig, install the closest available build, re-run the regression test, and log any key that changes as a deviation.

## Last updated
2026-11-12
