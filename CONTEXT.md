# CONTEXT

Domain glossary, component overview, and key flows for `tacacs-web`. Strategic decisions are captured as ADRs under [`docs/adr/`](docs/adr/); this document is the running glossary and runtime-architecture map.

## Architecture overview

```
                            Docker Compose stack (single host)
   +----------------------------------------------------------------------------+
   |                                                                            |
   |  Network devices --TACACS+:49--> tac_plus-ng --fd pipe--> mavis (Python)   |
   |                                       |                       |            |
   |                                       v                       v            |
   |                                   acct log file         +-----------+      |
   |                                       |                 | Postgres  |      |
   |                                       v                 +-----------+      |
   |                                accounting-ingestor             ^           |
   |                                       |                        |           |
   |                                       v                        |           |
   |                              remote syslog (TCP/TLS, RFC5424)  |           |
   |                                                                |           |
   |  Browser --HTTPS:8443--> nginx --> backend (FastAPI) ----------+           |
   |                                       |                                    |
   |                                       |-- SAML SP                          |
   |                                       |-- AD-Sync worker -----------------+|
   |                                       `-- REST API + Setup-Wizard         ||
   |                                                                           ||
   +----------------------------------------------------------------------------+
                                       |                                       |
                                       v                                       v
                          Active Directory (LDAPS:636)         Remote Syslog Collector
                          FortiAuthenticator (SAML)
```

## Components

| Container | Role | Notes |
|---|---|---|
| `tac_plus-ng` | TACACS+ daemon (Marc Huber) | Built from source. Minimal static config. MAVIS-external module wired to `mavis`. Logs accounting to a file shared with the ingestor. |
| `mavis` | Python MAVIS handler | Long-lived child spawned by `tac_plus-ng`. Handles authn (LDAPS bind) and authz (DB lookup). In-memory authz cache, 60s TTL, flushable from UI. |
| `backend` | FastAPI app | REST API, SAML SP, AD-sync worker, accounting-ingestor, setup wizard. Alembic auto-migrates on start. |
| `frontend` | React + Mantine SPA (build artifact) | Served as static files via nginx. Built with Vite + TypeScript. i18n via i18next (en + de from day one). |
| `nginx` | Reverse proxy + TLS termination | BYO cert via UI upload. Self-signed bootstrap on first start. |
| `db` | Postgres 17 | App state + accounting + audit log. |

The `mavis` process runs inside the `tac_plus-ng` container (spawned by the daemon). The accounting-ingestor runs inside the `backend` container as a background worker.

## Glossary

- **NAS** (Network Access Server) — a network device (switch, router, firewall) that authenticates its admin users via TACACS+.
- **MAVIS** — Marc Huber's modular authentication system used by `tac_plus-ng`. We use the *external* module mode where `tac_plus-ng` pipes requests to a long-lived child process.
- **AV-Pair** — TACACS+ attribute-value pair, e.g. `priv-lvl=15`, `service=shell`, `cmd=show*`.
- **Principal** — entity that holds permissions. Can be a `User` (synced from AD) or an `AD-Group` (synced from AD). Local break-glass TACACS users are not principals — they bypass the authz model entirely and always get a fixed configured profile.
- **Device** — a single network device entry, identified by IP (`/32`, `/128`) or CIDR. Longest-prefix wins on overlap with the NAS source IP.
- **DeviceGroup** — flat grouping of Devices. A Device belongs to exactly one DeviceGroup. Authorizations target a DeviceGroup, not individual Devices.
- **PrivilegeProfile** — named, globally reusable bundle of TACACS+ authorization attributes: `tacacs_priv_lvl` (0..15), `permit_commands_regex` (list), `deny_commands_regex` (list, deny wins over permit), `extra_av_pairs`. Service is implicitly `shell`.
- **Authorization** — link of `(principal, device_group, privilege_profile)`. Drives "who gets what on which device group".
- **Effective Permissions** — the union of all matching Authorizations for a given user against a given device group. Conflict resolution: highest `tacacs_priv_lvl` wins; direct-user Authorization overrides AD-group Authorization (see ADR-0006).
- **Break-Glass account (TACACS)** — local-only network-operator user with bcrypt-hashed password in DB, never synced from AD. Allows network-device login when AD is unreachable. Managed via UI under Settings → Break-Glass.
- **Break-Glass account (Web UI)** — exactly one local admin for the management UI, managed via CLI (`tacacs-web bootstrap-admin`). Argon2 hash. Used when SAML IdP is unreachable. Lives at a separate `/login/local` path; every action audited with `auth_method=local`.
- **MAVIS Cache** — in-memory cache in the `mavis` process keyed by `(username, nas_ip, service)` → authz result. TTL 60s default, flushable from the UI. Authn is **never** cached.
- **Sync Scope** — AD search base(s) + optional LDAP filter that define which AD users land in our DB. Users dropping out of scope are soft-disabled (`enabled=false`) — their record and accounting history are retained, MAVIS rejects their next login.
- **Shared Secret** — TACACS+ pre-shared key, one per Device. We store `current_secret_enc` and `previous_secret_enc` so a Device can accept both during a rotation window (see ADR-0007).
- **Master Key** — 32-byte AES-GCM key used to decrypt all encrypted columns in the DB. Operator-supplied via Docker secret; app refuses to start without it.

## Key flows

### TACACS+ login flow

1. Operator runs `ssh admin@core-sw-01`. Switch sends TACACS+ Authn-START to our daemon.
2. `tac_plus-ng` looks up the NAS by source IP, validates the shared secret.
3. Daemon hands the authn request to `mavis` over the pipe.
4. `mavis`:
   1. Looks up the username in DB. User exists and `enabled=true`? Else REJECT.
   2. Resolves the user's cached DN (from last AD sync).
   3. Opens a fresh LDAPS bind to AD with the supplied password. Bind succeeds? Else REJECT.
   4. Returns ACCEPT to the daemon.
5. Daemon sends Authn-PASS back to the switch.
6. Switch sends Authz-REQUEST (`service=shell`, usually with empty `cmd` for the exec session).
7. `mavis`:
   1. Computes Effective Permissions for `(user, nas_ip → device_group)`.
   2. Returns AV-pairs from the winning PrivilegeProfile (priv-lvl + extra AVs).
8. Switch grants shell at the resolved `priv-lvl` (no Cisco `enable` step — see ADR-0001 / DEPLOYMENT cookbook).
9. Per-command authorization (if configured on the switch) flows the same way with `cmd=show running-config` etc., matched against `permit_commands_regex` / `deny_commands_regex` (deny wins).
10. Accounting records (start/stop/cmd) are written to the daemon's log file, picked up by the accounting-ingestor, persisted in DB, and forwarded to remote syslog.

### AD sync flow

1. APScheduler triggers sync (default: every 1h) or admin clicks "Sync now".
2. Backend opens an LDAPS bind with the service account (password from encrypted DB column).
3. For each configured Base-DN, runs a paged subtree search with the configured filter.
4. For each returned user: upsert into `user` table; compute transitive group memberships using `LDAP_MATCHING_RULE_IN_CHAIN` (OID `1.2.840.113556.1.4.1941`); upsert `ad_group` rows; replace `user_ad_group` join rows.
5. Users present in DB but not returned by this sync get `enabled=false`; `last_seen_in_sync_at` is preserved; authorization rows are not touched.
6. Sync result (counts, errors, duration) recorded in audit log.

### Admin login flow (SAML)

1. Browser hits `/login` → backend issues SAML AuthnRequest, redirects to FortiAuthenticator.
2. User authenticates at FortiAuthenticator.
3. FortiAuthenticator POSTs SAML Response to `/saml/acs`.
4. Backend validates signature, audience, recipient, NotOnOrAfter, replay (single-use assertion-ID cache).
5. Extracts `nameID` + configured groups claim; maps the user's AD groups to one of `viewer` / `operator` / `admin` (highest match wins); rejects if no mapping.
6. Issues HttpOnly + Secure + SameSite=Lax session cookie, 8h sliding expiration, 24h hard cap.

### Admin login flow (local break-glass)

1. Browser hits `/login/local` (distinct route, prominently styled as emergency).
2. User enters break-glass username + password.
3. Backend verifies Argon2 hash. Optional CIDR restriction enforced if configured.
4. Session cookie identical to SAML path, but with `auth_method=local` claim. Every audit-log row of this session carries that marker.

### Setup wizard (first boot)

1. Operator runs `docker compose up` with master-key secret + DB env-vars set.
2. Backend boots, runs `alembic upgrade head`, detects empty `local_admin` table.
3. Any browser request gets redirected to `/setup`.
4. Wizard steps:
   1. Set local-admin password → log in immediately.
   2. Configure AD / LDAPS connection (Base-DN, bind DN, password, filter) → "Test connection" button.
   3. Configure SAML SP (upload IdP metadata or paste URL) → show SP entity-ID + ACS URL for the FortiAuth admin to register → map AD groups to viewer/operator/admin → "Test SAML round-trip" optional.
   4. Trigger first AD sync → preview user/group counts → done.
5. Wizard endpoints disable themselves once `local_admin` row exists.

## Authorization model (recap)

- **PrivilegeProfiles are global**, reusable across many DeviceGroups.
- **Devices are 1:1 with DeviceGroups**, no nesting, no tags (ADR-0005).
- **Conflict resolution**: highest `tacacs_priv_lvl` wins among all matching Authorizations; direct-user Authorization overrides AD-group Authorization (ADR-0006).
- **No time-bound Authorizations** in v1 — `valid_from`/`valid_until` columns deferred.
- **MAVIS cache TTL**: 60s default, flushable from UI. Authn never cached.

## Secrets at rest

- **Master key**: 32-byte AES-GCM key, operator-supplied as Docker secret. App refuses to start without it. Rotated via CLI `tacacs-web rotate-master-key`.
- **Encrypted columns**: AD bind password, TACACS shared secrets (`current` + `previous`), SAML signing key, TLS private key.
- **Local-admin password**: Argon2id hash (not encrypted).
- **TACACS break-glass passwords**: bcrypt hash (not encrypted).

## Observability

- All services log structured JSON to stdout. `LOG_LEVEL` configurable per service via env-var.
- Backend and `mavis` expose Prometheus `/metrics`. No bundled Grafana — operator integrates with their existing observability stack.
- Health endpoints: `/healthz/live` (process alive) + `/healthz/ready` (DB + LDAP + master-key + cert all OK). `tac_plus-ng` health via TCP-check on port 49.

## Concurrency

- All mutating REST endpoints support `If-Unmodified-Since` (or a `version` field) for optimistic locking. A stale write returns `409 Conflict` and the UI prompts the operator to reload.

## What's explicitly out of scope for v1

- Multiple AD domains / forests
- Time-bound authorizations
- Bulk import (CSV / YAML)
- TACACS+-over-TLS (RFC 8907 draft) — vendor support too thin in 2026
- TACACS+ services other than `shell` (`junos-exec`, `ppp`, …)
- Cisco `enable` authentication phase — devices must use `aaa authorization exec ... if-authenticated` so the priv-lvl from our authz response is honored directly
- HA / clustering
- Single Logout (SLO) for SAML
- UI-driven backup / restore (use the helper scripts in `scripts/`)

## File-system layout

```
.
|-- CONTEXT.md              (this file)
|-- README.md
|-- LICENSE
|-- docs/
|   `-- adr/                Architecture Decision Records
|-- docker/
|   |-- compose.yml         Stack definition
|   |-- tac_plus-ng/        Dockerfile + entrypoint + config template
|   |-- backend/            Dockerfile (multi-stage)
|   |-- frontend/           Dockerfile (multi-stage build)
|   `-- nginx/              Dockerfile + nginx.conf template
|-- backend/                FastAPI app + mavis + alembic + tests
|-- frontend/               React + Vite + Mantine SPA
|-- scripts/                backup.sh / restore.sh
`-- .github/workflows/      ci.yml / integration.yml / release.yml
```
