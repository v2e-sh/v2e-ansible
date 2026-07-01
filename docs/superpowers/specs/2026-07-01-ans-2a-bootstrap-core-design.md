# ANS-2a — Bootstrap core (design)

**Date:** 2026-07-01
**Repos:** `v2e-ansible` (primary) + `v2e-tf` (one cross-repo edit)
**Branch:** `feat/ansible-bootstrap` (off `refactor/ansible-structure`)
**Master-plan phase:** ANS-2 (this is the first half — "bootstrap core") · depends on ANS-1 · upstream of ANS-3
**Status:** approved design → implementation plan next

## Purpose

Fill the `01-bootstrap` phase with real behaviour: a fail-fast `health_check` gate and a
swap of the hand-rolled `deb_hardening_basic` role for `devsec.hardening`, making
`devsec.hardening` the **single owner** of `sshd_config` hardening. The developer-ergonomics
half of ANS-2 (`dev-tools`, `terminal-polish`) is deferred to a separate **ANS-2b**.

**Scope decision:** split ANS-2 → do the critical-path, security-sensitive bootstrap core
first; defer ergonomics. This spec is the bootstrap core only.

## Out of scope
- `dev-tools` (17 CLIs) and `terminal-polish` (Zsh/Starship/Ghostty) → ANS-2b.
- Automated Molecule harness → ANS-5 (its dedicated phase).
- Widening `AllowUsers` to the AI accounts → deliberate containment decision (Phase I / ANS-6), not here.

## Decisions (settled in brainstorming)
1. **Split scope** — bootstrap core now; ergonomics later.
2. **Single owner of sshd_config** — `devsec.hardening.ssh_hardening` owns it; retire BOTH the
   `deb_hardening_basic` `10-hardening.conf` drop-in AND cloud-init's `60-v2e.conf` (paired
   `v2e-tf` edit lands with this spec). Accepted trade-off: a brief first-boot window where
   `AllowUsers` isn't yet enforced — cloud-init still sets `ssh_pwauth: false` and creates only
   the intended users, and bootstrap closes the gap immediately.
3. **Testing** — static now (`ansible-lint`, `--syntax-check`, `--check`) + a written live-env
   behavioral test plan; Molecule deferred to ANS-5.
4. **fail2ban** — preserved (don't silently drop a security control) as a small dedicated role.
5. **AllowUsers** — preserved exactly as today; the pre-existing claude/codex inbound-mesh gap
   is documented, not changed here.
6. **`ip_forward=1`** — preserved on the whole `linux` group (simplest; harmless on non-Docker
   nodes, required on the Docker node).

## Current state (what we're replacing)
- `roles/deb_hardening_basic`: SSH drop-in (`/etc/ssh/sshd_config.d/10-hardening.conf`),
  sysctl drop-in (`/etc/sysctl.d/90-hardening.conf`), and a fail2ban sshd jail (systemd backend).
- `v2e-tf/cloud-init/node.yaml.tftpl`: writes `/etc/ssh/sshd_config.d/60-v2e.conf` with
  `PermitRootLogin no`, `PasswordAuthentication no`, `AllowUsers ${ssh_allow_users}`; also sets
  `ssh_pwauth: false`. `ssh_allow_users` (from `v2e-tf/nodes.tf`): control → `v2e`;
  services/agent → `v2e ansible`.
- `roles/health_check`, `roles/dev_tools`: ANS-1 no-op scaffolds.
- AI mesh (`roles/ai_identities`, run in `03-applications`): `claude`/`codex` on the agent hub
  SSH to all nodes as those users — but they are NOT in `AllowUsers` today, so the inbound mesh
  leg is already gated. The primary `task-agent` flow runs locally on the agent (become_user),
  so it does not need inbound SSH. **Pre-existing; unchanged by this spec.**

## Components

### 1. `health_check` role — fail-fast preflight gate
Runs first in `01-bootstrap` on `linux`. Pure `ansible.builtin`/`ansible.posix`.
- **Mesh reachability:** `ansible.builtin.wait_for_connection` (timeout `health_check_connect_timeout`, default 30s) — abort early if a node is unreachable.
- **Disk assert:** fail if free space on `/` < `health_check_min_disk_percent` (default 15).
- **Memory assert:** fail if available memory < `health_check_min_mem_mb` (default 512).
- **Inter-VLAN reachability:** from `control`, assert TCP:22 reachability to `services`
  (10.1.2.10) and `agent` (10.1.3.10) via `ansible.builtin.wait_for` (through the router);
  targets in `defaults` (`health_check_intervlan_targets`).
- Clear `fail_msg` on every assert. `defaults/main.yml` holds all thresholds/targets.

### 2. `devsec.hardening` swap (in `01-bootstrap`, on `linux`)
Replace the `deb_hardening_basic` role reference with two devsec roles + a fail2ban role.
- **`devsec.hardening.ssh_hardening`** — sole `sshd_config` owner:
  - `ssh_allow_users`: from group_vars — `control` → `["v2e"]`; `services`/`agent` → `["v2e","ansible"]`.
  - `ssh_password_authentication: false`, `ssh_permit_root_login: "no"`, `sftp_enabled: true`.
  - `ssh_client_alive_interval`/`count_max` to match current intent (300 / 2).
  - Session-safe: devsec validates + reloads; no session drop.
- **`devsec.hardening.os_hardening`** — sysctl/kernel hardening:
  - Preserve Docker networking: `sysctl_overwrite: { 'net.ipv4.ip_forward': 1 }` on `linux`.
  - Keep `os_hardening`'s defaults otherwise; do NOT enable measures that break the workload
    (no auditd changes here — that's ANS-6; no password-aging surprises for service accounts).
  - Confirm it doesn't clamp anything the current sysctl drop-in intentionally set
    (rp_filter, syncookies, redirects, kptr/dmesg restrict are all in os_hardening's set).
- **`fail2ban` role (new, small)** — carry over the existing sshd jail (systemd backend) so
  brute-force protection survives the swap. Toggle `fail2ban_enabled` (default true).
- **Retire the drop-ins:**
  - Delete `roles/deb_hardening_basic` and remove its reference from `01-bootstrap.yml`.
  - `v2e-tf`: remove the `60-v2e.conf` `write_files` block (and its `systemctl restart ssh`
    runcmd if now dead) from `cloud-init/node.yaml.tftpl`; keep `ssh_pwauth: false` and user
    creation. This is the paired cross-repo edit (own branch/commit in `v2e-tf`).

### 3. Wiring
`01-bootstrap.yml` becomes: `ping` → `health_check` → `baseline` →
`devsec.hardening.os_hardening` → `devsec.hardening.ssh_hardening` → `fail2ban`.
(`devsec` roles need `become`; keep the play `become: true`.)

## Testing

**Static (now):**
- `ansible-lint` → 0 failures (production profile), including the new roles.
- `ansible-playbook --syntax-check site.yml`.
- `ansible-playbook --check site.yml` resolves (unreachable acceptable; no role/plugin errors).
- `requirements.yml` already pins `devsec.hardening >=10,<11` (ANS-1) — confirm it installs.

**Live-env behavioral test plan (run at next Proxmox apply, with Proxmox-console rollback ready):**
1. `sshd -T` on each node shows `passwordauthentication no`, `permitrootlogin no`,
   `allowusers` == expected set, `subsystem sftp` present.
2. `sysctl net.ipv4.ip_forward` == `1` on all linux nodes.
3. From control, `ansible all -m ansible.builtin.copy` (a temp file) succeeds → SFTP path intact.
4. Inter-VLAN: control reaches services+agent:22; a container on services reaches the internet
   and another container (forwarding intact) — validated once ANS-3 Docker lands.
5. **No lockout:** `v2e`/`ansible` sessions survive; a fresh SSH login as each allowed user
   succeeds; console fallback verified available before apply.

## Risks / mitigations
- **SSH lockout (highest):** `AllowUsers` preserved exactly; `sftp_enabled: true`; devsec's
  validate-then-reload; a `--check` diff reviewed before apply; Proxmox console as rollback.
- **Docker networking break:** `ip_forward=1` explicitly preserved; verified in the live plan
  before/with ANS-3.
- **Double-ownership window:** cloud-init drop-in retired in the SAME change set as the devsec
  swap; only the ansible-side owns `sshd_config` after apply.
- **fail2ban regression:** preserved as its own role rather than dropped.

## Cross-repo coordination
- `v2e-ansible`: health_check, devsec swap, fail2ban role, delete deb_hardening_basic, group_vars.
- `v2e-tf`: retire `60-v2e.conf` in `cloud-init/node.yaml.tftpl` (separate branch/commit;
  reference this spec). Must land together with the ansible change for single-ownership.
