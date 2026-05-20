"""LDAP3-based fetcher for AD users and their (transitively resolved) groups.

Concrete production fetcher consumed by `app.ldap_sync.sync.run_sync`. Kept
separate so the sync logic in `sync.py` can be unit-tested with a static
list of `ADUserRecord` instances.

Transitive group membership is computed via the AD-specific OID
`1.2.840.113556.1.4.1941` (LDAP_MATCHING_RULE_IN_CHAIN) on the `memberOf`
attribute — one search per user, scoped to the configured base DNs.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import TypedDict

from ldap3 import SUBTREE, Connection

from app.ldap_sync.sync import ADGroupRecord, ADUserRecord


class _Entry(TypedDict):
    dn: str
    attributes: dict[str, object]
    raw_attributes: dict[str, object]


USER_ATTRS = [
    "sAMAccountName",
    "objectGUID",
    "userPrincipalName",
    "distinguishedName",
    "displayName",
]
GROUP_ATTRS = ["objectSid", "distinguishedName", "name"]

# Skip disabled accounts (userAccountControl bit 2 == ACCOUNTDISABLE).
DEFAULT_USER_FILTER = (
    "(&(objectCategory=person)(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))"
)
TRANSITIVE_MEMBER_RULE = "1.2.840.113556.1.4.1941"
# RFC 2696 Simple Paged Results — the response control OID we read the
# continuation cookie out of.
PAGED_RESULTS_OID = "1.2.840.113556.1.4.319"


def fetch_users(
    conn: Connection,
    base_dns: Iterable[str],
    *,
    user_filter: str = DEFAULT_USER_FILTER,
    page_size: int = 500,
) -> list[ADUserRecord]:
    """Walk each base DN and return one record per user found."""
    records: list[ADUserRecord] = []
    group_cache: dict[str, ADGroupRecord] = {}

    for base_dn in base_dns:
        for entry in _paged_search(conn, base_dn, user_filter, USER_ATTRS, page_size):
            sam = _str(entry, "sAMAccountName")
            if sam is None:
                continue
            dn = entry["dn"]
            groups = _resolve_groups_for_user(conn, base_dn, dn, group_cache, page_size)
            records.append(
                ADUserRecord(
                    sam_account_name=sam,
                    distinguished_name=dn,
                    ad_object_guid=_format_guid(_raw(entry, "objectGUID")),
                    upn=_str(entry, "userPrincipalName"),
                    display_name=_str(entry, "displayName"),
                    groups=tuple(groups),
                )
            )
    return records


def _resolve_groups_for_user(
    conn: Connection,
    base_dn: str,
    user_dn: str,
    group_cache: dict[str, ADGroupRecord],
    page_size: int,
) -> list[ADGroupRecord]:
    filt = f"(member:{TRANSITIVE_MEMBER_RULE}:={_escape_filter_value(user_dn)})"
    groups: list[ADGroupRecord] = []
    for entry in _paged_search(conn, base_dn, filt, GROUP_ATTRS, page_size):
        gdn = entry["dn"]
        cached = group_cache.get(gdn)
        if cached is not None:
            groups.append(cached)
            continue
        sid = _format_sid(_raw(entry, "objectSid"))
        if sid is None:
            continue
        record = ADGroupRecord(
            sid=sid,
            distinguished_name=gdn,
            name=_str(entry, "name"),
        )
        group_cache[gdn] = record
        groups.append(record)
    return groups


def _paged_search(
    conn: Connection,
    base_dn: str,
    filter_: str,
    attrs: list[str],
    page_size: int,
) -> Iterable[_Entry]:
    """Iterate every result of a paged subtree search as a `response`-style dict."""
    cookie = None
    while True:
        conn.search(
            search_base=base_dn,
            search_filter=filter_,
            search_scope=SUBTREE,
            attributes=attrs,
            paged_size=page_size,
            paged_cookie=cookie,
        )
        for entry in conn.response:
            if entry.get("type") != "searchResEntry":
                continue
            yield _Entry(
                dn=entry["dn"],
                attributes=entry.get("attributes", {}) or {},
                raw_attributes=entry.get("raw_attributes", {}) or {},
            )
        ctrl = conn.result.get("controls", {}) if conn.result else {}
        cookie = ctrl.get(PAGED_RESULTS_OID, {}).get("value", {}).get("cookie")
        if not cookie:
            return


def _str(entry: _Entry, name: str) -> str | None:
    value = entry["attributes"].get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value if isinstance(value, str) else None


def _raw(entry: _Entry, name: str) -> bytes | None:
    value = entry["raw_attributes"].get(name)
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return None


def _format_guid(blob: bytes | None) -> str | None:
    """AD stores objectGUID in a mixed-endian layout; convert to canonical UUID."""
    if blob is None or len(blob) != 16:
        return None
    return str(uuid.UUID(bytes_le=bytes(blob)))


def _format_sid(blob: bytes | None) -> str | None:
    """Decode a binary objectSid into the canonical `S-1-5-...` string form."""
    if blob is None or len(blob) < 8:
        return None
    revision = blob[0]
    sub_authority_count = blob[1]
    identifier_authority = int.from_bytes(blob[2:8], "big")
    parts = [f"S-{revision}-{identifier_authority}"]
    for i in range(sub_authority_count):
        offset = 8 + i * 4
        if offset + 4 > len(blob):
            return None
        sub = int.from_bytes(blob[offset : offset + 4], "little")
        parts.append(str(sub))
    return "-".join(parts)


def _escape_filter_value(value: str) -> str:
    """RFC 4515 escaping for an LDAP filter assertion value."""
    return (
        value.replace("\\", r"\5c")
        .replace("(", r"\28")
        .replace(")", r"\29")
        .replace("\x00", r"\00")
        .replace("*", r"\2a")
    )
