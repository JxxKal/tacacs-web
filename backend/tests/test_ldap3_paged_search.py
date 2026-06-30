"""Regression tests for the paged-search wrapper.

The wrapper delegates to ldap3's own paged_search_generator, so the
tests inject a fake `conn.extend.standard.paged_search` that hands
back two pages worth of response dicts and asserts the wrapper
forwards the right keyword arguments and filters out non-entry
items.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from ldap3 import SUBTREE

from app.ldap_sync.ldap3_client import _paged_search


class _FakeStandard:
    def __init__(self, pages: list[list[dict]]) -> None:
        self._pages = pages
        self.last_kwargs: dict[str, object] | None = None

    def paged_search(self, **kwargs: object) -> Iterable[dict]:
        self.last_kwargs = kwargs

        def _gen() -> Iterator[dict]:
            for page in self._pages:
                yield from page

        return _gen()


class _FakeExtend:
    def __init__(self, standard: _FakeStandard) -> None:
        self.standard = standard


class _FakeConn:
    def __init__(self, pages: list[list[dict]]) -> None:
        self.standard = _FakeStandard(pages)
        self.extend = _FakeExtend(self.standard)


def _entries(count: int, start: int = 0) -> list[dict]:
    return [
        {
            "type": "searchResEntry",
            "dn": f"CN=u{i},OU=t",
            "attributes": {},
            "raw_attributes": {},
        }
        for i in range(start, start + count)
    ]


def test_paged_search_streams_every_page() -> None:
    conn = _FakeConn([_entries(500), _entries(250, start=500)])
    results = list(_paged_search(conn, "DC=corp", "(objectClass=user)", ["sAMAccountName"], 500))
    assert len(results) == 750
    kw = conn.standard.last_kwargs
    assert kw is not None
    assert kw["search_base"] == "DC=corp"
    assert kw["search_filter"] == "(objectClass=user)"
    assert kw["search_scope"] == SUBTREE
    assert kw["paged_size"] == 500
    assert kw["paged_criticality"] is True
    assert kw["generator"] is True


def test_paged_search_filters_referrals() -> None:
    pages = [
        [
            {"type": "searchResRef", "uri": "ldap://ref"},
            {
                "type": "searchResEntry",
                "dn": "CN=u",
                "attributes": {},
                "raw_attributes": {},
            },
        ]
    ]
    conn = _FakeConn(pages)
    results = list(_paged_search(conn, "DC=corp", "(o=*)", [], 500))
    assert len(results) == 1
    assert results[0]["dn"] == "CN=u"


def test_paged_search_uses_paged_criticality_true() -> None:
    """If AD ignores an uncritical paged-results control we cap silently
    at the server-side MaxPageSize. Forcing criticality makes the
    server reject the search instead of returning half the data."""
    conn = _FakeConn([_entries(1)])
    list(_paged_search(conn, "DC=corp", "(o=*)", [], 500))
    assert conn.standard.last_kwargs is not None
    assert conn.standard.last_kwargs["paged_criticality"] is True
