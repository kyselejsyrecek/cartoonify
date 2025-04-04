#!/usr/bin/env bash
cd /cartoonify/zj-58
make
sudo ./install
sudo lpadmin -p ZJ-58 -E -v serial:/dev/ttyS0?baud=9600 -m zjiang/ZJ-58.ppd
sudo lpoptions -d ZJ-58
cd /cartoonify
#sudo pip install -e . # FIXME WTF?
sudo gpio mode 0 OUT # TODO Set all required GPIOs!
sudo gpio drive 0 7 # group 0 is GPIO 0..27, 7 is 16mA (max) # FIXME Is sudo required?
cartoonify --raspi-headless --raspi-gpio
