# 0001. tac_plus-ng as TACACS engine, MAVIS-external for live lookups

- Date: 2026-05-12
- Status: Accepted

## Context

We need a TACACS+ daemon at the core of the stack, plus a mechanism to feed it dynamic authentication and authorization decisions sourced from our web-managed DB and from Active Directory. Two daemon families dominate the open-source landscape:

- **Shrubbery tac_plus** — the classic, widely deployed implementation. Static config file, no native LDAP support (would require PAM or wrapper scripts), no first-class hook for live lookups.
- **tac_plus-ng** (Marc Huber, Pro-Bono Publico) — actively maintained, ships the MAVIS module system, can talk to LDAP natively or via external lookup processes, supports config reloads.

Beyond the daemon choice, there are two ways to inject our dynamic state:

- **File regeneration + reload** — render `tac_plus-ng.conf` from DB state on every change, SIGHUP the daemon. Atomic per change, easy to debug, but introduces a render-and-reload latency on every UI write.
- **MAVIS external lookup live** — daemon pipes each authn/authz request to a long-lived child process that resolves it against DB + AD on demand. Maximum reactivity to UI changes, but every request pays a Python/DB/LDAP roundtrip.

## Decision

Use **`tac_plus-ng`** as the daemon, and wire all authentication and authorization decisions through a **MAVIS-external Python process** (called `mavis` in the stack). The daemon's static config carries only the daemon-level settings, the syslog/log file paths, the MAVIS module declaration, and the list of NAS clients with their shared secrets. Everything user-, group-, device-group-, and profile-related lives in the DB and is resolved by `mavis` per request.

## Consequences

- One single source of truth for state: the Postgres DB. No "is the rendered config in sync with the DB" failure mode.
- Permission changes in the UI are visible to the next TACACS+ request immediately, modulo the MAVIS authz cache (60s TTL, flushable).
- We pay a per-request cost: a Python function call, a DB round-trip (cached), and for authn an LDAPS bind. Authz cache amortizes this for command-heavy sessions.
- We are tied to `tac_plus-ng`'s MAVIS protocol and conventions. Migrating to a different daemon later means re-writing the lookup glue.
- Building `tac_plus-ng` from source is part of our Dockerfile, with the upstream license tracked in NOTICE.
- The NAS client list (with shared secrets) is the one piece of state that does *not* live behind MAVIS — `tac_plus-ng` needs to know it at TCP-accept time to validate the encrypted TACACS packet. We re-render that block from the DB on device CRUD operations and reload the daemon (see ADR-0007 for the implications on shared-secret rotation).

## Alternatives considered

- **Shrubbery tac_plus + PAM/script wrapper** — possible, but every dynamic lookup would be a one-off shell-out; no clean way to do AV-pair-driven authz from a DB. Ages of pain.
- **File regeneration + reload with tac_plus-ng** — clean and debuggable, but every UI write triggers a reload window in which the daemon briefly accepts no new connections. Permission changes only apply after a render cycle, and the render becomes a serialized point of contention. Wins on simplicity but loses on UX.
- **Custom TACACS+ implementation** — full control, no third-party daemon dependency. Out of scope; the protocol is non-trivial and we'd be re-implementing 15+ years of `tac_plus-ng`-shaped corners.
