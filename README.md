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

Ansible itself is installed on control via `pipx install --include-deps ansible`
(user-isolated, full bundle incl. community collections) by the cloud-init
bootstrap — not apt.

## What `site.yml` does

```
ping (smoke test)  ->  baseline (all)  ->  patch (on demand)  ->  docker (services)
```

- **smoke test** — `ping` every node; proves the automation mesh is reachable.
- **baseline** (`roles/baseline`) — qemu-guest-agent, time sync, timezone,
  journald disk cap, and unattended-upgrades as a **security-only, no-reboot**
  safety net. Pure `ansible.builtin`.
- **patch** (`roles/patch`) — on-demand full `dist-upgrade` + reboot-if-required,
  controller-safe. **Tag-gated**: skipped by default, runs only with `--tags patch`.
- **docker** (`roles/docker`, vendored geerlingguy.docker) — Docker CE + Compose
  v2 on `services`.

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
ansible-playbook site.yml                 # baseline + docker (patch is skipped)
ansible-playbook playbooks/ops/patch.yml  # on-demand full patch + reboot-if-needed
```

## Layout

```
ansible.cfg                        # inventory + roles_path, sudo defaults
inventory/hosts.ini                # control (local) + services (SSH as ansible)
requirements.yml                   # Galaxy sources (docker vendored; replaced in ANS-3)
site.yml                           # thin orchestrator — imports the three phase playbooks
playbooks/01-bootstrap.yml         # smoke test + health_check + baseline + deb hardening
playbooks/02-services.yml          # Docker CE + Compose on services node
playbooks/03-applications.yml      # AI-agent identities + workbench on agent node
playbooks/ops/killswitch.yml       # VyOS cut/allow/cut-hard for the agent subnet (tag-gated)
playbooks/ops/patch.yml            # on-demand full dist-upgrade + reboot-if-required
playbooks/ops/vyos-hardening.yml   # VyOS router hardening (network_cli, operator-run)
playbooks/ops/agents.yml           # provision AI-agent identities + workbench (operator-run)
playbooks/ops/task-agent.yml       # task an AI agent from control
roles/baseline/                    # OS baseline (ansible.builtin only)
roles/deb_hardening_basic/         # SSH + sysctl + fail2ban hardening for Debian/Ubuntu
roles/dev_tools/                   # developer CLI toolset (ANS-1 scaffold, wired in ANS-2)
roles/health_check/                # fail-fast reachability + sanity assertions
roles/patch/                       # on-demand full patch (ansible.builtin only)
roles/ai_identities/               # per-AI Unix accounts + SSH mesh + NOPASSWD sudo
roles/ai_workbench/                # Node.js, Claude Code, Codex, superpowers, agent-run
roles/vyos_hardening_basic/        # VyOS key-only SSH + syslog + commit-confirm hardening
roles/docker/                      # vendored geerlingguy.docker (replaced wholesale in ANS-3)
roles/killswitch/                  # VyOS cut/allow/cut-hard for the agent subnet
```

## Agents & kill switch

Separate from the unattended `site.yml` first-boot run, these are **deliberate
operator actions**, run from control as the `ansible` user.

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

### Secrets (Ansible Vault)

`ai_workbench` reads API keys from vault; empty = skip auth (log in interactively
later). Put them in an encrypted file referenced by the inventory, e.g.
`inventory/group_vars/all/vault.yml`:

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
