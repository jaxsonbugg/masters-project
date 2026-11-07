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
       IdentityFile ~/.ssh/talon_ed25519
       IdentitiesOnly yes
   ```
   (The last two lines are optional and need the key from `recovery/talon_ssh_access.md`; without them login uses password + Duo.)
2. Create `C:\Users\Buggb\bin\redhawk.cmd` containing the single line `@ssh redhawk %*`.
3. Add `C:\Users\Buggb\bin` to the user PATH (PowerShell): append it to `[Environment]::GetEnvironmentVariable("Path","User")` and write it back with `[Environment]::SetEnvironmentVariable("Path", <new value>, "User")`. Open a new terminal.
4. Test: type `redhawk`, log in (with the key from step 1, or your Miami password and Duo), then type `exit`. **Off campus, connect the Miami VPN first:** without it, SSH to the cluster times out (port 22 is blocked from outside the campus network; observed 2026-11-04).

## Versions, seeds, and settings
- Source / model revision / API model + version: Windows OpenSSH 9.5p2 (`ssh -V`).
- Random seeds: none.
- Key hyperparameters or config file: the `Host redhawk` block above.
- Package versions (see environment/): none.
- Login method: SSH key, no password or Duo (since 2026-11-06). Redhawk and Talon share one home folder, so the key made for Talon (`~/.ssh/talon_ed25519`, set up in `recovery/talon_ssh_access.md`) also works here; the `Host redhawk` block has `IdentityFile ~/.ssh/talon_ed25519` and `IdentitiesOnly yes`. Without the key, the fallback is the Miami password + Duo (remove those two lines, or the key line from `~/.ssh/authorized_keys`). Record only the public-key fingerprint, never the private key. Revoking the key on one cluster revokes it on the other.

## Verification
- Expected file count / size: 2 small files (config entry, `redhawk.cmd`).
- Expected checksum: none.
- Quick sanity check: `ssh -G redhawk` shows hostname `redhawk.hpc.muohio.edu` and user `buggjm`; `redhawk` then `exit` round-trips.

## If it is lost
Re-create the two files as above (a minute, no cost). If the account itself is gone or expired, request or renew a sponsored account in the cluster management app (a faculty sponsor must approve) or email rescomp@miamioh.edu.

## Last updated
2026-11-06 (key login shared with Talon; VPN note)
