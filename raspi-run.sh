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

source ./virtualenv/bin/activate
cd cartoonify/images/
python3 ../run.py --raspi-headless --web-server --port 80 --max-inference-dimension $MAX_INFERENCE_DIMENSION --fit-width $MAX_OUTPUT_DIMENSTION --fit-height $MAX_OUTPUT_DIMENSTION --force-download --camera --rotate-180deg --volume 0.5 "$@"
EXIT_CODE=$?
cd ..
deactivate
exit $EXIT_CODE