#!/bin/bash

# Configure ngrok with auth token
ngrok config add-authtoken ${NGROK_AUTHTOKEN:-2wOMeC9CkWjnbjQa0bvC42cNLsR_617fw5AQqYQVpBdwpckkX}

# Start ngrok in the background with your reserved domain
ngrok http --url=seagull-winning-personally.ngrok-free.app 7860 &

# Wait a moment for ngrok to start
sleep 3

# Start the Python server in the background (it will serve the built React app)
python server.py &

# Keep container running
tail -f /dev/null
