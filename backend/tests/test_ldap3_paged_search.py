"""Regression tests for the AD paged-search cookie handling.

Reading the cookie out of the wrong control-OID silently caps every
sync at one page. This test exercises the loop with two pages so a
future typo trips on the way in.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.ldap_sync.ldap3_client import PAGED_RESULTS_OID, _paged_search


class _FakeConn:
    def __init__(self, pages: list[tuple[list[dict], bytes]]) -> None:
        # Each tuple = (response_entries, cookie_after_this_call).
        # The last cookie is empty bytes to mark "no more pages".
        self._pages = list(pages)
        self.response: list[dict] = []
        self.result: dict[str, object] = {}
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs: object) -> None:
        self.calls.append(kwargs)
        entries, cookie = self._pages.pop(0)
        self.response = entries
        self.result = {
            "controls": {
                PAGED_RESULTS_OID: {"value": {"cookie": cookie}},
            }
        }


def _drain(it: Iterator[object]) -> list[object]:
    return list(it)


def test_paged_search_iterates_until_cookie_empty() -> None:
    pages = [
        (
            [
                {
                    "type": "searchResEntry",
                    "dn": f"CN=u{i},OU=t",
                    "attributes": {},
                    "raw_attributes": {},
                }
                for i in range(500)
            ],
            b"\x01continue",
        ),
        (
            [
                {
                    "type": "searchResEntry",
                    "dn": f"CN=u{i},OU=t",
                    "attributes": {},
                    "raw_attributes": {},
                }
                for i in range(500, 750)
            ],
            b"",
        ),
    ]
    conn = _FakeConn(pages)
    results = _drain(_paged_search(conn, "DC=corp", "(objectClass=user)", [], 500))
    assert len(results) == 750
    assert len(conn.calls) == 2
    assert conn.calls[0]["paged_cookie"] is None
    assert conn.calls[1]["paged_cookie"] == b"\x01continue"


def test_paged_search_stops_when_no_controls() -> None:
    conn = _FakeConn(
        [
            (
                [
                    {
                        "type": "searchResEntry",
                        "dn": "CN=only,OU=t",
                        "attributes": {},
                        "raw_attributes": {},
                    }
                ],
                b"",
            )
        ]
    )
    results = _drain(_paged_search(conn, "DC=corp", "(o=*)", [], 500))
    assert len(results) == 1
    assert len(conn.calls) == 1


def test_paged_search_skips_non_entry_responses() -> None:
    conn = _FakeConn(
        [
            (
                [
                    {"type": "searchResRef", "uri": "ldap://ref"},
                    {
                        "type": "searchResEntry",
                        "dn": "CN=u",
                        "attributes": {},
                        "raw_attributes": {},
                    },
                ],
                b"",
            )
        ]
    )
    results = _drain(_paged_search(conn, "DC=corp", "(o=*)", [], 500))
    assert len(results) == 1
    assert results[0]["dn"] == "CN=u"
