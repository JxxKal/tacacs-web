#!/bin/sh
# Render the tac_plus-ng config from the template using a curated set of
# env vars, then exec spawnd in the foreground (it supervises the
# tac_plus-ng worker process).
set -eu

: "${TACACS_SHARED_SECRET:?TACACS_SHARED_SECRET env var must be set}"

CFG_TEMPLATE=/etc/tac_plus-ng/tac_plus-ng.cfg.template
CFG_OUT=/etc/tac_plus-ng/tac_plus-ng.cfg

# Restrict envsubst to the named variables so unrelated `$FOO` strings in
# the config template are left intact.
envsubst '$TACACS_SHARED_SECRET' < "$CFG_TEMPLATE" > "$CFG_OUT"

exec /usr/local/sbin/spawnd -f "$CFG_OUT"
