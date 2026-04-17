#!/bin/bash
# Run the Agentrust Demo

cd "$(dirname "$0")/.." || exit 1

echo "Running Agentrust Demo..."
echo "========================"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Running setup first..."
    ./scripts/setup.sh
    echo ""
fi

# Activate virtual environment
source venv/bin/activate

# Run the demo
python scripts/demo.py
