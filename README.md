# WiFi Silent Disco

Create a fully synchronized silent disco in any local network. The stack uses [OvenMediaEngine](https://airensoft.gitbook.io/ovenmediaengine/) for ultra low latency ingest from OBS and serves a web-based player that keeps every guest in sync automatically.

## Features

- **One-click setup:** `scripts/setup_ome_server.py` validates dependencies, generates the `.env` file and pulls the required Docker images.
- **GUI control panel:** `scripts/start_stream_server.py` starts a desktop window with start/stop controls, port diagnostics and live OBS instructions.
- **OBS ready:** Default RTMP endpoint (`rtmp://<host>:1935/app`) and stream key (`stream`) work out of the box.
- **Guest portal:** `guest/index.html` hosts a low-latency HLS player that self-calibrates against the server clock, dynamically adjusting playback rate so every listener stays in sync.
- **Self-healing ports:** The GUI can scan for blocked ports and automatically choose alternatives, updating the `.env` file and the OBS instructions.

## Prerequisites

- Docker Engine / Docker Desktop with Compose v2 support
- Python 3.9+ with Tkinter (`python3-tk` on most Linux distros)

## 1. Setup

```bash
python3 scripts/setup_ome_server.py
```

The script will:

1. Verify that `docker` and `docker compose` are available.
2. Generate `.env` from `.env.example` (auto-detecting your LAN IP).
3. Pull the latest `airensoft/ovenmediaengine` container image.

If you change network interfaces later, re-run the script with `--force-env` to regenerate the `.env` file.

## 2. Start the server

```bash
python3 scripts/start_stream_server.py
```

The control panel provides:

- Buttons to start/stop the Docker stack.
- Real-time status for the OME container and the LL-HLS stream.
- A guest counter fed by the built-in static HTTP server (`http://<host>:8088`).
- Automatic OBS configuration text showing the current RTMP URL and stream key.
- A port analyzer that scans for conflicts (firewalls, other apps) and rewrites `.env` with available ports.

## 3. Stream from OBS

In OBS go to **Settings → Stream** and choose **Custom…**.

- **Server:** `rtmp://<server-ip>:<rtmp-port>/<app>` (defaults: `rtmp://<server-ip>:1935/app`)
- **Stream Key:** `<stream-name>` (default: `stream`)

Once you start streaming, the GUI will detect the LL-HLS manifest and mark the stream as live.

## 4. Guest experience

The start script launches a lightweight HTTP server that hosts the content under `guest/`.

1. Guests open `http://<server-ip>:<guest-http-port>` (default `8088`).
2. Enter the host IP if it differs from the page origin (e.g. when using HTTPS reverse proxies) and press **Connect**.
3. The page fetches `/api/time` to align its clock with the server, then plays the LL-HLS stream using `hls.js`.
4. Playback rate and seek adjustments keep the measured latency close to the shared target so every listener stays synchronized.

If you already run a web server you can deploy the files inside `guest/` separately; just proxy `/api/time` back to the Python control panel.

## Configuration

All tunables live in `.env`:

| Variable | Description |
| --- | --- |
| `OME_HOST_IP` | LAN IP advertised to OBS/guests. Detected automatically during setup. |
| `OME_RTMP_PORT` | Public RTMP ingest port for OBS. |
| `OME_LLHLS_PORT` | Port serving LL-HLS manifests and the WebRTC signalling endpoint. |
| `OME_WEBRTC_CANDIDATE_PORT_RANGE` | UDP range for WebRTC candidates. |
| `GUEST_HTTP_PORT` | Port used by the built-in static guest web server. |
| `OME_STREAM_APP` | OvenMediaEngine application name (default `app`). |
| `OME_STREAM_NAME` | Default stream key (default `stream`). |

Adjust the values and restart the server. The GUI will regenerate the OBS instructions automatically.

## Troubleshooting

- Run `python3 scripts/setup_ome_server.py --force-env` if your network interface changes.
- Use **Analyze Ports** in the GUI when Docker fails to start (firewalls or other software might be occupying the default ports).
- Delete `./.env` to revert to the defaults and rerun the setup script.
- Review Docker logs with `docker compose logs -f` from the repository root for advanced debugging.

## Project structure

```
.
├── docker-compose.yml        # OvenMediaEngine container orchestration
├── guest/                    # Public guest web application (LL-HLS player)
├── scripts/
│   ├── setup_ome_server.py   # Environment bootstrapper
│   └── start_stream_server.py# GUI control panel + guest web server
└── .env.example              # Default configuration template
```

Enjoy your wireless silent disco! 🎧
