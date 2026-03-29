#!/bin/bash
echo "============================================"
echo "  Fantasy Cricket - Setup"
echo "============================================"
echo ""

echo "[1/3] Installing backend dependencies..."
pip install -r backend/requirements.txt || { echo "FAILED: pip install"; exit 1; }
echo ""

echo "[2/3] Installing frontend dependencies..."
cd frontend && npm install || { echo "FAILED: npm install"; exit 1; }
cd ..
echo ""

echo "[3/3] Seeding database..."
python -m backend.scripts.seed_db || { echo "FAILED: seed_db"; exit 1; }
echo ""

echo "============================================"
echo "  Setup complete!"
echo "  Run './start.sh' to launch the app."
echo "============================================"
