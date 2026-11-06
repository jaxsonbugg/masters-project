# Recovery: Talon SSH access and the `talon` command

**What it is:** The SSH config entry and one-word command that log this PC into Miami's Talon GPU cluster.
**Status (2026-11-05):** the head node name came from Research Computing, but **no connection has been made yet and the host key has not been verified or accepted**. Fields marked `<TO FILL IN>` are completed on the first login.
**Location (once created):** `C:\Users\Buggb\.ssh\config` (entry `Host talon`) and `C:\Users\Buggb\bin\talon.cmd`.
**Approx. size:** a few hundred bytes
**Backed up?** No (only this recipe is in the repository). No secrets are stored in these files. The account itself is managed by Miami.

## What is known and not known (evidence labels as in `docs/talon_setup.md`)
- **TOLD BY RESEARCH COMPUTING (message to Jaxson, 2026-11-05):** the login (head) node is `mualhphp01.hpc.miamioh.edu`; the GPU partition is `talon` (`--partition=talon`); a job is placed on GPU node 1 with `--nodelist=mualhpgp01.mpi` (a way to choose a node, not a requirement).
- **Documented (Miami IT news and research-computing pages):** 4 GPU nodes with 4 H100 each; student accounts via "Research Cluster Account Sponsorships" (faculty sponsor, expiry date); contacts ResComp@MiamiOH.edu and Jens Mueller (muellej@miamioh.edu).
- **UNVERIFIED:** whether the VPN and Duo are needed, whether the account is the same as the Redhawk account, the user name, pricing, allocation, GPU quotas, access rules.

## Verify the host key BEFORE the first login (do not just type "yes")
**Why.** The first time ssh connects to a server it shows a *fingerprint*, a short hash of the server's public host key, and asks whether to trust it. If an attacker answered in place of the real server, typing "yes" without checking would
hand them your password and Duo response. Checking the fingerprint against a value obtained *another way* proves you reached the real server.
1. **Reachability (PowerShell):** `Test-NetConnection mualhphp01.hpc.miamioh.edu -Port 22`. `TcpTestSucceeded : True` means reachable. If it times out, connect the Miami VPN (`muvpn.miamioh.edu`, Duo) and test again. Record below whether the VPN was needed.
2. **Show the fingerprints the server presents (Git Bash).** This only downloads public keys; nothing is trusted or saved:
   `ssh-keyscan -t ed25519,ecdsa,rsa mualhphp01.hpc.miamioh.edu 2>/dev/null | ssh-keygen -lf -`
   Each line looks like `256 SHA256:abc... mualhphp01.hpc.miamioh.edu (ED25519)`.
3. **Get the reference values from Research Computing by a channel that does not depend on that network path** (email ResComp@MiamiOH.edu or Jens Mueller, a phone call, or in person). Ask for the SHA256 fingerprints of the head node's SSH host keys (ED25519, ECDSA, RSA). On the node they can print them with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` (and `ssh_host_ecdsa_key.pub`, `ssh_host_rsa_key.pub`).
   Suggested email: *"Hello, I am a Miami graduate student about to log in to mualhphp01.hpc.miamioh.edu for the first time. Could you send me the SHA256 fingerprints of its SSH host keys (ED25519, ECDSA, RSA) so I can verify the server before entering my password? Thank you."*
4. **Compare character by character.** For each key type, the `SHA256:` string from step 2 must equal the one Research Computing sent. If any differ, **do not connect**; tell Research Computing.
5. **Only then connect once by hand:** `ssh talon "hostname; id; echo CONNECTED"`. ssh shows the fingerprint again and asks to continue: confirm it equals the verified one, then type `yes`. That records the key in `known_hosts`. From then on a changed key is refused automatically.
   The probe wrapper (`configs/talon/run_probe_local.sh`) uses `StrictHostKeyChecking=yes`, so it can never accept a new key by itself.
6. **Optional second opinion** from an already trusted Redhawk session: `ssh redhawk "ssh-keyscan -t ed25519 mualhphp01.hpc.miamioh.edu | ssh-keygen -lf -"` shows what Redhawk sees over the campus network. It supports, but does not replace, Research Computing's confirmation.
   If the head node uses SSH certificates instead of plain host keys, ask which certificate authority to trust.

## How to rebuild
1. Create or extend `C:\Users\Buggb\.ssh\config` with:
   ```
   Host talon
       HostName mualhphp01.hpc.miamioh.edu
       User buggjm
       ServerAliveInterval 60
   ```
   (`User buggjm` assumes the Talon login equals the Redhawk one; the connection test confirms it.)
2. Create `C:\Users\Buggb\bin\talon.cmd` containing the single line `@ssh talon %*` (the folder is already on the user PATH, see `recovery/redhawk_ssh_access.md`).
3. Test as in step 5 above (after verifying the host key), then `exit`.

## Outcomes of the first connection
- `CONNECTED` after the password and Duo prompts: the account is active; the host and Duo method are confirmed.
- `Permission denied`: the Talon account may not be active yet, or the password or Duo step failed: ask Research Computing.
- Timeout or "could not resolve": connect the Miami VPN and repeat step 1.
- "Host key verification failed" or a warning that the key CHANGED: stop; do not bypass it; tell Research Computing.

## Record these on the first login (fill in)
- Date of first login: `<TO FILL IN>`; VPN needed: `<TO FILL IN>`; Duo method: `<TO FILL IN>`; user name that worked: `<TO FILL IN>`
- Host-key fingerprints verified with Research Computing on `<date>` by `<channel>`: ED25519 `<TO FILL IN>`, ECDSA `<TO FILL IN>`, RSA `<TO FILL IN>` (public values; safe to record)

## Versions, seeds, and settings
- Source: Windows or Git Bash OpenSSH (`ssh -V`).
- Random seeds: none.
- Key config files: the `Host talon` block above; cluster paths in `configs/paths.yaml` (`talon_root`, `talon_repo`, `talon_models`, `talon_outputs`, all `UNSET` until the probe shows an approved location); Slurm settings in `configs/talon/talon_settings.sh`.
- Login method: Miami password + Duo expected (`UNVERIFIED`). If an SSH key is added later, record only its public-key fingerprint here, never the private key.

## Verification
- Expected file count / size: 2 small files (config entry, `talon.cmd`).
- Quick sanity check: `ssh -G talon` shows the recorded host and user; `talon` then `exit` round-trips.

## If it is lost
Re-create the two files as above (a minute, no cost). The verified fingerprints above let you check the server again. If the account is gone or expired, renew the sponsorship (a faculty sponsor must approve) or email ResComp@MiamiOH.edu.

## Last updated
2026-11-05 (head node, partition and node option from Research Computing; host key not yet verified; no login yet)
