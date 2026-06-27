# baseline

OS baseline applied to every managed node. Pure `ansible.builtin` (no collection
dependency — safe for the unattended first-boot run).

- qemu-guest-agent enabled (clean shutdown + IP reporting to Proxmox)
- time sync via systemd-timesyncd (`timedatectl set-ntp`)
- timezone (`baseline_timezone`, default `UTC`)
- systemd-journald disk cap (`baseline_journald_max_use`, default `200M`)
- unattended-upgrades: security-only, **no auto-reboot** (reboots are owned by the
  on-demand `patch` role and first-boot cloud-init)

See `defaults/main.yml` for variables.
