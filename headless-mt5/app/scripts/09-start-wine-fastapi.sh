#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "09-start-wine-fastapi.sh"

log_message "INFO" "Starting FastAPI server in Wine environment..."

# Always launch the MT5 terminal here so it appears on the VNC desktop. On a
# fresh install a one-time broker login is done in that desktop; MT5 then saves
# the credentials into /config and auto-connects on later boots. The FastAPI app
# attaches to this running terminal in the background (it never spawns/login on
# its own, to avoid a conflicting terminal instance / IPC timeout).
$wine_executable "C:\Program Files\MetaTrader 5\terminal64.exe" &
sleep 2
$wine_executable python /app/main.py &

FASTAPI_PID=$!

# Give the server some time to start
sleep 5

# Check if the FastAPI server is running
if ps -p $FASTAPI_PID > /dev/null; then
    log_message "INFO" "FastAPI server in Wine started successfully with PID $FASTAPI_PID."
else
    log_message "ERROR" "Failed to start FastAPI server in Wine."
    exit 1
fi
