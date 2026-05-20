"""RFC5424 syslog forwarder for accounting records.

A second consumer of the `accounting_record` table (the first is the
M6d UI search). On a poll loop, reads rows newer than the persisted
`syslog.last_forwarded_id`, formats each as one RFC5424 message with
TACACS-specific structured-data, and ships them over TCP or TLS to
the operator-configured collector. ADR-0008.
"""

from app.syslog.forwarder import (
    SETTING_ENABLED,
    SETTING_HOST,
    SETTING_LAST_ID,
    SETTING_PORT,
    SETTING_PROTOCOL,
    SyslogConfig,
    format_rfc5424,
    load_config,
    send_test_message,
    start_forwarder,
    stop_forwarder,
)

__all__ = [
    "SETTING_ENABLED",
    "SETTING_HOST",
    "SETTING_LAST_ID",
    "SETTING_PORT",
    "SETTING_PROTOCOL",
    "SyslogConfig",
    "format_rfc5424",
    "load_config",
    "send_test_message",
    "start_forwarder",
    "stop_forwarder",
]
