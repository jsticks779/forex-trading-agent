# Headless MT5

A Dockerised **HTTP wrapper around [MetaTrader 5](https://www.metatrader5.com/)**, running
under [Wine](https://www.winehq.org/) on Linux. The official `MetaTrader5` Python package is
Windows-only; this image runs the MT5 terminal and a Windows Python build inside a Wine
prefix, and exposes the library over a clean [FastAPI](https://fastapi.tiangolo.com/) REST
interface so you can drive MT5 from any Linux host, container, or language.

Largely built for healdess environments.

A [KasmVNC](https://github.com/linuxserver/docker-baseimage-kasmvnc) web desktop is bundled
for the one-time interactive broker login.

---

## How it works

```text
┌─────────────────────────── Docker container ───────────────────────────┐
│  linuxserver/baseimage-kasmvnc (Ubuntu Noble + KasmVNC web desktop)     │
│                                                                         │
│   Wine prefix (/config/.wine, win64)                                    │
│     ├── MetaTrader 5 terminal (terminal64.exe)                          │
│     └── Windows Python 3.12 + MetaTrader5 lib                           │
│             └── FastAPI app (app/main.py)  ──►  :5001  REST API         │
│                                                                         │
│   KasmVNC desktop  ──►  :3000  (broker login UI)                        │
└─────────────────────────────────────────────────────────────────────────┘
```

On first boot the s6 init script (`root/etc/cont-init.d/01-start`) runs the bootstrap
sequence in `app/scripts/` — `01-start.sh` chains them in order:

| Script | Does |
| --- | --- |
| `02-common.sh` | Shared vars (MT5 / Python download URLs, versions) and logging helpers |
| `03-install-mono.sh` | Installs Wine Mono (optional, best-effort) |
| `04-install-gecko.sh` | Installs Wine Gecko (optional, best-effort) |
| `05-install-winetricks.sh` | `vcrun2019`, `ucrtbase2019`, `corefonts`, win10 mode |
| `06-install-mt5.sh` | Downloads + silently installs the MT5 terminal |
| `07-install-python.sh` | Installs Windows Python 3.12 into the Wine prefix |
| `08-install-libraries.sh` | `pip install -r requirements.txt` (incl. `MetaTrader5`) in Wine |
| `09-start-wine-fastapi.sh` | Launches the FastAPI server via Wine's Python |

Everything is installed into the `/config` volume, so it persists across restarts —
**only the first boot is slow.**

---

## Quick start

Requirements: Docker + Docker Compose, an x86-64 Linux host, and a MetaTrader 5 broker
account (a demo account is fine).

```bash
cp .env.example .env        # set CUSTOM_USER / PASSWORD for the VNC desktop
docker compose up -d --build
docker compose logs -f mt5  # watch the first-boot install sequence (scripts 03 → 09)
```

**First boot takes ~10–15 minutes** while it downloads and installs the MT5 terminal and
Windows Python into the Wine prefix. The container's healthcheck has a 15-minute grace
period for this reason. Subsequent boots are fast.

Once it's up:

1. Open the **VNC desktop** at <http://localhost:3000> (log in with `CUSTOM_USER` /
   `PASSWORD` from your `.env`). Use the MetaTrader 5 window to log into your broker
   account **once** — the session is saved into the `/config` volume.
2. Open the **API docs** at <http://localhost:5001/docs> (interactive Swagger UI).
3. Drive MT5 over HTTP:

   ```bash
   # Connect the API to the running terminal
   curl -s -X POST http://localhost:5001/api/v1/connect

   # Account snapshot
   curl -s http://localhost:5001/api/v1/account
   ```

---

## API overview

Base path `/api/v1`. See **`/docs`** (Swagger) or **`/redoc`** for full request/response
schemas — the table below is just a map.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`  | `/` | Health / liveness check |
| `POST` | `/api/v1/connect` | Initialise the MT5 connection |
| `POST` | `/api/v1/disconnect` | Shut down the MT5 connection |
| `GET`  | `/api/v1/account` | Account info (balance, equity, margin, …) |
| `GET`  | `/api/v1/rates` | Historical OHLC bars (`copy_rates`) for a symbol/timeframe |
| `GET`  | `/api/v1/tick` | Latest tick for a symbol |
| `POST` | `/api/v1/order/send` | Place a market/pending order |
| `POST` | `/api/v1/order/modify` | Modify an order's SL/TP (ticket in body) |
| `POST` | `/api/v1/order/close` | Close a position (ticket in body) |
| `GET`  | `/api/v1/order/{ticket}` | Fetch a single order/position by ticket |
| `GET`  | `/api/v1/positions` | List open positions |
| `GET`  | `/api/v1/position/{ticket}` | Get one position |
| `POST` | `/api/v1/position/{ticket}/modify` | Modify a position's SL/TP |
| `POST` | `/api/v1/position/{ticket}/close` | Close a position |
| `GET`  | `/api/v1/deals` | Historical deals |

---

## ⚠️ Security

**This API has no built-in authentication.** It exposes full trading control — anyone who
can reach port 5001 can place and close orders on your account.

- The bundled `docker-compose.yml` binds the API and VNC ports to `127.0.0.1` only. **Do
  not** change that to `0.0.0.0` / a public interface without putting authentication in
  front of it.
- For remote access, run it behind a reverse proxy that enforces auth and TLS. A
  [Traefik](https://traefik.io/) basic-auth example:

  ```yaml
  # docker-compose.yml — on the mt5 service
  labels:
    traefik.enable: "true"
    traefik.http.routers.mt5-api.rule: "Host(`api.mt5.example.com`)"
    traefik.http.routers.mt5-api.entrypoints: "https"
    traefik.http.routers.mt5-api.tls.certresolver: "le"
    traefik.http.routers.mt5-api.middlewares: "mt5-api-auth"
    # Generate with: htpasswd -nB <user>  (escape $ as $$ in compose)
    traefik.http.middlewares.mt5-api-auth.basicauth.users: "<user>:<bcrypt-hash>"
    traefik.http.services.mt5-api.loadbalancer.server.port: "5001"
  ```

- Treat the VNC desktop the same way — it grants full GUI access to the terminal.

---

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `TZ` | `UTC` | Container timezone |
| `CUSTOM_USER` | `admin` | KasmVNC desktop username |
| `PASSWORD` | `changeme` | KasmVNC desktop password |

The FastAPI server listens on a fixed `0.0.0.0:5001` inside the container (hardcoded in
`app/main.py`); remap the host port in `docker-compose.yml` if needed. Pinned MT5 / Python
versions live in `app/scripts/02-common.sh`.

---

## Credits & license

- Base image: [linuxserver.io KasmVNC base image](https://github.com/linuxserver/docker-baseimage-kasmvnc).
- MetaTrader 5 and the `MetaTrader5` Python package are products of MetaQuotes.

Licensed under the **GNU General Public License v3.0** — see [`LICENSE`](./LICENSE).
