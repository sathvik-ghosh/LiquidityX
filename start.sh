#!/bin/sh
# Runs the real Tkinter app on a virtual screen and streams it to the browser (noVNC).
# Env: PORT (default 8080) · VNC_PASSWORD (optional, strongly recommended) · VIEW_ONLY=1 (viewers cannot click)
set -e
export DISPLAY=:99 HOME="${HOME:-/tmp}"
PORT="${PORT:-8080}"
Xvfb :99 -screen 0 1440x900x24 -nolisten tcp >/dev/null 2>&1 &
sleep 1
OPTS="-display :99 -forever -shared -localhost -rfbport 5900 -quiet -noxdamage"
[ -n "$VNC_PASSWORD" ] && { x11vnc -storepasswd "$VNC_PASSWORD" /tmp/vncpass >/dev/null 2>&1; OPTS="$OPTS -rfbauth /tmp/vncpass"; } || OPTS="$OPTS -nopw"
[ "$VIEW_ONLY" = "1" ] && OPTS="$OPTS -viewonly"
x11vnc $OPTS &
# restart the Tk app if the window is closed
( while true; do python3 main.py --demo --no-intro --db /tmp/workspace.db || true; rm -f /tmp/workspace.db; sleep 1; done ) &
NOVNC=/usr/share/novnc
[ -f $NOVNC/vnc.html ] && cp -f $NOVNC/vnc.html $NOVNC/index.html 2>/dev/null || true
exec websockify --web $NOVNC "$PORT" localhost:5900
