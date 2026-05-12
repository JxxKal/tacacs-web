# 0009. Append-only action-only audit log

- Date: 2026-05-12
- Status: Accepted

## Context

A web UI that mutates security-relevant state (Devices, Authorizations, Profiles, Settings) must keep a defensible audit trail. Two dimensions to decide on:

- **Mutability**: append-only vs. operator-editable.
- **Granularity**: action-only (`actor performed action X on target Y`) vs. full state diff (before / after JSON for the entity touched).

Full state diffs enable rollback semantics and forensic deep-dives. They also balloon storage and complicate retention; secrets and PII can leak into the diff log if we are not careful.

## Decision

- The audit log is **append-only**: no UI path to update or delete individual records. Bulk pruning by retention policy is the only deletion path, and the pruning action itself is audited.
- Records are **action-only**: each row captures `actor`, `actor_role`, `auth_method` (saml | local), `action` (string code, e.g. `device.update`), `target_type`, `target_id`, `summary` (free-text one-liner), `ts`, `client_ip`, `user_agent`. **No before/after JSON columns.**
- **Retention default**: 365 days, configurable.
- The Audit-Log browser is only accessible to the `admin` role.
- Action codes are a closed vocabulary defined in code (`backend/app/audit/actions.py`), not free-form strings. Filters in the UI key off this vocabulary.

## Consequences

- Compliance: append-only is the minimum-viable property for any auditor conversation.
- Storage cost is bounded; no JSON blob columns growing with the size of edited entities.
- Forensic ceiling: "what was the previous value of `device.shared_secret_id`?" cannot be answered from the audit log alone. Operators must rely on their own change-management records or take periodic DB snapshots if they want rollback fidelity.
- The closed action-code vocabulary means adding an audited action requires a code change. We see this as a feature (every audited action has been explicitly designed) rather than a limitation.
- Audit-log entries reference principal IDs that may later be soft-disabled or hard-deleted. We retain a `username_snapshot` field to make rows readable post-deletion.

## Alternatives considered

- **Full state-diff audit** — gives rollback and forensic depth, but doubles the schema effort (each entity needs a snapshot serializer), and risks leaking encrypted-column plaintexts if the diff is captured naively. Reconsider in v2 if operators report missing context.
- **Mutable audit log** — anything an admin can delete is not an audit log. Disqualified.
- **Per-entity versioned history (Git-style)** — every entity carries its own revision history. Cleanest forensic model, but a separate project in itself. Out of scope.
