# vyos_hardening_basic

General, minimal hardening for a VyOS router (1.4 sagitta / 1.5 circinus), applied
via the `vyos.vyos` collection over `network_cli`. No topology/firewall specifics —
those are baked at `tofu apply` time (Terraform's rendered cloud-init), not
day-2 Ansible; see `v2e-docs/docs/system/networking.md`.

> **Prerequisite:** the management user's SSH public key must already be authorized
> on the router (Terraform seeds the mesh keys). This role enables **key-only** SSH,
> so a missing/mismatched key = lockout. Keep the Proxmox serial console as
> out-of-band recovery.

What it sets (override `vyos_hardening_lines` / vars in `defaults/main.yml`):
- `service ssh disable-password-authentication` (key-only)
- `service ssh client-keepalive-interval` / `disable-host-validation` / `loglevel`
- `system config-management commit-confirm action reload` — makes confirmed-commit
  non-disruptive (reload, not reboot), so later risky changes can use
  commit-confirm safely.
- pre-login banner.

Every change here is safe over an existing key-based session (none drop your
connection), so a plain commit is fine. **Connectivity-breaking changes (firewall,
listen-address, ciphers, dynamic-protection) are Terraform/cloud-init concerns,
not this role's.**

## Run (on demand, from control)

```bash
ansible-playbook playbooks/ops/vyos-hardening.yml
```

`network_cli` needs `ansible-pylibssh` (or paramiko) in the Ansible venv — the
v2e-tf bootstrap injects it on control (`pipx inject ansible ansible-pylibssh`).
