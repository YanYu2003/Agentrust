#!/bin/bash
# Start the Agentrust backend server

cd "$(dirname "$0")/.." || exit 1

echo "Starting Agentrust Backend Server..."
echo "=================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Please run setup.sh first."
    exit 1
fi

# Activate virtual environment and start server
source venv/bin/activate

# Start the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
