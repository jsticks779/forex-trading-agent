#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "09-start-wine-fastapi.sh"

log_message "INFO" "Starting FastAPI server in Wine environment..."

# When broker credentials are provided via env (MT5_LOGIN), we let the FastAPI
# app's startup auto-connect own the terminal (mt5.initialize(login, ...)) so it
# launches and logs in a single terminal instance. Pre-launching terminal64.exe
# here too would spawn a second, conflicting instance and cause an IPC timeout.
if [ -z "${MT5_LOGIN:-}" ]; then
    log_message "INFO" "No MT5_LOGIN provided; launching terminal64.exe for manual/GUI login."
    $wine_executable "C:\Program Files\MetaTrader 5\terminal64.exe" &
else
    log_message "INFO" "MT5_LOGIN provided; letting FastAPI startup auto-connect own the terminal."
fi
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
