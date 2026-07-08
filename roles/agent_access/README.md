# agent_access

Operator switch that OPENS and CLOSES the AI agent's jump-host reach (agent VLAN
-> control:22) for a bounded production-readiness test window, then re-hardens
with zero residue. Two halves: a VyOS forward-filter rule via
`vyos.vyos.vyos_config` (network_cli), and control-side `authorized_keys`
management via `ansible.posix.authorized_key` / `ansible.builtin.lineinfile`.
Driven by `agent_access_state` + `agent_access_half`; normally invoked through
`agent-access.yml`'s tags rather than directly.

| state | half | effect |
|-------|------|--------|
| `open` | `key` | Authorize the agent's pubkey (reused from `ai_identities`, hub = `groups['agent'][0]`) on control's landing account. Runs FIRST so the path has somewhere to land before it opens. |
| `open` | `rule` | Add a temporary VyOS forward-filter accept: `agent_subnet` (10.1.3.0/24) -> `control_ip` (10.1.1.10), dport 22/tcp. Forward chain only — never touches the input chain, so the network_cli path Ansible rides is never severed. |
| `open` | `verify` | From control, TCP-reachability-check control->services:22 and control->vyos:22. Confirms the mesh survived. Hard-gates on failure by default (`agent_access_verify_hard`). |
| `close` | `rule` | Delete the temporary rule (idempotent, `failed_when: false`). Runs FIRST so the path is cut before the key is touched. |
| `close` | `key` | Strip every agent key from the landing account's `authorized_keys` by an anchored comment match (`@v2e-ai\s*$`) — no hub round-trip, multi-account safe, works even if the agent VLAN is already cut. **The only remover for the key half.** |

Both halves are **additive and removable**, mirroring
[`roles/killswitch`](../killswitch/README.md). Ordering across the 5 plays in
`playbooks/ops/agent-access.yml` is load-bearing:

- **OPEN:** key -> rule -> verify (authorize before opening the path; verify last).
- **CLOSE:** rule -> key (cut the path before deauthorizing — the reverse of OPEN).

Like `killswitch`, every play carries `never`, so a bare
`ansible-playbook playbooks/ops/agent-access.yml` does nothing — you must pass
`--tags open` or `--tags close`. Each play also forces
`agent_access_state`/`agent_access_half` itself, so there's nothing to
fat-finger with `-e`.

## Rule number: 111

`agent_access_rule` (111) MUST sit **above** the killswitch reserve (100-110):
VyOS matches lowest-number-first, so if the kill switch is engaged (its drop
lives at `killswitch_rule_base + 10` = 110) it must win over this accept when
both are active — a lower-numbered allow would otherwise silently punch
through a higher-numbered drop. 111 also clears the v2e-tf cloud-init baseline
(10, 20, 21, 25, 26, 27, 30-35). `preflight.yml` hard-fails if
`agent_access_rule` is ever moved into either reserved range.

## Drift & residue

- `agent_access_save` defaults to **`false`** (session-only): a router reboot
  self-heals the rule half back to the closed Terraform cloud-init baseline —
  Terraform never has to fight a persisted rule it doesn't own.
  `agent_access_save: true` is a **footgun**: it persists the accept to
  `config.boot` AND Terraform won't remove it (the rule isn't in its state) —
  don't set it without a specific reason and a plan to clean it up by hand.
- The **key half has no baseline to self-heal to** — `authorized_keys` isn't
  Terraform-managed. `--tags close` is the ONLY remover. Re-hardening after
  any open window is **mandatory**, not optional.

### Post-close residue check

After `--tags close`, confirm zero residue:

```
# On vyos: the rule should be gone
show firewall ipv4 forward filter rule 111

# On control: no agent key should remain for the landing account
grep '@v2e-ai' /home/v2e/.ssh/authorized_keys   # expect: no output
```

## Prerequisites

This role does **not** generate keys — it reuses the keypair `ai_identities`
already generated on the hub (`/home/<ai>/.ssh/id_ed25519`). `preflight.yml`
fails clearly ("run playbooks/ops/agents.yml first") if that keypair is absent.

## ⚠️ Operator decision: landing account = v2e (Option A)

The chosen landing account is `v2e` — already in control's `ssh_allow_users`,
so no new AllowUsers entry is needed. **But `v2e`'s control-side key also
reaches the VyOS router** (the existing v2e/ansible mesh). During any open
window this means a jumped-in agent could reach the router and undo an
in-band kill switch — so **operate the kill switch OUT-OF-BAND** (operator Mac
/ Proxmox console) for the duration of any `agent_access` open window.
`preflight.yml` prints a debug warning to this effect on every open run.
`agent_access_save` stays `false` and `agent_access_verify_hard` stays `true`
for the same reason: this configuration has no built-in backstop if the
operator forgets the out-of-band discipline, so the automated guards are the
next line of defense.

**Deferred hardening (Option B, not built):** stand up a dedicated control
landing account whose key does NOT reach VyOS, and land the agent there
instead of `v2e`, so "jump host only" holds by construction and the
out-of-band-killswitch requirement goes away. Tracked as a brain task
(`agent-access-dedicated-landing-account`).

## Key variables

| var | default |
|-----|---------|
| `agent_access_state` | `close` (forced by `agent-access.yml`'s plays) |
| `agent_access_half` | `rule` (forced by `agent-access.yml`'s plays) |
| `agent_access_agent_subnet` | `10.1.3.0/24` |
| `agent_access_control_ip` | `10.1.1.10` |
| `agent_access_rule` | `111` |
| `agent_access_killswitch_reserve_start` / `_end` | `100` / `110` |
| `agent_access_baseline_rules` | `[10, 20, 21, 25, 26, 27, 30, 31, 32, 33, 34, 35]` |
| `agent_access_save` | `false` |
| `agent_access_landing_account` | `v2e` |
| `agent_access_hub_host` | `{{ groups['agent'][0] }}` |
| `agent_access_ai_account` | `claude` |
| `agent_access_services_ip` | `10.1.2.10` |
| `agent_access_vyos_ip` | `10.1.1.1` |
| `agent_access_verify_hard` | `true` |
