# ANS-3 Services Docker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install Docker on the `services` node via `geerlingguy.docker` and deploy the v2e-compose stack (traefik + tinyauth + whoami) with `community.docker.docker_compose_v2`, sourcing secrets from the SOPS-decrypted `group_vars/all.yml` delivered by TF-2.

**Architecture:** `02-services.yml` runs `geerlingguy.docker` (engine, ansible in docker group, daemon.json) then a new `compose_stack` role that ensures git, asserts the required secrets, clones v2e-compose to `/opt/v2e-compose`, creates the external `frontend` network, renders a 0600 root `.env`, and deploys each stack via `docker_compose_v2` (project_src per stack dir, `env_files: ["../.env"]`). The vendored `roles/docker` is deleted.

**Tech Stack:** Ansible, `geerlingguy.docker` 7.9.0, `community.docker` >=3.6.0 (`docker_compose_v2`, `docker_network`), `ansible-lint`.

## Global Constraints

- Branch `feat/ansible-services-docker` (already created off `feat/ansible-bootstrap`).
- Services node only. Deploy stacks: `[traefik, tinyauth, whoami]`.
- Engine: `geerlingguy.docker` **7.9.0** (requirements pin); `docker_users: ["ansible"]`; `docker_daemon_options` = json-file log rotation (max-size 10m, max-file 3) + `live-restore: true`.
- **All Galaxy deps pinned to EXACT versions** in `requirements.yml` (reproducibility; Renovate bumps them later — no ranges): `geerlingguy.docker 7.9.0`, `artis3n.tailscale v5.0.1`, `community.docker 5.2.0` (has `docker_compose_v2`), `devsec.hardening 10.6.0`, `community.sops 2.3.0`.
- **Galaxy ROLES install to the gitignored `.galaxy/roles`** — `ansible.cfg` `roles_path = .galaxy/roles:roles` (gitignored dir FIRST, so a bare `ansible-galaxy install` lands there and can never re-pollute `roles/`). The repo's `roles/` holds ONLY our roles (no upstream Galaxy copies committed or lint-scanned). Cloud-init installs Galaxy deps at runtime (Task 6).
- `compose_stack_dir` = `/opt/v2e-compose` (root:root). Repo cloned from HTTPS `https://github.com/v2e-sh/v2e-compose.git`, `version: main`.
- Secrets from SOPS `group_vars/all.yml`: `cf_dns_api_token`, `tinyauth_auth_users` → mapped to `CF_DNS_API_TOKEN` / `TINYAUTH_AUTH_USERS`. Fail-fast if blank.
- Non-secret config in `group_vars/services.yml`: `DOMAIN`, `ACME_EMAIL`, `CERT_RESOLVER: staging`.
- `.env` is `{{ compose_stack_dir }}/.env`, root:root **0600**; referenced by each stack as `env_files: ["../.env"]` (relative to `project_src`).
- Role vars are `compose_stack_*`-prefixed (var-naming passes). Task names capitalized.
- Git: short imperative commits, NO attribution trailer.
- No live env: static gate only — `ansible-lint` 0 failures (production) + `ansible-playbook --syntax-check site.yml`. No live `--check`. Real deploy = the ANS-3 live test plan (Task 5).

---

### Task 1: Bump `community.docker` requirement to `>=3.6.0`

**Files:**
- Modify: `requirements.yml`

- [ ] **Step 1: Edit the pin**

Change the `community.docker` line from `version: ">=3.0.0"` to `version: ">=3.6.0"` (the floor that ships `docker_compose_v2`). Leave `geerlingguy.docker` at `7.9.0` and the others unchanged.

- [ ] **Step 2: Verify the file still resolves**

Run:
```bash
TMP=$(mktemp -d)
ansible-galaxy install -r requirements.yml --roles-path "$TMP/roles" \
  && ansible-galaxy collection install -r requirements.yml -p "$TMP/collections"
echo "resolved rc=$?"; rm -rf "$TMP"
```
Expected: `resolved rc=0`.

- [ ] **Step 3: Commit**

```bash
git add requirements.yml
git commit -m "deps: require community.docker >=3.6.0 for docker_compose_v2"
```

---

### Task 2: `group_vars/services.yml` — compose deploy config

**Files:**
- Modify: `inventory/group_vars/services.yml` (append; keep the existing `ssh_allow_users`)

**Interfaces:**
- Produces: `compose_stack_*` config consumed by the `compose_stack` role (Task 3).

- [ ] **Step 1: Append the compose config to `inventory/group_vars/services.yml`**

Keep the existing `ssh_allow_users: "v2e ansible"` line; add below it:

```yaml
# --- v2e-compose deploy (ANS-3). Non-secret config only. Secrets
# (cf_dns_api_token, tinyauth_auth_users) come from SOPS group_vars/all.yml. ---
compose_stack_repo_url: "https://github.com/v2e-sh/v2e-compose.git"
compose_stack_dir: /opt/v2e-compose
compose_stack_stacks:
  - traefik
  - tinyauth
  - whoami
compose_stack_domain: "v2e.sh"
compose_stack_acme_email: "admin@v2e.sh"
compose_stack_cert_resolver: staging
```

- [ ] **Step 2: Verify resolution + lint**

Run:
```bash
ansible -i inventory/hosts.ini services01 -m ansible.builtin.debug -a "var=compose_stack_stacks" 2>/dev/null | grep -A4 compose_stack_stacks
ansible-lint inventory/group_vars/services.yml 2>&1 | tail -2
```
Expected: the three stacks list resolves on services01; ansible-lint reports no failures for the file.

- [ ] **Step 3: Commit**

```bash
git add inventory/group_vars/services.yml
git commit -m "group_vars: v2e-compose deploy config for services"
```

---

### Task 3: `compose_stack` role — clone, network, deploy

**Files:**
- Create: `roles/compose_stack/defaults/main.yml`, `roles/compose_stack/tasks/main.yml`, `roles/compose_stack/templates/env.j2`, `roles/compose_stack/README.md`

**Interfaces:**
- Consumes: `compose_stack_*` (group_vars/services.yml + these defaults) and `cf_dns_api_token`/`tinyauth_auth_users` (SOPS group_vars/all.yml).
- Produces: role `compose_stack`, wired after `geerlingguy.docker` in Task 4.

- [ ] **Step 1: Create `roles/compose_stack/defaults/main.yml`**

```yaml
---
# Overridden by inventory/group_vars/services.yml. Secrets are NOT here — they
# come from SOPS group_vars/all.yml (cf_dns_api_token, tinyauth_auth_users).
compose_stack_repo_url: ""
compose_stack_repo_version: main
compose_stack_dir: /opt/v2e-compose
compose_stack_stacks:
  - traefik
  - tinyauth
  - whoami
compose_stack_network: frontend
compose_stack_domain: ""
compose_stack_acme_email: ""
compose_stack_cert_resolver: staging
```

- [ ] **Step 2: Create `roles/compose_stack/templates/env.j2`**

```jinja
# Managed by Ansible (compose_stack role). Non-secret config + SOPS secrets.
# Consumed by docker compose via env_files (../.env from each stack dir).
DOMAIN={{ compose_stack_domain }}
ACME_EMAIL={{ compose_stack_acme_email }}
CERT_RESOLVER={{ compose_stack_cert_resolver }}
CF_DNS_API_TOKEN={{ cf_dns_api_token }}
TINYAUTH_AUTH_USERS={{ tinyauth_auth_users }}
```

- [ ] **Step 3: Create `roles/compose_stack/tasks/main.yml`**

```yaml
---
# Deploy the v2e-compose stacks on the services node. geerlingguy.docker (run
# before this role) provides the engine + compose plugin.

- name: Assert required SOPS secrets are present
  ansible.builtin.assert:
    that:
      - cf_dns_api_token | default('') | length > 0
      - tinyauth_auth_users | default('') | length > 0
    fail_msg: >-
      compose_stack needs cf_dns_api_token and tinyauth_auth_users from the SOPS
      group_vars/all.yml (delivered by TF-2). One or both are missing/empty —
      set them in your sops_secrets_file and re-run.

- name: Ensure git is installed (needed to clone v2e-compose)
  ansible.builtin.apt:
    name: git
    state: present
    update_cache: true
    cache_valid_time: 3600

- name: Clone the v2e-compose repository
  ansible.builtin.git:
    repo: "{{ compose_stack_repo_url }}"
    dest: "{{ compose_stack_dir }}"
    version: "{{ compose_stack_repo_version }}"

- name: Create the shared external frontend network
  community.docker.docker_network:
    name: "{{ compose_stack_network }}"
    state: present

- name: Render the shared .env (non-secret config + SOPS secrets)
  ansible.builtin.template:
    src: env.j2
    dest: "{{ compose_stack_dir }}/.env"
    owner: root
    group: root
    mode: "0600"

- name: Deploy each compose stack
  community.docker.docker_compose_v2:
    project_src: "{{ compose_stack_dir }}/{{ item }}"
    env_files:
      - ../.env
    state: present
  loop: "{{ compose_stack_stacks }}"
  loop_control:
    label: "{{ item }}"
```

- [ ] **Step 4: Create `roles/compose_stack/README.md`**

```markdown
# compose_stack

Deploys the `v2e-compose` stacks (traefik, tinyauth, whoami) on the services
node with `community.docker.docker_compose_v2`. Ensures git, asserts the SOPS
secrets (`cf_dns_api_token`, `tinyauth_auth_users`), clones the repo to
`compose_stack_dir` (`/opt/v2e-compose`), creates the external `frontend`
network, renders a 0600 root `.env`, and brings each stack up. Non-secret config
(`DOMAIN`/`ACME_EMAIL`/`CERT_RESOLVER`) is in `group_vars/services.yml`; secrets
come from SOPS `group_vars/all.yml`. Run after `geerlingguy.docker`.
```

- [ ] **Step 5: Lint the role**

Run: `ansible-lint roles/compose_stack`
Expected: 0 failures (community.docker resolves; env.j2 has no undefined-at-lint errors). Fix only real failures in the role, keeping the logic intact.

- [ ] **Step 6: Commit**

```bash
git add roles/compose_stack
git commit -m "compose_stack: deploy v2e-compose stacks via docker_compose_v2"
```

---

### Task 4: Rewire `02-services.yml` to geerlingguy.docker + compose_stack

**Files:**
- Modify: `playbooks/02-services.yml`
- Delete: `roles/docker/` (whole vendored directory)

**Interfaces:**
- Consumes: `geerlingguy.docker` (installed collection/role) + `compose_stack` (Task 3).

- [ ] **Step 1: Rewrite `playbooks/02-services.yml`**

```yaml
---
# Phase 02 — services: Docker engine + the v2e-compose stack on the services node.
# geerlingguy.docker replaces the vendored role (ANS-3); compose_stack deploys the
# traefik/tinyauth/whoami stacks.

- name: Docker engine + v2e-compose stack on the services host
  hosts: services
  become: true
  roles:
    - role: geerlingguy.docker
      vars:
        docker_users:
          - ansible
        docker_daemon_options:
          log-driver: json-file
          log-opts:
            max-size: "10m"
            max-file: "3"
          live-restore: true
    - role: compose_stack
```

- [ ] **Step 2: Delete the vendored role**

```bash
git rm -r roles/docker
```

- [ ] **Step 3: Confirm no remaining reference to the vendored role**

Run: `grep -rnE '^\s*-\s*(role:\s*)?docker\b' site.yml playbooks/ 2>/dev/null || echo "no vendored-docker role refs"`
Expected: `no vendored-docker role refs` (the only `docker` now is the FQCN collection `geerlingguy.docker`, which this pattern does not match).

- [ ] **Step 4: Syntax-check + lint**

Run: `ansible-playbook --syntax-check site.yml && ansible-lint`
Expected: syntax-check resolves `geerlingguy.docker` + `compose_stack`; `ansible-lint` → 0 failures, production profile.

- [ ] **Step 5: Commit**

```bash
git add playbooks/02-services.yml
git commit -m "services: geerlingguy.docker engine + compose_stack deploy"
```

---

### Task 5: Final acceptance + live-env test plan

**Files:**
- Create: `docs/superpowers/plans/ans-3-live-test-plan.md`

- [ ] **Step 1: Confirm requirements + collections resolve**

Run:
```bash
TMP=$(mktemp -d); ansible-galaxy install -r requirements.yml --roles-path "$TMP/roles" >/dev/null 2>&1 \
  && ansible-galaxy collection install -r requirements.yml -p "$TMP/collections" >/dev/null 2>&1 && echo "requirements OK rc=$?"; rm -rf "$TMP"
ansible-galaxy collection list 2>/dev/null | grep -iE 'community.docker'
```
Expected: `requirements OK rc=0`; `community.docker` present (>=3.6).

- [ ] **Step 2: Full static acceptance**

Run:
```bash
ansible-playbook --syntax-check site.yml && echo "syntax OK"
ansible-lint && echo "lint 0 failures"
```
Expected: `syntax OK` and `lint 0 failures` (production profile).

- [ ] **Step 3: Write the live-env test plan**

Create `docs/superpowers/plans/ans-3-live-test-plan.md`:

```markdown
# ANS-3 — live-env behavioral test plan

Run at the full from-scratch deploy (real domain + Cloudflare token + age key + sops_secrets_file).

1. Engine: `systemctl is-active docker` = active; `id ansible` shows the `docker` group;
   `docker info -f '{{.LoggingDriver}}'` = json-file; `/etc/docker/daemon.json` has live-restore + log limits.
2. Network: `docker network ls` shows `frontend`.
3. `.env`: `/opt/v2e-compose/.env` is 0600 root; holds DOMAIN/ACME_EMAIL/CERT_RESOLVER=staging + the two secrets.
4. Stacks up: `docker compose ls` shows traefik, tinyauth, whoami; `docker ps` all healthy.
5. Cert: Traefik issues a valid **staging** wildcard cert via Cloudflare DNS-01 (traefik logs / acme.json 0600).
6. Reachability: `https://whoami.<domain>` returns 200 over HTTPS; `http://` redirects to `https://`.
7. tinyauth container is up (COMPOSE-2 caveat: full forward-auth middleware enforcement is COMPOSE-2's job).
8. Flip `compose_stack_cert_resolver: production` and re-run once staging issues cleanly.
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/ans-3-live-test-plan.md
git commit -m "docs: ANS-3 live-env test plan"
```

---

### Task 6: Cloud-init installs Galaxy deps at runtime (v2e-tf, cross-repo)

**Context:** cloud-init currently clones v2e-ansible and runs the playbook but **never installs
`requirements.yml`**, so `geerlingguy.docker` (a Galaxy role) is absent on control at deploy time
and the ANS-3 services play fails with "role not found". This task adds the install step.

**Files (in the `v2e-tf` repo at `/Users/alex/Documents/v2e-environment/v2e-tf`):**
- Modify: `cloud-init/node.yaml.tftpl` (the ansible bootstrap runcmd on control)

- [ ] **Step 1: Branch in v2e-tf**

```bash
cd /Users/alex/Documents/v2e-environment/v2e-tf
git checkout -b feat/cloud-init-galaxy-install
```

- [ ] **Step 2: Add the Galaxy install before the playbook run**

In the control ansible-bootstrap runcmd (the `su - ${ansible_user} -c '... git clone ... && cd ~/ansible && ... ansible-playbook ...'` line), insert a requirements install **after `cd ~/ansible`** and **before** the `ansible-playbook` invocation. Use the **negated-guard** form so it tolerates a missing `requirements.yml` but ABORTS on a genuine install failure (rather than running a playbook doomed to fail on the missing role):
```bash
{ [ ! -f requirements.yml ] || { ansible-galaxy role install -r requirements.yml -p .galaxy/roles && ansible-galaxy collection install -r requirements.yml; }; } && \
```
Semantics: no `requirements.yml` → `[ ! -f ]` short-circuits, chain continues; file present → both installs run under `&&`, and if either fails the block returns non-zero so the outer `&&` chain aborts before `ansible-playbook`. `-p .galaxy/roles` matches the repo's `roles_path = .galaxy/roles:roles`; collections go to the default `~/.ansible/collections`. (Do NOT use `{ [ -f ] && {...} || true; }` — the `|| true` swallows real install failures.)

- [ ] **Step 3: Validate**

Run: `export PATH="/opt/homebrew/bin:$PATH"; tofu fmt && tofu validate`
Expected: `fmt` clean; `validate` → "Success! The configuration is valid." Confirm the string is present: `grep -c 'ansible-galaxy role install -r requirements.yml' cloud-init/node.yaml.tftpl` → `1`.

- [ ] **Step 4: Commit (in v2e-tf)**

```bash
git add cloud-init/node.yaml.tftpl
git commit -m "cloud-init: install galaxy requirements before the playbook run"
```

---

## Self-review notes

- **Spec coverage:** engine swap + daemon.json + docker group (T4, geerlingguy vars) · community.docker floor (T1) · compose_stack clone/network/.env/deploy + fail-fast + git (T3) · non-secret config (T2) · delete vendored docker (T4) · static acceptance + live plan (T5). All spec components mapped.
- **Placeholder scan:** every step has concrete content; `docker_compose_v2`/`docker_network` params + `env_files` semantics (relative to project_src → `../.env`) verified against installed community.docker; geerlingguy var names (`docker_users`, `docker_daemon_options`, `docker_install_compose_plugin`) verified. No TBD.
- **Consistency:** `compose_stack_*` var names + `compose_stack_dir` (/opt/v2e-compose) + stacks list + secret var names (`cf_dns_api_token`, `tinyauth_auth_users`) match across the role, group_vars, and env.j2. Role runs after geerlingguy.docker in T4 as the role's README requires.
- **Testing note:** the assert on `cf_dns_api_token`/`tinyauth_auth_users` is undefined at static-check time (SOPS-only) — not evaluated by syntax-check/lint, so it doesn't fail the static gate; it fires at live deploy, which is intended fail-fast.
