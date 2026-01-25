#!/bin/bash

echo "========================================"
echo "Starting Multi-Agent System"
echo "========================================"

# Function to kill process on port
kill_port() {
    local port=$1
    if command -v lsof >/dev/null 2>&1; then
        # macOS and most Linux distros
        local pid=$(lsof -ti:$port)
        if [ ! -z "$pid" ]; then
            kill -9 $pid 2>/dev/null
        fi
    elif command -v netstat >/dev/null 2>&1; then
        # Alternative for Linux
        local pid=$(netstat -tulpn 2>/dev/null | grep :$port | awk '{print $7}' | cut -d'/' -f1)
        if [ ! -z "$pid" ]; then
            kill -9 $pid 2>/dev/null
        fi
    fi
}

# Clean up old processes
echo "Cleaning up old processes..."
pkill -f "python.*uvicorn" 2>/dev/null
pkill -f "blender.*blender_server.py" 2>/dev/null

# Clean up ports
echo "Cleaning up ports..."
for port in 8001 8002 8003 8004 8089; do
    kill_port $port
done

# Wait for cleanup
sleep 5

# Set paths - adjust these for your system
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    BLENDER_PATH="/Applications/Blender.app/Contents/MacOS/Blender"
    PYTHON_PATH="python3"
else
    # Linux
    BLENDER_PATH="blender"
    PYTHON_PATH="python3"
fi

PROJECT_ROOT=$(pwd)

# Check if Blender exists
if ! command -v "$BLENDER_PATH" >/dev/null 2>&1; then
    echo "Error: Blender not found at $BLENDER_PATH"
    echo "Please update BLENDER_PATH in this script"
    exit 1
fi

# Start Blender Server in background
echo "[1/6] Starting Blender Server (GUI mode)..."
"$BLENDER_PATH" --python "$PROJECT_ROOT/blender_server.py" > /dev/null 2>&1 &
echo "Waiting for Blender server to start..."
sleep 8

# Start all agents in background with error logging
echo "[2/6] Starting Execution Agent (background)..."
cd "$PROJECT_ROOT/Agents/execution_agent"
$PYTHON_PATH -m uvicorn main:app --host 0.0.0.0 --port 8001 > /tmp/execution_agent.log 2>&1 &
cd "$PROJECT_ROOT"
sleep 3

echo "[3/6] Starting PR Review Agent (background)..."
cd "$PROJECT_ROOT/Agents/pr_review_agent"
$PYTHON_PATH -m uvicorn main:app --host 0.0.0.0 --port 8002 > /tmp/pr_review_agent.log 2>&1 &
cd "$PROJECT_ROOT"
sleep 3

echo "[4/6] Starting Scene Planning Agent (background)..."
cd "$PROJECT_ROOT/Agents/scene_planning_agent"
$PYTHON_PATH -m uvicorn main:app --host 0.0.0.0 --port 8003 > /tmp/scene_planning_agent.log 2>&1 &
cd "$PROJECT_ROOT"
sleep 3

echo "[5/6] Starting Coding Agent (background)..."
cd "$PROJECT_ROOT/Agents/coding_agent"
$PYTHON_PATH -m uvicorn main:app --host 0.0.0.0 --port 8004 > /tmp/coding_agent.log 2>&1 &
cd "$PROJECT_ROOT"
sleep 3

echo ""
echo "========================================"
echo "All agents started in background!"
echo "Waiting for all services to be ready..."
echo "========================================"

# Check if agents are actually running
echo "Checking agent status..."
for port in 8001 8002 8003 8004; do
    if lsof -i:$port > /dev/null 2>&1; then
        echo "✓ Agent on port $port is running"
    else
        echo "✗ Agent on port $port failed to start"
        echo "Check log at /tmp/*_agent.log for details"
    fi
done

sleep 5

# Start the Orchestrator
echo "[6/6] Starting Orchestrator (with console)..."
echo "========================================"
echo "SCENE GENERATION WILL START AUTOMATICALLY"
echo "========================================"
echo ""
echo "Running Orchestrator..."
echo ""
$PYTHON_PATH Orchestrator.py

echo ""
echo "========================================"
echo "Orchestrator finished."
echo "========================================"

# Function to cleanup on exit
cleanup() {
    echo "Stopping all services..."
    pkill -f "python.*uvicorn" 2>/dev/null
    pkill -f "blender.*blender_server.py" 2>/dev/null
    for port in 8001 8002 8003 8004 8089; do
        kill_port $port
    done
}

# Set trap to cleanup on script exit
trap cleanup EXIT

echo "Still running..."
echo "Press any key to exit."
read -n 1 -s