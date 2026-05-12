# 0002. Hybrid AD model: sync users for selection, live LDAPS bind for password

- Date: 2026-05-12
- Status: Accepted

## Context

Authentication against Active Directory could happen at three different points:

1. **Inside the daemon** — `tac_plus-ng` supports an LDAP MAVIS module that binds directly to AD. The web UI would only manage authorization metadata.
2. **Synced into our DB** — periodic LDAPS pull replicates user records (and password hashes? AD usually does not expose them) into our DB; the daemon authenticates against the local copy.
3. **Hybrid** — periodic sync brings users and their group memberships into our DB so the UI can offer them for selection in authorization rules. Password verification still happens live against AD at every TACACS login.

The UI requirement to "select users from the AD" rules out a pure live-only model (we cannot enumerate AD at every UI keystroke). The compliance requirement that "password validation is the source of truth" rules out copying a hashed password into our DB.

## Decision

Implement the **hybrid model**:

- A periodic LDAPS sync (default 1h, plus a "Sync now" button) pulls users and groups from configured AD OUs into the `user`, `ad_group`, and `user_ad_group` tables. The single AD login key is `sAMAccountName`. Nested AD-group memberships are flattened at sync time using `LDAP_MATCHING_RULE_IN_CHAIN` (OID `1.2.840.113556.1.4.1941`).
- The `mavis` process performs a **live LDAPS bind** for every TACACS authentication request, using the password sent by the device. No password material is ever stored in our DB.
- AD-Sync scope is OU-based: a configurable list of Base-DNs + an optional LDAP filter, subtree search.
- Users that fall out of scope between syncs are soft-disabled (`enabled=false`, `last_seen_in_sync_at` retained). Their authorization rows are not auto-deleted; MAVIS rejects their login by the `enabled=false` check.

## Consequences

- Two roundtrips for every TACACS login: one DB lookup, one LDAPS bind. The bind dominates the latency; pooling a TLS handshake across connections is non-trivial because the bind itself is the auth, so we accept the per-request cost.
- A user disabled or password-rotated in AD is rejected at the next TACACS login attempt without any sync delay.
- A user newly granted in AD must wait for the next sync (or operator clicks "Sync now") before they appear in the UI for authorization — but once authorized, they can log in immediately.
- Sync is single-domain only in v1. Multi-domain/forest is deferred (ADR omitted; see CONTEXT.md "Out of scope").
- When AD is unreachable, all live binds fail. We fail closed at the TACACS layer; see the local TACACS break-glass mechanism for the safety net.
- A separate concern from this ADR but worth noting here: AD-Sync scope filters are operator-controlled. Setting them too broadly leaks unrelated user records into our DB; documented in DEPLOYMENT guidance.

## Alternatives considered

- **Daemon-internal LDAP module** — works for authentication but leaves us without a UI-side user list for granting authorizations. We could combine this with our own authz module, but it doubles the moving parts.
- **Full local sync including a re-hashed password** — AD does not expose hashes; we would need to capture the password at login time and store our own hash. That breaks "AD is the source of truth for credentials" and creates an additional compliance burden.
- **No sync at all, live `subtree-search` to populate UI** — requires LDAP search latency on every UI page that lists users. Doesn't scale and breaks completely when AD is unreachable.
