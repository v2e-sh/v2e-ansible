# ANS-2a Bootstrap Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill `01-bootstrap` with a real fail-fast `health_check` gate and replace the hand-rolled `deb_hardening_basic` role with `devsec.hardening` as the single owner of `sshd_config`, preserving AllowUsers, `ip_forward=1`, SFTP, and fail2ban.

**Architecture:** `health_check` (pure `ansible.builtin`) runs first and aborts on an unreachable/low-resource node. `devsec.hardening.os_hardening` + `devsec.hardening.ssh_hardening` do OS/SSH hardening, configured via `inventory/group_vars` (per-group `ssh_allow_users`, group-wide `sysctl_overwrite` to keep `ip_forward=1`). A small new `fail2ban` role preserves the sshd jail. The paired cross-repo change retires cloud-init's `60-v2e.conf` so only Ansible owns `sshd_config`.

**Tech Stack:** Ansible (ansible-core 2.x), `devsec.hardening` 10.x (os_hardening + ssh_hardening), `ansible-lint`, Terraform/OpenTofu (v2e-tf cloud-init template).

## Global Constraints

- Branches: `v2e-ansible` work on `feat/ansible-bootstrap` (already created off `refactor/ansible-structure`); the v2e-tf edit (Task 5) on its own branch **in the v2e-tf repo**.
- **Preserve AllowUsers exactly:** control → `"v2e"`; services + agent → `"v2e ansible"`. Do NOT add the AI accounts (claude/codex) — pre-existing gap, out of scope.
- **Preserve `net.ipv4.ip_forward = 1`** on the whole `linux` group (Docker networking).
- **Keep fail2ban** (own role); **keep `sftp_enabled: true`** (devsec default — confirm, don't override off).
- devsec var facts (verified against installed 10.6.0): `ssh_allow_users` is a **space-separated string**; `ssh_server_password_login` defaults `false`, `ssh_permit_root_login` defaults `"no"`, `sftp_enabled` defaults `true`, `ssh_pubkey_authentication` defaults `true`. os_hardening default `sysctl_settings["net.ipv4.ip_forward"] = 0`; override via `sysctl_overwrite`.
- Role vars use the role-name prefix (`health_check_*`, `fail2ban_*`) so `var-naming` passes with no noqa.
- Task names start with a capital letter (ansible-lint `name[casing]`).
- Git: short imperative commit messages, NO attribution trailer.
- **No live env:** verify with `ansible-playbook --syntax-check` + targeted `ansible-lint` (0 failures, production profile). A full `--check` run WILL fail at the `health_check` connectivity gate while the env is down — that is the gate working, not a defect; real behaviour is covered by the live-env test plan (Task 6).

---

### Task 1: `health_check` role — real fail-fast gate

**Files:**
- Modify: `roles/health_check/tasks/main.yml` (replace the no-op scaffold)
- Modify: `roles/health_check/defaults/main.yml`
- Modify: `roles/health_check/README.md`

**Interfaces:**
- Produces: role `health_check`, already wired first in `playbooks/01-bootstrap.yml`. Reads `health_check_*` vars from defaults.

- [ ] **Step 1: Write `roles/health_check/defaults/main.yml`**

```yaml
---
# Thresholds + targets for the fail-fast preflight gate.
health_check_connect_timeout: 30      # wait_for_connection per-node timeout (s)
health_check_min_disk_percent: 15     # minimum free space on / (percent)
health_check_min_mem_mb: 512          # minimum available memory (MB)
health_check_intervlan_timeout: 10    # per-target TCP:22 probe timeout (s)
# Nodes control must reach across VLANs (through the router), checked on :22.
health_check_intervlan_targets:
  - { name: services, host: 10.1.2.10 }
  - { name: agent, host: 10.1.3.10 }
```

- [ ] **Step 2: Write `roles/health_check/tasks/main.yml`**

```yaml
---
# Fail-fast preflight gate. Runs first in 01-bootstrap so an unhealthy or
# unreachable node aborts the run before hardening/config touches anything.
# Pure ansible.builtin so it can never fail on a missing collection.

- name: Wait for every managed node to be reachable
  ansible.builtin.wait_for_connection:
    timeout: "{{ health_check_connect_timeout }}"

- name: Gather hardware facts for the resource asserts
  ansible.builtin.setup:
    gather_subset:
      - hardware
      - min

- name: Assert sufficient free disk on /
  ansible.builtin.assert:
    that:
      - (root_mount.size_available | float) / (root_mount.size_total | float) * 100 >= health_check_min_disk_percent
    fail_msg: >-
      Free space on / below {{ health_check_min_disk_percent }}% on {{ inventory_hostname }}
      ({{ (root_mount.size_available / 1048576) | round | int }} MB free).
    success_msg: "Disk OK on {{ inventory_hostname }}"
  vars:
    root_mount: "{{ ansible_mounts | selectattr('mount', 'equalto', '/') | first }}"

- name: Assert sufficient available memory
  ansible.builtin.assert:
    that:
      - ansible_memory_mb.nocache.free >= health_check_min_mem_mb
    fail_msg: >-
      Available memory below {{ health_check_min_mem_mb }} MB on {{ inventory_hostname }}
      ({{ ansible_memory_mb.nocache.free }} MB free).
    success_msg: "Memory OK on {{ inventory_hostname }}"

- name: Inter-VLAN reachability — control reaches the other nodes on SSH
  ansible.builtin.wait_for:
    host: "{{ item.host }}"
    port: 22
    timeout: "{{ health_check_intervlan_timeout }}"
  loop: "{{ health_check_intervlan_targets }}"
  loop_control:
    label: "{{ item.name }} ({{ item.host }}:22)"
  when: inventory_hostname in groups['control']
  changed_when: false
```

- [ ] **Step 3: Write `roles/health_check/README.md`**

```markdown
# health_check

Fail-fast preflight gate, run first in `01-bootstrap`. Aborts the whole run early
if any node is unreachable (`wait_for_connection`), low on disk/memory (asserts),
or if control can't reach the other nodes across VLANs on SSH. Thresholds and
targets are in `defaults/main.yml`. Pure `ansible.builtin` — no collection deps.
```

- [ ] **Step 4: Lint + syntax-check the role**

Run: `ansible-lint roles/health_check && ansible-playbook --syntax-check playbooks/01-bootstrap.yml`
Expected: `ansible-lint` reports 0 failures for the role; syntax-check prints the play list with no error.

- [ ] **Step 5: Commit**

```bash
git add roles/health_check
git commit -m "health_check: real fail-fast gate (reachability, disk/mem, inter-VLAN)"
```

---

### Task 2: `inventory/group_vars` — devsec configuration

**Files:**
- Create: `inventory/group_vars/linux.yml`
- Create: `inventory/group_vars/control.yml`
- Create: `inventory/group_vars/services.yml`
- Create: `inventory/group_vars/agent.yml`

**Interfaces:**
- Produces: `ssh_allow_users` per group + `sysctl_overwrite` group-wide, consumed by the devsec roles wired in Task 4. `group_vars` under `inventory/` are auto-loaded (inventory is `inventory/hosts.ini`).

- [ ] **Step 1: Create `inventory/group_vars/linux.yml`**

```yaml
---
# devsec os_hardening: its default sysctl set forces net.ipv4.ip_forward=0, which
# breaks Docker/container routing. Override back to 1 on every Linux node. All
# other os_hardening sysctls (rp_filter, syncookies, redirects, kptr/dmesg
# restrict, ...) are kept at devsec defaults — they match the retired drop-in.
sysctl_overwrite:
  net.ipv4.ip_forward: 1
```

- [ ] **Step 2: Create the three per-group `ssh_allow_users` files**

`inventory/group_vars/control.yml`:
```yaml
---
# Preserve the exact AllowUsers from cloud-init (v2e-tf nodes.tf): control allows
# only the cluster user. devsec.hardening.ssh_hardening becomes the sole owner.
ssh_allow_users: "v2e"
```

`inventory/group_vars/services.yml`:
```yaml
---
# Preserve AllowUsers exactly: cluster user + ansible automation account.
ssh_allow_users: "v2e ansible"
```

`inventory/group_vars/agent.yml`:
```yaml
---
# Preserve AllowUsers exactly: cluster user + ansible automation account.
ssh_allow_users: "v2e ansible"
```

- [ ] **Step 3: Verify variable resolution per host**

Run:
```bash
for h in control01 services01 agent01; do
  echo -n "$h ssh_allow_users="; ansible -i inventory/hosts.ini "$h" -m ansible.builtin.debug -a "var=ssh_allow_users" 2>/dev/null | grep -o '"ssh_allow_users": "[^"]*"'
done
ansible -i inventory/hosts.ini services01 -m ansible.builtin.debug -a "var=sysctl_overwrite" 2>/dev/null | grep -A2 sysctl_overwrite
```
Expected: control01 → `"v2e"`; services01/agent01 → `"v2e ansible"`; `sysctl_overwrite` shows `net.ipv4.ip_forward: 1` on services01. (These read only vars, no connection.)

- [ ] **Step 4: Commit**

```bash
git add inventory/group_vars
git commit -m "group_vars: devsec ssh_allow_users per node + preserve ip_forward"
```

---

### Task 3: `fail2ban` role — preserve the sshd jail

**Files:**
- Create: `roles/fail2ban/tasks/main.yml`, `roles/fail2ban/handlers/main.yml`, `roles/fail2ban/defaults/main.yml`, `roles/fail2ban/README.md`

**Interfaces:**
- Produces: role `fail2ban`, wired last in the hardening play (Task 4). Toggle `fail2ban_enabled`.

- [ ] **Step 1: Create `roles/fail2ban/defaults/main.yml`**

```yaml
---
fail2ban_enabled: true
```

- [ ] **Step 2: Create `roles/fail2ban/tasks/main.yml`** (carried over from the retired deb_hardening_basic)

```yaml
---
# sshd brute-force protection. Carried over from the retired deb_hardening_basic
# role — devsec.hardening does not provide fail2ban.

- name: Install fail2ban (+ python3-systemd for the journal backend)
  ansible.builtin.apt:
    name:
      - fail2ban
      - python3-systemd
    state: present
    update_cache: true
    cache_valid_time: 3600
  when: fail2ban_enabled

- name: Enable the sshd jail (systemd backend)
  ansible.builtin.copy:
    dest: /etc/fail2ban/jail.d/sshd.local
    owner: root
    group: root
    mode: "0644"
    content: |
      # Managed by Ansible (fail2ban role).
      [sshd]
      enabled = true
      # bookworm has no rsyslog/auth.log; sshd logs to the journal.
      backend = systemd
  notify: Restart fail2ban
  when: fail2ban_enabled

- name: Ensure fail2ban is enabled and running
  ansible.builtin.systemd_service:
    name: fail2ban
    enabled: true
    state: started
  when: fail2ban_enabled
```

- [ ] **Step 3: Create `roles/fail2ban/handlers/main.yml`**

```yaml
---
- name: Restart fail2ban
  ansible.builtin.systemd_service:
    name: fail2ban
    state: restarted
```

- [ ] **Step 4: Create `roles/fail2ban/README.md`**

```markdown
# fail2ban

sshd brute-force protection (systemd journal backend). Carried over from the
retired `deb_hardening_basic` role when `devsec.hardening` took over SSH/OS
hardening (devsec provides no fail2ban). Toggle with `fail2ban_enabled`.
```

- [ ] **Step 5: Lint the role**

Run: `ansible-lint roles/fail2ban`
Expected: 0 failures.

- [ ] **Step 6: Commit**

```bash
git add roles/fail2ban
git commit -m "fail2ban: preserve sshd jail as its own role"
```

---

### Task 4: Rewire `01-bootstrap` to devsec + delete `deb_hardening_basic`

**Files:**
- Modify: `playbooks/01-bootstrap.yml`
- Delete: `roles/deb_hardening_basic/` (whole directory)

**Interfaces:**
- Consumes: `health_check` (Task 1), `fail2ban` (Task 3), group_vars (Task 2), `devsec.hardening.os_hardening` + `devsec.hardening.ssh_hardening` (installed collection).

- [ ] **Step 1: Rewrite `playbooks/01-bootstrap.yml`**

```yaml
---
# Phase 01 — bootstrap: reachability gate → baseline OS → OS/SSH hardening.
# devsec.hardening is the SOLE owner of sshd_config hardening (the cloud-init
# 60-v2e.conf drop-in is retired in v2e-tf). health_check runs first (fail-fast).

- name: Smoke test — confirm the automation mesh can reach every node
  hosts: linux
  gather_facts: false
  tasks:
    - name: Ping all managed hosts
      ansible.builtin.ping:

- name: Health checks (fail-fast gate)
  hosts: linux
  gather_facts: false
  roles:
    - health_check

- name: Baseline configuration on all Linux nodes
  hosts: linux
  become: true
  roles:
    - baseline

- name: OS + SSH hardening (devsec) and fail2ban
  hosts: linux
  become: true
  roles:
    - devsec.hardening.os_hardening
    - devsec.hardening.ssh_hardening
    - fail2ban
```

- [ ] **Step 2: Delete the retired role**

```bash
git rm -r roles/deb_hardening_basic
```

- [ ] **Step 3: Confirm nothing else references the deleted role**

Run: `grep -rnE '\bdeb_hardening_basic\b' site.yml playbooks/ roles/ inventory/ 2>/dev/null || echo "no references"`
Expected: `no references`.

- [ ] **Step 4: Syntax-check + lint the whole tree**

Run: `ansible-playbook --syntax-check site.yml && ansible-lint`
Expected: syntax-check prints the combined play list resolving `devsec.hardening.os_hardening`/`ssh_hardening` (collection installed); `ansible-lint` → 0 failures, production profile.

- [ ] **Step 5: Commit**

```bash
git add playbooks/01-bootstrap.yml
git commit -m "bootstrap: swap deb_hardening_basic for devsec.hardening + fail2ban"
```

---

### Task 5: Retire cloud-init `60-v2e.conf` (v2e-tf, cross-repo)

**Files (in the `v2e-tf` repo at `/Users/alex/Documents/v2e-environment/v2e-tf`):**
- Modify: `cloud-init/node.yaml.tftpl` (remove the `60-v2e.conf` write_files entry)
- Possibly modify: `nodes.tf` (drop the now-unused `ssh_allow_users` local)

- [ ] **Step 1: Branch in v2e-tf**

```bash
cd /Users/alex/Documents/v2e-environment/v2e-tf
git checkout -b fix/retire-sshd-dropin
```

- [ ] **Step 2: Inspect the exact block to remove**

Run: `grep -n '60-v2e\|ssh_allow_users\|restart ssh\|ssh_pwauth' cloud-init/node.yaml.tftpl`
Expected: shows the `write_files` entry writing `/etc/ssh/sshd_config.d/60-v2e.conf` (PermitRootLogin/PasswordAuthentication/AllowUsers), plus `ssh_pwauth: false` and a `systemctl restart ssh` runcmd.

- [ ] **Step 3: Remove the `60-v2e.conf` write_files entry**

Delete ONLY the `write_files` list item whose `path` is `/etc/ssh/sshd_config.d/60-v2e.conf` (the `- path:`/`permissions:`/`content:` block, lines ~41–47). **Keep** `ssh_pwauth: false` and all user creation. If the `- systemctl restart ssh` runcmd existed solely to apply that drop-in, remove it too; if unsure, keep it (harmless — sshd reload is idempotent).

- [ ] **Step 4: Drop the now-unused `ssh_allow_users` local (if unreferenced)**

Run: `grep -rn 'ssh_allow_users' *.tf cloud-init/`
If `ssh_allow_users` is no longer referenced by any template, remove its definition in `nodes.tf` (the `ssh_allow_users = k == "control" ? ...` line) and the corresponding key in the `templatefile(...)` vars map. If still referenced anywhere, leave it.

- [ ] **Step 5: Validate**

Run: `export PATH="/opt/homebrew/bin:$PATH"; tofu fmt && tofu validate`
Expected: `fmt` clean; `validate` → "Success! The configuration is valid." Then confirm the drop-in is gone:
`grep -c '60-v2e' cloud-init/node.yaml.tftpl` → `0`.

- [ ] **Step 6: Commit (in v2e-tf)**

```bash
git add cloud-init/node.yaml.tftpl nodes.tf
git commit -m "cloud-init: retire 60-v2e.conf; devsec (ansible) owns sshd_config"
```

---

### Task 6: Final acceptance + live-env test plan

**Files:**
- Create: `docs/superpowers/plans/ans-2a-live-test-plan.md` (v2e-ansible)

- [ ] **Step 1: Confirm requirements + collection resolve**

Run:
```bash
cd /Users/alex/Documents/v2e-environment/v2e-ansible
TMP=$(mktemp -d); ansible-galaxy collection install -r requirements.yml -p "$TMP" >/dev/null 2>&1 && echo "requirements OK rc=$?"; rm -rf "$TMP"
ansible-galaxy collection list 2>/dev/null | grep -i devsec.hardening
```
Expected: `requirements OK rc=0`; `devsec.hardening` present (10.x).

- [ ] **Step 2: Full static acceptance**

Run:
```bash
ansible-playbook --syntax-check site.yml && echo "syntax OK"
ansible-lint && echo "lint 0 failures"
```
Expected: `syntax OK` and `lint 0 failures` (production profile).

- [ ] **Step 3: Write the live-env test plan**

Create `docs/superpowers/plans/ans-2a-live-test-plan.md` with these checks to run against the rebuilt Proxmox env (Proxmox console open as rollback before the first apply):

```markdown
# ANS-2a — live-env behavioral test plan

Run at the next Proxmox apply. Keep the Proxmox console open before applying.

1. sshd effective config (per node): `sudo sshd -T | grep -E 'passwordauthentication|permitrootlogin|allowusers|subsystem sftp'`
   Expect: `passwordauthentication no`, `permitrootlogin no`,
   `allowusers v2e` on control / `allowusers v2e ansible` on services+agent,
   `subsystem sftp` present.
2. Docker networking sysctl: `sysctl net.ipv4.ip_forward` → `= 1` on all linux nodes.
3. SFTP file copy: from control, `ansible all -m ansible.builtin.copy -a "content=ok dest=/tmp/ans2a.test"` → all changed/ok.
4. Inter-VLAN: from control, `nc -zv 10.1.2.10 22` and `nc -zv 10.1.3.10 22` succeed.
5. fail2ban: `sudo fail2ban-client status sshd` → jail active.
6. No lockout: a NEW ssh session as v2e (control) and as ansible (services/agent) succeeds;
   existing sessions survive; break-glass console login verified available.
7. (with ANS-3 Docker) a container reaches the internet and another container — forwarding intact.
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/ans-2a-live-test-plan.md
git commit -m "docs: ANS-2a live-env behavioral test plan"
```

---

## Self-review notes

- **Spec coverage:** health_check (T1) · devsec ssh/os config via group_vars, AllowUsers + ip_forward preserved (T2, T4) · fail2ban preserved (T3) · retire role + cloud-init drop-in single-owner (T4, T5) · static verification + live test plan (T6). All spec sections mapped.
- **Placeholder scan:** every step has concrete content; devsec var names + values verified against the installed 10.6.0 collection. No TBD/TODO.
- **Consistency:** role names `health_check`/`fail2ban` and their `health_check_*`/`fail2ban_*` vars match across tasks; `ssh_allow_users` values (`"v2e"`, `"v2e ansible"`) and `sysctl_overwrite` key match spec; devsec FQCN role refs (`devsec.hardening.os_hardening`/`ssh_hardening`) consistent.
- **Testing note:** `--check` against the down env is intentionally NOT an acceptance gate (health_check's wait_for_connection would fail); static (syntax + lint) is the gate, live behaviour is Task 6's plan.
