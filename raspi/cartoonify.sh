#! /bin/sh

### BEGIN INIT INFO
# Provides:          cartoonify.py
# Required-Start:    $remote_fs $syslog
# Required-Stop:     $remote_fs $syslog
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
### END INIT INFO

PID_FILE="/var/run/cartoonify.pid"
CARTOONIFY_DIR=

start_daemon() {
  stop_daemon
  daemon &
  echo $! > "$PID_FILE"
}

stop_daemon() {
  pid=$( cat "$PID_FILE" )
  [ ! -z "$pid" ] && kill $pid &> /dev/null
}

daemon() {
  cd "$CARTOONIFY_DIR"
  while true; do
    ./raspi-run.sh
    # Wait a bit if something is broken so that we don't overload the CPU.
    sleep 1
  done
}

# Carry out specific functions when asked to by the system
case "$1" in
  start)
    echo "Starting cartoonify"
    start_daemon
    ;;
  stop)
    echo "Stopping cartoonify"
    stop_daemon
    ;;
  restart)
    echo "Restarting cartoonify"
    stop_daemon
    start_daemon
    ;;
  *)
    echo "Usage: /etc/init.d/cartoonify.sh {start|stop|restart}"
    exit 1
    ;;
esac

exit 0
