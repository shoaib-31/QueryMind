#!/bin/bash

set -e

echo "Deploying QueryMind..."

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
nohup python3 main.py > querymind.log 2>&1 &

SERVER_PID=$!
echo $SERVER_PID > querymind.pid

sleep 3

if ps -p $SERVER_PID > /dev/null; then
    echo ""
    echo "QueryMind is running"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "PID: $SERVER_PID"
    echo "API: http://localhost:8080"
    echo "Health: http://localhost:8080/health"
    echo "Logs: tail -f querymind.log"
    echo "Stop: kill \$(cat querymind.pid)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Deployment complete. Following logs..."
    echo ""
    tail -f querymind.log
else
    echo "Failed to start server. Check querymind.log:"
    cat querymind.log
    exit 1
fi

