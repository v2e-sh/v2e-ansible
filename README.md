# v2e-ansible

Phase-2 automation for the v2e homelab. Cloned to `~ansible/ansible` on the
**control** node by cloud-init at first boot and run as the `ansible` automation
account (NOPASSWD sudo on every node; the mesh SSH key + `~/.ssh/config` are
provisioned by Terraform in v2e-tf).

## Execution model

Ansible runs **from control**. control manages itself over a local connection;
other nodes are reached by direct SSH as the `ansible` user.

| Host       | Reached via                                     |
|------------|-------------------------------------------------|
| `control`  | local — `ansible_connection=local`              |
| `services` | direct SSH from control → 10.1.2.10 (`ansible`) |
| `agent`    | direct SSH from control → 10.1.3.10 (`ansible`) |
| `infra`    | direct SSH from control → 10.1.0.10 (`ansible`) |

Ansible itself is installed on control via `pipx install --include-deps ansible`
(user-isolated, full bundle incl. community collections) by the cloud-init
bootstrap — not apt.

## What `site.yml` does

`site.yml` statically imports six phase playbooks, in order:

```
01-bootstrap  ->  02-services  ->  03-applications  ->  04-infra  ->  05-tailscale  ->  06-control-desktop
```

- **01-bootstrap** (`hosts: linux`) — `ping` smoke test, then `health_check`
  (fail-fast gate), `baseline` (qemu-guest-agent, time sync, timezone, journald
  disk cap, unattended-upgrades as a **security-only, no-reboot** safety net —
  pure `ansible.builtin`), `devsec.hardening.os_hardening` + `.ssh_hardening`,
  and `fail2ban`.
- **02-services** (`hosts: services`) — `geerlingguy.docker` (Docker CE + Compose
  v2), then `compose_stack` (the v2e-compose stacks).
- **03-applications** (`hosts: agent`) — `ai_identities` + `ai_workbench` (AI
  agent accounts + Claude Code/Codex workbench), already run unattended here —
  see [Agents & kill switch](#agents--kill-switch) for the wider operator-run
  variant.
- **04-infra** (`hosts: infra`) — Docker + `compose_stack` (Technitium DNS,
  RustDesk relay) + `technitium_zone` (internal DNS records).
- **05-tailscale** (`hosts: control:infra`) — Tailscale mesh + exit-node
  advertisement.
- **06-control-desktop** — autologin, resolver, RustDesk client on `control`.

**On-demand full patch** — `roles/patch` runs a full `dist-upgrade` +
reboot-if-required, controller-safe. It is **not** part of `site.yml`
(`site.yml`'s header says operational playbooks are run explicitly from
`playbooks/ops/`) — invoke it directly:
`ansible-playbook playbooks/ops/patch.yml`.

### OS patching layers

1. **First boot (once)** — cloud-init `package_upgrade` + `package_reboot_if_required`
   (in v2e-tf) run a full `dist-upgrade` *before* Ansible starts, so Ansible always
   sees a patched system.
2. **Ongoing security (autonomous)** — unattended-upgrades, security-only, no
   auto-reboot (baseline role).
3. **On-demand full patch** — `ansible-playbook playbooks/ops/patch.yml` (patch role).

## Run it manually (on control)

```bash
cd ~/ansible
ansible all -m ping                       # connectivity
ansible-playbook site.yml                 # runs all six phases (bootstrap -> services -> applications -> infra -> tailscale -> control-desktop)
ansible-playbook playbooks/ops/patch.yml  # on-demand full patch + reboot-if-needed
```

## Layout

```
ansible.cfg                        # inventory + roles_path, sudo defaults; community.sops vars plugin
inventory/hosts.ini                # control (local) + services/agent/infra (SSH as ansible) + vyos (network_cli)
requirements.yml                   # Galaxy sources, pinned exact (geerlingguy.docker, artis3n.tailscale, collections)
site.yml                           # thin orchestrator — imports the six phase playbooks
playbooks/01-bootstrap.yml         # smoke test + health_check + baseline + devsec.hardening (OS/SSH) + fail2ban
playbooks/02-services.yml          # geerlingguy.docker + compose_stack on services node
playbooks/03-applications.yml      # ai_identities + ai_workbench on agent node
playbooks/04-infra.yml             # Docker + compose_stack + technitium_zone on infra node
playbooks/05-tailscale.yml         # Tailscale mesh + exit-node advertisement (control + infra)
playbooks/06-control-desktop.yml   # autologin, resolver, RustDesk client on control
playbooks/ops/killswitch.yml       # VyOS cut/allow/cut-hard for the agent subnet (tag-gated)
playbooks/ops/patch.yml            # on-demand full dist-upgrade + reboot-if-required
playbooks/ops/vyos-hardening.yml   # VyOS router hardening (network_cli, operator-run)
playbooks/ops/agents.yml           # provision AI-agent identities + workbench on every Linux node (operator-run)
playbooks/ops/task-agent.yml       # task an AI agent from control
playbooks/ops/agent-access.yml     # bounded agent-VLAN -> control:22 access window (tag-gated)
playbooks/ops/backup-estate.yml    # file-level estate backup (tag-gated)
playbooks/ops/egress-tap.yml       # bounded egress capture on the agent node (tag-gated)
playbooks/ops/health-check.yml     # standalone reachability + sanity assertions
playbooks/ops/add-user.yml         # add an ad-hoc Unix user
roles/baseline/                    # OS baseline (ansible.builtin only)
roles/health_check/                # fail-fast reachability + sanity assertions
roles/patch/                       # on-demand full patch (ansible.builtin only)
roles/fail2ban/                    # fail2ban jail config (retired the old deb_hardening_basic role)
roles/ai_identities/               # per-AI Unix accounts + SSH mesh + NOPASSWD sudo
roles/ai_workbench/                # Node.js, Claude Code, Codex, superpowers, agent-run
roles/compose_stack/               # renders + deploys the v2e-compose stacks from SOPS group_vars
roles/vyos_hardening_basic/        # VyOS key-only SSH + syslog + commit-confirm hardening
roles/killswitch/                  # VyOS cut/allow/cut-hard for the agent subnet
roles/agent_access/                # bounded agent-VLAN -> control:22 access window
roles/backup_estate/               # file-level estate backup (design; not yet applied)
roles/egress_tap/                  # bounded egress capture on the agent node
roles/tailscale/                   # Tailscale mesh + exit-node advertisement
roles/technitium_zone/             # internal DNS zone records on infra's Technitium
roles/control_desktop/             # control-node autologin + resolver config
roles/rustdesk_client/             # RustDesk client on control
```

## Agents & kill switch

`site.yml`'s **03-applications** phase already runs `ai_identities` + `ai_workbench`
unattended, scoped to the `agent` host. The commands below are the wider,
**deliberate operator actions** — `playbooks/ops/agents.yml` targets every Linux
node (`hosts: linux`), including `control` — run from control as the `ansible` user.

```bash
ansible-playbook playbooks/ops/agents.yml                              # create AI identities + build the workbench
ansible-playbook playbooks/ops/task-agent.yml -e agent=claude -e 'task=Summarise the repo'
ansible-playbook playbooks/ops/killswitch.yml --tags cut              # surgical cut of the agent subnet
ansible-playbook playbooks/ops/killswitch.yml --tags allow            # restore
ansible-playbook playbooks/ops/killswitch.yml --tags cut-hard         # disable the agent VLAN interface
```

- **`agents.yml`** — `ai_identities` creates `claude` + `codex` accounts (root via
  NOPASSWD sudo) on every Linux node with an SSH mesh keyed from the agent node;
  `ai_workbench` installs Claude Code + Codex + the `superpowers` plugin on the
  agent node and an `agent-run` headless wrapper.
- **`task-agent.yml`** — runs `agent-run <agent> "<task>"` on the agent node as the
  chosen AI account and returns its output. Long jobs: wrap in `tmux`/`systemd-run`.
- **`killswitch.yml`** — tag-gated (`cut`/`allow`/`cut-hard`); a tagless run does
  nothing on purpose. The `cut` keeps `control`↔`agent` SSH alive for recovery.

### Secrets (SOPS)

`ai_workbench` reads API keys from the `vault_*`-prefixed variables; empty = skip
auth (log in interactively later). Secrets are SOPS-encrypted, not Ansible Vault —
put them in `secrets.sops.yaml`, which lands as `inventory/group_vars/all.sops.yaml`
and is auto-decrypted by the `community.sops.sops` vars plugin (`ansible.cfg`):

```yaml
vault_anthropic_api_key: "sk-ant-..."
vault_openai_api_key: "sk-..."
```

### ⚠️ Kill-switch integrity

The AI accounts get **root on `control`**, and control holds the `ansible`/`v2e`
SSH keys that reach the VyOS router. So a rooted agent on control can SSH to the
router and re-open its own kill switch — **the switch is not tamper-proof against a
control-resident agent.** Mitigations:

1. Operate the kill switch **out-of-band** — from the Mac (router WAN SSH / Proxmox
   console), not via an agent-reachable path.
2. Later phase: retire the `ansible`/`v2e` keys from the router's authorized_keys
   and keep router-admin keys **only on the Mac**. The AI mesh already excludes the
   router by design.
