# egress_tap

**DESIGN, NOT YET VALIDATED AGAINST A LIVE ROUTER.** Bounded, reversible WAN
egress capture on VyOS's `eth0` (WAN) interface via a transient, self-
terminating `systemd-run` + `tcpdump` unit. Modeled on
[`roles/agent_access`](../agent_access/README.md) and
[`roles/killswitch`](../killswitch/README.md): additive, removable, tagged,
`never`-guarded plays that force their own state. Driven by
`egress_tap_state`; normally invoked through `playbooks/ops/egress-tap.yml`'s
tags rather than directly.

| state | effect |
|-------|--------|
| `start` | Launch a bounded `tcpdump` capture on `egress_tap_interface` (default `eth0`/WAN) via `systemd-run`, ring-buffered by both `-G`/`-W` (rotation count) and a hard `RuntimeMaxSec` (self-terminates even if `stop` is never run). Headers-only (`egress_tap_snaplen`, default 96 bytes) unless `egress_tap_full_payload` is explicitly set. |
| `status` | Read-only: unit health + capture directory usage. Safe anytime. |
| `stop` | Stop the unit (idempotent), fetch the bounded pcap set to the control host, delete the on-router copy. |

## Why tcpdump, not a VyOS interface mirror

The router has exactly two NICs (`eth0` WAN, `eth1` LAN trunk carrying all
VLAN sub-interfaces — see `v2e-tf/variables.tf:159-168`); a true SPAN-style
port mirror needs a third destination interface this VM doesn't have. An
on-box, transient capture needs no new interface and makes **zero**
persistent VyOS config changes (no `set`/`commit`/`save`) — reversibility is
just "the process ends," not "and someone remembers to remove the config."

## ⚠️ Connection model — reads against the grain of the existing inventory

`inventory/hosts.ini`'s `[vyos:vars]` pins the router to
`ansible.netcommon.network_cli` specifically because it's "not python" — that
connection type only understands structured VyOS op-mode/config commands, not
arbitrary shell execution, so it **cannot** run `tcpdump`/`systemd-run`. This
role's plays deliberately override `ansible_connection` to plain `ssh` for
just these three plays, landing in `vbash` (VyOS's login shell — a real,
unrestricted bash, not a jail) with `become: true` for the root privilege
`tcpdump`/`systemd-run` need.

**Not yet confirmed against a live box:** that python3 and passwordless sudo
are actually available to the router's SSH login user in vbash. VyOS's own
CLI tooling is itself Python-based, so python3 is very likely present, but
this needs a real check before this role is ever run for real — it has not
been applied or tested.

## Data handling

Captured pcaps carry NAT'd WAN traffic for every internal host — treat as
secret-adjacent even with the default headers-only snaplen (DNS query names,
TLS SNI, and metadata can already be sensitive). **Never** commit a pcap to
git or paste its contents into a vault note. Feed it to
`scripts/egress-analysis.py` and keep only that script's classified,
non-payload report.

## Key variables

| var | default |
|-----|---------|
| `egress_tap_state` | `status` (forced by `egress-tap.yml`'s plays) |
| `egress_tap_interface` | `eth0` |
| `egress_tap_duration_seconds` | `900` (15 min hard cap) |
| `egress_tap_snaplen` | `96` (headers only) |
| `egress_tap_full_payload` | `false` |
| `egress_tap_full_payload_snaplen` | `262144` |
| `egress_tap_rotate_seconds` | `60` |
| `egress_tap_max_files` | `20` |
| `egress_tap_capture_dir` | `/run/egress-tap` (tmpfs — self-clears on reboot) |
| `egress_tap_fetch_dest` | `~/egress-tap-captures/{{ inventory_hostname }}` on the control host |

## Prerequisites (unverified — flag for the operator)

- python3 + passwordless sudo for the router's SSH user, in vbash.
- `tcpdump` present on the VyOS image (VyOS ships it for `monitor traffic`;
  the CLI's `monitor traffic` op-mode command is itself a tcpdump wrapper,
  which is reasonable evidence it's present, but not directly confirmed for
  scripted/backgrounded use).
