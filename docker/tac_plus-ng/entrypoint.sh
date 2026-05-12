#!/bin/sh
# Render the tac_plus-ng config from the template, start busybox syslogd
# to surface daemon errors on stderr, then exec tac_plus-ng in the
# foreground.
#
# Why not spawnd? In a from-source build the spawnd binary is a thin
# listener that re-execs its own /proc/self/exe expecting that path to
# contain the worker code; in our two-binary install it doesn't, and
# spawnd hits a recursive-exec guard. tac_plus-ng accepts the same
# config (including the `id = spawnd { ... }` block) and runs the
# listener + worker itself.
set -u

echo "[entrypoint] starting as $(id)" >&2
: "${TACACS_SHARED_SECRET:?TACACS_SHARED_SECRET env var must be set}"

CFG_TEMPLATE=/etc/tac_plus-ng/tac_plus-ng.cfg.template
CFG_OUT=/etc/tac_plus-ng/tac_plus-ng.cfg

envsubst '$TACACS_SHARED_SECRET' < "$CFG_TEMPLATE" > "$CFG_OUT"

echo "[entrypoint] rendered config (secret elided):" >&2
sed 's|"[^"]*"|"<elided>"|g' "$CFG_OUT" >&2

busybox syslogd -n -O /dev/stderr &
echo "[entrypoint] syslogd pid=$!" >&2
sleep 1

echo "[entrypoint] exec: /usr/local/sbin/tac_plus-ng -d 1 -f $CFG_OUT" >&2
exec /usr/local/sbin/tac_plus-ng -d 1 -f "$CFG_OUT"
