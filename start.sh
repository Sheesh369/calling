#!/bin/bash

# Start the Python server (ngrok is handled by docker-compose)
python server.py &

# Keep container running
tail -f /dev/null
