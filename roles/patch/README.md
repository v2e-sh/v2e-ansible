# patch

On-demand full OS patch. Pure `ansible.builtin`.

Runs `apt-get dist-upgrade` + autoremove, then reboots **only if**
`/var/run/reboot-required` exists — and **never** the Ansible controller (guarded
by group + local-connection checks).

Invoked via the standalone, tag-gated `playbooks/ops/patch.yml` (not part of
`site.yml`):

```bash
ansible-playbook playbooks/ops/patch.yml
```

First-boot patching is handled by cloud-init; ongoing *security* patching by
unattended-upgrades (baseline role). This role is the on-demand *full* upgrade.

See `defaults/main.yml` for variables.
