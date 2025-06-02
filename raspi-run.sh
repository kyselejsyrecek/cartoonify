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

# Disable swapping to protect the storage from excessive usage and application from slowing down.
sudo swapoff -a

# Set power LED state
sudo sh -c "echo none > /sys/class/leds/power_led/trigger && echo 0 > /sys/class/leds/power_led/brightness"

source ./virtualenv/bin/activate
cd cartoonify/images/
python3 ../run.py --raspi-headless --max-inference-dimension $MAX_INFERENCE_DIMENSION --fit-width $MAX_OUTPUT_DIMENSTION --fit-height $MAX_OUTPUT_DIMENSTION --force-download --camera "$@"
cd ..
deactivate