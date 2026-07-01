# compose_stack

Deploys the `v2e-compose` stacks (traefik, tinyauth, whoami) on the services
node with `community.docker.docker_compose_v2`. Asserts the SOPS secrets
(`cf_dns_api_token`, `tinyauth_auth_users`), ensures git, clones the repo to
`compose_stack_dir` (`/opt/v2e-compose`), creates the external `frontend`
network, renders a 0600 root `.env`, and brings each stack up. Non-secret config
(`DOMAIN`/`ACME_EMAIL`/`CERT_RESOLVER`) is in `group_vars/services.yml`; secrets
come from SOPS `group_vars/all.yml`. Run after `geerlingguy.docker`.
