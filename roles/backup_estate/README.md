# backup_estate

**DESIGN, NOT YET APPLIED.** File-level backup of mutable estate state —
`pg_dump` targets, named Docker volumes, and bind-mounted state directories
— staged locally then rsynced to an external target (path from SOPS) under
a dated subdirectory, pruned by `backup_estate_retain_days`. Complements
`v2e-tf`'s coarse `proxmox_backup_job` (whole-VM vzdump): this role is the
fast, granular restore path (a single dashboard, a single cert, a single
DB) where a whole-VM restore would be overkill.

Tag-gated exactly like `roles/killswitch`/`roles/agent_access`: every task
carries `never` plus its own tag. `--tags install` renders the script +
systemd timer and enables it (does not run the backup itself); `--tags run`
executes the backup script once, immediately, for manual testing or a
first backup before the timer's first scheduled fire.

## What it does NOT do

- **Does not manage the backup target's mount.** `backup_estate_target_dir`
  must already exist and be mounted (e.g. an NFS/SMB share from TrueNAS,
  mounted by whatever role/fstab entry owns that) — the role's first task
  asserts this and fails loudly rather than writing backups nowhere.
- **Does not touch `.env`/secret files.** Every bind-dir tar explicitly
  excludes `.env`, `*.env`, and `secrets/*` — this role backs up *rendered*
  state, never the secret material that renders it (SOPS already owns that,
  safely, elsewhere).
- **Does not back up `control`.** Control holds the mesh SSH keys and SOPS
  age key in plaintext on disk — a control backup is a materially different
  risk (see `docs-secrets-residual-exposure` in the brain) and needs its
  own, separately-reviewed handling, not bolted onto this role.

## Per-host configuration (group_vars, not this role's defaults)

Named Docker volumes are Compose-project-prefixed as `<stack-dir-name>_<volume-key>`
— confirmed against `roles/compose_stack`'s `project_src` (no explicit
`project_name` override exists anywhere in `v2e-compose`, so Compose
defaults the project name to the stack directory's basename).

**`inventory/group_vars/services.yml`** (illustrative — confirm exact
container/volume names against the live stack before applying):

```yaml
vault_backup_estate_target_dir: "{{ vault_backup_target_nfs_path }}"  # from SOPS

backup_estate_pg_dumps:
  - name: semaphore
    container: semaphore-postgres-1
    user: semaphore
    db: semaphore

backup_estate_docker_volumes:
  - observability_prometheus-data
  - observability_grafana-data
  - observability_loki-data
  - observability_kuma-data
  - authelia-data
  - vaultwarden-data

backup_estate_bind_dirs:
  - name: acme
    path: /opt/v2e-compose/traefik/data/certs/acme.json
```

**`inventory/group_vars/infra.yml`**:

```yaml
vault_backup_estate_target_dir: "{{ vault_backup_target_nfs_path }}"  # from SOPS

backup_estate_bind_dirs:
  - name: technitium-zone
    path: /opt/v2e-compose/technitium/data
```

Container/volume names above are derived from the charter's stated targets
(pg_dump semaphore db; tar of technitium zone, acme.json, grafana,
uptime-kuma; the docker volumes the original plan missed — prometheus-data,
loki-data) plus the compose-project-prefix convention — **not independently
re-verified against `docker volume ls`/`docker ps` on a live host this
run**. Confirm exact names before the first real `--tags run`.

## Observability

Every run (success or failure) writes a node-exporter textfile metric to
`backup_estate_textfile_dir` (`v2e_backup_estate_last_run_timestamp_seconds`,
`_last_run_success`, `_last_run_duration_seconds`) — this exists now so
charter AREA 5.4 (backup-job observability + alerting) has something to
scrape immediately rather than needing a second role change.

## Key variables

| var | default |
|-----|---------|
| `backup_estate_target_dir` | none — `mandatory`, set via SOPS (`vault_backup_estate_target_dir`) |
| `backup_estate_retain_days` | `14` |
| `backup_estate_docker_volumes` | `[]` — set per host group |
| `backup_estate_bind_dirs` | `[]` — set per host group |
| `backup_estate_pg_dumps` | `[]` — set per host group |
| `backup_estate_exclude_patterns` | `[.env, *.env, secrets/*]` |
| `backup_estate_schedule` | `*-*-* 03:00:00` (1h after the default vzdump 02:00, to avoid disk-I/O contention) |
| `backup_estate_textfile_dir` | `/var/lib/node_exporter/textfile_collector` |
