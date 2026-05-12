"""Active Directory synchronisation (ADR-0002)."""

from app.ldap_sync.sync import ADUserRecord, SyncResult, run_sync

__all__ = ["ADUserRecord", "SyncResult", "run_sync"]
