#!/usr/bin/env bash

echo "Installing requirements..."

sudo apt update

command -v git &>/dev/null || sudo apt install git

if [ ! -d "WiringPi" ]; then
  git clone https://github.com/WiringPi/WiringPi
  cd WiringPi
  ./build
  cd ..
fi

if [ ! -d "zj-58" ]; then
git clone https://github.com/kyselejsyrecek/zj-58
  cd zj-58
  sudo apt install cups libcups2-dev cmake # TODO Merge all DEB dependencies to one command.
  cmake .
  cmake --build .
  sudo make install
  #sudo sed -i 's/#FileDevice.*/FileDevice Yes/g' /etc/cups/cups-files.conf
  #sudo service cups restart
  #sudo lpadmin -p ZJ-58 -E -v serial:/dev/ttyS0?baud=9600 -m zjiang/zj58.ppd
  #sudo lpadmin -p ZJ-58 -E -v usb:/dev/ttyUSB0 -m zjiang/zj58.ppd
  sudo lpadmin -p ZJ-58 -E -v parallel:/dev/usb/lp0 -m zjiang/zj58.ppd
  sudo usermod -a -G lpadmin "$USER" # FIXME TODO
  sudo usermod -a -G lp "$USER" # FIXME TODO
  #su - "$USER" # Reload group settings. # TODO May be required in raspi-run.sh as well! # FIXME Requires Password and loses CWD. # FIXME Reboot may be necessary to take effect.
  sudo lpadmin -d ZJ-58
  cd ..
fi

# Install start-up scripts.
echo "Copying start-up scripts..."
sudo cp raspi/gpio-mode.sh /etc/init.d/
echo "setting script to run on boot..."
sudo update-rc.d gpio-mode.sh defaults
sudo /etc/init.d/gpio-mode.sh start
# XXX Legacy code. GPIO pin 6 (BCM numbering) is used instead. See README for more information.
# Install the shutdown listener script.
# Shutdown listener runs on startup and shuts down the system when GPIO3 goes low.
#sudo cp raspi/listen-for-shutdown.py /usr/local/bin/
#sudo cp raspi/listen-for-shutdown.sh /etc/init.d/
#echo "setting script to run on boot..."
#sudo update-rc.d listen-for-shutdown.sh defaults
#sudo /etc/init.d/listen-for-shutdown.sh start

# Disable Wi-Fi power save to resolve network lags.
sudo nmcli con mod preconfigured wifi.powersave disable

sudo apt install libcairo2 python3-virtualenv libcap-dev #python3-picamera2 # FIXME Balik python3-picamera2 instaluje 600 MB závislostí vč. NumPy! To asi není správný způsob získávání obrázků.

# Create virtual Python 3 environment inside the cartoonify repository.
# The environment is not isolated so that libcamera and its dependencies do not have to be rebuilt and so that their proper versions are used.
[ ! -d "virtualenv" ] && python3 -m venv --system-site-packages virtualenv
source ./virtualenv/bin/activate
cd cartoonify

# Install the "cartoonify" shell command.
echo "Installing the cartoonify command..."
sudo python3 -m pip install -e .

# DEBUGGING: Incrementally gather Python dependencies.
#DIMENSION=640; while ! python3 ../run.py --min-inference-dimension $DIMENSION --max-inference-dimension $DIMENSION --fit-width 1280 --fit-height 1280; do PKG=$( tail -n1 `ls ../logs/*.log | tail -n1` | sed -e "/ModuleNotFoundError: No module named/!d" -e "s/.*'\(.*\)'/\\1/g" ); { [ -z "$PKG" ] && echo "Unknown error: $( cat `ls ../logs/*.log | tail -n1`)" && break; }; python3 -m pip install $PKG >/opt/python3/install_logs/$PKG.log 2>&1 || { echo "Error installing $PKG."; break; }; done

python3 -m pip install -r requirements_raspi.txt
RETVAL=$?

if [ ! -z "$DEBUG" ]; then
  # Development requirements
  sudo apt install tk-dev
  sudo python3 -m pip install matplotlib
fi
echo ""
echo ""
echo "NOTE 1: If you see errors trying to access the printer or change printer settings (produced by commands lp or lpadmin), it is necessary that you reboot Raspberry Pi and re-execute the following command:"
echo "    sudo lpadmin -d ZJ-58"
echo ""
echo "NOTE 2: If your printer is not listed as /dev/usb/lp0, please comment-out the \"lpadmin\" line in this script, uncomment the relevant one, remove the \"zj-58\" directory using command \"rm -rf zj-58\" and re-run this script."
echo ""
echo "Done."

cd ..
exit $RETVAL