# ANS-1 — Ansible Structure + Skeleton (design)

**Date:** 2026-06-30
**Repo:** `v2e-ansible`
**Branch:** `refactor/ansible-structure` (off `ai-agents`)
**Master-plan phase:** ANS-1 · depends on TF-1 · upstream of ANS-2/ANS-3
**Status:** approved design → implementation plan next

## Purpose

Lay down the clean, target directory structure for the v2e Ansible layer as a
**pure skeleton**: a thin `site.yml` that statically imports three ordered phase
playbooks, standalone tag-gated operational playbooks, a declared `requirements.yml`,
an `ansible.cfg` prepared for later phases (SOPS, SFTP, collections), and two
scaffolded roles (`health_check`, `dev-tools`).

This is a **clean start** — nothing is in production. Existing role/playbook bodies
(`baseline`, `deb-hardening-basic`, vendored `docker`, `ai-*`, `killswitch`, `patch`,
`vyos-hardening-basic`) are treated as **transitional placeholders**: wired into the
new structure only so a `--check` dry-run stays green. They are explicitly slated to
be replaced or merged by later phases and carry no requirement to be preserved
verbatim:

- ANS-2 replaces `deb-hardening-basic` with `devsec.hardening` and folds `baseline`
  into `01-bootstrap`; fills in `health_check` + `dev-tools`.
- ANS-3 replaces the vendored `docker` role with pinned `geerlingguy.docker`.

**Out of scope for ANS-1:** any role-body swap, `devsec.hardening` wiring, docker
swap, SOPS secret content, Tailscale, Molecule/CI. Structure only.

## Target structure

```
v2e-ansible/
├── ansible.cfg                  # + collections_path, SOPS vars plugin, sftp transfer
├── requirements.yml             # declared Galaxy deps (installed/used by later phases)
├── README.md                    # run commands updated for new playbook paths
├── site.yml                     # thin orchestrator: import_playbook 01 → 02 → 03
├── inventory/
│   └── hosts.ini                # unchanged (control/services/agent/vyos already correct)
├── playbooks/
│   ├── 01-bootstrap.yml         # hosts: linux   — ping → health_check → baseline → deb-hardening-basic
│   ├── 02-services.yml          # hosts: services — docker (vendored, untouched)
│   ├── 03-applications.yml      # hosts: linux/agent — ai-identities → ai-workbench
│   └── ops/                     # standalone, operator-run, tag-gated (NOT in site.yml)
│       ├── killswitch.yml       # hosts: vyos — tags cut/allow/cut-hard (+never)
│       ├── patch.yml            # hosts: linux — tags patch
│       ├── vyos-hardening.yml   # hosts: vyos — tags vyos
│       ├── agents.yml           # hosts: linux/agent — operator-initiated ai provisioning
│       └── task-agent.yml       # hosts: agent — one-shot agent task
└── roles/
    ├── health_check/            # NEW scaffold (no-op task, defaults, README)
    ├── dev-tools/               # NEW scaffold (no-op task, defaults, README)
    ├── baseline/                # unchanged (folded into bootstrap at ANS-2)
    ├── deb-hardening-basic/     # unchanged (replaced by devsec.hardening at ANS-2)
    ├── docker/                  # unchanged vendored (replaced by geerlingguy at ANS-3)
    ├── ai-identities/           # unchanged
    ├── ai-workbench/            # unchanged
    ├── killswitch/              # unchanged
    ├── patch/                   # unchanged
    └── vyos-hardening-basic/    # unchanged
```

## Changes in detail

### 1. Git hygiene (first commit)
- Delete the stray `v2e-tf.git/` bare repo (a misplaced mirror of the separate
  `v2e-tf` project; currently **not** gitignored, so it would otherwise be committed
  into `v2e-ansible`). The real `v2e-tf` lives at `../v2e-tf`.

### 2. `site.yml` → thin orchestrator
```yaml
---
- import_playbook: playbooks/01-bootstrap.yml
- import_playbook: playbooks/02-services.yml
- import_playbook: playbooks/03-applications.yml
```
- `import_playbook` paths are relative to `site.yml` (repo root). Roles continue to
  resolve via `roles_path`, so no role path changes.

### 3. Phase playbooks (carved from today's inline `site.yml`)
- `01-bootstrap.yml` — `hosts: linux`: smoke `ansible.builtin.ping` → `health_check`
  (scaffold, no-op) → `baseline` → `deb-hardening-basic`. Health check is first so it
  gates later phases (fail-fast); real assertions land in ANS-2.
- `02-services.yml` — `hosts: services`: `docker` (vendored geerlingguy, unchanged),
  keeping the current `docker_install_compose_plugin: true` var.
- `03-applications.yml` — `ai-identities` on `linux`, `ai-workbench` on `agent`.

### 4. Operational playbooks → `playbooks/ops/`, standalone + tag-gated
- `killswitch.yml`, `agents.yml`, `task-agent.yml` — moved from repo root, content
  unchanged.
- `patch.yml` (new) — extracted from the `--tags patch` play in `site.yml`;
  `hosts: linux`, `tags: [patch]`. Runs the existing `patch` role.
- `vyos-hardening.yml` (new) — extracted from the `--tags vyos` play; `hosts: vyos`,
  network_cli, `tags: [vyos]`. Runs the existing `vyos-hardening-basic` role.
- None of these are imported by `site.yml`. `v2e-tf` cloud-init only runs
  `ansible-playbook site.yml`, so moving them breaks no cross-repo call.
- Update run commands in `README.md` (and any role READMEs that cite the old paths).

### 5. `requirements.yml` (declared only; nothing installed/used this branch)
- roles: `geerlingguy.docker`, `artis3n.tailscale`
- collections: `community.docker` (>=3), `devsec.hardening` (10.x), `community.sops`
- **Version note:** the master plan pins `geerlingguy.docker` 7.x, but the vendored
  copy is 8.0.0. Pin per the plan here and flag reconciliation at ANS-3 (the actual
  docker swap) rather than silently diverging.

### 6. `ansible.cfg` additions
- `collections_path` (alongside existing `roles_path`).
- Enable the SOPS vars plugin: `vars_plugins_enabled = host_group_vars,community.sops.sops`.
- SFTP-compatible transfer: `ssh_transfer_method = sftp` under `[ssh_connection]`
  (pairs with `devsec.hardening`'s `sftp_enabled: true` in ANS-2).
- Keep existing `host_key_checking = False`, `become` settings.

### 7. Scaffold two roles
- `roles/health_check/` and `roles/dev-tools/`, each with `tasks/main.yml` (a single
  no-op `ansible.builtin.debug` so syntax-check + `ansible-lint` pass), `defaults/main.yml`,
  and a short `README.md` stating the role's ANS-2 purpose.
- `health_check` is wired into `01-bootstrap`. `dev-tools` is created but left
  unwired (ANS-2 decides placement: control, optionally other nodes).

## Acceptance / verification

- `ansible-playbook --syntax-check site.yml` passes.
- `ansible-lint` passes (no new violations).
- `ansible-playbook --check site.yml` dry-run resolves all plays/roles.
- `playbooks/ops/killswitch.yml`, `playbooks/ops/patch.yml`, and
  `playbooks/ops/vyos-hardening.yml` each resolve standalone (syntax-check).
- `git status` shows `v2e-tf.git/` gone and no bare-repo artifacts staged.

## Notes for later phases
- ANS-2: fill `health_check` (mesh `wait_for_connection`, disk/mem asserts, inter-VLAN
  reachability, fail-fast); swap `deb-hardening-basic` → `devsec.hardening`
  (`sftp_enabled: true`, `ip_forward=1` preserved, retire cloud-init `60-v2e.conf`);
  fill `dev-tools` + add `terminal-polish`; fold `baseline` in (drop qemu-guest-agent,
  now baked by Packer).
- ANS-3: swap vendored `docker` → pinned `geerlingguy.docker` + `community.docker`
  `docker_compose_v2`; reconcile the 7.x/8.0.0 pin.
