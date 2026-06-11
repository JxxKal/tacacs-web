# tacacs-web — Deployment Guide

End-to-end setup for a single-host production install. Audience: network /
platform admin comfortable with Docker Compose, AD/LDAPS, and PKI basics.
Cross-references to the relevant ADRs are included where a decision has
operational consequences.

> **Status note.** v1 is still in development. The current build covers the
> TACACS+ daemon, MAVIS authn + authz (with live LDAPS bind), the four CRUD
> resources (DeviceGroups, PrivilegeProfiles, Devices, Authorizations), the
> local break-glass admin login, an append-only audit log, the accounting
> ingestor + RFC5424 syslog forwarder (M6) and the in-UI first-boot Setup
> Wizard (M7). Remaining gaps are listed under
> [Current limitations](#current-limitations).

---

## 1. Host requirements

| Item | Minimum | Notes |
|---|---|---|
| OS | Linux with cgroups v2 | Tested on Debian 13 |
| Docker Engine | 24+ | Compose v2 plugin must be installed |
| RAM | 2 GB | Postgres, backend, daemon, nginx, build cache |
| Disk | 10 GB | Postgres data + image layers grow with accounting (M6) |
| Open ports outbound | 636/tcp to AD | LDAPS bind, both sync and live-bind |
| Outbound HTTP(S) during install | reach to `ghcr.io` / `docker.io` / `pypi.org` / `npmjs.com` / GitHub releases / upstream `tac_plus-ng` repo | Only required during `docker compose build`. If you're behind a corporate proxy, see [3.0 Behind a corporate proxy](#30-behind-a-corporate-proxy-skip-if-you-have-direct-internet). |
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

### 3.0 Behind a corporate proxy (skip if you have direct internet)

OT hosts usually only reach the public internet through an HTTP/HTTPS
proxy. Three separate clients need to know about it during the install:
`git` (for the clone), the Docker **daemon** (for pulling base images),
and the Docker **build** stages (so `apt-get`, `npm`, `uv` and the
upstream `tac_plus-ng` checkout can reach their package repos). Wiring
each one independently is what trips most first-time installs.

**Shell variables.** Set both lower- and upper-case forms — some tools
read one, some the other:

```sh
export http_proxy=http://proxy.corp.example:3128
export https_proxy=http://proxy.corp.example:3128
export HTTP_PROXY=$http_proxy
export HTTPS_PROXY=$https_proxy
# Anything that must stay direct. Docker's embedded DNS routes container
# names like `backend` / `db` through here; without it Postgres calls
# would try to traverse the proxy and fail.
export no_proxy=localhost,127.0.0.1,::1,backend,db,tac_plus-ng,nginx,.corp.example
export NO_PROXY=$no_proxy
```

Drop these into `/etc/profile.d/proxy.sh` or `~/.bashrc` so reconnects
don't lose them.

**Git.** With the env vars above, `git clone` over HTTPS works
directly. If git ignores them (older versions, restricted shells):

```sh
git config --global http.proxy  $http_proxy
git config --global https.proxy $https_proxy
```

**Docker daemon (image pulls).** The daemon does NOT inherit the user
shell. Either configure systemd:

```sh
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/proxy.conf >/dev/null <<EOF
[Service]
Environment="HTTP_PROXY=$http_proxy"
Environment="HTTPS_PROXY=$https_proxy"
Environment="NO_PROXY=$no_proxy"
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
```

…or per-user via `~/.docker/config.json` (newer Docker CLIs auto-pass
this to the daemon for pulls and propagate to builds):

```json
{
  "proxies": {
    "default": {
      "httpProxy":  "http://proxy.corp.example:3128",
      "httpsProxy": "http://proxy.corp.example:3128",
      "noProxy":    "localhost,127.0.0.1,backend,db,tac_plus-ng,nginx,.corp.example"
    }
  }
}
```

**Docker build (apt / npm / uv inside `Dockerfile`s).** BuildKit
propagates `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` from the build
environment automatically. If your shell exports them, `docker compose
build` picks them up. To be explicit (and to survive a fresh CI runner
or a `sudo` that drops env):

```sh
docker compose -f docker/compose.yml build \
  --build-arg HTTP_PROXY=$http_proxy \
  --build-arg HTTPS_PROXY=$https_proxy \
  --build-arg NO_PROXY=$no_proxy
```

**Proxy with TLS interception (Zscaler, Forcepoint, …).** If your
proxy MITMs HTTPS with its own root CA, the `apt-get` / `npm` / `uv`
calls inside the build stages will fail with `certificate verify
failed`. Drop the corporate CA bundle into `secrets/corp-ca.pem` and
mount it during the build — see the troubleshooting table at the
bottom of this document for the exact recipe; the dependency-fetch
stages are the only ones that need it.

**Runtime traffic.** Once the stack is up the containers only talk to
each other (over Docker's internal bridge), to AD on 636/tcp, and
optionally to your SIEM for the syslog forwarder (M6c). None of that
goes through the HTTP proxy, so once the build is done you can stop
worrying about it.

### 3.1 Clone

```sh
git clone https://github.com/JxxKal/tacacs-web.git
cd tacacs-web
```

### 3.2 Generate secrets

Both secrets are supplied as **environment variables** (`MASTER_KEY`,
`POSTGRES_PASSWORD`) so they can be managed in Portainer's stack editor
without a Swarm secret store. Generate two values and keep them for the
next step:

```sh
# AES-GCM master key — base64 of 32 bytes, single line.
openssl rand -base64 32

# Postgres password — single line, no trailing newline.
openssl rand -base64 24 | tr -d '\n'; echo
```

Back both up immediately. Without the `MASTER_KEY` value a DB dump is
unreadable (ADR-0004) — treat it like a root credential.

> **Security note.** As an env var the master key is visible via
> `docker inspect` / the Portainer stack config to anyone with host or
> Portainer-admin access. On a single-operator OT host that is the normal
> tradeoff for UI manageability. If you need it off the process
> environment, mount it as a file instead — see [§3.8](#38-optional-mount-the-master-key-as-a-file-instead-of-env).

### 3.3 Copy the env template

```sh
cp docker/.env.example docker/.env
```

Edit `docker/.env`:

| Key | Notes |
|---|---|
| `POSTGRES_PASSWORD` | **Required.** The value generated in [§3.2](#32-generate-secrets). Used by both the `db` container (DB init) and the `backend` (connection). No default — the stack refuses to start if unset. |
| `MASTER_KEY` | **Required.** The base64 master key from [§3.2](#32-generate-secrets). No default — the stack refuses to start if unset. |
| `BASE_URL` | The HTTPS URL operators will reach. Used for SAML callbacks in M5b and absolute URLs. Example: `https://tacacs.internal.example.com:8443`. Must include the same port as `HTTPS_HOST_PORT` (see below) — otherwise the SAML ACS redirect breaks. |
| `TACACS_SHARED_SECRET` | Generated value, **at least 32 chars**. Every NAS that talks to us uses this one secret until the per-device-secret regen flow lands (see [Current limitations](#current-limitations)). |
| `TZ` | Affects log timestamps. Use `Europe/Berlin` or your host TZ. |
| `HTTPS_HOST_PORT` | Host-side port the UI listens on. Default `8443`. Override when another service (UniFi controller, Cockpit, …) already binds `8443`. **Important:** the nginx container always listens on `8443` *inside* — only the host-side mapping changes. Pair the new port with `BASE_URL` so the SP-Metadata + cookie domain stay consistent. Example: `HTTPS_HOST_PORT=8444` plus `BASE_URL=https://tacacs.internal.example.com:8444`. |
| `TACACS_BIND_ADDR` | Default `0.0.0.0`. Set to a specific host IP if the host has multiple NICs and TACACS should only listen on the OT-facing one. The TACACS+ TCP port itself is the hard-coded `49` — every NAS expects it there, so it is **not** configurable. |
| `HTTPS_BIND_ADDR` | Default `0.0.0.0`. Same idea for the operator UI: pin to one host IP if you want the UI reachable only on the management interface. |

### 3.4 Build and start the stack (plain `docker compose`)

Prefer a UI? Skip to [§3.4a](#34a-deploy-as-a-portainer-stack).

```sh
docker compose -f docker/compose.yml up -d --build
```

The build takes ~3-5 min on first run (the `tac_plus-ng` container is
compiled from upstream source; the SPA is built with Vite). Subsequent
restarts skip rebuilding unless you change source files.

> Behind a corporate proxy? Make sure the steps in
> [3.0](#30-behind-a-corporate-proxy-skip-if-you-have-direct-internet)
> are done first — without them the build either fails at the base-image
> pull (daemon proxy missing) or inside one of the dependency-install
> stages (build-arg proxy missing).

Verify all services are healthy:

```sh
docker compose -f docker/compose.yml ps
```

Expect `db`, `backend`, `tac_plus-ng`, `nginx` all in `running (healthy)`.
The first few seconds the backend's healthcheck may be `starting` while
Alembic applies migrations.

### 3.4a Deploy as a Portainer stack

The same `docker/compose.yml` runs as a Portainer **stack**. Because the
images are built from source (the `tac_plus-ng` daemon is compiled, the
SPA is built with Vite) and there is no image registry, use the
**Repository** method so Portainer has the build context — the Web-editor
and Upload methods cannot build images.

> This is a build-on-the-host deployment. On an isolated / OT host the
> Docker **daemon proxy** and **build-arg proxy** from
> [§3.0](#30-behind-a-corporate-proxy-skip-if-you-have-direct-internet)
> must be in place first, or the build fails at the base-image pull or a
> dependency-install stage. Portainer surfaces the build log under the
> stack on failure.

1. **Portainer → Stacks → Add stack → Repository.**
2. **Repository URL:** `https://github.com/JxxKal/tacacs-web.git`
   **Reference:** the branch or tag you deploy (e.g. `refs/heads/main`).
   **Compose path:** `docker/compose.yml`
   (`build.context: ..` resolves to the repo root inside Portainer's clone.)
3. **Environment variables** — add each key from `docker/.env.example`.
   The required ones (no default; the stack refuses to start without them):

   | Key | Value |
   |---|---|
   | `POSTGRES_PASSWORD` | DB password from [§3.2](#32-generate-secrets) |
   | `MASTER_KEY` | base64 master key from [§3.2](#32-generate-secrets) |
   | `TACACS_SHARED_SECRET` | catch-all NAS secret (≥32 chars) |
   | `BASE_URL` | external HTTPS URL incl. port |

   The rest (`POSTGRES_DB`, `POSTGRES_USER`, `LOG_LEVEL`, `TZ`,
   `HTTPS_HOST_PORT`, `TACACS_BIND_ADDR`, `HTTPS_BIND_ADDR`) have sane
   defaults — override only when needed.
4. **Deploy the stack.** First build takes ~3–5 min. The `backend`
   container runs `alembic upgrade head` on startup, so migrations apply
   automatically — no host-side `alembic` needed.

**Updating later:** push/merge the change, then in Portainer open the
stack and use **Pull and redeploy** (enable *Re-pull image / rebuild* so
the backend image is rebuilt — the Alembic migrations are baked into the
image at build time, so a plain restart would not pick up a new
migration). On redeploy the backend re-runs `alembic upgrade head`.

> The catch-all `openldap` service is gated behind the `integration`
> Compose profile and never starts in a normal deploy — leave it alone.

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
(RSA 2048, 825 days) into the `tls-state` volume. From M7 onwards a real
certificate can be uploaded straight through the UI:
**Settings → TLS certificate** accepts a PEM cert + key pair or a
Windows AD-CS PFX (with password). The change is hot — nginx picks the
new file up on its next request without a container restart.

Log in at `/login` with the admin credentials. You should land on the
dashboard and see the Devices / Privilege Profiles / Authorizations / etc.
in the sidebar.

### 3.7 Walk the Setup Wizard (M7)

Until the wizard is marked complete, every page in the UI shows a yellow
banner pointing at `/setup`. The wizard is a checklist — each row deep-
links to the relevant Settings card or CRUD page. Required rows must be
green before the "Mark wizard as complete" button enables; optional rows
(AD-sync, SAML, first device, syslog forwarder, …) can be skipped and
filled in later.

| Step | Where it lives |
|---|---|
| Local break-glass admin | host CLI (`tacacs-web bootstrap-admin`) |
| Web base URL | Settings → Web base URL |
| TLS certificate | Settings → TLS certificate |
| Active Directory endpoint | Settings → Active Directory / LDAPS |
| AD sync (optional) | Settings → Active Directory Sync |
| SAML login (optional) | Settings → SAML 2.0 admin login |
| First device group | Device groups page |
| First privilege profile | Privilege profiles page |
| First device (optional) | Devices page |
| First authorization (optional) | Authorizations page |
| Syslog forwarder (optional) | Settings → Syslog forwarder |

The wizard can be re-opened from `/setup` at any time. Both the
completion and the re-open events land in the audit log under
`setup.wizard_completed` / `setup.wizard_reopened`.

### 3.8 (optional) Mount the master key as a file instead of env

The env-var path ([§3.2](#32-generate-secrets)) is the comfortable default
for Portainer. If your threat model says the AES-GCM master key must not
appear in `docker inspect` / the stack config, mount it as a file — the
backend reads `master_key_file` first and only falls back to `MASTER_KEY`
when no file is set (`app/core/config.py`). The same applies to
`database_password_file` vs `DATABASE_PASSWORD`.

1. Place the key on the host, readable only by the Docker user:

   ```sh
   install -m 0600 /dev/stdin /opt/tacacs-web/master.key <<<"$(openssl rand -base64 32)"
   ```

2. In the stack, drop `MASTER_KEY`, bind-mount the file read-only, and
   point the backend at it:

   ```yaml
   services:
     backend:
       environment:
         MASTER_KEY_FILE: /run/secrets/master_key
       volumes:
         - /opt/tacacs-web/master.key:/run/secrets/master_key:ro
   ```

   (In Portainer, add the bind mount under the stack's `backend` service
   in the Web editor, or keep it in the repo's compose on a private fork.)

The file must contain either 32 raw bytes or a base64 line that decodes to
32 bytes; otherwise the backend's readiness check reports
`master_key: error` and stays `503`.

---

## 4. Configure AD live-bind (M3 path)

The MAVIS AUTH handler binds against a configurable LDAP endpoint. Set
this in the UI under **Settings → Active Directory / LDAPS** (URL
field). The Setup Wizard (`/setup`) lists it as a required step.

The handler infers TLS from the scheme (`ldaps://` -> TLS on). It does
not currently consume `ldap.bind_dn` / `ldap.bind_password` at AUTH time
— those exist for the AD-sync worker (M3b/c), configured under
**Settings → Active Directory Sync** (bind DN, password, base DNs,
cadence). The worker is opt-in: leave "Run periodically" off if you
only want manual one-shot syncs.

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

- The `MASTER_KEY` value that was active at backup time — the AES-GCM key
  that decrypts the column ciphertext. Back up the stack's env (the
  `docker/.env` file, or your Portainer stack's env vars) somewhere safe;
  without this exact key a dump is unreadable (ADR-0004).
- The `POSTGRES_PASSWORD` value — for Postgres role auth (not required to
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
- [ ] Firewall TCP/49 to only your NAS subnets. The daemon accepts any
      Device row from the UI; until the first Device is provisioned, a
      `bootstrap` block still accepts any source IP with the env-supplied
      `TACACS_SHARED_SECRET`.
- [ ] Confirm Postgres is not bound to a host port (the compose file
      does not expose it; verify with `docker compose ps`).
- [ ] Restrict who can read `MASTER_KEY` / `POSTGRES_PASSWORD`: the
      `docker/.env` file mode 0600, Portainer access limited to trusted
      admins, and the values excluded from any host-level backup that
      could leak them. For a stricter posture, mount the master key as a
      file ([§3.8](#38-optional-mount-the-master-key-as-a-file-instead-of-env))
      so it stays out of `docker inspect`.
- [ ] Plan for master-key rotation. v1 has no in-place rotation tool
      yet; the path is: backup, change the key, re-insert the encrypted
      columns from a recompute, restore. Document this for your IR
      runbook before it becomes urgent.

---

## 10. Current limitations

These are real gaps you will hit. Tracking them here so an early
deployer knows what to expect.

- **No HA / clustering.** Single-node Compose. Explicit non-goal for v1
  (ADR-0001 / ADR-0010). A v2 cluster story is plausible but blocked on
  a state-replication design for the encrypted `system_secret` table.
- **No SAML SLO.** Logging out of the IdP does not invalidate the local
  session cookie. Use the local "Log out" link and the 8h sliding cap.
  ADR-0003 documents the rationale.
- **Time-bound authorizations are out of scope** for v1 — every
  authorization is permanent until deleted. The audit log records the
  delete so you can reconstruct the timeline.

---

## 11. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Backend healthcheck stays `unhealthy` after `compose up`. | Master key missing or wrong size. `MASTER_KEY` must be base64 that decodes to exactly 32 bytes (a file mount must be 32 raw bytes or base64 of 32). The readiness check reports `master_key: not_configured` / `error` and stays `503` otherwise (ADR-0004). |
| `/login/local` always returns 401 with `invalid_credentials` even with the right password. | `local_admin` row missing — run `tacacs-web bootstrap-admin`. Or `allowed_source_cidr` is set and you are outside the CIDR. |
| TACACS auth from a NAS fails with `tac_plus-ng` logging `bad secret`. | The shared secret on the NAS does not match `TACACS_SHARED_SECRET` in `docker/.env`. Rotate both sides in lock-step. |
| TACACS auth fails with the daemon logging `MAVIS ERR`. | Backend unreachable from the `tac_plus-ng` container, or LDAP unreachable from the backend. Check `docker compose logs backend` for the `/internal/mavis/auth` traffic. ADR-0002's fail-closed semantics make AD-down look like an error rather than a deny. |
| Operator gets `ACCEPT` on authn but `REJECT` on the next shell-session authz. | No matching Authorization for the resolved `(user, device_group)`. Inspect the Effective Permissions view (route lives at `/api/v1/users/{id}/effective-permissions`; UI page pending). |
| `npm run build` of the frontend silently times out behind a proxy. | The `node:22-alpine` build stage cannot reach the npm registry. Set `http_proxy` / `https_proxy` in the shell **and** pass them via `--build-arg` (see [3.0](#30-behind-a-corporate-proxy-skip-if-you-have-direct-internet)). |
| `docker compose pull` / build dies with `failed to resolve reference ...: dial tcp: lookup ghcr.io: i/o timeout`. | The Docker **daemon** isn't using the proxy. Shell env doesn't propagate to it — apply the systemd override or `~/.docker/config.json` recipe in [3.0](#30-behind-a-corporate-proxy-skip-if-you-have-direct-internet). |
| Build inside a stage fails with `certificate verify failed` against pypi / npm / apt mirrors. | Proxy is doing TLS interception. Bake the corporate CA into the build: `cp /etc/ssl/certs/corp-root.pem secrets/corp-ca.pem` and add `COPY secrets/corp-ca.pem /usr/local/share/ca-certificates/corp.crt && update-ca-certificates` near the top of the affected `Dockerfile` (backend / nginx / tac_plus-ng each have their own; the npm one also needs `npm config set cafile /usr/local/share/ca-certificates/corp.crt`). |
| Cookie not sent on a fresh login — `/me` immediately returns 401. | You are talking HTTP to a backend that emits `Secure` cookies. Always reach the UI via HTTPS through nginx; the bootstrap self-signed cert is enough. |
| `docker compose up` fails with `Bind for 0.0.0.0:8443 failed: port is already allocated`. | Another service already listens on 8443. Set `HTTPS_HOST_PORT=8444` (or any free port) in `docker/.env` **and** update `BASE_URL` to the same port (`https://…:8444`). Restart with `docker compose -f docker/compose.yml up -d`. The container's internal port stays 8443 either way; only the host-side mapping moves. |
| SAML login redirects to `https://…:8443/saml/acs` even though you changed the port. | `BASE_URL` still points at 8443. After updating `HTTPS_HOST_PORT`, `BASE_URL` must match (it drives the SP-Metadata + the ACS URL the IdP redirects to). Re-export the SP-Metadata from Settings → SAML and re-import it on the IdP. |

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
