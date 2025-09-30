#!/usr/bin/env python3
"""Utility CLI for configuring and operating the Silent Disco streaming stack."""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from string import Template
from typing import Dict, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "defaults.json"
USER_CONFIG_PATH = CONFIG_DIR / "user_config.json"
GENERATED_DIR = CONFIG_DIR / "generated"
GENERATED_DIR.mkdir(exist_ok=True)

COMPOSE_FILE = PROJECT_ROOT / "compose.yaml"
ENV_FILE = PROJECT_ROOT / ".env"
NGINX_TEMPLATE_PATH = CONFIG_DIR / "nginx.conf.template"
NGINX_CONFIG_PATH = GENERATED_DIR / "nginx.conf"

CONFIG_SCHEMA = {
    "container_name": str,
    "application_name": str,
    "stream_key": str,
    "public_host": str,
    "rtmp_port": int,
    "http_port": int,
    "hls_fragment": float,
    "hls_playlist_length": int,
    "hls_output_dir": str,
    "web_root": str,
}


class ConfigurationError(RuntimeError):
    """Raised when configuration is invalid."""


def load_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def merge_config(base: Dict[str, object], overrides: Dict[str, object]) -> Dict[str, object]:
    merged = dict(base)
    merged.update(overrides)
    return merged


def parse_overrides(pairs: Iterable[str]) -> Dict[str, object]:
    parsed: Dict[str, object] = {}
    for item in pairs:
        if "=" not in item:
            raise ConfigurationError(f"Invalid --set value '{item}'. Expected key=value format.")
        key, raw_value = item.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if key not in CONFIG_SCHEMA:
            raise ConfigurationError(f"Unknown configuration key: {key}")
        cast = CONFIG_SCHEMA[key]
        try:
            if cast is bool:
                value = raw_value.lower() in {"1", "true", "yes", "on"}
            else:
                value = cast(raw_value)
        except ValueError as exc:
            raise ConfigurationError(f"Invalid value for {key}: {raw_value}") from exc
        parsed[key] = value
    return parsed


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def ensure_directories(config: Dict[str, object]) -> Dict[str, Path]:
    hls_path = resolve_path(str(config["hls_output_dir"]))
    web_root = resolve_path(str(config["web_root"]))

    hls_path.mkdir(parents=True, exist_ok=True)
    web_root.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    return {"hls_path": hls_path, "web_root": web_root}


def project_relative(path: Path) -> str:
    """Represent ``path`` relative to the project root when possible."""

    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def render_nginx_config(config: Dict[str, object]) -> None:
    template = Template(NGINX_TEMPLATE_PATH.read_text(encoding="utf-8"))
    rendered = template.safe_substitute({
        "http_port": config["http_port"],
        "rtmp_port": config["rtmp_port"],
        "application_name": config["application_name"],
        "hls_fragment": config["hls_fragment"],
        "hls_playlist_length": config["hls_playlist_length"],
    })
    NGINX_CONFIG_PATH.write_text(rendered, encoding="utf-8")


def write_env_file(config: Dict[str, object], paths: Dict[str, Path]) -> None:
    env_values = {
        "CONTAINER_NAME": str(config["container_name"]),
        "RTMP_PORT": str(config["rtmp_port"]),
        "HTTP_PORT": str(config["http_port"]),
        "NGINX_CONFIG": project_relative(NGINX_CONFIG_PATH),
        "HLS_OUTPUT_DIR": project_relative(paths["hls_path"]),
        "WEB_ROOT": project_relative(paths["web_root"]),
    }
    lines = [f"{key}={value}" for key, value in env_values.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_player_config(config: Dict[str, object], paths: Dict[str, Path]) -> None:
    endpoints = build_stream_endpoints(config)
    payload = {
        "rtmpUrl": endpoints["rtmp"],
        "streamKey": config["stream_key"],
        "playbackUrl": endpoints["playback"],
    }
    player_config_path = paths["web_root"] / "config.js"
    player_config_path.write_text(
        "window.SILENT_DISCO_CONFIG = " + json.dumps(payload, indent=2) + ";\n",
        encoding="utf-8",
    )


def ensure_compose_command() -> List[str]:
    if shutil.which("docker"):
        return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    raise ConfigurationError(
        "Docker Compose not found. Install Docker Desktop or docker-compose before continuing."
    )


def run_compose(subcommand: List[str]) -> subprocess.CompletedProcess:
    command = ensure_compose_command() + subcommand
    try:
        return subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    except FileNotFoundError as exc:
        raise ConfigurationError("Docker executable not found.") from exc
    except subprocess.CalledProcessError as exc:
        raise ConfigurationError(
            f"Docker Compose command failed with exit code {exc.returncode}."
        ) from exc


def build_stream_endpoints(config: Dict[str, object]) -> Dict[str, str]:
    playback_url = (
        f"http://{config['public_host']}:{config['http_port']}/hls/{config['application_name']}/{config['stream_key']}.m3u8"
    )
    rtmp_url = f"rtmp://{config['public_host']}:{config['rtmp_port']}/{config['application_name']}"
    player_page = f"http://{config['public_host']}:{config['http_port']}/"
    return {"playback": playback_url, "rtmp": rtmp_url, "player": player_page}


def prompt_with_default(message: str, default: str) -> str:
    """Prompt the user for a value with a default fallback."""

    try:
        response = input(f"{message} [{default}]: ").strip()
    except EOFError:
        return default
    return response or default


def detect_host_ip() -> str:
    """Attempt to determine the primary IP address of this machine."""

    with contextlib.ExitStack() as stack:
        sock = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        except OSError:
            hostname_ip = ""
            with contextlib.suppress(OSError):
                hostname_ip = socket.gethostbyname(socket.gethostname())
            return hostname_ip or "127.0.0.1"


def port_available(port: int, host: str = "0.0.0.0") -> bool:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_available_port(preferred: int, *, exclude: Optional[Iterable[int]] = None) -> int:
    exclude_set = {preferred}
    if exclude:
        exclude_set.update(int(value) for value in exclude)

    if port_available(preferred):
        return preferred

    for candidate in range(1024, 65535):
        if candidate in exclude_set:
            continue
        if port_available(candidate):
            return candidate
    raise ConfigurationError("Unable to find an available network port.")


def prepare_runtime_configuration(
    config: Dict[str, object], *, interactive: bool
) -> Dict[str, object]:
    """Ensure the runtime configuration is interactive and collision-free."""

    updated = dict(config)
    if interactive and sys.stdin.isatty():
        print("\nSilent Disco setup")
        updated["application_name"] = prompt_with_default(
            "Stream name (used in the RTMP path)", str(config["application_name"])
        )
        updated["stream_key"] = prompt_with_default(
            "Stream key", str(config["stream_key"])
        )
    else:
        print(
            "Using configured stream name and key (non-interactive mode)."
        )

    ip_address = detect_host_ip()
    updated["public_host"] = ip_address

    updated["rtmp_port"] = find_available_port(int(updated["rtmp_port"]))
    updated["http_port"] = find_available_port(
        int(updated["http_port"]), exclude={updated["rtmp_port"]}
    )

    save_user_configuration(updated)
    return updated


def load_configuration() -> Dict[str, object]:
    defaults = load_json(DEFAULT_CONFIG_PATH)
    user = load_json(USER_CONFIG_PATH)
    return merge_config(defaults, user)


def save_user_configuration(config: Dict[str, object]) -> None:
    defaults = load_json(DEFAULT_CONFIG_PATH)
    overrides = {
        key: value
        for key, value in config.items()
        if defaults.get(key) != value
    }
    USER_CONFIG_PATH.write_text(json.dumps(overrides, indent=2) + "\n", encoding="utf-8")


def apply_overrides(config: Dict[str, object], overrides: Dict[str, object]) -> Dict[str, object]:
    if not overrides:
        return config
    updated = dict(config)
    updated.update(overrides)
    save_user_configuration(updated)
    return updated


def command_configure(args: argparse.Namespace) -> None:
    config = load_configuration()
    overrides = parse_overrides(args.set or [])
    updated = apply_overrides(config, overrides)
    print(json.dumps(updated, indent=2))


def command_render(args: argparse.Namespace) -> None:
    config = load_configuration()
    overrides = parse_overrides(args.set or [])
    config = apply_overrides(config, overrides)
    config = prepare_runtime_configuration(config, interactive=False)
    paths = ensure_directories(config)
    render_nginx_config(config)
    write_env_file(config, paths)
    write_player_config(config, paths)
    print("Configuration rendered successfully.")


def command_start(args: argparse.Namespace) -> None:
    config = load_configuration()
    overrides = parse_overrides(args.set or [])
    config = apply_overrides(config, overrides)
    config = prepare_runtime_configuration(config, interactive=True)
    paths = ensure_directories(config)
    render_nginx_config(config)
    write_env_file(config, paths)
    write_player_config(config, paths)
    print("Starting Silent Disco stack via Docker Compose…")
    run_compose(["up", "-d", "--remove-orphans"])
    endpoints = build_stream_endpoints(config)
    print("Silent Disco stack is running.")
    print()
    print("Streaming details:")
    print(f"  Stream URL: {endpoints['rtmp']}")
    print(f"  Stream Key: {config['stream_key']}")
    print(f"  Guest player page: {endpoints['player']}")
    print(f"  HLS playlist: {endpoints['playback']}")


def command_stop(args: argparse.Namespace) -> None:
    print("Stopping Silent Disco stack…")
    run_compose(["down"])
    print("Stack stopped.")


def command_status(args: argparse.Namespace) -> None:
    try:
        result = run_compose(["ps"])
    except ConfigurationError as exc:
        print(f"Status unavailable: {exc}")
        return
    if result.returncode == 0:
        print("Docker Compose status retrieved.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure = subparsers.add_parser("configure", help="Show and update configuration values")
    configure.add_argument(
        "--set",
        action="append",
        help="Override configuration key-value pairs (key=value).",
    )
    configure.set_defaults(func=command_configure)

    render = subparsers.add_parser("render", help="Render configuration files without starting Docker")
    render.add_argument("--set", action="append", help="Override configuration values temporarily.")
    render.set_defaults(func=command_render)

    start = subparsers.add_parser("start", help="Render configuration and start Docker services")
    start.add_argument("--set", action="append", help="Override configuration values before starting.")
    start.set_defaults(func=command_start)

    stop = subparsers.add_parser("stop", help="Stop Docker services")
    stop.set_defaults(func=command_stop)

    status = subparsers.add_parser("status", help="Show Docker Compose status")
    status.set_defaults(func=command_status)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
