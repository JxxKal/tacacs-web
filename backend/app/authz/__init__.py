"""Authorization domain: device resolution, policy, profile rendering.

Three independent pure-Python modules wired together by `policy.evaluate`:

- `device_resolution` — NAS source IP -> Device row (longest-prefix match)
- `policy` — collect candidate Authorizations and pick the winner per ADR-0006
- `profile_render` — turn the winning PrivilegeProfile into a tac_plus-ng
  inline TACPROFILE script that the daemon evaluates per command
"""

from app.authz.device_resolution import resolve_device_for_ip
from app.authz.policy import EffectiveAuthorization, evaluate_for_user
from app.authz.profile_render import render_tacprofile

__all__ = [
    "EffectiveAuthorization",
    "evaluate_for_user",
    "render_tacprofile",
    "resolve_device_for_ip",
]
