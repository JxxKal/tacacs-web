"""Render a PrivilegeProfile into a tac_plus-ng inline TACPROFILE script.

The daemon evaluates that script per command/AV-pair against the live
TACACS+ request. Script grammar reference (`tac_plus-ng.cfg(5)` and the
upstream `mavis_tacplus-ng-demo-database.pl`).

The shape we emit:

    {
        profile {
            script {
                if (service == shell) {
                    if (cmd == "") {
                        set priv-lvl = <N>
                        set <k> = "<v>"   # per extra_av_pairs entry
                        permit
                    }
                    if (cmd =~ /<deny_re>/) deny     # repeats per pattern
                    if (cmd =~ /<permit_re>/) permit # repeats per pattern
                    deny                              # default-deny tail
                }
                deny
            }
        }
    }

When both regex lists are empty we omit the per-command block entirely
and emit a single `permit` after the shell-session grant — that's the
"admin profile, no command restrictions" case.
"""

from __future__ import annotations

from app.db.models import PrivilegeProfile

_INDENT_3 = " " * 12
_INDENT_4 = " " * 16
_INDENT_5 = " " * 20


def render_tacprofile(profile: PrivilegeProfile) -> str:
    extra_av_lines = [
        f'{_INDENT_5}set {key} = "{_escape_double_quote(value)}"'
        for key, value in profile.extra_av_pairs.items()
    ]

    shell_session_block = [
        f'{_INDENT_4}if (cmd == "") {{',
        f"{_INDENT_5}set priv-lvl = {profile.tacacs_priv_lvl}",
        *extra_av_lines,
        f"{_INDENT_5}permit",
        f"{_INDENT_4}}}",
    ]

    permit_patterns = profile.permit_commands_regex or []
    deny_patterns = profile.deny_commands_regex or []
    no_command_restrictions = not permit_patterns and not deny_patterns

    if no_command_restrictions:
        per_command_lines: list[str] = [f"{_INDENT_4}permit"]
    else:
        per_command_lines = []
        for pattern in deny_patterns:
            per_command_lines.append(
                f"{_INDENT_4}if (cmd =~ /{_escape_regex_for_script(pattern)}/) deny"
            )
        for pattern in permit_patterns:
            per_command_lines.append(
                f"{_INDENT_4}if (cmd =~ /{_escape_regex_for_script(pattern)}/) permit"
            )
        per_command_lines.append(f"{_INDENT_4}deny")

    body = "\n".join(
        [
            "{",
            f"{' ' * 4}profile {{",
            f"{' ' * 8}script {{",
            f"{_INDENT_3}if (service == shell) {{",
            *shell_session_block,
            *per_command_lines,
            f"{_INDENT_3}}}",
            f"{_INDENT_3}deny",
            f"{' ' * 8}}}",
            f"{' ' * 4}}}",
            "}",
        ]
    )
    return body


def _escape_double_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _escape_regex_for_script(pattern: str) -> str:
    """Escape `/` because the script delimits regexes with `/.../`."""
    return pattern.replace("/", "\\/")
