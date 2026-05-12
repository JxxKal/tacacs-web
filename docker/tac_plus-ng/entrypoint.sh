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

echo "[entrypoint] /usr/local/sbin listing:" >&2
ls -laL /usr/local/sbin >&2 || true

echo "[entrypoint] tac_plus-ng -h:" >&2
/usr/local/sbin/tac_plus-ng -h 2>&1 | head -30 >&2 || true

# Make spawnd's `/proc/self/exe` resolution point at tac_plus-ng. Upstream
# spawnd execs its own binary to start the worker; in our two-binary build
# the worker logic lives in tac_plus-ng. Replacing spawnd with a copy of
# tac_plus-ng (or symlink) makes /proc/self/exe → tac_plus-ng for the
# worker exec, which matches what spawnd is checking. Symlink keeps both
# names available.
if [ ! -L /usr/local/sbin/spawnd.orig ]; then
    cp /usr/local/sbin/spawnd /usr/local/sbin/spawnd.orig
    ln -sf /usr/local/sbin/tac_plus-ng /usr/local/sbin/spawnd-as-tacplus
fi

# `-1` selects single-process / "degraded" mode. Keep it for now even though
# spawnd silently exits after the listener binds — the M2 smoke needs
# something serving on port 49.
echo "[entrypoint] exec: /usr/local/sbin/spawnd -d 1 -f -1 $CFG_OUT" >&2
exec /usr/local/sbin/spawnd -d 1 -f -1 "$CFG_OUT"
