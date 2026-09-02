# Forex Trading Setup (Linux, MT5 via Docker)

An end-to-end MetaTrader 5 trading environment that runs on your Linux PC and can be
managed both visually (web desktop + dashboard) and programmatically (REST API + AI engine).

## Architecture

```
┌─────────────── your PC (Linux) ───────────────────────────────┐
│                                                               │
│  Docker container (headless-mt5)                              │
│    ├─ MetaTrader 5 terminal (under Wine)                      │
│    ├─ FastAPI REST API  ──►  http://localhost:5001            │
│    └─ KasmVNC web desktop ─►  http://localhost:3000           │
│                                                               │
│  Python venv (.venv)                                          │
│    ├─ Streamlit dashboard ──►  http://localhost:8501          │
│    └─ Automated trading engine (app/engine)                   │
└───────────────────────────────────────────────────────────────┘
```

## Quick start

### 1. Start the MT5 container (first build takes ~10–15 min)

```bash
scripts/trade.sh up
scripts/trade.sh logs     # watch the install
```

### 2. One-time broker login (needed before anything trades)

1. Open `scripts/trade.sh desktop`  →  http://localhost:3000
2. Log in with the VNC credentials in `credentials/README.txt`.
3. Inside the desktop, launch MetaTrader 5 and log in with your broker
   demo account (login / password / server). This is saved on disk.

### 3. Launch the trading console

```bash
scripts/trade.sh dashboard   # http://localhost:8501
```

### 4. (Optional) Run the automated engine

```bash
scripts/trade.sh engine      # one scan cycle
```

## Access

| Thing                | URL / command                              |
|----------------------|--------------------------------------------|
| MT5 REST API docs    | http://localhost:5001/docs                 |
| MT5 web desktop      | http://localhost:3000                      |
| Trading dashboard    | http://localhost:8501 (after `trade.sh dashboard`) |
| Credentials          | `credentials/README.txt`                   |

## Important notes / risk

- **Demo first.** Connect a demo account and watch the engine operate before
  ever considering live capital.
- **No auth on the API.** The container binds ports to `127.0.0.1` only. Do not
  expose them publicly without adding authentication.
- Trading is risky. This tooling is for learning and automation; the included
  engine is intentionally conservative.

## Project layout

```
app/
  config.py            # shared settings (API base, magic number, symbols)
  client/mt5_client.py # typed Python wrapper around the MT5 REST API
  dashboard/app.py     # Streamlit trading console
  engine/engine.py     # automated, risk-managed strategy runner
headless-mt5/          # the Dockerised MT5 (from thanderoy/headless-mt5)
scripts/trade.sh       # workflow helpers
credentials/           # local access credentials (git-ignore)
```
