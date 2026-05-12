# 0004. AES-GCM column encryption with operator-supplied master key

- Date: 2026-05-12
- Status: Accepted

## Context

The app must hold several long-lived secrets at rest:

- AD service-account bind password (needed for periodic sync).
- TACACS+ shared secrets (one or two per Device, including the previous secret during rotation windows).
- SAML SP signing key.
- TLS private key (uploaded via the UI).

These secrets must survive container restarts, be backupable, be rotatable, and not leak via a DB-only compromise. They must also be modifiable from the running UI so the operator does not have to redeploy the stack to change them.

## Decision

- Every sensitive column is **AES-256-GCM encrypted** in the DB. Plaintext never touches disk.
- The **master key** is a 32-byte random value supplied by the operator as a **Docker secret** (mounted as a file). The backend reads it at startup; if the file is missing or unreadable, the backend refuses to start with a clear error pointing at the bootstrap procedure.
- All encrypted columns share a single master key. Per-row keys / envelope encryption is not introduced — the added blast-radius reduction is not worth the operational complexity for a single-tenant tool.
- Key rotation is a CLI subcommand: `tacacs-web rotate-master-key --old-key-file ... --new-key-file ...` runs a transactional re-encryption of all encrypted columns and writes the new key to the configured secret path.
- We use the [`cryptography`](https://cryptography.io/) library's `AESGCM` API with a fresh 12-byte nonce per record, prepended to the ciphertext (`nonce || ciphertext`).
- DEPLOYMENT documentation makes the dependency between DB backup and master-key backup explicit: a DB dump without the master key is unrecoverable.
- Argon2id (local-admin password) and bcrypt (TACACS break-glass) hashes are **not** encrypted — they are hashes, not secrets we need to recover.

## Consequences

- A leaked DB dump alone does not expose any secrets — the attacker also needs the master key.
- Operator workflow is constrained: do not lose the master key, period. The CLI rotation path makes "I rotated, kept old key briefly, all good" the canonical update story.
- The bootstrap experience requires one extra Docker-secret setup step before first `docker compose up`. We document this in DEPLOYMENT and the setup-wizard preflight.
- We accept a single-master-key blast radius. A v2 path to envelope encryption with per-row DEKs is plausible but not justified by current threat model.
- Database migrations that touch encrypted columns must be tested with a known master key fixture; CI runs them so we catch breakage early.

## Alternatives considered

- **Env-var-only secrets** — every secret lives in the Compose file or a `.env`. Cannot be changed without a redeploy, and the UI cannot manage them. Bad UX for operators who want to rotate the AD bind password without touching infrastructure.
- **External vault (HashiCorp Vault, Bitwarden Secrets Manager)** — clean separation, but adds a mandatory external dependency for a single-node Compose stack. Out of scope for v1; pluggable in v2 if needed.
- **Auto-generated master key persisted in a Docker volume** — convenient first boot, but invites the disaster scenario "operator wiped the volume, all secrets gone". Forcing operator-supply is a deliberate trade of convenience for explicit ownership.
- **Passphrase-derived key (Argon2 → AES-GCM)** — human-memorable, but rotation requires the human to remember two passphrases simultaneously. Not better for a one-off ops tool.
