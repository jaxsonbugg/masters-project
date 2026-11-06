# Recovery: Talon SSH access and the `talon` command

**What it is:** The SSH config entry and one-word command that will log this PC into Miami's Talon GPU cluster. **Nothing here has been
set up yet: there is no Talon account.** This file is the template; the lines marked `<PLACEHOLDER>` are filled in on the first login.
**Location (once created):** `C:\Users\Buggb\.ssh\config` (entry `Host talon`) and `C:\Users\Buggb\bin\talon.cmd`.
**Approx. size:** a few hundred bytes
**Backed up?** No (only this recipe is in the repository). No secrets are stored in these files. The account itself is managed by Miami.

## What is known and not known (as of 2026-11-05)
- **Known (Miami IT news and research-computing pages):** Talon has 4 GPU nodes with 4 H100 GPUs each. Faculty can request accounts; a student
  account is requested on the "Research Cluster Account Sponsorships" page ("Request New Sponsorship": a faculty sponsor approves, and an expiry date
  is chosen). Questions go to ResComp@MiamiOH.edu (Jens Mueller, Director of HPC, muellej@miamioh.edu).
- **UNVERIFIED (ask Miami Research Computing):** the login host name, whether the campus VPN and Duo are needed, whether the account is the same as
  the Redhawk account, pricing, allocation, GPU quotas and access rules. Do not guess the host name.

## How to rebuild (after the first login)
1. Create or extend `C:\Users\Buggb\.ssh\config` with:
   ```
   Host talon
       HostName <PLACEHOLDER: login host given by Miami Research Computing>
       User buggjm
       ServerAliveInterval 60
   ```
   (the user name is assumed to match the Miami UniqueID, as for Redhawk: confirm it.)
2. Create `C:\Users\Buggb\bin\talon.cmd` containing the single line `@ssh talon %*` (the folder is already on the user PATH, see
   `recovery/redhawk_ssh_access.md`).
3. Test: type `talon`, log in with your Miami password and Duo, then `exit`. If the connection times out away from campus, connect the Miami VPN first
   (this was needed for Redhawk; for Talon it is UNVERIFIED).
4. Record here: the host name, whether VPN was needed, the Duo method.

## Versions, seeds, and settings
- Source / model revision / API model + version: Windows OpenSSH (`ssh -V`).
- Random seeds: none.
- Key hyperparameters or config file: the `Host talon` block above; the cluster paths go in `configs/paths.yaml` (`talon_root`, `talon_repo`, `talon_models`, `talon_outputs`, all `UNSET` until the first login) and the Slurm settings in `configs/talon/talon_settings.sh`.
- Login method: <PLACEHOLDER: Miami password + Duo expected, UNVERIFIED>. If an SSH key is added later, record only its public-key fingerprint here, never the private key.

## Verification
- Expected file count / size: 2 small files (config entry, `talon.cmd`).
- Quick sanity check: `ssh -G talon` shows the recorded host and user; `talon` then `exit` round-trips.

## If it is lost
Re-create the two files as above (a minute, no cost). If the account is gone or expired, renew the sponsorship (a faculty sponsor must approve) or
email ResComp@MiamiOH.edu.

## Last updated
2026-11-05 (template only; no account yet)
