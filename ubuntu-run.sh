#!/bin/bash

source ./virtualenv/bin/activate
cd cartoonify/images/
python ../run.py "$@"
cd ..