"""Audit-log helpers (ADR-0009).

Closed action vocabulary in `actions.py`, append-only insertion in
`logger.py`. The audit log is never updated or deleted by application
code; the retention-pruning job is the only authorised delete path.
"""

from app.audit.logger import append, append_crud

__all__ = ["append", "append_crud"]
