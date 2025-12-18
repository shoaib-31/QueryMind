#!/bin/bash

set -e

echo "Deploying Spike AI..."

if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed"
    exit 1
fi

if ! command -v pip3 &> /dev/null; then
    echo "Error: pip3 is not installed"
    exit 1
fi

if [ ! -f "credentials.json" ]; then
    echo "Warning: credentials.json not found - GA4 functionality will not work"
fi

if [ ! -f ".env" ]; then
    echo "Error: .env file not found. Please create it based on .env.example"
    exit 1
fi

echo "Installing dependencies..."
pip3 install -r requirements.txt

echo "Checking for existing processes on port 8080..."
if lsof -ti:8080 > /dev/null 2>&1; then
    echo "Stopping existing process..."
    kill $(lsof -ti:8080) 2>/dev/null || true
    sleep 2
fi

echo "Starting server..."
nohup python3 main.py > spike_ai.log 2>&1 &

SERVER_PID=$!
echo $SERVER_PID > spike_ai.pid

sleep 3

if ps -p $SERVER_PID > /dev/null; then
    echo ""
    echo "Spike AI is running"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "PID: $SERVER_PID"
    echo "API: http://localhost:8080"
    echo "Health: http://localhost:8080/health"
    echo "Logs: tail -f spike_ai.log"
    echo "Stop: kill \$(cat spike_ai.pid)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Deployment complete. Following logs..."
    echo ""
    tail -f spike_ai.log
else
    echo "Failed to start server. Check spike_ai.log:"
    cat spike_ai.log
    exit 1
fi

