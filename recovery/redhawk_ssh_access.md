# Recovery: Redhawk SSH access and the `redhawk` command

**What it is:** The SSH config entry and one-word command that log this PC into the Miami Redhawk cluster.
**Location:** `C:\Users\Buggb\.ssh\config` (entry `Host redhawk`) and `C:\Users\Buggb\bin\redhawk.cmd`; `C:\Users\Buggb\bin` is on the user PATH.
**Approx. size:** a few hundred bytes
**Backed up?** No (only this recipe is in the repository). No secrets are stored in these files. The cluster account itself is managed by Miami (sponsored account, https://www.apps.miamioh.edu/puppet-user-management/cluster-management).

## How to rebuild
1. Create `C:\Users\Buggb\.ssh\config` (append the block if the file already exists):
   ```
   Host redhawk
       HostName redhawk.hpc.muohio.edu
       User buggjm
       ServerAliveInterval 60
   ```
2. Create `C:\Users\Buggb\bin\redhawk.cmd` containing the single line `@ssh redhawk %*`.
3. Add `C:\Users\Buggb\bin` to the user PATH (PowerShell): append it to `[Environment]::GetEnvironmentVariable("Path","User")` and write it back with `[Environment]::SetEnvironmentVariable("Path", <new value>, "User")`. Open a new terminal.
4. Test: type `redhawk`, log in with your Miami password and Duo, then type `exit`.

## Versions, seeds, and settings
- Source / model revision / API model + version: Windows OpenSSH 9.5p2 (`ssh -V`).
- Random seeds: none.
- Key hyperparameters or config file: the `Host redhawk` block above.
- Package versions (see environment/): none.
- Login method: Miami password + Duo. No SSH key is installed yet. If a key is added later (`~/.ssh/redhawk_ed25519`), add `IdentityFile ~/.ssh/redhawk_ed25519` to the block and record only the public-key fingerprint here, never the private key. To revoke, delete that key's line from `~/.ssh/authorized_keys` on the cluster.

## Verification
- Expected file count / size: 2 small files (config entry, `redhawk.cmd`).
- Expected checksum: none.
- Quick sanity check: `ssh -G redhawk` shows hostname `redhawk.hpc.muohio.edu` and user `buggjm`; `redhawk` then `exit` round-trips.

## If it is lost
Re-create the two files as above (a minute, no cost). If the account itself is gone or expired, request or renew a sponsored account in the cluster management app (a faculty sponsor must approve) or email rescomp@miamioh.edu.

## Last updated
2026-10-01
