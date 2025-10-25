#!/bin/bash
echo "Starting DavidAPI with keepalive system..."

# Install dependencies
pip install -r requirements.txt

# Start the keepalive script which will manage the Flask app
python keepalive.py
