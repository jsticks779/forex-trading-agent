#!/bin/bash

# Source common variables and functions
source /scripts/02-common.sh

log_message "INFO" "------------------------------------------------"
log_message "INFO" "Running installation scripts..."

# Optional dependencies - allow failures (Mono/Gecko are nice-to-have)
/scripts/03-install-mono.sh || log_message "WARN" "Mono installation failed, continuing..."
/scripts/04-install-gecko.sh || log_message "WARN" "Gecko installation failed, continuing..."
/scripts/05-install-winetricks.sh || log_message "WARN" "Winetricks setup failed, continuing..."

# Required scripts - fail if these don't work
set -e
/scripts/06-install-mt5.sh
/scripts/07-install-python.sh
/scripts/08-install-libraries.sh

# Fix KasmVNC web client landing page (iframe index.html -> vnc.html & pcm-player stub)
sed -i 's|vnc/index.html|vnc/vnc.html|g' /kclient/public/index.html 2>/dev/null || true
mkdir -p /kclient/public/js 2>/dev/null || true
cat << "EOF" > /kclient/public/js/pcm-player.js 2>/dev/null || true
function PCMPlayer() { this.destroy=function(){}; this.play=function(){}; this.pause=function(){}; this.feed=function(){}; }
EOF

# Start background watcher to auto-accept initial setup dialogs on display :0
(
  export DISPLAY=:0
  while true; do
    sleep 3
    xdotool search --onlyvisible "" key --delay 50 Return space 2>/dev/null || true
  done
) &

# Start FastAPI server inside Wine
/scripts/09-start-wine-fastapi.sh

# Streamlit dashboard is started by the supervised S6 service
# (root/etc/services.d/streamlit/run) so it runs alongside KasmVNC.

log_message "INFO" "------------------------------------------------"
log_message "INFO" "Container is ready."
