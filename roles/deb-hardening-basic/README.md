# deb-hardening-basic

General, reusable **baseline** hardening for any Debian/Ubuntu host. Minimal and
host-agnostic — no environment-specific assumptions. Layer host/role-specific
hardening on top with `deb-hardening-{server,agent,host}`.

Pure `ansible.builtin`. What it does (all toggleable — see `defaults/main.yml`):

- **SSH** drop-in (`/etc/ssh/sshd_config.d/10-hardening.conf`): key-only auth, no
  root login, sane limits. The handler validates the **full** config (`sshd -t`)
  and only then reloads (not restarts) — never locks out key auth; live sessions
  preserved. Sorts before `50-cloud-init.conf`, so it overrides the image default.
- **sysctl** (`/etc/sysctl.d/90-hardening.conf`): IPv4 network + kernel hardening.
- **fail2ban**: sshd jail enabled (journal backend, so it works on Debian too).

> Defaults disable password SSH auth (`deb_hardening_ssh_password_auth: false`).
> Make sure key access works before applying to a host that relies on passwords.
