#!/bin/bash

echo "🔄 Restarting Hummingbird server..."

# Find and kill existing server process
SERVER_PID=$(ps aux | grep "python.*server.py" | grep -v grep | awk '{print $2}')

if [ ! -z "$SERVER_PID" ]; then
    echo "📍 Found server running with PID: $SERVER_PID"
    echo "🛑 Stopping server..."
    kill $SERVER_PID
    sleep 2
    
    # Force kill if still running
    if ps -p $SERVER_PID > /dev/null; then
        echo "⚠️  Force killing server..."
        kill -9 $SERVER_PID
    fi
    echo "✅ Server stopped"
else
    echo "ℹ️  No server process found"
fi

echo "🚀 Starting server with new code..."
nohup python server.py > server.log 2>&1 &
NEW_PID=$!

sleep 2

if ps -p $NEW_PID > /dev/null; then
    echo "✅ Server started successfully with PID: $NEW_PID"
    echo "📋 Checking logs..."
    tail -20 server.log
else
    echo "❌ Server failed to start. Check server.log for errors"
    tail -50 server.log
fi
