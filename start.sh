#!/bin/bash
echo "Starting DavidAPI with integrated keep-alive..."

# Install dependencies
pip install -r requirements.txt

# Start the main Flask app (keep-alive runs inside it)
python davidapi.py
