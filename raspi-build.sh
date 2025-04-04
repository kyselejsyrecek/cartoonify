#!/usr/bin/env bash

echo "Installing requirements..."

[ command -v git ] || apt install git

git clone https://github.com/WiringPi/WiringPi
pushd WiringPi
./build
popd

git clone https://github.com/kyselejsyrecek/zj-58
pushd zj-58
make
sudo ./install
popd

# Install the shutdown listener script.
# Shutdown listener runs on startup and shuts down the system when GPIO3 goes low.
echo "Copying start-up scripts..."
sudo cp listen-for-shutdown.py /usr/local/bin/
sudo cp listen-for-shutdown.sh /etc/init.d/
echo "setting script to run on boot..."
sudo update-rc.d listen-for-shutdown.sh defaults
sudo /etc/init.d/listen-for-shutdown.sh start
# Install the "cartoonify" shell command.
sudo pip install -e .

# Disable Wi-Fi power save to resolve network lags.
sudo nmcli con mod preconfigured wifi.powersave disable

sudo apt install libcairo2 python3-virtualenv libcap-dev #python3-picamera2 # FIXME Balik python3-picamera2 instaluje 600 MB závislostí vč. NumPy! To asi není správný způsob získávání obrázků.

# Create virtual Python 3 environment inside the cartoonify repository.
# The environment is not isolated so that libcamera and its dependencies do not have to be rebuilt and so that their proper versions are used.
python3 -m venv --system-site-packages virtualenv
source ./virtualenv/bin/activate
pushd cartoonify

# DEBUGGING: Incrementally gather Python dependencies.
#DIMENSION=640; while ! python3 ../run.py --min-inference-dimension $DIMENSION --max-inference-dimension $DIMENSION --fit-width 1280 --fit-height 1280; do PKG=$( tail -n1 `ls ../logs/*.log | tail -n1` | sed -e "/ModuleNotFoundError: No module named/!d" -e "s/.*'\(.*\)'/\\1/g" ); { [ -z "$PKG" ] && echo "Unknown error: $( cat `ls ../logs/*.log | tail -n1`)" && break; }; python3 -m pip install $PKG >/opt/python3/install_logs/$PKG.log 2>&1 || { echo "Error installing $PKG."; break; }; done

python3 -m pip install -r requirements_raspi.txt
RETVAL=$?

if [ ! -z "$DEBUG" ]; then
  # Development requirements
  sudo apt install tk-dev
  pip install matplotlib
fi

popd
exit $RETVAL