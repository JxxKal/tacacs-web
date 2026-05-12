# 0008. Accounting in DB + RFC5424/TCP/TLS forwarding via ingestor

- Date: 2026-05-12
- Status: Accepted

## Context

TACACS+ accounting records (login start/stop, per-command audit entries) are valuable for two distinct audiences:

- **Operators**, who want a UI to answer "who ran `clear arp` on `core-sw-01` yesterday".
- **SIEM / Compliance**, who want every record forwarded to a centralized collector for long-term retention.

Two questions:

1. **Source of the forwarded stream**: does `tac_plus-ng` write to syslog directly, or do we ingest the daemon's records into our DB and forward from there?
2. **Wire format and protocol**: UDP/514 vs. TCP/514 vs. TLS/6514; RFC3164 (BSD-style) vs. RFC5424 (structured) vs. CEF/LEEF (SIEM-specific).

## Decision

- The `tac_plus-ng` daemon writes accounting records to a **shared log file** in a stable format.
- A Python **accounting-ingestor**, running as a background worker inside the backend container, **tails** that file, parses each record, persists a row in the `accounting_record` DB table (with resolved username, NAS name, and DeviceGroup as snapshot columns for forensic stability), and then **forwards** the same record to the configured remote syslog target.
- Forwarding uses **RFC5424** with Structured-Data elements (`[tacacs nas="10.0.0.1" user="jan" cmd="show run"]`), over **TCP** or **TLS** (operator-configurable, no UDP option).
- Retention in the DB is **30 days by default**, operator-configurable, with a daily cleanup job. The SIEM holds the long-term archive.
- Acct-record schema includes both `user_id` (FK) and `username_snapshot` (TEXT) so accounting remains joinable even if a user record is hard-deleted later.

## Consequences

- One canonical code path produces both stores; the DB and the SIEM see the same records with the same field semantics.
- The ingestor is the failure-isolation point. If the SIEM is unreachable, we keep buffering DB inserts; forwarding catches up when the SIEM comes back (the buffer is the tail-position on the log file plus a small in-memory queue). If the DB is unreachable, the ingestor backs off and the log file grows until the disk fills — operator must monitor disk space (documented).
- We accept the cost of a parser layer over the daemon's log format. If `tac_plus-ng` changes its format, we update the parser.
- UDP is deliberately ruled out — silent drops are unacceptable for an audit trail. TCP gives us reliable delivery; TLS adds in-transit confidentiality.
- RFC5424 with SD-Elements is the format most modern SIEMs (Splunk, ELK, QRadar, Sentinel) parse without custom rules. We do not bind to a vendor format like CEF in v1.
- Accounting-DB retention is intentionally short (30d) because the SIEM is the system of record. Operators who want longer in-DB retention can change the setting.

## Alternatives considered

- **`tac_plus-ng` writes directly to syslog, no DB persistence** — operators lose the in-UI history view. Forces ad-hoc grep against the SIEM for every "what did Jan do" question.
- **`tac_plus-ng` writes to both DB and syslog directly** — requires custom MAVIS or external log modules in the daemon and duplicated configuration; harder to ensure both copies see the same enriched fields.
- **UDP syslog** — universal compatibility, but silent drops break the audit-trail guarantee. Not worth the operational savings.
- **CEF/LEEF format** — pre-mapped for one specific SIEM vendor, friction for everyone else. RFC5424 is the lowest-common-denominator structured choice.
