#!/bin/sh

# Verify that essential dependencies are installed.
if [ ! -d /opt/python3 -o ! -x /opt/python3/bin/pip3 ]; then
  echo "ERROR: Please install Python 3 with pip Router App first."
  exit 1
fi
if [ ! -d /opt/libcairo2 ]; then
  echo "ERROR: Please install LibCairo2 Router App first."
  exit 1
fi
if [ ! -d /opt/cartoonify ]; then
  echo "WARNING: The Cartoonify Router App is not installed."
  echo "Only terminal interface will be available."
fi

# Incrementally gather Python dependencies.
#DIMENSION=640; while ! python3 ../run.py --min-inference-dimension $DIMENSION --max-inference-dimension $DIMENSION --fit-width 1280 --fit-height 1280; do PKG=$( tail -n1 `ls ../logs/*.log | tail -n1` | sed -e "/ModuleNotFoundError: No module named/!d" -e "s/.*'\(.*\)'/\\1/g" ); { [ -z "$PKG" ] && echo "Unknown error: $( cat `ls ../logs/*.log | tail -n1`)" && break; }; python3 -m pip install $PKG >/opt/python3/install_logs/$PKG.log 2>&1 || { echo "Error installing $PKG."; break; }; done

# Create virtual Python 3 environment inside the cartoonify repository.
#python -m virtualenv virtualenv
#source ./virtualenv/bin/activate
cd cartoonify
python3 -m pip install -r requirements_icr.txt
RETVAL=$?

# Development requirements
#sudo apt install tk-dev
#pip install matplotlib

cd ..
exit $RETVAL