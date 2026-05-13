"""Public REST API surface, version 1.

Routes here are operator-facing and meant to be reached via the nginx
reverse proxy. SAML SP gating lands in M5; until then the routes are open
on the docker-internal network — they MUST NOT be exposed publicly until
the SAML dependency is wired up. The nginx config in M5 will refuse to
proxy /api/* without an authenticated session cookie.
"""
