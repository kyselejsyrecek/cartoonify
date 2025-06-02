#!/bin/sh

### BEGIN INIT INFO
# Provides:          gpio-mode.py
# Required-Start:    $remote_fs $syslog
# Required-Stop:     $remote_fs $syslog
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
### END INIT INFO

# Initialize GPIOs.
# We need to set drive strength here since Python package gpiozero does not provide that functionality.
# Python package pigpio is able to do that.
# Either way, we want the green LED to have constant brightness throughout the entire life-cycle of the app.

# Carry out specific functions when asked to by the system
case "$1" in
  start|restart)
    gpio drive 0 7 # group 0 is GPIO 0..27, 7 is 16mA (max is 16 mA, 50 mA total for all GPIOs)
    ;;
  stop)
    gpio drive 0 0
    ;;
  *)
    echo "Usage: /etc/init.d/gpio-mode.sh {start|stop|restart}"
    exit 1
    ;;
esac