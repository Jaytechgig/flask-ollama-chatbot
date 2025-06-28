@echo off
echo ===============================================
echo 🚀 Starting Ollama...
echo ===============================================
start cmd /k ollama run my-chat

echo ===============================================
echo 🚀 Starting Flask API with Waitress...
echo ===============================================
start cmd /k venv\Scripts\python.exe run_waitress.py

echo ===============================================
echo 🚀 Starting Caddy reverse proxy...
echo ===============================================
cd /d C:\caddy
start cmd /k caddy_windows_amd64.exe run

echo ===============================================
echo ✅ All services started: Ollama + Waitress + Caddy
echo ===============================================
