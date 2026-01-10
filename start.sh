#!/bin/bash

# Configure ngrok with auth token
ngrok config add-authtoken ${NGROK_AUTHTOKEN:-2wOMeC9CkWjnbjQa0bvC42cNLsR_617fw5AQqYQVpBdwpckkX}

# Start ngrok in the background with your reserved domain
ngrok http --url=seagull-winning-personally.ngrok-free.app 7860 &

# Wait a moment for ngrok to start
sleep 3

# Start the Python server in the background
python server.py &

# Wait a moment for Python server to start
sleep 2

# Start the npm frontend on port 7861
cd frontend
PORT=7861 npm start
