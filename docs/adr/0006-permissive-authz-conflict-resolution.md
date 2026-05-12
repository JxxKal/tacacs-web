# 0006. Permissive authorization conflict resolution; direct user overrides AD group

- Date: 2026-05-12
- Status: Accepted

## Context

A user can be granted access to a DeviceGroup through multiple paths:

- Membership in AD group `G1` that is granted profile `admin` (priv-lvl 15).
- Membership in AD group `G2` that is granted profile `operator` (priv-lvl 7).
- Direct user-level Authorization with profile `read-only` (priv-lvl 1).

When two or more of these match, which wins? Four candidate policies:

- **Permissive (union, highest privilege wins)** — RBAC-standard. Operators add to permissions; intersections never reduce.
- **Restrictive (intersection, lowest privilege wins)** — defense-in-depth, but unintuitive and hard to debug.
- **Per-Authorization priority field** — each row has a numeric priority; highest wins. Maximum control, maximum UI complexity.
- **Conflict = REJECT** — if multiple Authorizations resolve to different profiles, refuse login and alert. Sound, but creates operational footguns.

Independent question: when a **direct-user** Authorization and an **AD-group** Authorization both match, which one wins? This is the "personal override" case, common in identity systems.

## Decision

- **Permissive** wins among matching Authorizations: the profile with the highest `tacacs_priv_lvl` is returned. Tie-breaks (same priv-lvl, different profiles) are deterministic by Authorization-row ID, but we treat them as effectively interchangeable; the UI surfaces the ambiguity.
- **Direct-user Authorizations override AD-group Authorizations**. Even if the AD-group grant has higher priv-lvl, an explicit user-targeted grant takes precedence. This expresses the "exception" semantic without requiring a priority field.
- The UI exposes an **"Effective Permissions per User"** view that lists every DeviceGroup the user can reach, the winning Authorization row, and what was overridden. This makes conflicts visible without requiring the operator to trace them manually.

## Consequences

- Matches the expectation set by every mainstream RBAC system. No surprises for operators who have used Azure RBAC, AWS IAM, or similar.
- "Why does Jan have admin?" is answered by clicking through the Effective Permissions table, not by mental simulation.
- Restricting a user requires removing them from the permissive grant, not adding a restrictive one. We accept that this is the costlier operation in our model.
- Direct-user overrides give an operator-visible "break the pattern" handle without inventing a new construct.
- A user who is granted access via two overlapping AD groups will end up with the more permissive role. Documented; operators must keep AD-group → profile mappings consistent or accept the consequence.

## Alternatives considered

- **Restrictive** — would reject Jan's admin login because he is "also" in an operator group. Counter-intuitive enough to generate ongoing support load.
- **Priority field** — would force every Authorization to carry a number, every UI row to surface it, and every conflict to be debugged in priority-order rather than data-order. Powerful but expensive.
- **Conflict = REJECT** — a single overlap takes the user offline. Untenable in environments where AD group hygiene is imperfect.
