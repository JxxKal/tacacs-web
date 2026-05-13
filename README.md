# tacacs-web

Web-managed TACACS+ stack with Active Directory authentication. Built on `tac_plus-ng` (Marc Huber) with a FastAPI backend and React/Mantine frontend, all wrapped as a Docker Compose stack.

## Status

Early development. Architecture decisions captured in [`docs/adr/`](docs/adr/); domain glossary and component overview in [`CONTEXT.md`](CONTEXT.md). End-to-end install walkthrough: [`docs/DEPLOY.md`](docs/DEPLOY.md).

## What this does

- Runs a TACACS+ server (`tac_plus-ng`) for network device authentication.
- Authenticates network operators live against Active Directory via LDAPS (hybrid model: AD users are synced into the app DB for selection in the UI, passwords are verified at login time against AD).
- Authorizes those users for specific device groups with configurable privilege profiles (priv-lvl + permit/deny regex command lists + extra AV-pairs).
- All configuration via a web UI — devices, device groups, privilege profiles, authorizations. Admin login via SAML SP (designed against FortiAuthenticator).
- Records every TACACS+ command in the local DB and forwards to external syslog (RFC5424 over TCP or TLS).

## High-level architecture

```
Network devices --TACACS+:49--> tac_plus-ng <--pipe--> mavis (Python)
                                                          |
                                                          v
Browser --HTTPS--> nginx --> backend (FastAPI) <--> Postgres
                              |                       ^
                              |-> SAML SP             |
                              |-> AD-Sync ------------|
                              `-> Accounting-Ingestor-`
```

See [`CONTEXT.md`](CONTEXT.md) for components, glossary, and key flows.

## Roadmap (v1)

| Milestone | Goal |
|---|---|
| M1 | Repo bootstrap, CI, empty Compose, Alembic init |
| M2 | `tac_plus-ng` container + stub MAVIS handler, end-to-end smoke test |
| M3 | AD sync (OU-based, transitive groups) + live LDAPS bind in MAVIS |
| M4 | Domain CRUD (Devices, DeviceGroups, PrivilegeProfiles, Authorizations) + real MAVIS authz |
| M5 | SAML admin auth via FortiAuthenticator + local break-glass admin |
| M6 | Accounting: DB persistence + RFC5424/TCP/TLS forwarding |
| M7 | Hardening, TLS upload, setup wizard, deployment docs |

## Requirements

- Docker Engine 24+ with Compose v2
- TACACS+-capable network devices
- Active Directory reachable via LDAPS (port 636)
- SAML 2.0 IdP for admin login (designed against FortiAuthenticator)
- 32-byte AES-GCM master key, generated and supplied as a Docker secret before first start (`openssl rand -base64 32`)

## Out of scope for v1

Multi-domain/forest AD, time-bound authorizations, bulk CSV import, TACACS+-over-TLS, TACACS services other than `shell`, Cisco `enable` re-auth (devices must use `aaa authorization` so the priv-lvl flows directly from authz), HA/clustering, SAML SLO.

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
