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
