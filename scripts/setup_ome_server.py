#!/usr/bin/env python3
"""Setup helper for the WiFi Silent Disco OvenMediaEngine stack."""
from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"
ENV_TEMPLATE_PATH = REPO_ROOT / ".env.example"

REQUIRED_COMMANDS = {
    "docker": "Docker is required to run OvenMediaEngine. Install Docker Desktop (Windows/macOS) or Docker Engine (Linux) and rerun this script.",
    "docker compose": "Docker Compose V2 is required. On Linux ensure you installed the docker-compose-plugin package. On macOS/Windows it ships with Docker Desktop.",
}


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the completed process."""
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def docker_daemon_ready() -> bool:
    try:
        run(["docker", "info"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        return False
    except subprocess.CalledProcessError as exc:
        print("[!] Docker is installed but not running. Start Docker Desktop / Engine and ensure WSL integration is enabled if you are on Windows.")
        if exc.stdout:
            print(exc.stdout)
        return False
    return True


def command_available(command: str) -> bool:
    parts = command.split()
    if len(parts) == 1:
        return shutil.which(command) is not None
    primary = shutil.which(parts[0])
    if not primary:
        return False
    try:
        run(parts + ["--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Exception:
        return False
    return True


def ensure_requirements() -> None:
    missing = []
    for command, message in REQUIRED_COMMANDS.items():
        if not command_available(command):
            print(f"[!] {command} missing. {message}")
            missing.append(command)
    if missing:
        raise SystemExit("Install the missing dependencies listed above and re-run the setup.")
    if not docker_daemon_ready():
        raise SystemExit("Start Docker and re-run the setup once the daemon is ready.")


def detect_host_ip() -> str:
    """Best effort local network IP detection."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "127.0.0.1"


def load_env_template() -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not ENV_TEMPLATE_PATH.exists():
        raise FileNotFoundError("Missing .env.example template")
    with ENV_TEMPLATE_PATH.open("r", encoding="utf-8") as fp:
        for line in fp:
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.strip().split("=", 1)
            data[key] = value
    return data


def write_env_file(values: Dict[str, str]) -> None:
    with ENV_PATH.open("w", encoding="utf-8") as fp:
        for key, value in values.items():
            fp.write(f"{key}={value}\n")
    print(f"[✓] Wrote {ENV_PATH}")


def ensure_env_file(force: bool = False) -> Dict[str, str]:
    template = load_env_template()
    if ENV_PATH.exists() and not force:
        print("[i] Existing .env detected. Keeping current values.")
        current: Dict[str, str] = {}
        with ENV_PATH.open("r", encoding="utf-8") as fp:
            for line in fp:
                if "=" not in line:
                    continue
                key, value = line.strip().split("=", 1)
                current[key] = value
        refreshed = False
        if current.get("OME_HOST_IP", "").lower() in {"auto", ""}:
            current["OME_HOST_IP"] = detect_host_ip()
            refreshed = True
        for key, value in template.items():
            if key not in current:
                current[key] = value
                refreshed = True
        if refreshed:
            write_env_file(current)
        return current

    ip = detect_host_ip()
    template.setdefault("OME_HOST_IP", ip)
    if template.get("OME_HOST_IP", "").lower() in {"auto", ""}:
        template["OME_HOST_IP"] = ip
    write_env_file(template)
    return template


def pull_images() -> None:
    if not docker_daemon_ready():
        print("[!] Skipping image pull because Docker is not running. Start Docker and run the setup again or pull the image manually later.")
        return
    try:
        run(["docker", "pull", "airensoft/ovenmediaengine:latest"])
    except subprocess.CalledProcessError as exc:
        print("[!] Failed to pull OvenMediaEngine image. You can pull it manually later.")
        print(exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare the WiFi Silent Disco streaming stack")
    parser.add_argument("--force-env", action="store_true", help="Overwrite the existing .env file with defaults")
    parser.add_argument("--skip-pull", action="store_true", help="Skip pulling the Docker images")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_requirements()
    env_values = ensure_env_file(force=args.force_env)
    print("[✓] Environment values:")
    for key, value in env_values.items():
        print(f"    {key}={value}")
    compose_file = REPO_ROOT / "docker-compose.yml"
    if not compose_file.exists():
        raise SystemExit("docker-compose.yml is missing. Verify the repository clone.")
    if not args.skip_pull:
        pull_images()
    print("[✓] Setup complete. Run scripts/start_stream_server.py to start the stack.")


if __name__ == "__main__":
    main()
