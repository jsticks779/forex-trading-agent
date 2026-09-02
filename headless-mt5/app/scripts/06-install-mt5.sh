#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "06-install-mt5.sh"

# Ensure an X display is available before any Wine GUI runs (MT5 installer
# and terminal both need a window server; on container boots this is started
# by the base image's S6 services which may not be up yet during cont-init).
export DISPLAY="${DISPLAY:-:0}"
log_message "INFO" "Waiting for X display ${DISPLAY}..."
for i in $(seq 1 120); do
    if [ -e "/tmp/.X11-unix/X${DISPLAY#:}" ] && xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
        log_message "INFO" "X display ${DISPLAY} is available."
        break
    fi
    sleep 2
done
if ! xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
    log_message "WARN" "X display never became available; starting a virtual framebuffer."
    if command -v Xvfb >/dev/null 2>&1; then
        Xvfb "$DISPLAY" -screen 0 1280x800x24 -nolisten tcp >/var/log/xvfb.log 2>&1 &
    else
        Xvnc "$DISPLAY" -geometry 1280x800 -depth 24 -SecurityTypes None -AlwaysShared \
            -interface 0.0.0.0 >/var/log/xvnc-fallback.log 2>&1 &
    fi
    sleep 3
fi

# Check if MetaTrader 5 is installed
if [ -e "$mt5file" ]; then
    log_message "INFO" "File $mt5file already exists."
else
    log_message "INFO" "File $mt5file is not installed. Installing..."

    # Set Windows 10 mode in Wine and download and install MT5
    $wine_executable reg add "HKEY_CURRENT_USER\\Software\\Wine" /v Version /t REG_SZ /d "win10" /f
    
    # Download MT5 with retry logic
    log_message "INFO" "Downloading MT5 installer..."
    MAX_RETRIES=3
    RETRY_COUNT=0
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if wget -O /tmp/mt5setup.exe $mt5setup_url 2>&1; then
            log_message "INFO" "MT5 installer downloaded successfully."
            break
        else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            log_message "WARN" "Download failed. Retry $RETRY_COUNT of $MAX_RETRIES..."
            sleep $((RETRY_COUNT * 5))
        fi
    done
    
    if [ ! -f /tmp/mt5setup.exe ]; then
        log_message "ERROR" "Failed to download MT5 installer after $MAX_RETRIES attempts."
        exit 1
    fi
    
    log_message "INFO" "Installing MetaTrader 5..."
    $wine_executable /tmp/mt5setup.exe /auto
    rm -f /tmp/mt5setup.exe
fi

# Recheck if MetaTrader 5 is installed
if [ -e "$mt5file" ]; then
    log_message "INFO" "File $mt5file is installed. Running MT5..."
    $wine_executable "$mt5file" &
else
    log_message "ERROR" "File $mt5file is not installed. MT5 cannot be run."
fi