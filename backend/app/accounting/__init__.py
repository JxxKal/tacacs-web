"""TACACS+ accounting ingestor (M6b).

Tails the daemon's accounting log file from the shared `tac-plus-ng-acct`
volume, parses each TSV record, and persists into `accounting_record`.
Runs as a background task in the FastAPI lifespan.
"""

from app.accounting.ingestor import (
    ACCT_LOG_PATH,
    SETTING_OFFSET,
    parse_record,
    start_ingestor,
    stop_ingestor,
)

__all__ = [
    "ACCT_LOG_PATH",
    "SETTING_OFFSET",
    "parse_record",
    "start_ingestor",
    "stop_ingestor",
]
