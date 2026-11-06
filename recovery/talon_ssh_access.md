# Recovery: Talon SSH access, the `talon` command and the key pair

**What it is:** The SSH config entry, one-word command and key pair that log this PC into Miami's Talon GPU cluster.
**Status (2026-11-06):** the first login worked, the public key is installed on Talon and key login works without a password or Duo (`KEY_LOGIN_OK` from a `BatchMode` test). The read-only probe is the next step.
**Location:** `C:\Users\Buggb\.ssh\config` (entry `Host talon`), `C:\Users\Buggb\bin\talon.cmd`, and the key pair `C:\Users\Buggb\.ssh\talon_ed25519` (private, never shared) and `talon_ed25519.pub` (public).
**Approx. size:** a few hundred bytes for the config and command; the keys are about 400 and 100 bytes.
**Backed up?** No (only this recipe is in the repository). The private key must never be copied into the repository, a chat or an email. The account itself is managed by Miami.

## What is known and not known (evidence labels as in `docs/talon_setup.md`)
- **TOLD BY RESEARCH COMPUTING (message, 2026-11-05):** the login (head) node is `mualhphp01.hpc.miamioh.edu`; the GPU partition is `talon` (`--partition=talon`); `--nodelist=mualhpgp01.mpi` places a job on GPU node 1 (an option, not a requirement; we let the scheduler choose).
- **TOLD BY RESEARCH COMPUTING (meeting, 2026-11-06; verbal, not yet in writing):** the Talon account uses the same user name as Redhawk (`buggjm`); the VPN is needed off campus; using Talon costs nothing; storage limit 500 GB (ask for more if needed); one job may run up to 3 days; own software may be installed (conda environments); contact: Dr. Mueller.
- **OBSERVED (2026-11-05):** the head node answers on port 22 only while the Miami VPN is connected.
- **Documented (Miami IT news and research-computing pages):** 4 GPU nodes with 4 H100 each; student accounts via "Research Cluster Account Sponsorships".
- **OBSERVED (2026-11-06):** the first login worked with password and Duo push (option 1); the user name `buggjm` worked; groups are `hpcusers` and `leed13-shared`; there was no `~/.ssh` folder on Talon before the key was installed; key login skips Duo. The probe (section 1b) showed that **the home folder is shared with Redhawk** (`/home` is the same network disk; `~/masters_project` is visible on Talon), so the one `authorized_keys` file serves both: the Talon key (`talon_ed25519`) also logs in to Redhawk without a password (tested by Jaxson, 2026-11-06). Revoking the key on one cluster revokes it on the other.
- **UNVERIFIED:** GPU-hour allocation.

## Host key (decision recorded 2026-11-06)
The first time ssh connects it shows the server's *fingerprint* (a short hash of its public host key). Normally you compare it with a value Research Computing gives you. Jaxson decided to trust the server as given, without comparing fingerprints; the server is reachable only on the Miami VPN. To keep one safeguard, the first login uses `-o StrictHostKeyChecking=accept-new`: ssh saves the key on that first connection and from then on **refuses automatically if the key ever changes** (a warning "REMOTE HOST IDENTIFICATION HAS CHANGED" means stop and tell Research Computing). The probe wrapper (`configs/talon/run_probe_local.sh`) uses `StrictHostKeyChecking=yes`, so it never accepts a new key by itself.

## How to rebuild
1. Create or extend `C:\Users\Buggb\.ssh\config` with:
   ```
   Host talon
       HostName mualhphp01.hpc.miamioh.edu
       User buggjm
       ServerAliveInterval 60
   ```
   Add two more lines to the block (done once the key worked): `IdentityFile ~/.ssh/talon_ed25519` and `IdentitiesOnly yes`.
2. Create `C:\Users\Buggb\bin\talon.cmd` containing the single line `@ssh talon %*` (the folder is already on the user PATH, see `recovery/redhawk_ssh_access.md`).
3. Connect the Miami VPN, then test: `ssh -o StrictHostKeyChecking=accept-new talon "hostname; id; echo CONNECTED"`. Log in with your Miami password and Duo.

## Key pair (so you do not type a password and Duo every time)
**What it is.** Two files made together. The *private key* stays on this PC. The *public key* is a line of text copied into `~/.ssh/authorized_keys` on Talon. When you connect, Talon sends a puzzle only the private key can solve, so it knows it is you. Miami's NoMachine guide describes the same idea for Redhawk (with PuTTYgen); we use Windows' own `ssh-keygen`.
1. Make the pair (PowerShell): `ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\talon_ed25519 -C "buggjm-pc-talon"` (press Enter twice for no passphrase, as Miami's guide allows).
2. After the first login (step 3 above) install the public key (Git Bash; the one write on Talon): `cat ~/.ssh/talon_ed25519.pub | ssh talon "umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys"`. `>>` adds a line and keeps any existing ones. (Do this in Git Bash: PowerShell's pipe can add a hidden carriage return that breaks the key.)
3. Test: `ssh -o BatchMode=yes -i ~/.ssh/talon_ed25519 talon "echo KEY_LOGIN_OK"`. `BatchMode` forbids password prompts, so `KEY_LOGIN_OK` proves the key works.
4. To revoke: delete that key's line from `~/.ssh/authorized_keys` on Talon and delete the two local files.

## Outcomes of the first connection
- `CONNECTED` after the password and Duo prompts: the account is active.
- `Permission denied`: the Talon account may not be active yet, or the password or Duo step failed: ask Research Computing.
- Timeout or "could not resolve": connect the Miami VPN and repeat.
- "Host key verification failed" or a warning that the key CHANGED: stop; do not bypass it; tell Research Computing.
- Key login still asks for Duo: the server requires it regardless of keys; that is allowed by policy, so keep using password + Duo (the probe is a single login).

## Record these as the steps finish (fill in)
- Date of first login: 2026-11-06; Duo method: push (option 1); user name that worked: `buggjm`
- Key installed on: 2026-11-06; public-key fingerprint (from `ssh-keygen -lf ~/.ssh/talon_ed25519.pub`; public, safe to record): `SHA256:pXePaflorB2GPHHHCkxKSEGlDuCGvGQIIBMwywM5gWw` (ED25519); key login skips Duo: yes

## Versions, seeds, and settings
- Source: Windows OpenSSH 9.5p2 (`ssh -V`).
- Random seeds: none.
- Key config files: the `Host talon` block above; cluster paths in `configs/paths.yaml` (`talon_root`, `talon_repo`, `talon_models`, `talon_outputs`, all `UNSET` until the probe shows an approved location); Slurm settings in `configs/talon/talon_settings.sh`.

## Verification
- Expected file count / size: 2 small files (config entry, `talon.cmd`) plus the two key files.
- Quick sanity check: `ssh -G talon` shows hostname `mualhphp01.hpc.miamioh.edu` and user `buggjm`; `talon` then `exit` round-trips; the BatchMode test prints `KEY_LOGIN_OK`.

## If it is lost
Re-create the config entry and `talon.cmd` as above (a minute, no cost). If the key pair is lost, make a new one and install its public key again (the old line can stay or be removed). If the account is gone or expired, renew the sponsorship (a faculty sponsor must approve) or email ResComp@MiamiOH.edu.

## Last updated
2026-11-06 (first login, key installed and tested; meeting answers; host-key decision)
