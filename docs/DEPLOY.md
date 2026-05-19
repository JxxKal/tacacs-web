# tacacs-web — Deployment Guide

End-to-end setup for a single-host production install. Audience: network /
platform admin comfortable with Docker Compose, AD/LDAPS, and PKI basics.
Cross-references to the relevant ADRs are included where a decision has
operational consequences.

> **Status note.** v1 is still in development. The current build covers the
> TACACS+ daemon, MAVIS authn + authz (with live LDAPS bind), the four CRUD
> resources (DeviceGroups, PrivilegeProfiles, Devices, Authorizations), the
> local break-glass admin login, and an append-only audit log. Setup wizard,
> SAML SP, AD-sync scheduler, accounting forwarder, and NAS-config-regen are
> not yet wired — see [Current limitations](#current-limitations).

---

## 1. Host requirements

| Item | Minimum | Notes |
|---|---|---|
| OS | Linux with cgroups v2 | Tested on Debian 13 |
| Docker Engine | 24+ | Compose v2 plugin must be installed |
| RAM | 2 GB | Postgres, backend, daemon, nginx, build cache |
| Disk | 10 GB | Postgres data + image layers grow with accounting (M6) |
| Open ports outbound | 636/tcp to AD | LDAPS bind, both sync and live-bind |
| Open ports inbound | 49/tcp from NAS devices; 8443/tcp from operator browsers (override via `HTTPS_HOST_PORT`) | HTTPS only; no plain-HTTP listener is exposed. |

The stack is single-host. HA / clustering is explicitly out of scope for v1.

---

## 2. Concepts to know before you start

These follow directly from the ADRs and shape every step below:

- **Master key** (32 raw bytes, AES-GCM). Every encrypted DB column (TACACS
  shared secrets, AD bind password) is sealed with this. Lose it and the
  ciphertexts become unreadable; rotate it and you must re-encrypt the
  columns. Stored as a Docker secret, never in the DB. (ADR-0004)
- **Local break-glass admin.** Exactly one local account, managed only via
  the `tacacs-web bootstrap-admin` CLI. Argon2id hash. Used when the SAML
  IdP is unreachable. (ADR-0003)
- **AD model.** Users are synced from AD into the local DB for the UI to
  reference them, but each TACACS login still does a live LDAPS bind to
  verify the password. (ADR-0002)
- **Device groups** are flat and 1:1 with devices. Authorizations bind a
  principal (user XOR AD group) to `(device_group, privilege_profile)`.
  Direct-user grants override AD-group grants; otherwise the highest
  `priv-lvl` wins. (ADR-0005, ADR-0006)

---

## 3. First-time setup

All commands run from the repo root unless noted.

### 3.1 Clone

```sh
git clone https://github.com/JxxKal/tacacs-web.git
cd tacacs-web
```

### 3.2 Generate secrets

```sh
mkdir -p secrets

# AES-GCM master key — 32 bytes, base64 single line.
openssl rand -base64 32 > secrets/master.key

# Postgres password — one line, no trailing newline.
openssl rand -base64 24 | tr -d '\n' > secrets/postgres_password
```

Back both up immediately. Without `secrets/master.key` a DB dump is
unreadable (ADR-0004).

### 3.3 Copy the env template

```sh
cp docker/.env.example docker/.env
```

Edit `docker/.env`:

| Key | Notes |
|---|---|
| `BASE_URL` | The HTTPS URL operators will reach. Used for SAML callbacks in M5b and absolute URLs. Example: `https://tacacs.internal.example.com:8443`. |
| `TACACS_SHARED_SECRET` | Generated value, **at least 32 chars**. Every NAS that talks to us uses this one secret until the per-device-secret regen flow lands (see [Current limitations](#current-limitations)). |
| `TZ` | Affects log timestamps. Use `Europe/Berlin` or your host TZ. |
| `*_BIND_ADDR` | Default `0.0.0.0`. Restrict to specific host IPs if you do not want TACACS or the UI bound on every interface. |

### 3.4 Build and start the stack

```sh
docker compose -f docker/compose.yml up -d --build
```

The build takes ~3-5 min on first run (the `tac_plus-ng` container is
compiled from upstream source; the SPA is built with Vite). Subsequent
restarts skip rebuilding unless you change source files.

Verify all services are healthy:

```sh
docker compose -f docker/compose.yml ps
```

Expect `db`, `backend`, `tac_plus-ng`, `nginx` all in `running (healthy)`.
The first few seconds the backend's healthcheck may be `starting` while
Alembic applies migrations.

### 3.5 Bootstrap the local admin

```sh
docker compose -f docker/compose.yml exec -it backend tacacs-web bootstrap-admin
```

It prompts for username (default `admin`) and password (twice). The
password is Argon2id-hashed before insert; the audit log records the
bootstrap.

To rotate the password later:

```sh
docker compose -f docker/compose.yml exec -it backend tacacs-web bootstrap-admin --reset-password
```

### 3.6 Accept the self-signed cert and log in

Browse to your `BASE_URL`. The first start generates a self-signed cert
(RSA 2048, 825 days) into the `tls-state` volume; replace it with a
trusted cert by mounting your own files into `/etc/nginx/tls/server.crt`
and `server.key` and restarting `nginx`. (UI-driven cert upload lands in
M7.)

Log in at `/login` with the admin credentials. You should land on the
dashboard and see the Devices / Privilege Profiles / Authorizations / etc.
in the sidebar.

---

## 4. Configure AD live-bind (M3 path)

The MAVIS AUTH handler binds against a configurable LDAP endpoint. Until
the setup wizard lands (M7) you set this directly in `system_setting`:

```sh
docker compose -f docker/compose.yml exec -T db psql -U tacacs tacacs <<'SQL'
INSERT INTO system_setting (key, value, updated_at)
VALUES ('ldap.url', 'ldaps://dc01.corp.example:636', now())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now();
SQL
```

The handler infers TLS from the scheme (`ldaps://` -> TLS on). It does
not currently consume `ldap.bind_dn` / `ldap.bind_password` at AUTH time
— those exist for the AD-sync worker (M3b/c), which is not yet
scheduled (see limitations below).

> **DNS gotcha.** The backend container resolves AD via Docker's embedded
> DNS, which proxies to the host. If `dc01.corp.example` is only
> resolvable on your corporate split-horizon DNS, set
> `dns:` in `docker/compose.yml` on the `backend` service, or use the
> AD's IP literally.

---

## 5. Configure devices through the UI

In the operator UI:

1. **Privilege profiles** — create at least one. The bundled `priv-lvl 15`
   profile with empty permit/deny lists is the equivalent of "full admin
   shell". A scoped read-only profile would be `priv-lvl 1` plus permit
   patterns like `^show ` / `^ping ` and an explicit deny on
   `^configure `.
2. **Device groups** — flat groupings, 1:1 with devices. A typical
   first-cut layout is one group per device role (`core-switches`,
   `firewalls`, `wifi-controllers`).
3. **Devices** — each device's `ip_or_cidr` is matched against the NAS
   source IP at request time via longest-prefix. A device gets exactly
   one `device_group`. The shared-secret slot is encrypted at rest and
   never shown back in the UI (only an "Active / Missing / In window"
   badge).
4. **Authorizations** — bind a principal to `(device_group,
   privilege_profile)`. Until AD sync runs (see limitations), there are
   no synced User / ADGroup rows to pick — for early testing seed one
   manually:

   ```sh
   docker compose -f docker/compose.yml exec -T db psql -U tacacs tacacs <<'SQL'
   INSERT INTO "user" (sam_account_name, distinguished_name, enabled, created_at, updated_at)
   VALUES ('jan', 'CN=jan,OU=Users,DC=corp,DC=example', true, now(), now());
   SQL
   ```

   Reload the Authorizations page — `jan` will appear in the principal
   picker.

---

## 6. Point a NAS at the daemon

On the network device (Cisco-style; adapt for Juniper/Aruba):

```
aaa new-model
aaa authentication login default group tacacs+ local
aaa authorization exec default group tacacs+ if-authenticated
aaa accounting commands 15 default start-stop group tacacs+

tacacs server tacacs-web
 address ipv4 <host running tacacs-web>
 key <TACACS_SHARED_SECRET from docker/.env>
```

> **Important.** The device must use `aaa authorization exec ...
> if-authenticated` rather than the Cisco `enable` re-auth flow. Our
> profile script sets `priv-lvl` directly during the shell-session authz;
> a subsequent `enable` would ask MAVIS again with no clean way to map
> the request. (See ADR-0001 consequences + CONTEXT.md / out-of-scope.)

Verify end-to-end:

```sh
TACACS_HOST=<your host> TACACS_PORT=49 \
TACACS_SECRET="$(grep '^TACACS_SHARED_SECRET=' docker/.env | cut -d= -f2-)" \
TACACS_USER=jan TACACS_PASSWORD='<real AD password>' \
EXPECT=ACCEPT \
python3 scripts/smoke-tacacs.py
```

Then for the authorization step:

```sh
… STEP=AUTHZ EXPECT_PRIV_LVL=15 python3 scripts/smoke-tacacs.py
```

The script lives at [`scripts/smoke-tacacs.py`](../scripts/smoke-tacacs.py)
and is the canonical end-to-end check.

---

## 7. Backup and restore

DB-only dumps via the included helpers:

```sh
./scripts/backup.sh ./backups       # writes ./backups/tacacs-<ts>.dump
./scripts/restore.sh ./backups/tacacs-<ts>.dump
```

The dump is encrypted *at the column level* — ciphertext blobs only. To
restore you also need:

- `secrets/master.key` — the AES-GCM key that was active at backup time.
- `secrets/postgres_password` — for Postgres role auth (not required to
  decrypt the data; required to bring the role up).

Restore is destructive: it drops the running database content before
loading the dump. Keep the daemon and backend stopped while you restore.

---

## 8. Logs and observability

```sh
docker compose -f docker/compose.yml logs -f tac_plus-ng   # daemon + MAVIS child
docker compose -f docker/compose.yml logs -f backend       # FastAPI + auth events
docker compose -f docker/compose.yml logs -f nginx         # access + error
```

Backend and the daemon log structured JSON to stdout. `LOG_LEVEL` from
`docker/.env` is honoured per service.

The append-only audit log lives in the `audit_log` table; it's not yet
exposed in the UI (planned). Query it directly:

```sh
docker compose -f docker/compose.yml exec -T db \
  psql -U tacacs tacacs -c "SELECT ts, actor_username_snapshot, action, summary FROM audit_log ORDER BY id DESC LIMIT 50;"
```

---

## 9. Hardening checklist before exposing operationally

- [ ] Replace the self-signed TLS cert with one your operators' browsers
      trust.
- [ ] Rotate `TACACS_SHARED_SECRET` away from the bootstrap value and
      apply it on every NAS.
- [ ] Set `allowed_source_cidr` on the local admin if the UI is
      reachable from broader than the operator subnet:
      ```sql
      UPDATE local_admin SET allowed_source_cidr = '10.0.0.0/16';
      ```
- [ ] Firewall TCP/49 to only your NAS subnets. The TACACS+ daemon
      currently uses a catch-all NAS block (any source IP, single shared
      secret) — see limitations.
- [ ] Confirm Postgres is not bound to a host port (the compose file
      does not expose it; verify with `docker compose ps`).
- [ ] Confirm `secrets/master.key` and `secrets/postgres_password` are
      mode 0600 on the host and excluded from any host-level backup that
      could leak them.
- [ ] Plan for master-key rotation. v1 has no in-place rotation tool
      yet; the path is: backup, change the key, re-insert the encrypted
      columns from a recompute, restore. Document this for your IR
      runbook before it becomes urgent.

---

## 10. Current limitations

These are real gaps you will hit. Tracking them here so an early
deployer knows what to expect.

- **No AD-sync scheduler.** The sync engine (`app.ldap_sync.run_sync`)
  is present and tested, but nothing triggers it on a cadence yet.
  Until that lands, populate the `user` / `ad_group` tables manually
  for testing, or call `run_sync` from a one-off Python shell inside
  the backend container.
- **No setup wizard.** LDAP URL and sync scope must be inserted into
  `system_setting` via psql (see §4). The wizard that puts this behind
  a UI is M7.
- **No NAS-config regeneration.** Devices created in the UI store
  per-device shared secrets in the DB, but the daemon still consumes a
  single catch-all `host` block with `TACACS_SHARED_SECRET` from the
  env. The regen path (render `host` blocks per Device, SIGHUP the
  daemon) is the last task of M4; the render function + tests are in
  the tree.
- **No SAML SP.** The break-glass admin is the only login path today.
  ADR-0003's day-job SAML half is M5b.
- **No accounting persistence or forwarding.** `aaa accounting` rows
  from the daemon are not yet ingested into the DB or forwarded to
  external syslog. That's M6.
- **No UI-driven cert upload.** Replace the self-signed cert by
  mounting your own files into the `tls-state` volume. M7 adds the
  upload + reload flow.

---

## 11. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Backend healthcheck stays `unhealthy` after `compose up`. | Master key missing or wrong size. Check `secrets/master.key` is exactly 32 raw bytes or base64 of 32 bytes. The backend refuses to start otherwise (ADR-0004). |
| `/login/local` always returns 401 with `invalid_credentials` even with the right password. | `local_admin` row missing — run `tacacs-web bootstrap-admin`. Or `allowed_source_cidr` is set and you are outside the CIDR. |
| TACACS auth from a NAS fails with `tac_plus-ng` logging `bad secret`. | The shared secret on the NAS does not match `TACACS_SHARED_SECRET` in `docker/.env`. Rotate both sides in lock-step. |
| TACACS auth fails with the daemon logging `MAVIS ERR`. | Backend unreachable from the `tac_plus-ng` container, or LDAP unreachable from the backend. Check `docker compose logs backend` for the `/internal/mavis/auth` traffic. ADR-0002's fail-closed semantics make AD-down look like an error rather than a deny. |
| Operator gets `ACCEPT` on authn but `REJECT` on the next shell-session authz. | No matching Authorization for the resolved `(user, device_group)`. Inspect the Effective Permissions view (route lives at `/api/v1/users/{id}/effective-permissions`; UI page pending). |
| `npm run build` of the frontend silently times out behind a proxy. | The `node:22-alpine` build stage cannot reach the npm registry. Add `npm_config_registry` or set `http_proxy` / `https_proxy` on the build args. |
| Cookie not sent on a fresh login — `/me` immediately returns 401. | You are talking HTTP to a backend that emits `Secure` cookies. Always reach the UI via HTTPS through nginx; the bootstrap self-signed cert is enough. |

When in doubt, both the integration smoke (`scripts/smoke-tacacs.py`)
and the audit log (`audit_log` table) tell you whether a request made
it past authn vs. failed at authz.

---

## 12. Where to look next

- Architecture and design rationale: [`docs/adr/`](./adr/).
- Domain glossary + key flows: [`CONTEXT.md`](../CONTEXT.md).
- Reproducible integration test:
  [`.github/workflows/integration.yml`](../.github/workflows/integration.yml)
  spins the same compose stack with an `openldap` sidecar so you can
  watch the full flow on a clean machine.
