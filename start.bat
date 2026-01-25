@echo off
echo ========================================
echo Starting Multi-Agent System
echo ========================================
REM force clean up old processes
echo Cleaning up old processes...
taskkill /IM python.exe /F 2>nul
taskkill /IM blender.exe /F 2>nul
REM Kill processes using specific ports
echo Cleaning up ports...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8001') do taskkill /PID %%a /F 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8002') do taskkill /PID %%a /F 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8003') do taskkill /PID %%a /F 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8004') do taskkill /PID %%a /F 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8089') do taskkill /PID %%a /F 2>nul
timeout /t 5 /nobreak > nul

set BLENDER_PATH=D:\blender.exe
set PROJECT_ROOT=%cd%
set PYTHON_PATH=C:\Users\Jasper\miniconda3\python.exe

REM Start Blender Server in background (no window)
echo [1/6] Starting Blender Server (GUI mode - no console)...
start /B "" "%BLENDER_PATH%" --python "%PROJECT_ROOT%\blender_server.py" > nul 2>&1
echo Waiting for Blender server to start...
timeout /t 8 /nobreak > nul

REM Start all agents in background (no windows)
echo [2/6] Starting Execution Agent (background)...
cd /d "%PROJECT_ROOT%\agents\execution_agent"
start /B "" "%PYTHON_PATH%" -m uvicorn main:app --host 0.0.0.0 --port 8001 > nul 2>&1
cd /d "%PROJECT_ROOT%"
timeout /t 3 /nobreak > nul

echo [3/6] Starting Reviewing Agent (background)...
cd /d "%PROJECT_ROOT%\agents\reviewing_agent"
start /B "" "%PYTHON_PATH%" -m uvicorn main:app --host 0.0.0.0 --port 8002 > nul 2>&1
cd /d "%PROJECT_ROOT%"
timeout /t 3 /nobreak > nul

echo [4/6] Starting Scene Planning Agent (background)...
cd /d "%PROJECT_ROOT%\agents\scene_planning_agent"
start /B "" "%PYTHON_PATH%" -m uvicorn main:app --host 0.0.0.0 --port 8003 > nul 2>&1
cd /d "%PROJECT_ROOT%"
timeout /t 3 /nobreak > nul

echo [5/6] Starting Coding Agent (background)...
cd /d "%PROJECT_ROOT%\agents\coding_agent"
start /B "" "%PYTHON_PATH%" -m uvicorn main:app --host 0.0.0.0 --port 8004 > nul 2>&1
cd /d "%PROJECT_ROOT%"
timeout /t 3 /nobreak > nul

echo.
echo ========================================
echo All agents started in background!
echo Waiting for all services to be ready...
echo ========================================
timeout /t 5 /nobreak > nul

REM Start the Orchestrator with visible window
echo [6/6] Starting Orchestrator (with console)...
echo ========================================
echo SCENE GENERATION WILL START AUTOMATICALLY
echo ========================================
echo.
echo Running Orchestrator...
echo.
"%PYTHON_PATH%" Orchestrator.py

echo.
echo ========================================
echo Orchestrator finished. Stopping all services...
echo ========================================

echo.
echo ========================================
echo Orchestrator finished.
echo ========================================
echo still running...
echo press any key to exit.
pause