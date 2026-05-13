"""Render the NAS-client-list block of tac_plus-ng.cfg from the Device table.

Per ADR-0001 the NAS client list is the one piece of daemon state that does
not flow through MAVIS — `tac_plus-ng` validates the encrypted TACACS packet
at TCP-accept time, so it needs the shared secret(s) in static config. We
re-render this fragment on every Device CRUD operation and reload the
daemon (the reload sidecar lands in a follow-up commit; the render output
is already useful for diffing + the upcoming UI preview).
"""

from app.nas_config.render import render_host_blocks

__all__ = ["render_host_blocks"]
