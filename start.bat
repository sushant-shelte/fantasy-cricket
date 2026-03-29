@echo off
echo ============================================
echo   Fantasy Cricket - Starting Servers
echo ============================================
echo.
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo.
echo   Press Ctrl+C in each window to stop.
echo ============================================
echo.

:: Start backend in a new window
start "Fantasy Cricket - Backend" cmd /k "cd /d %~dp0 && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000"

:: Wait a moment for backend to start
timeout /t 3 /nobreak >nul

:: Start frontend in a new window
start "Fantasy Cricket - Frontend" cmd /k "cd /d %~dp0\frontend && npx vite --host 0.0.0.0 --port 5173"

:: Wait and open browser
timeout /t 5 /nobreak >nul
start http://localhost:5173

echo Both servers started. Browser opening...
