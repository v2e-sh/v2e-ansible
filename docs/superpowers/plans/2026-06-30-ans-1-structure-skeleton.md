# ANS-1 Structure + Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `v2e-ansible` into a clean, testable skeleton — a thin `site.yml` importing three ordered phase playbooks, standalone tag-gated operational playbooks under `playbooks/ops/`, declared `requirements.yml`, a phase-ready `ansible.cfg`, and two scaffolded roles — without changing any role behaviour.

**Architecture:** `site.yml` becomes a pure orchestrator (`import_playbook` of `01-bootstrap` → `02-services` → `03-applications`). Today's inline plays are carved into those phase files; the on-demand `patch`/`vyos` plays and the existing standalone playbooks move to `playbooks/ops/`. Existing roles are wired in **unchanged** as transitional placeholders so a `--check` dry-run stays green; ANS-2/ANS-3 replace the bodies.

**Tech Stack:** Ansible (ansible-core), `ansible-lint`, `ansible-galaxy`, vyos.vyos + community.sops/community.docker/devsec.hardening collections (declared, installed to a gitignored path for verification only).

## Global Constraints

- Branch: `refactor/ansible-structure` (already created off `ai-agents`).
- **Pure skeleton** — no role-body swaps, no devsec/geerlingguy wiring, no SOPS secret content. Structure only.
- Existing role **task logic** is left unchanged. The one exception (Task 8, lint cleanup) is mechanical: the 5 hyphenated role directories are renamed to underscores (`ai-identities`→`ai_identities`, `ai-workbench`→`ai_workbench`, `deb-hardening-basic`→`deb_hardening_basic`, `dev-tools`→`dev_tools`, `vyos-hardening-basic`→`vyos_hardening_basic`) with references updated — no behavioural edits to their tasks.
- The vendored `roles/docker` (upstream geerlingguy, replaced wholesale by the Galaxy role in ANS-3) is **excluded from lint**, not hand-edited — you don't lint a vendored dependency.
- `import_playbook` paths are relative to `site.yml` (repo root); roles resolve via `roles_path`.
- Galaxy deps are **declared only**; verified installable to a throwaway temp dir — nothing installed is committed. Every collection ANS-1 references at runtime (`vyos.vyos`, `ansible.netcommon`, `community.sops`, `community.docker`) already ships with the host's `ansible` package and is always searched regardless of `collections_path`, so **no** local install and **no** `collections_path` override are needed. Do not set `collections_path`.
- Git: short commit messages, no attribution trailer (user convention).
- Acceptance for the whole plan: `ansible-playbook --syntax-check site.yml` and `ansible-playbook --check site.yml` pass; the three `playbooks/ops/` router/patch playbooks resolve standalone; `v2e-tf.git/` is gone; and after Task 8, repo-wide `ansible-lint` reports **0 failures** (with `roles/docker` excluded as vendored). The linter environment must have `vyos.vyos` + `ansible.netcommon` available (install into `~/.ansible/collections` if using an isolated ansible-lint) so `vyos.vyos.vyos_config` resolves.

---

### Task 1: Git hygiene — remove stray bare repo, add `.gitignore`

**Files:**
- Delete: `v2e-tf.git/` (stray bare mirror of the separate `v2e-tf` project)
- Create: `.gitignore`

- [ ] **Step 1: Confirm the stray repo is untracked and unignored**

Run: `git -C /Users/alex/Documents/v2e-environment/v2e-ansible status --porcelain v2e-tf.git | head`
Expected: a line beginning `??` (untracked), confirming it is not part of history.

- [ ] **Step 2: Delete the stray bare repo**

```bash
cd /Users/alex/Documents/v2e-environment/v2e-ansible
rm -rf v2e-tf.git
```

- [ ] **Step 3: Create `.gitignore`**

```gitignore
# Ansible runtime + local galaxy-install noise. Deps are declared in
# requirements.yml and installed by CI / control cloud-init in later phases —
# never committed here.
*.retry
__pycache__/
.galaxy/
```

- [ ] **Step 4: Verify the stray repo is gone and nothing bare remains**

Run: `ls -d v2e-tf.git 2>&1; git status --porcelain | grep -c 'v2e-tf.git'`
Expected: `ls` reports "No such file or directory"; the grep count is `0`.

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore: drop stray v2e-tf.git mirror; add .gitignore"
```

---

### Task 2: Declare Galaxy dependencies in `requirements.yml`

**Files:**
- Modify: `requirements.yml` (currently `roles: []`)

**Interfaces:**
- Produces: a `requirements.yml` installable by `ansible-galaxy install -r requirements.yml`. Not consumed at runtime in ANS-1 — the collections it names already ship with the host `ansible` package; this file is the manifest CI / control cloud-init install from in later phases.

- [ ] **Step 1: Write `requirements.yml`** (version pins verified against Galaxy 2026-06-30)

```yaml
---
# Galaxy dependencies for v2e-ansible. Declared here for later phases; installed by
# CI / control cloud-init via:  ansible-galaxy install -r requirements.yml
#
# NOTE: geerlingguy.docker is pinned to the 7.x line per the master plan, while
# roles/docker is a vendored 8.0.0 copy. Reconcile at ANS-3 (the docker swap).
roles:
  - name: geerlingguy.docker
    version: "7.9.0"
  - name: artis3n.tailscale
    version: "v5.0.1"

collections:
  - name: community.docker
    version: ">=3.0.0"
  - name: devsec.hardening
    version: ">=10.0.0,<11.0.0"
  - name: community.sops
    version: ">=1.6.0"
```

- [ ] **Step 2: Verify the whole file resolves (install to a throwaway temp dir, nothing committed)**

Run:
```bash
TMP=$(mktemp -d)
ansible-galaxy install -r requirements.yml --roles-path "$TMP/roles" \
  && ansible-galaxy collection install -r requirements.yml -p "$TMP/collections"
echo "resolved rc=$?"; rm -rf "$TMP"
```
Expected: both complete without error and `resolved rc=0` (proves every pin exists). The temp dir is discarded — nothing lands in the repo.

If a **role** version is rejected as non-existent, list the real tags and correct the pin, then re-run:
```bash
curl -s "https://galaxy.ansible.com/api/v1/roles/?owner__username=geerlingguy&name=docker" | python3 -c "import sys,json;print([v['name'] for v in json.load(sys.stdin)['results'][0]['summary_fields']['versions'][:10]])"
```

- [ ] **Step 3: Confirm only `requirements.yml` changed**

Run: `git status --porcelain`
Expected: shows only `requirements.yml` modified (no `.galaxy/`, no temp artifacts).

- [ ] **Step 4: Commit**

```bash
git add requirements.yml
git commit -m "deps: declare galaxy roles/collections for later phases"
```

---

### Task 3: Extend `ansible.cfg` for later phases (SOPS vars plugin, SFTP)

**Files:**
- Modify: `ansible.cfg`

**Interfaces:**
- Consumes: `community.sops` from the bundled `ansible` package collections (always searched; no install needed).
- Produces: the SOPS vars plugin enabled and SFTP transfer set. `collections_path` is deliberately NOT set (bundled collections resolve without it; overriding it adds nothing).

- [ ] **Step 1: Verify the SOPS vars plugin is currently NOT enabled**

Run: `ansible-config dump --only-changed 2>/dev/null | grep -i vars_plugins_enabled || echo "not set"`
Expected: `not set`.

- [ ] **Step 2: Write the updated `ansible.cfg`**

```ini
[defaults]
inventory = inventory/hosts.ini
roles_path = roles
host_key_checking = False
retry_files_enabled = False
stdout_callback = default
result_format = yaml
# SOPS-encrypted group/host vars are auto-decrypted by the community.sops vars
# plugin (used from ANS-2). host_group_vars stays enabled for plain vars.
# community.sops ships with the ansible package, so no collections_path is needed.
vars_plugins_enabled = host_group_vars,community.sops.sops

[privilege_escalation]
become = True
become_method = sudo

[ssh_connection]
# devsec.hardening (ANS-2) sets sftp_enabled: true; use SFTP for file transfer so
# Ansible copies keep working after hardening. (ini key is `transfer_method`; the
# ssh plugin option name is ssh_transfer_method.)
transfer_method = sftp
```

- [ ] **Step 3: Verify the config loads and the vars plugin resolves**

Run: `ansible-config dump --only-changed 2>&1 | grep -iE 'vars_plugins_enabled|transfer_method'`
Expected: shows `community.sops.sops` and `sftp` — with **no** "vars plugin not found" error above them.

- [ ] **Step 4: Smoke-check that a trivial local play still runs (plugin loads cleanly)**

Run: `ansible localhost -m ansible.builtin.ping -o 2>&1 | tail -1`
Expected: `localhost | SUCCESS => {"changed": false, "ping": "pong"}` (no vars-plugin traceback).

- [ ] **Step 5: Commit**

```bash
git add ansible.cfg
git commit -m "config: add collections_path, SOPS vars plugin, sftp transfer"
```

---

### Task 4: Scaffold `health_check` and `dev-tools` roles

**Files:**
- Create: `roles/health_check/tasks/main.yml`, `roles/health_check/defaults/main.yml`, `roles/health_check/README.md`
- Create: `roles/dev-tools/tasks/main.yml`, `roles/dev-tools/defaults/main.yml`, `roles/dev-tools/README.md`

**Interfaces:**
- Produces: role `health_check` (wired into `01-bootstrap` in Task 5) and role `dev-tools` (created, left unwired). Both are no-ops in ANS-1.

- [ ] **Step 1: Create `roles/health_check/tasks/main.yml`**

```yaml
---
# ANS-1 scaffold. ANS-2 fills this with the real fail-fast gate:
#   mesh wait_for_connection, disk/memory asserts, inter-VLAN reachability.
- name: Health check placeholder (ANS-1 scaffold — no assertions yet)
  ansible.builtin.debug:
    msg: "health_check: scaffold — real checks land in ANS-2"
```

- [ ] **Step 2: Create `roles/health_check/defaults/main.yml`**

```yaml
---
# Thresholds for ANS-2 (min free disk %, min free memory MB, VLANs to probe).
# Declared empty in ANS-1.
```

- [ ] **Step 3: Create `roles/health_check/README.md`**

```markdown
# health_check

Fail-fast preflight gate, run first in `01-bootstrap`. **ANS-1: scaffold only.**
ANS-2 adds mesh `wait_for_connection`, disk/memory asserts, and inter-VLAN
reachability so the rest of the run aborts early on an unhealthy node.
```

- [ ] **Step 4: Create `roles/dev-tools/tasks/main.yml`**

```yaml
---
# ANS-1 scaffold. ANS-2 installs the CLI toolset (ripgrep, fd, fzf, bat, eza, jq,
# yq, tmux, lazygit, zoxide, delta, hyperfine, tldr, dust, duf, btop, ncdu) on
# control (optionally other nodes). Left UNWIRED in ANS-1.
- name: Dev-tools placeholder (ANS-1 scaffold — installs nothing yet)
  ansible.builtin.debug:
    msg: "dev-tools: scaffold — toolset install lands in ANS-2"
```

- [ ] **Step 5: Create `roles/dev-tools/defaults/main.yml`**

```yaml
---
# ANS-2: dev_tools_packages list + target-node toggles. Declared empty in ANS-1.
```

- [ ] **Step 6: Create `roles/dev-tools/README.md`**

```markdown
# dev-tools

Developer CLI toolset for control (optionally other nodes). **ANS-1: scaffold
only, not wired into any phase playbook.** ANS-2 populates the package list and
decides placement.
```

- [ ] **Step 7: Verify both roles lint clean**

Run: `ansible-lint roles/health_check roles/dev-tools`
Expected: passes with no errors (warnings about `debug` are acceptable; no failures).

- [ ] **Step 8: Commit**

```bash
git add roles/health_check roles/dev-tools
git commit -m "roles: scaffold health_check and dev-tools (no-op)"
```

---

### Task 5: Create the three phase playbooks

**Files:**
- Create: `playbooks/01-bootstrap.yml`, `playbooks/02-services.yml`, `playbooks/03-applications.yml`

**Interfaces:**
- Consumes: roles `health_check` (Task 4), `baseline`, `deb-hardening-basic`, `docker`, `ai-identities`, `ai-workbench` (existing).
- Produces: three playbooks imported by `site.yml` in Task 7.

- [ ] **Step 1: Create `playbooks/01-bootstrap.yml`**

```yaml
---
# Phase 01 — bootstrap: reachability + baseline OS + basic hardening on every
# Linux node. Imported first by site.yml; health_check runs first as the
# fail-fast gate (real assertions arrive in ANS-2).

- name: Smoke test — confirm the automation mesh can reach every node
  hosts: linux
  gather_facts: false
  tasks:
    - name: Ping all managed hosts
      ansible.builtin.ping:

- name: Health checks (fail-fast gate)
  hosts: linux
  become: true
  roles:
    - health_check

- name: Baseline configuration on all Linux nodes
  hosts: linux
  become: true
  roles:
    - baseline

- name: Basic system hardening on all Linux nodes
  hosts: linux
  become: true
  roles:
    - deb-hardening-basic
```

- [ ] **Step 2: Create `playbooks/02-services.yml`**

```yaml
---
# Phase 02 — services: container runtime on the services node.
# Vendored docker role unchanged (geerlingguy swap is ANS-3).

- name: Install Docker on the services host
  hosts: services
  become: true
  roles:
    - role: docker
      vars:
        # Keep the Compose v2 plugin (`docker compose ...`) installed.
        docker_install_compose_plugin: true
```

- [ ] **Step 3: Create `playbooks/03-applications.yml`**

```yaml
---
# Phase 03 — applications: AI-agent identities (all Linux) + workbench (agent).

- name: AI-agent identities across all Linux nodes
  hosts: linux
  become: true
  roles:
    - ai-identities

- name: AI workbench on the agent node
  hosts: agent
  become: true
  roles:
    - ai-workbench
```

- [ ] **Step 4: Verify each phase playbook is syntactically valid**

Run:
```bash
for p in playbooks/01-bootstrap.yml playbooks/02-services.yml playbooks/03-applications.yml; do
  echo "== $p =="; ansible-playbook --syntax-check "$p"; done
```
Expected: each prints its play list with no error (roles resolve via `roles_path`).

- [ ] **Step 5: Commit**

```bash
git add playbooks/01-bootstrap.yml playbooks/02-services.yml playbooks/03-applications.yml
git commit -m "playbooks: carve site.yml into 01/02/03 phase playbooks"
```

---

### Task 6: Move and create the standalone operational playbooks

**Files:**
- Move: `killswitch.yml` → `playbooks/ops/killswitch.yml`
- Move: `agents.yml` → `playbooks/ops/agents.yml`
- Move: `task-agent.yml` → `playbooks/ops/task-agent.yml`
- Create: `playbooks/ops/patch.yml`, `playbooks/ops/vyos-hardening.yml`
- Modify: `README.md` (run-command paths)

**Interfaces:**
- Consumes: roles `killswitch`, `patch`, `vyos-hardening-basic`, `ai-identities`, `ai-workbench` (existing).
- Produces: five standalone playbooks under `playbooks/ops/`, none imported by `site.yml`.

- [ ] **Step 1: Move the three existing standalone playbooks (preserve history)**

```bash
mkdir -p playbooks/ops
git mv killswitch.yml playbooks/ops/killswitch.yml
git mv agents.yml     playbooks/ops/agents.yml
git mv task-agent.yml playbooks/ops/task-agent.yml
```

- [ ] **Step 2: Create `playbooks/ops/patch.yml`** (carved from the `--tags patch` play)

```yaml
---
# Standalone operational — orchestrated full patch. Run explicitly from control:
#   ansible-playbook playbooks/ops/patch.yml            # patch all Linux nodes
#   ansible-playbook playbooks/ops/patch.yml --tags patch --limit services
# Reboots only nodes that need it, never the controller (see roles/patch).

- name: Orchestrated full patch
  hosts: linux
  become: true
  tags:
    - patch
  roles:
    - patch
```

- [ ] **Step 3: Create `playbooks/ops/vyos-hardening.yml`** (carved from the `--tags vyos` play)

```yaml
---
# Standalone operational — VyOS router hardening (network_cli). Run explicitly:
#   ansible-playbook playbooks/ops/vyos-hardening.yml
#   ansible-playbook playbooks/ops/vyos-hardening.yml --tags vyos
# Every line in the role is safe over a key-based session (see roles/vyos-hardening-basic).

- name: VyOS router hardening
  hosts: vyos
  gather_facts: false
  tags:
    - vyos
  roles:
    - vyos-hardening-basic
```

- [ ] **Step 4: Update run-command paths in `README.md`**

Find every `ansible-playbook killswitch.yml`, `ansible-playbook agents.yml`, `ansible-playbook task-agent.yml`, and any `site.yml --tags patch` / `site.yml --tags vyos` reference, and repoint them:

```bash
grep -rnE 'ansible-playbook (killswitch|agents|task-agent)\.yml|site\.yml --tags (patch|vyos)' README.md
```
Then edit each hit to the new path, e.g.:
- `ansible-playbook killswitch.yml --tags cut` → `ansible-playbook playbooks/ops/killswitch.yml --tags cut`
- `ansible-playbook site.yml --tags patch` → `ansible-playbook playbooks/ops/patch.yml`
- `ansible-playbook site.yml --tags vyos` → `ansible-playbook playbooks/ops/vyos-hardening.yml`

Expected after re-running the grep: no stale root-level `killswitch.yml`/`agents.yml`/`task-agent.yml` invocations and no `site.yml --tags patch|vyos` remain.

- [ ] **Step 5: Verify all five ops playbooks resolve standalone**

Run:
```bash
for p in playbooks/ops/*.yml; do echo "== $p =="; ansible-playbook --syntax-check "$p"; done
```
Expected: each of `killswitch.yml`, `agents.yml`, `task-agent.yml`, `patch.yml`, `vyos-hardening.yml` syntax-checks with no error.

- [ ] **Step 6: Commit**

```bash
git add playbooks/ops README.md
git commit -m "playbooks: move ops playbooks under playbooks/ops; add patch + vyos-hardening"
```

---

### Task 7: Rewrite `site.yml` as the thin orchestrator + full acceptance

**Files:**
- Modify: `site.yml` (replace inline plays with imports)

**Interfaces:**
- Consumes: `playbooks/01-bootstrap.yml`, `playbooks/02-services.yml`, `playbooks/03-applications.yml` (Task 5).

- [ ] **Step 1: Confirm the pre-rewrite dry-run baseline still works**

Run: `ansible-playbook --syntax-check site.yml`
Expected: passes (old inline `site.yml` still valid). This is the "before" baseline.

- [ ] **Step 2: Replace `site.yml` with the orchestrator**

```yaml
---
# Unattended first-boot entry point. Run FROM control as the `ansible` user
# (see README). Statically imports the phase playbooks in order; health_check in
# 01-bootstrap is the fail-fast gate.
#
# Operational playbooks are NOT imported here — run them explicitly from
# playbooks/ops/ (killswitch, patch, vyos-hardening, agents, task-agent).

- import_playbook: playbooks/01-bootstrap.yml
- import_playbook: playbooks/02-services.yml
- import_playbook: playbooks/03-applications.yml
```

- [ ] **Step 3: Syntax-check the orchestrator resolves all imports + roles**

Run: `ansible-playbook --syntax-check site.yml`
Expected: prints the combined play list from all three phase playbooks; no "Could not find" errors.

- [ ] **Step 4: Lint the restructured playbooks (interim — authoritative lint is Task 8)**

Run: `ansible-lint site.yml playbooks/`
Expected: the only remaining failures are `role-name` on the still-hyphenated role directories (`ai-identities`, `ai-workbench`, `deb-hardening-basic`, `dev-tools`, `vyos-hardening-basic`) — those are renamed in Task 8. No OTHER new failures from the restructure. (Repo-wide 0-failures is verified in Task 8.)

- [ ] **Step 5: Full dry-run resolves every play/role**

Run: `ansible-playbook --check site.yml 2>&1 | tail -20`
Expected: plays resolve and execute in check mode. Tasks may report `unreachable` if the env isn't running — that is acceptable (the goal is resolution, not live convergence). There must be **no** "role not found", "playbook not found", or vars-plugin errors.

- [ ] **Step 6: Confirm the acceptance checklist end-to-end**

Run:
```bash
echo "== stray repo gone ==";      ls -d v2e-tf.git 2>&1
echo "== site syntax ==";          ansible-playbook --syntax-check site.yml >/dev/null && echo OK
echo "== ops standalone ==";       for p in playbooks/ops/patch.yml playbooks/ops/vyos-hardening.yml playbooks/ops/killswitch.yml; do ansible-playbook --syntax-check "$p" >/dev/null && echo "OK $p"; done
```
Expected: `ls` → "No such file"; `site syntax` → `OK`; three `OK playbooks/ops/...` lines.

- [ ] **Step 7: Commit**

```bash
git add site.yml
git commit -m "site: thin orchestrator importing 01/02/03 phase playbooks"
```

---

### Task 8: Lint cleanup — exclude vendored role, rename hyphenated roles, reach 0 failures

**Context:** repo-wide `ansible-lint` currently reports 73 failures. 67 are inside the **vendored** `roles/docker` (upstream geerlingguy, replaced wholesale by the Galaxy role in ANS-3) — excluded, not edited. 1 was a linter-environment artifact (`vyos.vyos` not visible to an isolated ansible-lint). The remaining 5 are `role-name` on hyphenated role directories. This task drives the repo to **0 failures** by excluding the vendored role and renaming the 5 hyphenated roles to underscores.

**Files:**
- Create: `.ansible-lint`
- Rename (git mv, dirs): `roles/ai-identities`→`roles/ai_identities`, `roles/ai-workbench`→`roles/ai_workbench`, `roles/deb-hardening-basic`→`roles/deb_hardening_basic`, `roles/dev-tools`→`roles/dev_tools`, `roles/vyos-hardening-basic`→`roles/vyos_hardening_basic`
- Modify references: `playbooks/01-bootstrap.yml`, `playbooks/03-applications.yml`, `playbooks/ops/vyos-hardening.yml`, `playbooks/ops/agents.yml`, and the 5 renamed roles' `README.md` H1 headings
- Refresh: `README.md` `## Layout` tree (carried over from Task 6) — currently still shows the pre-refactor root-level playbooks and hyphenated role names; update it to the final structure.

**Interfaces:**
- Consumes: the full restructured tree from Tasks 5–7.
- Produces: underscore role names everywhere; `roles/docker` excluded from lint.

- [ ] **Step 1: Ensure the linter can resolve `vyos.vyos` (environment, one-time)**

Run: `ansible-galaxy collection install vyos.vyos ansible.netcommon -p ~/.ansible/collections --force`
Expected: both installed under `~/.ansible/collections/ansible_collections/`. (Fixes the `couldn't resolve module/action 'vyos.vyos.vyos_config'` syntax-check failure that an isolated pipx ansible-lint hits.)

- [ ] **Step 2: Create `.ansible-lint`**

```yaml
---
# roles/docker is vendored upstream (geerlingguy.docker 8.0.0), replaced wholesale
# by the pinned Galaxy role in ANS-3. Vendored dependencies are not ours to lint.
exclude_paths:
  - roles/docker/
```

- [ ] **Step 3: Rename the 5 hyphenated role directories (preserve history)**

```bash
git mv roles/ai-identities        roles/ai_identities
git mv roles/ai-workbench         roles/ai_workbench
git mv roles/deb-hardening-basic  roles/deb_hardening_basic
git mv roles/dev-tools            roles/dev_tools
git mv roles/vyos-hardening-basic roles/vyos_hardening_basic
```

- [ ] **Step 4: Update role references in the playbooks**

Edit these role references (the `- rolename` / `- role: rolename` lines only — leave task logic untouched):
- `playbooks/01-bootstrap.yml`: `deb-hardening-basic` → `deb_hardening_basic`
- `playbooks/03-applications.yml`: `ai-identities` → `ai_identities`, `ai-workbench` → `ai_workbench`
- `playbooks/ops/vyos-hardening.yml`: `vyos-hardening-basic` → `vyos_hardening_basic`
- `playbooks/ops/agents.yml`: `ai-identities` → `ai_identities`, `ai-workbench` → `ai_workbench`

Then confirm no stale hyphenated references remain:
```bash
grep -rnE '\b(ai-identities|ai-workbench|deb-hardening-basic|dev-tools|vyos-hardening-basic)\b' site.yml playbooks/ roles/*/README.md
```
Expected: no matches (update any README H1 headings the grep surfaces, e.g. `# dev-tools` → `# dev_tools`).

- [ ] **Step 4b: Refresh the top-level `README.md` `## Layout` tree**

The `## Layout` block in `README.md` still lists the pre-refactor structure (root-level `agents.yml`/`killswitch.yml`/`task-agent.yml`, hyphenated role names, no `playbooks/` tree). Rewrite it to reflect the final layout: `site.yml` (thin orchestrator), `playbooks/01-bootstrap.yml`/`02-services.yml`/`03-applications.yml`, `playbooks/ops/` (killswitch, patch, vyos-hardening, agents, task-agent), and the roles under their underscore names (`ai_identities`, `ai_workbench`, `deb_hardening_basic`, `dev_tools`, `health_check`, `vyos_hardening_basic`, plus `baseline`, `docker`, `killswitch`, `patch`). Keep the one-line description style already used in that block.
Verify: `grep -nE '^(agents|killswitch|task-agent)\.yml' README.md` returns nothing (no root-level playbook entries remain in the tree).

- [ ] **Step 5: Verify repo-wide lint is clean**

Run: `ansible-lint`
Expected: `Passed` / exit 0 — 0 failures (the `role-name` violations are gone; `roles/docker` is excluded).

- [ ] **Step 6: Verify the restructured playbooks still resolve after the renames**

Run:
```bash
ansible-playbook --syntax-check site.yml >/dev/null && echo "site OK"
for p in playbooks/ops/*.yml; do ansible-playbook --syntax-check "$p" >/dev/null && echo "OK $p"; done
```
Expected: `site OK` and one `OK` line per ops playbook — no "role not found" from a missed reference.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "lint: exclude vendored roles/docker; rename hyphenated roles to underscores"
```

---

## Self-review notes

- **Spec coverage:** git hygiene (T1) · requirements.yml pins incl. 7.x/8.0.0 note (T2) · ansible.cfg collections+SOPS+SFTP (T3) · health_check/dev-tools scaffold, dev-tools unwired (T4) · phase playbooks (T5) · ops move + patch/vyos-hardening + README (T6) · thin site.yml + acceptance (T7). All spec sections mapped.
- **Placeholder scan:** role bodies are intentionally no-op scaffolds (labelled ANS-1 scaffold), not plan placeholders; every code/command step is concrete. The only runtime-dependent value is the two Galaxy role version pins — Task 2 Step 2 gives the exact lookup+correct procedure if a pin is stale.
- **Consistency:** role names (`health_check`, `dev-tools`, `deb-hardening-basic`, `vyos-hardening-basic`), playbook paths (`playbooks/…`, `playbooks/ops/…`), and `roles_path`/`collections_path` values match across all tasks.
