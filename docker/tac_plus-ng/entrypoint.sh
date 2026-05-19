#!/bin/sh
# tac_plus-ng container entrypoint.
#
# - Renders the static template (no $-vars left after this; the dynamic
#   host blocks come from a shared-volume include that the backend
#   rewrites on every Device mutate).
# - Bootstraps the dynamic hosts.cfg with a catch-all if the file does
#   not yet exist (operator hasn't provisioned any Devices yet); the
#   catch-all uses TACACS_SHARED_SECRET so the smoke test keeps working.
# - Starts busybox syslogd to surface daemon errors on stderr.
# - Launches tac_plus-ng as a child process and a parallel inotify-watch
#   loop. Each time the dynamic hosts file is rewritten by the backend,
#   the loop kills -HUP the daemon so it re-reads the include without a
#   container restart.
#
# Why not spawnd? In a from-source build the spawnd binary re-execs its
# own /proc/self/exe expecting it to contain the worker code; in our
# two-binary install that's not the case, so spawnd trips a recursive-
# exec guard. tac_plus-ng accepts the same config (including the
# `id = spawnd { ... }` block) and runs the listener + worker itself.

set -u

echo "[entrypoint] starting as $(id)" >&2
: "${TACACS_SHARED_SECRET:?TACACS_SHARED_SECRET env var must be set}"

CFG_TEMPLATE=/etc/tac_plus-ng/tac_plus-ng.cfg.template
CFG_OUT=/etc/tac_plus-ng/tac_plus-ng.cfg
DYNAMIC_DIR=/etc/tac_plus-ng/dynamic
DYNAMIC_FILE="$DYNAMIC_DIR/hosts.cfg"

mkdir -p "$DYNAMIC_DIR"
chgrp 1000 "$DYNAMIC_DIR" 2>/dev/null || true
chmod 0775 "$DYNAMIC_DIR"

envsubst '$TACACS_SHARED_SECRET' < "$CFG_TEMPLATE" > "$CFG_OUT"

# Bootstrap the dynamic hosts file with a catch-all if the backend
# hasn't written one yet. The backend overwrites this on first Device
# CRUD or on the manual /api/v1/admin/regenerate-nas-config trigger.
if [ ! -f "$DYNAMIC_FILE" ]; then
    cat > "$DYNAMIC_FILE" <<EOF
host bootstrap {
    address = 0.0.0.0/0
    address = ::/0
    key = "$TACACS_SHARED_SECRET"
    mavis backend = yes
}

# Match the docker healthcheck source so it doesn't fill the log.
host healthcheck {
    address = 127.0.0.1
    address = ::1
    key = "healthcheck-only-no-tacacs-traffic"
}
EOF
    chgrp 1000 "$DYNAMIC_FILE" 2>/dev/null || true
    chmod 0664 "$DYNAMIC_FILE"
    echo "[entrypoint] wrote bootstrap $DYNAMIC_FILE" >&2
fi

echo "[entrypoint] rendered config (secrets elided):" >&2
sed 's|"[^"]*"|"<elided>"|g' "$CFG_OUT" >&2

busybox syslogd -n -O /dev/stderr &
SYSLOG_PID=$!
echo "[entrypoint] syslogd pid=$SYSLOG_PID" >&2
sleep 1

echo "[entrypoint] starting tac_plus-ng" >&2
/usr/local/sbin/tac_plus-ng -d 1 -f "$CFG_OUT" &
DAEMON_PID=$!
echo "[entrypoint] tac_plus-ng pid=$DAEMON_PID" >&2

# Inotify watcher: on any file change inside the dynamic dir, SIGHUP the
# daemon so it re-reads the included hosts.cfg. `-q` suppresses every-
# event chatter, `-r` would be wrong (we only watch one dir), `--monitor`
# keeps the loop alive between events.
reload_loop() {
    while true; do
        if ! inotifywait -q -e close_write -e move -e create -e delete \
                "$DYNAMIC_DIR" >/dev/null; then
            echo "[entrypoint] inotifywait exited, restarting in 1s" >&2
            sleep 1
            continue
        fi
        if kill -0 "$DAEMON_PID" 2>/dev/null; then
            echo "[entrypoint] hosts.cfg changed; SIGHUP $DAEMON_PID" >&2
            kill -HUP "$DAEMON_PID"
        else
            echo "[entrypoint] daemon gone; reload loop exits" >&2
            return
        fi
    done
}
reload_loop &
WATCHER_PID=$!
echo "[entrypoint] reload watcher pid=$WATCHER_PID" >&2

# Forward SIGTERM/SIGINT to the daemon for a clean shutdown.
shutdown() {
    echo "[entrypoint] shutting down" >&2
    kill -TERM "$DAEMON_PID" 2>/dev/null || true
    kill -TERM "$WATCHER_PID" 2>/dev/null || true
    kill -TERM "$SYSLOG_PID" 2>/dev/null || true
    wait
}
trap shutdown TERM INT

wait "$DAEMON_PID"
DAEMON_RC=$?
echo "[entrypoint] tac_plus-ng exited rc=$DAEMON_RC" >&2
kill -TERM "$WATCHER_PID" 2>/dev/null || true
kill -TERM "$SYSLOG_PID" 2>/dev/null || true
exit "$DAEMON_RC"
