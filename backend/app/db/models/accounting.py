"""Accounting-record storage for the M6 ingestor.

One row per TACACS+ accounting packet that the daemon writes to its
accounting log. The ingestor (M6b) tails that file, parses each record,
and inserts here. The Web-UI search page (M6d) reads from this table;
the syslog forwarder (M6c) also reads here for batching purposes.

Retention is 30 days by default per ADR-0008; the prune job (M6c
companion) deletes anything older than `accounting.retention_days`
(system_setting) on a daily APScheduler tick.

`task_id` correlates Start / Stop / Update for the same shell session:
the daemon emits the same task_id on all three packets for one
session, so the UI can group them. Cisco's per-command accounting
flows use a separate task_id per command — same idea.

`raw_av_pairs` keeps the full AV payload so operators can dig into
custom attributes without us having to model every TACACS+ AV up
front; the columns above are the indexed common ones.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AccountingRecord(Base):
    """One TACACS+ accounting packet, as ingested from the daemon log."""

    __tablename__ = "accounting_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # Identity-ish columns: queried often, indexed.
    nas_ip: Mapped[str | None] = mapped_column(String(64))
    username: Mapped[str | None] = mapped_column(String(256))
    port: Mapped[str | None] = mapped_column(String(64))
    nac_ip: Mapped[str | None] = mapped_column(String(64))
    # Action: "start" | "stop" | "update" (per RFC8907 / tac_plus-ng).
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    service: Mapped[str | None] = mapped_column(String(32))
    cmd: Mapped[str | None] = mapped_column(Text)
    priv_lvl: Mapped[int | None] = mapped_column(Integer)
    elapsed_seconds: Mapped[int | None] = mapped_column(Integer)
    # Correlates Start / Stop / Update for the same shell session.
    task_id: Mapped[str | None] = mapped_column(String(64))
    # Optional FK to the Device row whose IP the daemon recorded as
    # `nas_ip`. NULLed out on Device delete so retained accounting rows
    # survive a Device being decommissioned.
    device_id: Mapped[int | None] = mapped_column(ForeignKey("device.id", ondelete="SET NULL"))
    # Full AV payload as a flat string->string map. Lets operators
    # debug custom attributes without us having to schema every AV.
    raw_av_pairs: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_accounting_record_ts", "ts"),
        Index("ix_accounting_record_username", "username"),
        Index("ix_accounting_record_nas_ip", "nas_ip"),
        Index("ix_accounting_record_task_id", "task_id"),
        Index("ix_accounting_record_action", "action"),
    )
