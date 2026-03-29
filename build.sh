#!/bin/bash
# Build script for deployment (Render, Railway, etc.)
set -e

echo "=== Installing backend dependencies ==="
pip install -r backend/requirements.txt

echo "=== Installing frontend dependencies ==="
cd frontend
npm install

echo "=== Building frontend ==="
npm run build
cd ..

echo "=== Seeding database ==="
python -m backend.scripts.seed_db

echo "=== Build complete ==="
