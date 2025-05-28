#!/usr/bin/env bash

MAX_INFERENCE_DIMENSION=640
MAX_OUTPUT_DIMENSTION=1280

# Legacy Docker execution
#sudo docker run -d \
# --mount type=bind,source=$(pwd)/cartoonify,target=/cartoonify \
# --restart unless-stopped \
# --device=/dev/ttyS0 \
# --device /dev/mem:/dev/mem \
# --device=/dev/serial0 \
# --privileged \
# -p 8081:8081 \
# -p 8082:8082 \
# -w /cartoonify \
# cartoonify

# Initialize thermal printer.
pushd zj-58
sudo lpadmin -p ZJ-58 -E -v serial:/dev/ttyS0?baud=9600 -m zjiang/ZJ-58.ppd
sudo lpoptions -d ZJ-58
popd

# Initialize GPIOs.
# We need to set drive strength here since Python package RPi.GPIO does not provide that functionality.
# Python package pigpio is able to do that.
sudo gpio drive 0 7 # group 0 is GPIO 0..27, 7 is 16mA (max) # FIXME Is sudo required?
#sudo gpio mode 0 OUT # TODO Set all remaining GPIOs.

source ./virtualenv/bin/activate
pushd cartoonify/images/
python3 ../run.py --raspi-headless --max-inference-dimension $MAX_INFERENCE_DIMENSION --fit-width $MAX_OUTPUT_DIMENSTION --fit-height $MAX_OUTPUT_DIMENSTION --force-download --camera "$@"
popd
deactivate