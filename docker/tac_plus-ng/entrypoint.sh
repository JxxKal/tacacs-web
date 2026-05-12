#!/bin/sh
# Render the tac_plus-ng config from the template, start a tiny syslogd
# (busybox) that pipes /dev/log to our stdout so we actually see spawnd's
# errors, then exec spawnd in the foreground.
set -u

echo "[entrypoint] starting as $(id)" >&2
: "${TACACS_SHARED_SECRET:?TACACS_SHARED_SECRET env var must be set}"

CFG_TEMPLATE=/etc/tac_plus-ng/tac_plus-ng.cfg.template
CFG_OUT=/etc/tac_plus-ng/tac_plus-ng.cfg

envsubst '$TACACS_SHARED_SECRET' < "$CFG_TEMPLATE" > "$CFG_OUT"

echo "[entrypoint] rendered config (secret elided):" >&2
sed 's|"[^"]*"|"<elided>"|g' "$CFG_OUT" >&2

# spawnd writes errors via syslog(3). Without a syslog daemon those go
# nowhere. Start busybox syslogd to forward the local syslog socket to
# stdout (`-O -`), in the foreground (`-n`) but backgrounded by the shell.
busybox syslogd -n -O /dev/stderr &
SYSLOG_PID=$!
echo "[entrypoint] syslogd pid=$SYSLOG_PID" >&2
# Tiny pause so the syslog socket is ready before spawnd starts.
sleep 1

echo "[entrypoint] exec: /usr/local/sbin/spawnd -d 1 -f $CFG_OUT" >&2
exec /usr/local/sbin/spawnd -d 1 -f "$CFG_OUT"
