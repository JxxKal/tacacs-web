#!/bin/sh
# Render the tac_plus-ng config from the template using a curated set of
# env vars, then exec spawnd in the foreground (it supervises the
# tac_plus-ng worker process).
set -eu

echo "[entrypoint] starting as $(id)" >&2
: "${TACACS_SHARED_SECRET:?TACACS_SHARED_SECRET env var must be set}"

CFG_TEMPLATE=/etc/tac_plus-ng/tac_plus-ng.cfg.template
CFG_OUT=/etc/tac_plus-ng/tac_plus-ng.cfg

# Restrict envsubst to the named variables so unrelated `$FOO` strings in
# the config template are left intact.
envsubst '$TACACS_SHARED_SECRET' < "$CFG_TEMPLATE" > "$CFG_OUT"

echo "[entrypoint] rendered config (secret elided):" >&2
sed 's|"[^"]*"|"<elided>"|g' "$CFG_OUT" >&2

echo "[entrypoint] ldd /usr/local/sbin/spawnd:" >&2
ldd /usr/local/sbin/spawnd 2>&1 | head -20 >&2 || true

echo "[entrypoint] exec: /usr/local/sbin/spawnd -d 1 -f $CFG_OUT" >&2
exec /usr/local/sbin/spawnd -d 1 -f "$CFG_OUT"
