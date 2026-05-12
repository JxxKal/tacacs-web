# 0007. Soft shared-secret rotation with dual-key window

- Date: 2026-05-12
- Status: Accepted

## Context

Every Device has a TACACS+ shared secret. Rotating that secret without an outage is non-trivial: the moment our app changes the secret in its config, every TACACS packet from that Device authenticates with the wrong key until the operator updates the secret on the Device side.

Possible flows:

- **Hard replace** — UI changes the secret atomically. Operator must change the Device side simultaneously. Race condition window = TACACS retries.
- **Soft / dual-key rotation** — the daemon accepts the old *and* new secret for a configurable transition window. Operator changes the Device side at leisure, then retires the old secret.
- **Push-to-Device automation** — the app pushes the new secret to the Device via SSH/NETCONF. Vendor-specific, out of scope.

## Decision

Model **dual-key rotation** in the schema and the daemon flow:

- The `device` table carries `current_secret_enc`, `previous_secret_enc`, and `previous_retired_at`. Both encrypted columns are nullable; only `current_secret_enc` is mandatory after the first set.
- The `tac_plus-ng` NAS client block for each Device lists `current` and (if present) `previous` as accepted keys. `tac_plus-ng`'s shared-secret matching tries each in order.
- UI rotation flow:
  1. Operator clicks **Rotate**. The app generates (or accepts a pasted) new secret.
  2. The new value becomes `current`; the old `current` moves to `previous`.
  3. The plaintext new secret is shown **once** in the UI, with a clear "copy and apply on the device side" prompt.
  4. Operator clicks **Retire previous** when the Device side is updated. `previous_secret_enc` is cleared.
  5. The NAS-client config block in `tac_plus-ng` is re-rendered and reloaded on every state change.

The TTL of the `previous` window is operator-controlled (manual retire); there is no auto-retire timer in v1. An optional reminder mail / banner after N days lives in v2.

## Consequences

- Operators get a no-outage rotation path with a clear, two-step UI flow.
- The schema and the `tac_plus-ng` config block remain straightforward: two slots, not an unbounded list.
- Rotation requires a daemon config reload on every transition (set new + retire old = two reloads). Reload is non-disruptive for `tac_plus-ng`.
- An operator who never clicks "Retire previous" leaves the old secret valid indefinitely. The UI surfaces stale `previous` slots in a Devices-overview warning column.
- Building this in M2 requires deciding how the NAS-client block is generated. We render that block from the DB on every Device-state change (this is the one piece of state that does *not* go through MAVIS-live — see ADR-0001 consequences).

## Alternatives considered

- **Hard replace** — simplest implementation, but moves all the race-condition risk onto the operator's keyboard speed. Unacceptable for an operational tool.
- **Push aufs Device** — beyond scope (vendor matrix, network credentials, error handling). v2 candidate at best.
- **N-slot rolling history (current + N previous)** — over-engineering. A single dual-key window covers the operational need.
