# scripts/

Standalone operational tooling that doesn't belong to a specific Ansible
role or playbook run.

## egress-analysis.py

Reads the pcap set produced by `roles/egress_tap` (`playbooks/ops/
egress-tap.yml --tags stop` fetches captures to
`~/egress-tap-captures/<router>/` on the control host) and produces a
classified, non-payload report: unique `dst_ip:port` grouped by source VLAN
(control/services/agent/mgmt, per `v2e-tf/network.tf`'s octet layout),
classified as DNS/NTP/HTTP/HTTPS/SSH/other.

```sh
pip install scapy
python3 scripts/egress-analysis.py \
  --input ~/egress-tap-captures/vyos01 \
  --report egress-report.md \
  --json egress-report.json
```

- **Fully offline by default** — reads only the local pcap files. The one
  exception is `--resolve-dns`, which issues real reverse-DNS lookups from
  wherever the script runs; it's opt-in and off by default so the script has
  no network side effects unless explicitly asked for.
- **Never inspects payload bytes** — only IP/TCP/UDP headers (source/dest
  address, port, protocol, timestamp). Safe to run against a full-payload
  capture too; it just won't look at the parts that make one sensitive.
- Output is a report of *classes* of destination (an IP:port and a
  DNS/NTP/HTTP/HTTPS/other tag, with packet counts and first/last-seen
  timestamps) — treat the underlying pcaps as secret-adjacent per
  `roles/egress_tap/README.md`, but the report itself is safe to read,
  share, or paste into a vault note.

## Runbook: reading a report

1. Group by VLAN first — `agent` traffic should be small and match the
   allowlisted DNS/NTP/TCP-80-443 pattern (`docs-agent-egress-killswitch` in
   the brain); anything outside that pattern from `agent` is the first thing
   to investigate.
2. Within a VLAN, sort by count (the Markdown report already does this) —
   the biggest talkers are usually legitimate (OS updates, container
   registries); look at the **long tail** of low-count, unfamiliar
   `dst_ip:port` pairs for anything unexpected.
3. Cross-reference `class: other` entries against known service ports
   (registries often use 443 anyway, so `other` mostly means non-standard
   ports) before treating any single row as a finding.
4. Feed unexplained destinations into
   `[[area3-egress-allowlist-tightening]]` (the brain task for tightening
   the wide-open control/services WAN-egress rules) rather than treating a
   single report as conclusive — run more than one capture window before
   proposing a tightened allowlist.
