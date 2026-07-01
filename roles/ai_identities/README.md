# ai_identities

Per-AI-agent Unix identities and their SSH mesh, provisioned by Ansible. Run
against the `linux` group (see `agents.yml`).

For each account in `ai_identities_roster` (default `claude`, `codex`) on every
Linux node:

- creates the account in the `sudo` group with **NOPASSWD sudo** (root access),
- generates one Ed25519 keypair **on the hub** (`ai_identities_hub_host`, the agent
  node) and writes the account's `~/.ssh/config` for the other nodes,
- authorizes that public key for the account on **every** node.

Result: `claude@agent` / `codex@agent` can `ssh control|services` as themselves and
`sudo` to root with no password — the same mesh shape as the `v2e`/`ansible` users,
scoped to the AI accounts.

The VyOS **router is intentionally not a target** — the kill switch must stay
outside the contained agents' reach. See `agents.yml` for the residual risk that
remains because the accounts get root on `control`.

Collections used (shipped in the pipx `ansible` bundle): `community.general`,
`community.crypto`, `ansible.posix`.

## Key variables

| var | default | purpose |
|-----|---------|---------|
| `ai_identities_roster` | `[claude, codex]` | accounts to create |
| `ai_identities_hub_host` | `groups['agent'][0]` | holds the private keys |
| `ai_identities_sudo_nopasswd` | `true` | NOPASSWD sudo |
| `ai_identities_password` | `""` | sha-512 hash; empty = key-only |
| `ai_identities_ssh_targets` | control/services/agent | `~/.ssh/config` entries |
