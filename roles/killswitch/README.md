# killswitch

Router-enforced kill switch for the agent subnet, applied to the VyOS router via
`vyos.vyos.vyos_config` (network_cli). Driven by `killswitch_state`; normally
invoked through `killswitch.yml`'s tags rather than directly.

| state | effect |
|-------|--------|
| `cut` (default) | **Surgical.** Drop all forwarded traffic sourced from `killswitch_agent_subnet` (WAN egress + inter-VLAN), but keep `control`↔`agent` SSH alive (rules `base`/`base+1`). Also tears down in-flight agent sessions. |
| `allow` | Remove the kill-switch rules and re-enable the VLAN interface → back to the base firewall. Safe from any prior state. |
| `cut-hard` | Disable the agent VLAN sub-interface entirely. Total blackout, no recovery channel. |

The cut is **additive and removable** (rules `100`/`101`/`110` by default), so it
composes with a default-deny base firewall if one is present. Override
`killswitch_rule_base` if those numbers are already taken. Nothing here touches the
router's own input path from `control`, so a plain commit can't lock you out.

⚠️ The kill switch is only as strong as the agents' inability to reach the router.
With AI accounts rooted on `control` (which holds router-capable mesh keys), prefer
operating it **out-of-band** — see the repo README.

## Key variables

| var | default |
|-----|---------|
| `killswitch_state` | `cut` |
| `killswitch_agent_subnet` | `10.1.3.0/24` |
| `killswitch_mgmt_host` | `10.1.1.10` (control) |
| `killswitch_rule_base` | `100` |
| `killswitch_lan_iface` / `killswitch_agent_vlan` | `eth1` / `103` (cut-hard) |
| `killswitch_save` | `true` |
