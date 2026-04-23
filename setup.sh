#!/usr/bin/env bash
# One-time project setup
set -e

echo "Setting up LLM Trader..."

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip -q
pip install -r requirements.txt -q

if [ ! -f credentials.json ]; then
    cp credentials.json.example credentials.json
    echo ""
    echo "credentials.json created. Fill in your Alpaca Paper Trading keys:"
    echo "  https://app.alpaca.markets/paper/dashboard/overview"
    echo ""
fi

mkdir -p logs

echo "Done! Next steps:"
echo "  1. Edit credentials.json with your API keys"
echo "  2. source .venv/bin/activate"
echo "  3. python main.py status"
