#!/bin/sh

MAX_INFERENCE_DIMENSION=640
MAX_OUTPUT_DIMENSTION=1280

#source ./virtualenv/bin/activate
cd cartoonify/images/
python3 ../run.py --max-inference-dimension $MAX_INFERENCE_DIMENSION --fit-width $MAX_OUTPUT_DIMENSTION --fit-height $MAX_OUTPUT_DIMENSTION "$@"
cd ..
#deactivate