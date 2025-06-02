#!/bin/sh

### BEGIN INIT INFO
# Provides:          disable-swapping.py
# Required-Start:    $remote_fs $syslog
# Required-Stop:     $remote_fs $syslog
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
### END INIT INFO

# Disable swapping to protect the storage from excessive usage and application from slowing down.

# Carry out specific functions when asked to by the system
case "$1" in
  start|restart)
    swapoff -a
    ;;
  stop)
    swapon -a
    ;;
  *)
    echo "Usage: /etc/init.d/disable-swapping.sh {start|stop|restart}"
    exit 1
    ;;
esac