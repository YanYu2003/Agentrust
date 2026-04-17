#!/bin/bash
# Setup script for Agentrust backend

cd "$(dirname "$0")/.." || exit 1

echo "Setting up Agentrust Backend..."
echo "==============================="
echo ""

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo ""
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt
echo ""

# Create data directory
mkdir -p data
echo "Data directory ready: data/"
echo ""

# Initialize database
echo "Initializing database..."
python scripts/init_db.py
echo ""

echo "==============================="
echo "Setup complete!"
echo ""
echo "To start the server:"
echo "  ./scripts/start_server.sh"
echo ""
echo "To run the demo:"
echo "  python scripts/demo.py"
