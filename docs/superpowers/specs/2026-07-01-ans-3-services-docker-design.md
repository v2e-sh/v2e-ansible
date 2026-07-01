# ANS-3 — Services: Docker + compose deploy (design)

**Date:** 2026-07-01
**Repo:** `v2e-ansible`
**Branch:** `feat/ansible-services-docker` (off `feat/ansible-bootstrap`)
**Master-plan phase:** ANS-3 · depends on ANS-2 (done) + COMPOSE-1 (done) + TF-2 (done, merged)
**Status:** approved design → implementation plan next

## Purpose

Fill the `02-services` phase: install the Docker engine on the `services` node via
`geerlingguy.docker`, then deploy the `v2e-compose` stack (Traefik + TinyAuth + whoami)
with `community.docker.docker_compose_v2`, sourcing secrets from the SOPS-decrypted
`group_vars/all.yml` that TF-2 delivers to control.

## Decisions (settled in brainstorming)
1. **Deploy all three stacks** — traefik + tinyauth + whoami (user chose full stack; tinyauth
   deploys as a container even though COMPOSE-2's middleware wiring may be mid-flight — noted).
2. **Engine = `geerlingguy.docker` 7.9.0** (already pinned in `requirements.yml`; reconciles the
   ANS-1 7.x/8.0.0 note) — delete the vendored `roles/docker`.
3. **Deploy mechanism = `docker_compose_v2`** — confirmed by v2e-compose's own Makefile note:
   "`terraform apply` → Ansible → ANS-3 (docker_compose_v2); make is not involved there."
4. **Secrets from SOPS group_vars** (TF-2 path) — `cf_dns_api_token` + `tinyauth_auth_users` in
   `group_vars/all.yml`; fail-fast if blank.
5. **`compose_dir` = `/opt/v2e-compose`** (root-owned).
6. **SOPS var names = lowercase ansible-style** (`cf_dns_api_token`, `tinyauth_auth_users`),
   mapped to the uppercase env in the `.env`.
7. **`CERT_RESOLVER: staging`** first (flip to production at the live test, per COMPOSE-1).
8. **Full live test after ANS-3** (user chose): one from-scratch deploy validates ANS-1+2a+3.

## Out of scope
- COMPOSE-2 (TinyAuth) completion — its Traefik forward-auth middleware is that phase's job.
- Molecule harness → ANS-5. Monitoring/observability → Phase G.
- Any change to control/agent Docker (services node only).

## Current state
- `playbooks/02-services.yml`: `hosts: services`, uses the vendored `roles/docker` (geerlingguy
  8.0.0 copy) with `docker_install_compose_plugin: true`.
- `v2e-compose` layout: `traefik/compose.yml`, `tinyauth/compose.yml`, `whoami/compose.yml`,
  each joining an **external** `frontend` network. Env vars consumed:
  `.env` (non-secret) `DOMAIN`, `ACME_EMAIL`, `CERT_RESOLVER`; secrets `CF_DNS_API_TOKEN` (`:?`
  required), `TINYAUTH_AUTH_USERS` (`:?` required).
- TF-2 (merged) delivers the age key to control's `~/.config/sops/age/keys.txt` and the
  encrypted secrets to `~/ansible/group_vars/all.yml`; ANS-1's `ansible.cfg` enables the
  `community.sops` vars plugin, so those vars are decrypted when Ansible runs on control.
- `requirements.yml` pins `geerlingguy.docker 7.9.0` and `community.docker >=3.0.0`.

## Components

### 1. Engine swap — `geerlingguy.docker` (in `02-services.yml`, `hosts: services`)
Rewrite the services play to use `geerlingguy.docker` and delete `roles/docker`. Configure via
role vars:
- `docker_users: ["ansible"]` — the automation user joins the `docker` group.
- `docker_daemon_options`: `{ "log-driver": "json-file", "log-opts": {"max-size": "10m",
  "max-file": "3"}, "live-restore": true }` — the master-plan `daemon.json` (log rotation +
  live-restore).
- Keep the Compose v2 plugin installed (geerlingguy default).

### 2. `compose_stack` role — clone, network, deploy
New role applied to `services` after the engine:
- **Assert secrets present** — fail-fast with a clear message if `cf_dns_api_token` or
  `tinyauth_auth_users` is empty/undefined (a missing SOPS value must not silently 500 Traefik).
- **Clone** `v2e-compose` (`main`) to `compose_stack_dir` (default `/opt/v2e-compose`, root:root
  0755) via `ansible.builtin.git` (idempotent; `main`, no ref pin per master-plan decision).
- **Create** the external `frontend` network via `community.docker.docker_network`
  (`name: frontend`, `state: present`).
- **Template `.env`** (`{{ compose_stack_dir }}/.env`, root:root 0600) with:
  `DOMAIN`, `ACME_EMAIL`, `CERT_RESOLVER` (from `group_vars/services.yml`) and
  `CF_DNS_API_TOKEN={{ cf_dns_api_token }}`, `TINYAUTH_AUTH_USERS={{ tinyauth_auth_users }}`
  (from SOPS `group_vars/all.yml`).
- **Deploy** each stack via `community.docker.docker_compose_v2` looping
  `compose_stack_stacks: [traefik, tinyauth, whoami]` — `project_src: "{{ compose_stack_dir }}/{{ item }}"`,
  `env_files: ["{{ compose_stack_dir }}/.env"]`, `state: present`.
- Idempotent (git idempotent, docker_network present, docker_compose_v2 converges).

### 3. Variables
- `group_vars/services.yml` (committed, non-secret): `compose_stack_domain` (`v2e.sh`),
  `compose_stack_acme_email`, `compose_stack_cert_resolver: staging`, `compose_stack_dir:
  /opt/v2e-compose`, `compose_stack_stacks: [traefik, tinyauth, whoami]`,
  `compose_stack_repo_url` (the v2e-compose git URL).
- `group_vars/all.yml` (SOPS, NOT committed — operator-provided via TF-2): `cf_dns_api_token`,
  `tinyauth_auth_users`. Documented as required keys.
- `requirements.yml`: bump `community.docker` to **`>=3.6.0`** (floor for `docker_compose_v2`);
  `geerlingguy.docker` stays 7.9.0.

### 4. Wiring
`02-services.yml`: `hosts: services`, `become: true`, roles: `geerlingguy.docker` → `compose_stack`.

## Testing

**Static (now):** `ansible-lint` 0 failures (production), `ansible-playbook --syntax-check site.yml`.
The compose files self-validate in their own repo (`make validate` / `docker compose config`).
`requirements.yml` installs (temp dir) with `community.docker >=3.6.0` + `geerlingguy.docker 7.9.0`.

**Live-env test plan (full from-scratch deploy — the ANS-3 milestone, with real secrets):**
1. `docker` engine active; `ansible` in the `docker` group; `daemon.json` shows live-restore + log limits.
2. `docker network ls` shows `frontend`.
3. `/opt/v2e-compose/.env` is 0600 root and holds the resolved DOMAIN/resolver + secrets.
4. `docker compose ls` shows traefik, tinyauth, whoami up; `docker ps` healthy.
5. Traefik pulls a valid **staging** wildcard cert via Cloudflare DNS-01 (check `acme.json` / logs).
6. `whoami.<domain>` reachable over HTTPS with HTTP→HTTPS redirect.
7. (COMPOSE-2 caveat) tinyauth container is up; full forward-auth enforcement is COMPOSE-2's job.
8. Flip `CERT_RESOLVER=production` and re-run once staging issues cleanly.

## Risks / mitigations
- **Secret at rest/in transit:** control→services over ansible SSH/SFTP into a 0600 root `.env` —
  same posture as the local `sops exec-env` path. Fail-fast on blank secret.
- **community.docker floor:** `docker_compose_v2` needs `>=3.6.0`; requirements bumped so a fresh
  `ansible-galaxy install` on control gets a capable version.
- **COMPOSE-2 coupling:** tinyauth deploys as a container; its middleware wiring may be incomplete
  — flagged in the test plan; does not block Traefik/whoami.
- **No live env now:** static gate only; real cert issuance validated at the full deploy.

## Prerequisites for the full live test (operator-provided)
- A domain + Cloudflare zone + scoped `CF_DNS_API_TOKEN` (Zone:Read + DNS:Edit).
- An age keypair; a `sops_secrets_file` (age-encrypted) containing `cf_dns_api_token` +
  `tinyauth_auth_users`; `sops_secrets_file`/`sops_age_key_file` set in `terraform.tfvars`.
- Rebuilt templates (Phase 0) + `tofu apply`.
