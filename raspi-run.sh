#!/usr/bin/env bash

# Enable job control so that all processes handle SIGINT and exit gracefully.
set -m

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

interrupt_handler(){
  kill -INT $pid 2> /dev/null
}

pid=
trap 'interrupt_handler' SIGINT

source ./virtualenv/bin/activate
cd cartoonify/images/
python3 ../run.py --raspi-headless --port 80 --max-inference-dimension $MAX_INFERENCE_DIMENSION --fit-width $MAX_OUTPUT_DIMENSTION --fit-height $MAX_OUTPUT_DIMENSTION --force-download --camera "$@" &
pid=$!
wait $pid
cd ..
deactivate