# ANS-3 — live-env behavioral test plan

Run at the full from-scratch deploy (real domain + Cloudflare token + age key + sops_secrets_file).
**Prerequisite:** The Cloudflare token must be SCOPED (Zone:Read + DNS:Edit), not the global API key.

1. Engine: `systemctl is-active docker` = active; `id ansible` shows the `docker` group;
   `docker info -f '{{.LoggingDriver}}'` = json-file; `/etc/docker/daemon.json` has live-restore + log limits.
2. Network: `docker network ls` shows `frontend`.
3. `.env`: `/opt/v2e-compose/.env` is 0600 root; holds DOMAIN/ACME_EMAIL/CERT_RESOLVER=staging + `CF_DNS_API_TOKEN` and `TINYAUTH_AUTH_USERS`.
   **Note:** `docker compose --env-file` interpolates `$`; a bcrypt hash in `TINYAUTH_AUTH_USERS` contains `$` chars that must be `$$`-escaped in the SOPS secret (or stored such that compose doesn't mangle them). Verify tinyauth actually accepts the configured user at live deploy — not just that the container is up.
4. Stacks up: `docker compose ls` shows traefik, tinyauth, whoami; `docker ps` all healthy.
5. Cert: Traefik issues a valid **staging** wildcard cert via Cloudflare DNS-01 (traefik logs / acme.json 0600).
6. Reachability: `https://whoami.<domain>` returns 200 over HTTPS; `http://` redirects to `https://`.
7. tinyauth container is up (COMPOSE-2 caveat: full forward-auth middleware enforcement is COMPOSE-2's job).
8. Flip `compose_stack_cert_resolver: production` and re-run once staging issues cleanly.
