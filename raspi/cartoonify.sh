#!/usr/bin/env bash

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
  # Initialize GPIOs.
  # We need to set drive strength here since Python package gpiozero does not provide that functionality.
  # Python package pigpio is able to do that.
  # Either way, we want the green LED to have constant brightness throughout the entire life-cycle of the app.
  gpio drive 0 7 # group 0 is GPIO 0..27, 7 is 16mA (max is 16 mA, 50 mA total for all GPIOs)
  # Disable swapping to protect the storage from excessive usage and application from slowing down.
  swapoff -a
  # Enable job control so that all processes handle SIGINT and exit gracefully.
  set -m
  daemon &
  echo $! > "$PID_FILE"
}

stop_daemon() {
  pid=$( cat "$PID_FILE" 2> /dev/null )
  if [ ! -z "$pid" ]; then
    pgid=$( ps -o pgid= $pid | xargs echo -n )
    kill -INT -$pgid 2> /dev/null
  fi
}

daemon() {
  trap "exit 1" SIGINT
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
    # It is not desired to re-enable swapping if the system is being shut down.
    # Revert GPIO state back to its initial state.
    gpio drive 0 0
    ;;
  restart)
    echo "Restarting cartoonify"
    start_daemon
    ;;
  *)
    echo "Usage: /etc/init.d/cartoonify.sh {start|stop|restart}"
    exit 1
    ;;
esac

exit 0
