#!/bin/sh
# Render the tac_plus-ng config from the template using a curated set of
# env vars, then exec spawnd in the foreground (it supervises the
# tac_plus-ng worker process).
set -u
# Don't `set -e` while debugging — we want to see the parse-only exit code
# without the shell aborting silently.

echo "[entrypoint] starting as $(id)" >&2
: "${TACACS_SHARED_SECRET:?TACACS_SHARED_SECRET env var must be set}"

CFG_TEMPLATE=/etc/tac_plus-ng/tac_plus-ng.cfg.template
CFG_OUT=/etc/tac_plus-ng/tac_plus-ng.cfg

# Restrict envsubst to the named variables so unrelated `$FOO` strings in
# the config template are left intact.
envsubst '$TACACS_SHARED_SECRET' < "$CFG_TEMPLATE" > "$CFG_OUT"

echo "[entrypoint] rendered config (secret elided):" >&2
sed 's|"[^"]*"|"<elided>"|g' "$CFG_OUT" >&2

echo "[entrypoint] spawnd usage:" >&2
/usr/local/sbin/spawnd -h 2>&1 | head -40 >&2 || true

echo "[entrypoint] spawnd parse-only check:" >&2
/usr/local/sbin/spawnd -P "$CFG_OUT" 2>&1 >&2
parse_rc=$?
echo "[entrypoint] parse-only exit code: $parse_rc" >&2

echo "[entrypoint] exec: /usr/local/sbin/spawnd -d 9 $CFG_OUT" >&2
exec /usr/local/sbin/spawnd -d 9 "$CFG_OUT"
