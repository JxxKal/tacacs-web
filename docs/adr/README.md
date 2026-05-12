# Architecture Decision Records

Each ADR captures one load-bearing architectural decision: the context in which it was made, the alternatives considered, and the consequences. ADRs are append-only — to revise a decision, write a new ADR that supersedes the old one.

Template: see [`0000-template.md`](0000-template.md).

## Index

- [0001 — tac_plus-ng as TACACS engine, MAVIS-external for live lookups](0001-tac-plus-ng-with-mavis-external.md)
- [0002 — Hybrid AD model: sync users for selection, live LDAPS bind for password](0002-hybrid-ad-sync-plus-live-bind.md)
- [0003 — SAML SP for admin login with one CLI-managed local break-glass admin](0003-saml-admin-auth-with-local-breakglass.md)
- [0004 — AES-GCM column encryption with operator-supplied master key](0004-aes-gcm-secrets-with-operator-master-key.md)
- [0005 — Flat DeviceGroups, 1:1 Device-to-Group cardinality](0005-flat-device-groups-one-to-one.md)
- [0006 — Permissive authorization conflict resolution; direct user overrides AD group](0006-permissive-authz-conflict-resolution.md)
- [0007 — Soft shared-secret rotation with dual-key window](0007-soft-shared-secret-rotation.md)
- [0008 — Accounting in DB + RFC5424/TCP/TLS forwarding via ingestor](0008-accounting-db-plus-syslog-forwarding.md)
- [0009 — Append-only action-only audit log](0009-append-only-action-only-audit-log.md)
- [0010 — React + Mantine + Vite + TypeScript frontend stack](0010-react-mantine-frontend-stack.md)
