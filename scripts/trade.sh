#!/usr/bin/env bash
# Forex trading workflow helpers.
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv/bin"

usage() {
    echo "Usage: $0 {up|down|logs|api|desktop|dashboard|engine|status|health}"
    echo
    echo "  up         Start the MT5 container (first build ~15min)"
    echo "  down       Stop the MT5 container"
    echo "  logs       Follow MT5 container logs"
    echo "  api        Open the MT5 REST API docs (Swagger)"
    echo "  desktop    Open the MT5 web desktop (VNC) for broker login"
    echo "  dashboard  Launch the Streamlit trading console"
    echo "  engine     Run the automated trading engine (once)"
    echo "  status     Show container + API status"
    echo "  health     Quick API health check"
    echo "  verify     End-to-end check (API, account, rates, engine)"
}

cmd_up() { (cd "$ROOT/headless-mt5" && docker compose up -d --build); }
cmd_down() { (cd "$ROOT/headless-mt5" && docker compose down); }
cmd_logs() { (cd "$ROOT/headless-mt5" && docker compose logs -f mt5); }
cmd_api() { (command -v xdg-open >/dev/null && xdg-open http://localhost:5001/docs) || echo "http://localhost:5001/docs"; }
cmd_desktop() { (command -v xdg-open >/dev/null && xdg-open http://localhost:3000) || echo "http://localhost:3000"; }
cmd_dashboard() { "$VENV/streamlit" run "$ROOT/app/dashboard/app.py"; }
cmd_engine() { "$VENV/python" -m app.engine.engine "$@"; }
cmd_status() { docker ps --filter name=mt5 --format '{{.Names}} {{.Status}}'; }
cmd_health() { curl -s http://localhost:5001/ || echo "API down"; }
cmd_verify() { "$VENV/python" "$ROOT/scripts/verify.py"; }

case "${1:-}" in
    up) cmd_up ;;
    down) cmd_down ;;
    logs) cmd_logs ;;
    api) cmd_api ;;
    desktop) cmd_desktop ;;
    dashboard) cmd_dashboard ;;
    engine) shift; cmd_engine "$@" ;;
    status) cmd_status ;;
    health) cmd_health ;;
    verify) cmd_verify ;;
    *) usage ;;
esac
