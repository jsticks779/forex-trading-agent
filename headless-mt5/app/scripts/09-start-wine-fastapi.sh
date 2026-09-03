#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "09-start-wine-fastapi.sh"

log_message "INFO" "Starting FastAPI server in Wine environment..."

export PYTHONUNBUFFERED=1

INI_PATH="/config/.wine/drive_c/mt5_startup.ini"
if [ -n "${MT5_LOGIN:-}" ]; then
    log_message "INFO" "Generating MT5 startup configuration file at $INI_PATH..."
    cat << EOF > "$INI_PATH"
[Common]
Login=${MT5_LOGIN}
Password=${MT5_PASSWORD}
Server=${MT5_SERVER}
AutoConfiguration=true
EnableDDE=true
EOF
    log_message "INFO" "Launching MT5 terminal with auto-login config..."
    $wine_executable "C:\Program Files\MetaTrader 5\terminal64.exe" "/config:C:\mt5_startup.ini" &
else
    log_message "INFO" "Launching MT5 terminal in Wine environment..."
    $wine_executable "C:\Program Files\MetaTrader 5\terminal64.exe" &
fi

(
  export DISPLAY=:0
  while true; do
    sleep 5
    xdotool search --class "terminal64.exe" key --delay 100 Escape || true
  done
) &

sleep 5
$wine_executable python -u /app/main.py &

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
