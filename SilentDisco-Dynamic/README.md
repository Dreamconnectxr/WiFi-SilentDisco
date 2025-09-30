# SilentDisco-Dynamic

SilentDisco-Dynamic is a configurable OvenMediaEngine alternative built with Docker and nginx-rtmp that enables streaming live
sets from OBS (or any RTMP client) to a browser based HLS player.

The project focuses on resiliency and customisation:

- **No more crashing container** – the nginx configuration is generated automatically with the required directories so the Docker
  service stays running.
- **Configurable defaults** – you can change ports, stream keys, or even the output directories without touching the source
  files.
- **Self-service tooling** – the `manage.py` helper wraps common Docker commands and guarantees that configuration is rendered
  correctly before containers start.

## Requirements

- Docker Engine with the new `docker compose` plugin or the legacy `docker-compose` binary.
- Python 3.9 or newer for running the helper script.

## Quick start

```bash
cd SilentDisco-Dynamic
python manage.py start
```

The start command now walks you through an interactive setup:

1. You'll be prompted for the stream name (RTMP application) and stream key.
2. The helper automatically detects a suitable LAN IP address and picks free RTMP/HLS ports.
3. nginx configuration, Docker environment variables, and the web player metadata are rendered before the stack launches.

When Docker reports that the services are up, the CLI prints the ingest URL, the stream key, the audience player URL, and the direct HLS playlist so you always know where to point OBS and your guests.

## Changing settings

Use the `--set` flag to override a value and persist it for future runs:

```bash
python manage.py configure --set stream_key=mySuperSecret --set public_host=192.168.1.25
```

Run `python manage.py render` to regenerate configuration files without starting Docker. This is helpful when running on a
machine where Docker is not available (e.g. CI) or when you want to prepare configs in advance.

Available keys are:

| Key                  | Description                                         | Default |
| -------------------- | --------------------------------------------------- | ------- |
| `container_name`     | Name of the Docker container                        | `silentdisco_media` |
| `application_name`   | RTMP application name (also part of playback URL)   | `live` |
| `stream_key`         | Default stream name used by OBS and player          | `party` |
| `public_host`        | Hostname or IP embedded in the URLs                 | `localhost` |
| `rtmp_port`          | Host port for RTMP ingestion (auto-detected if busy) | `1935` |
| `http_port`          | Host port for the player/HLS output (auto-detected)  | `8080` |
| `hls_fragment`       | Segment length in seconds                           | `2.0` |
| `hls_playlist_length`| Playlist window in seconds                          | `10` |
| `hls_output_dir`     | Directory for generated HLS segments                | `data/hls` |
| `web_root`           | Directory served as the player website              | `web` |

## Troubleshooting

- If Docker is missing the script will exit with a helpful error message instead of failing silently.
- The media container exposes a health check (`nginx -t`) so configuration errors are visible via `docker compose ps`.
- Player configuration is written to `web/config.js`. Delete that file if you want to regenerate it manually.

## Stop and status

```bash
python manage.py status
python manage.py stop
```

Stopping the stack leaves the configuration files in place so future `start` commands can resume quickly.
