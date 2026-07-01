# ai_workbench

Turns the **agent** node into an AI workbench. Run against the `agent` host (see
`agents.yml`); the accounts themselves come from the `ai_identities` role.

Installs:

- **Node.js** (NodeSource LTS, `ai_workbench_node_major`),
- **Claude Code** and **Codex** as npm globals (system-wide),
- the **superpowers** Claude Code plugin for `ai_workbench_superpowers_accounts`
  (default `claude`), via `obra/superpowers-marketplace`,
- per-account auth from vault (`ANTHROPIC_API_KEY` for Claude, `codex login
  --api-key` for Codex) — **skipped when the key is empty**, so the play never
  fails without a vault; log in interactively later,
- `/usr/local/bin/agent-run`, a headless wrapper: `agent-run claude "<prompt>"`
  (→ `claude -p`) or `agent-run codex "<prompt>"` (→ `codex exec`).

## Secrets

Put the keys in an Ansible Vault file (e.g. `inventory/group_vars/all/vault.yml`,
encrypted), referenced by `ai_workbench_anthropic_api_key` /
`ai_workbench_openai_api_key`:

```yaml
vault_anthropic_api_key: "sk-ant-..."
vault_openai_api_key: "sk-..."
```

Never commit these in plaintext.

## Notes

- The exact `claude plugin marketplace add` / `claude plugin install` flags vary by
  Claude Code version; they're variableised and guarded so adjusting is a one-liner.
- Collections used (shipped in the pipx `ansible` bundle): `community.general`.

See the repo README for tasking an agent from control (`task-agent.yml`).
