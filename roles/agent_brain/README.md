# agent_brain

Makes node 313 login-ready for the v2e agent team: separate public/private
repository checkouts, the `vault` CLI, leak guard, Superpowers, a safe fast-forward
pull timer, and — as **optional** accelerators (never hard dependencies) — a pinned
Graphify CLI and the Context7 docs plugin.

## Required SOPS variables

```yaml
vault_agent_brain_public_deploy_key: <private key for v2e-sh/agents>
vault_agent_brain_private_deploy_key: <private key for v2e-sh/agents-pers>
```

GitHub deploy keys are repository-scoped, so generate and register two keys.
Grant write access only when the account is expected to push memory changes.
The role never creates, registers, prints, or commits key material.
The site play activates the role automatically once both SOPS variables are
available; before that, phase 07 is a safe no-op.

Graphify is optional: when installed it may accelerate code navigation, but the
brain never depends on it — if it is absent or errors, fall back to grep/targeted
reads. Graph output is globally ignored in Git status. Do not add private memory to
a shared/global graph or replace the vault's leak guard.

Context7 is installed through its official Claude plugin, which supplies MCP
tools, an automatic documentation skill, docs-researcher agent, and manual
command. Anonymous access works by default. For higher limits, optionally add
`vault_context7_api_key` to SOPS; it is rendered only to a mode-`0600` per-user
environment file.
