#!/bin/bash
echo "============================================"
echo "  Fantasy Cricket - Starting Servers"
echo "============================================"
echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo ""
echo "  Press Ctrl+C to stop both servers."
echo "============================================"
echo ""

# Start backend in background
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend in foreground
cd frontend && npx vite --host 0.0.0.0 --port 5173

# When frontend stops, also kill backend
kill $BACKEND_PID 2>/dev/null
