#!/bin/bash

# Install Python 3 essentials.
#python2.7 -m ensurepip --default-pip
#python2.7 -m pip install --upgrade pip setuptools wheel

# Create virtual Python 3 environment inside the cartoonify repository.
python -m virtualenv virtualenv
source ./virtualenv/bin/activate
pip install --upgrade pip setuptools
cd cartoonify
pip install -r requirements_desktop.txt

# Development requirements
sudo apt install tk-dev
pip install matplotlib

cd ..
