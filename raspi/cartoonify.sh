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

get_phy() {
  wifname=$1
  iw dev | \
  awk -v wifname=$wifname \
    '/^phy/ {sub("#", ""); phy = $1} \
     /Interface / && $2 == wifname {print phy; exit}'
}

gpio_init() {
  # Initialize GPIOs.
  # We need to set drive strength here since Python package gpiozero does not provide that functionality.
  # Python package pigpio is able to do that.
  # Either way, we want the green LED to have constant brightness throughout the entire life-cycle of the app.

  # Group 0 is GPIO 0..27, 7 is 16mA (max is 16 mA, 50 mA total for all GPIOs).
  gpio drive 0 7
  # Pin 7 (WiringPi's numbering, i.e., BCM 4) is connected to the power LED. So does pin 22 (BCM 6).
  # Let's set the former one to the low state just in case the aplication crashed so that we don't overpower the LED.
  gpio write 7 0
  echo heartbeat > /sys/class/leds/power_led/trigger
}

gpio_reset() {
  gpio_init
  # Revert GPIO state back to its initial state.
  gpio drive 0 0
}

start_daemon() {
  stop_daemon
  gpio_init
  # Disable swapping to protect the storage from excessive usage and application from slowing down.
  swapoff -a
  # Enable job control so that all processes handle SIGINT and exit gracefully.
  set -m
  daemon &
  echo $! > "$PID_FILE"

  # Initialize Wi-Fi hotspot
  if [ ! -d /sys/class/net/wlan0s1 ]; then
    iw phy $wiphy interface add wlan0s1 type __ap
    nmcli conn up Hotspot > /dev/null &
  fi
}

stop_daemon() {
  # Shut down Wi-Fi hotspot
  if [ -d /sys/class/net/wlan0s1 ]; then
    nmcli conn down Hotspot > /dev/null &
  fi

  # Stop daemon
  pid=$( cat "$PID_FILE" 2> /dev/null )
  if [ ! -z "$pid" ]; then
    pgid=$( ps -o pgid= $pid | xargs echo -n )
    kill -INT -$pgid 2> /dev/null
  fi

  gpio_release
}

daemon() {
  trap "gpio_init; exit 1" SIGINT
  cd "$CARTOONIFY_DIR"
  while true; do
    ./raspi-run.sh
    gpio_init
    # Wait a bit if something is broken so that we don't overload the CPU.
    sleep 1
  done
}

wiphy=$( get_phy wlan0 )

# Carry out specific functions when asked to by the system
case "$1" in
  start)
    echo "Starting cartoonify"
    start_daemon
    ;;
  stop)
    echo "Stopping cartoonify"
    stop_daemon
    gpio_reset
    # It is not desired to re-enable swapping if the system is being shut down.
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
