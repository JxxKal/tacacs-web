"""Tests for the authz domain: device resolution, policy, profile rendering."""

from __future__ import annotations

from app.authz import (
    evaluate_for_user,
    render_tacprofile,
    resolve_device_for_ip,
)
from app.db.models import (
    ADGroup,
    Authorization,
    Device,
    DeviceGroup,
    PrivilegeProfile,
    User,
)


def _device(ip_or_cidr: str, *, id: int = 0) -> Device:
    d = Device(
        name=f"d{id}",
        ip_or_cidr=ip_or_cidr,
        device_group_id=1,
    )
    d.id = id
    return d


def test_resolve_device_returns_longest_prefix() -> None:
    devices = [
        _device("10.0.0.0/8", id=1),
        _device("10.1.0.0/16", id=2),
        _device("10.1.2.0/24", id=3),
    ]
    match = resolve_device_for_ip("10.1.2.42", devices)
    assert match is not None and match.id == 3


def test_resolve_device_exact_host_wins_over_cidr() -> None:
    devices = [
        _device("10.0.0.0/8", id=1),
        _device("10.1.2.42", id=2),
    ]
    match = resolve_device_for_ip("10.1.2.42", devices)
    assert match is not None and match.id == 2


def test_resolve_device_no_match() -> None:
    assert resolve_device_for_ip("203.0.113.1", [_device("10.0.0.0/8")]) is None


def test_resolve_device_malformed_nas_ip() -> None:
    assert resolve_device_for_ip("not-an-ip", [_device("10.0.0.0/8")]) is None


def test_resolve_device_ignores_malformed_device_cidr() -> None:
    devices = [_device("not-a-cidr", id=1), _device("10.0.0.0/8", id=2)]
    match = resolve_device_for_ip("10.1.2.3", devices)
    assert match is not None and match.id == 2


def _profile(priv: int, *, id: int = 0, name: str = "p") -> PrivilegeProfile:
    p = PrivilegeProfile(
        name=name,
        tacacs_priv_lvl=priv,
        permit_commands_regex=[],
        deny_commands_regex=[],
        extra_av_pairs={},
    )
    p.id = id
    return p


def _user_with_groups(*group_ids: int, user_id: int = 1) -> User:
    user = User(sam_account_name="jan", distinguished_name="cn=jan,dc=x")
    user.id = user_id
    user.groups = []
    for gid in group_ids:
        g = ADGroup(sid=f"S-1-5-21-{gid}", distinguished_name=f"cn=g{gid}")
        g.id = gid
        user.groups.append(g)
    return user


def _ad_group_auth(
    ad_group_id: int, dg_id: int, profile: PrivilegeProfile, *, auth_id: int = 0
) -> Authorization:
    a = Authorization(
        principal_ad_group_id=ad_group_id,
        device_group_id=dg_id,
        privilege_profile_id=profile.id,
    )
    a.id = auth_id
    a.privilege_profile = profile
    a.device_group = DeviceGroup(name=f"dg{dg_id}")
    return a


def _user_auth(
    user_id: int, dg_id: int, profile: PrivilegeProfile, *, auth_id: int = 0
) -> Authorization:
    a = Authorization(
        principal_user_id=user_id,
        device_group_id=dg_id,
        privilege_profile_id=profile.id,
    )
    a.id = auth_id
    a.privilege_profile = profile
    a.device_group = DeviceGroup(name=f"dg{dg_id}")
    return a


def test_policy_no_authz_returns_none() -> None:
    user = _user_with_groups(100)
    outcome = evaluate_for_user(user, 1, [])
    assert outcome.winning is None
    assert outcome.profile is None


def test_policy_highest_priv_wins_among_ad_groups() -> None:
    user = _user_with_groups(100, 200)
    admin = _profile(15, id=1, name="admin")
    ro = _profile(1, id=2, name="ro")
    outcome = evaluate_for_user(
        user,
        1,
        [
            _ad_group_auth(100, 1, ro, auth_id=10),
            _ad_group_auth(200, 1, admin, auth_id=11),
        ],
    )
    assert outcome.winning is not None and outcome.winning.id == 11
    assert outcome.profile is admin
    assert len(outcome.overridden) == 1


def test_policy_direct_user_overrides_ad_group_even_with_lower_priv() -> None:
    user = _user_with_groups(100)
    admin = _profile(15, id=1, name="admin")
    ro = _profile(1, id=2, name="ro")
    outcome = evaluate_for_user(
        user,
        1,
        [
            _ad_group_auth(100, 1, admin, auth_id=10),
            _user_auth(user.id, 1, ro, auth_id=11),
        ],
    )
    assert outcome.winning is not None and outcome.winning.id == 11
    assert outcome.profile is ro


def test_policy_filters_by_device_group() -> None:
    user = _user_with_groups(100)
    p = _profile(7, id=1, name="op")
    outcome = evaluate_for_user(
        user,
        1,
        [_ad_group_auth(100, 2, p, auth_id=10)],
    )
    assert outcome.winning is None


def test_policy_ignores_unmemberships() -> None:
    user = _user_with_groups(100)
    p = _profile(15, id=1, name="admin")
    outcome = evaluate_for_user(
        user,
        1,
        [_ad_group_auth(999, 1, p, auth_id=10)],
    )
    assert outcome.winning is None


def test_render_profile_admin_no_command_restrictions() -> None:
    p = _profile(15, name="admin")
    out = render_tacprofile(p)
    assert "set priv-lvl = 15" in out
    assert "if (cmd =~" not in out
    # No-restrictions admin gets a single permit on the per-command branch.
    assert out.count("permit") >= 2  # one for cmd=="", one for any-command


def test_render_profile_with_permit_and_deny() -> None:
    p = PrivilegeProfile(
        name="ro",
        tacacs_priv_lvl=1,
        permit_commands_regex=["^show ", "^ping "],
        deny_commands_regex=["^configure "],
        extra_av_pairs={},
    )
    out = render_tacprofile(p)
    # Deny patterns come before permit patterns so deny wins on overlap.
    deny_pos = out.index("/^configure /")
    permit_pos = out.index("/^show /")
    assert deny_pos < permit_pos
    assert "deny" in out
    assert "permit" in out


def test_render_profile_extra_av_pairs() -> None:
    p = PrivilegeProfile(
        name="op",
        tacacs_priv_lvl=7,
        permit_commands_regex=[],
        deny_commands_regex=[],
        extra_av_pairs={"idletime": "30", "autocmd": 'echo "hi"'},
    )
    out = render_tacprofile(p)
    assert 'set idletime = "30"' in out
    # Double-quote inside a value must be escaped.
    assert 'set autocmd = "echo \\"hi\\""' in out


def test_render_profile_escapes_slash_in_regex() -> None:
    p = PrivilegeProfile(
        name="ro",
        tacacs_priv_lvl=1,
        permit_commands_regex=["^show vlan brief/all"],
        deny_commands_regex=[],
        extra_av_pairs={},
    )
    out = render_tacprofile(p)
    assert "/^show vlan brief\\/all/" in out
