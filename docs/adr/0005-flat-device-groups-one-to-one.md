# 0005. Flat DeviceGroups, 1:1 Device-to-Group cardinality

- Date: 2026-05-12
- Status: Accepted

## Context

A central modeling question: how do Devices relate to DeviceGroups, and how do DeviceGroups relate to each other? Options span a wide complexity range:

- **1:1, flat groups** — each Device belongs to exactly one DeviceGroup, groups don't nest.
- **n:m, flat groups** — a Device can be in multiple DeviceGroups. Authorization conflict resolution becomes a Device-level concern.
- **Nested groups (hierarchies)** — DeviceGroups contain other DeviceGroups; authz inherits down.
- **Tags + selectors** — Devices have free-form tags, DeviceGroups are predicate-driven selectors (`site=BER AND role=core`). Maximum expressivity, more model.

Real-world orgs often have orthogonal taxonomies (by site, by role, by tier), which argues for tags. But the authz tuple gets ugly: now we resolve principal × any-of-many-groups × profile, which forces a conflict-resolution policy at multiple levels.

## Decision

Use the **simplest viable model**: a Device belongs to **exactly one** DeviceGroup. DeviceGroups are **flat** (no nesting). Authorizations are tuples `(principal, device_group, privilege_profile)`.

If an operator needs orthogonal selectors ("Berlin AND core"), they pick the finest-grained dimension as the physical DeviceGroup and express the wider intent via multiple Authorizations on the same principal.

## Consequences

- The authorization model is a clean three-level join. No Device-level conflict resolution, no graph traversal.
- DB schema stays simple: `device.device_group_id` foreign key, no join table.
- We accept that operators with orthogonal taxonomies have to model the same logical grouping twice in some scenarios. In practice, network ops teams converge on one primary taxonomy quickly.
- A Device "moves" between groups by editing one column. No cascade, no detach logic.
- The Effective Permissions computation is cheap enough that we can render it live in the UI per user.
- Conflict resolution still has to live somewhere — it lives at the principal level instead (see ADR-0006).

## Alternatives considered

- **n:m with conflict resolution at Device level** — would require a precedence policy on Device-Group order, or yet another priority field. Doubles the number of "which row wins" questions.
- **Nested DeviceGroups** — natural for hierarchical orgs (Region → Site → Rack) but requires graph traversal in MAVIS, materialized closures for performance, and inheritance/override semantics in the UI. Overkill for v1.
- **Tags + selector-DeviceGroups** — flexible, but the UI complexity (writing selector predicates, previewing matched Devices) is a project in itself. Strong v2 candidate if the flat model proves too limiting.
