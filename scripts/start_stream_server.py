#!/usr/bin/env python3
"""Interactive controller for the WiFi Silent Disco streaming stack."""
from __future__ import annotations

import os
import sys
from pathlib import Path

EXPECTED_MAJOR = 3
EXPECTED_MINOR = 12

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = REPO_ROOT / ".venv"


def _venv_python_path() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def ensure_python_runtime() -> None:
    major, minor, micro = sys.version_info[:3]
    if (major, minor) == (EXPECTED_MAJOR, EXPECTED_MINOR):
        return

    venv_python = _venv_python_path()
    current_exec = Path(sys.executable).resolve()
    if venv_python.exists() and current_exec != venv_python.resolve():
        print(
            "Detected Python"
            f" {major}.{minor}.{micro}. Restarting with project interpreter {venv_python}..."
        )
        os.execv(str(venv_python), [str(venv_python), *sys.argv])

    raise SystemExit(
        "WiFi Silent Disco requires Python "
        f"{EXPECTED_MAJOR}.{EXPECTED_MINOR}. Detected {major}.{minor}.{micro}. "
        "Install the required version and rerun the script."
    )


ensure_python_runtime()

import json
import queue
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError:  # pragma: no cover - Tkinter is part of stdlib but optional on some distros
    raise SystemExit("Tkinter is required to run the start script. Install python3-tk or the platform equivalent.")

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

DOCKER_DAEMON_HINT = (
    "Docker Desktop/Engine does not appear to be running. Start Docker Desktop and ensure WSL 2 integration "
    "is enabled if you are on Windows."
)

ENV_PATH = REPO_ROOT / ".env"
GUEST_DIR = REPO_ROOT / "guest"
GUEST_DIR.mkdir(parents=True, exist_ok=True)

PORT_VARIABLES = {
    "OME_ORIGIN_PORT": "tcp",
    "OME_RTMP_PORT": "tcp",
    "OME_SRT_PORT": "udp",
    "OME_LLHLS_PORT": "tcp",
    "OME_LLHLS_TLS_PORT": "tcp",
    "OME_TURN_PORT": "tcp",
    "OME_WEBRTC_CANDIDATE_PORT_RANGE": "udp-range",
    "GUEST_HTTP_PORT": "tcp",
}

DEFAULT_TARGET_LATENCY = 2.0


@dataclass
class ComposeStatus:
    running: bool
    containers: int
    published_ports: Dict[str, str]


class EnvironmentManager:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.values: Dict[str, str] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            raise SystemExit("Missing .env file. Run scripts/setup_ome_server.py first.")
        with self.path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                self.values[key] = value

    def save(self) -> None:
        with self.path.open("w", encoding="utf-8") as fp:
            for key, value in self.values.items():
                fp.write(f"{key}={value}\n")

    def __getitem__(self, key: str) -> str:
        return self.values[key]

    def __setitem__(self, key: str, value: str) -> None:
        self.values[key] = value

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.values.get(key, default)


class GuestTrackerHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True):
        super().__init__(server_address, RequestHandlerClass, bind_and_activate)
        self.unique_clients: set[str] = set()
        self.last_ping = 0.0

    def register_client(self, ip: str) -> None:
        self.unique_clients.add(ip)
        self.last_ping = time.time()


class GuestRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: Optional[str] = None, **kwargs):
        super().__init__(*args, directory=str(GUEST_DIR), **kwargs)

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - match parent signature
        # Reduce noise in the GUI console. Logs still go to stderr.
        super().log_message(format, *args)

    def do_GET(self):  # noqa: N802 - API requirement
        if self.path.startswith("/api/time"):
            self.server.register_client(self.client_address[0])
            payload = json.dumps({
                "epoch": time.time(),
                "targetLatency": DEFAULT_TARGET_LATENCY,
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        return super().do_GET()


class BackgroundHTTPServer:
    def __init__(self, port: int) -> None:
        self.port = port
        self._thread: Optional[threading.Thread] = None
        self._server: Optional[GuestTrackerHTTPServer] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        server = GuestTrackerHTTPServer(("", self.port), GuestRequestHandler)
        self._server = server
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._thread = thread

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    @property
    def client_count(self) -> int:
        if self._server:
            return len(self._server.unique_clients)
        return 0

    @property
    def last_ping(self) -> float:
        if self._server:
            return self._server.last_ping
        return 0.0


def _docker_command_output(result: subprocess.CalledProcessError) -> str:
    output = result.stderr or ""
    if result.stdout:
        output = f"{output}\n{result.stdout}" if output else result.stdout
    return output.strip()


def ensure_docker_daemon() -> None:
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - depends on host setup
        raise RuntimeError("Docker is not installed or not available in PATH") from exc
    except subprocess.CalledProcessError as exc:
        output = _docker_command_output(exc)
        hint = DOCKER_DAEMON_HINT
        if output:
            hint = f"{hint}\n\nDocker reported:\n{output}"
        raise RuntimeError(hint) from exc


def run_compose_command(args: Iterable[str]) -> subprocess.CompletedProcess:
    ensure_docker_daemon()
    cmd = ["docker", "compose", *args]
    try:
        return subprocess.run(cmd, cwd=REPO_ROOT, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:  # pragma: no cover - depends on host setup
        raise RuntimeError("Docker Compose is not installed or not available in PATH") from exc


def get_compose_status() -> ComposeStatus:
    try:
        result = run_compose_command(["ps", "--format", "json"])
        services = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError, RuntimeError):
        return ComposeStatus(False, 0, {})
    running = any(service.get("State") == "running" for service in services)
    ports: Dict[str, str] = {}
    for service in services:
        svc_ports = service.get("Publishers", [])
        for item in svc_ports:
            target = item.get("TargetPort")
            published = item.get("PublishedPort")
            protocol = item.get("Protocol", "tcp")
            if target and published:
                ports[f"{target}/{protocol}"] = str(published)
    return ComposeStatus(running, len(services), ports)


def probe_tcp_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        try:
            sock.bind(("", port))
        except OSError:
            return False
    return True


def probe_udp_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.bind(("", port))
        except OSError:
            return False
    return True


def find_available_port(start_port: int, protocol: str) -> int:
    for offset in range(0, 50):
        candidate = start_port + offset
        available = probe_udp_port(candidate) if protocol == "udp" else probe_tcp_port(candidate)
        if available:
            return candidate
    raise RuntimeError(f"Unable to find available {protocol.upper()} port near {start_port}")


def resolve_ports(env: EnvironmentManager) -> Dict[str, str]:
    updated: Dict[str, str] = {}
    for key, proto in PORT_VARIABLES.items():
        value = env.get(key)
        if value is None:
            continue
        if proto == "udp-range":
            start, end = value.split("-", 1)
            start_port = int(start)
            end_port = int(end)
            new_start = find_available_port(start_port, "udp")
            if new_start == start_port:
                continue
            diff = new_start - start_port
            new_end = end_port + diff
            env[key] = f"{new_start}-{new_end}"
            updated[key] = env[key]
            continue
        port = int(value)
        available = probe_udp_port(port) if proto == "udp" else probe_tcp_port(port)
        if available:
            continue
        new_port = find_available_port(port, proto)
        env[key] = str(new_port)
        updated[key] = env[key]
    if updated:
        env.save()
    return updated


def check_stream_availability(env: EnvironmentManager) -> str:
    host = env["OME_HOST_IP"]
    port = env.get("OME_LLHLS_PORT", "3333")
    app = env.get("OME_STREAM_APP", "app")
    stream_name = env.get("OME_STREAM_NAME", "stream")
    url = f"http://{host}:{port}/{app}/{stream_name}/playlist.m3u8"
    try:
        with urlopen(url, timeout=2) as response:
            if response.status < 400:
                return "Live stream detected"
    except HTTPError as exc:
        if exc.code == 404:
            return "Waiting for OBS to publish"
        return f"HTTP {exc.code} from LL-HLS"
    except URLError:
        return "Stream endpoint unreachable"
    except Exception:
        return "Stream probe failed"
    return "Unknown stream state"


class StreamServerGUI:
    def __init__(self) -> None:
        self.env = EnvironmentManager(ENV_PATH)
        http_port = int(self.env.get("GUEST_HTTP_PORT", "8088"))
        self.http_server = BackgroundHTTPServer(http_port)
        self.status_queue: "queue.Queue[str]" = queue.Queue()

        self.root = tk.Tk()
        self.root.title("WiFi Silent Disco Server")
        self.root.geometry("640x520")

        self.server_status_var = tk.StringVar(value="Unknown")
        self.stream_status_var = tk.StringVar(value="Not checked")
        self.guest_count_var = tk.StringVar(value="0")
        self.instructions_var = tk.StringVar()
        self.log_text: Optional[tk.Text] = None

        self._build_layout()
        self._update_instructions()
        self.refresh_status()
        self.http_server.start()
        self._poll_status_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    def _build_layout(self) -> None:
        heading = tk.Label(self.root, text="WiFi Silent Disco", font=("Helvetica", 18, "bold"))
        heading.pack(pady=10)

        status_frame = tk.Frame(self.root)
        status_frame.pack(fill="x", padx=20)

        tk.Label(status_frame, text="Server status:", anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(status_frame, textvariable=self.server_status_var, anchor="w", fg="#065f46").grid(row=0, column=1, sticky="w")

        tk.Label(status_frame, text="Stream status:", anchor="w").grid(row=1, column=0, sticky="w")
        tk.Label(status_frame, textvariable=self.stream_status_var, anchor="w", fg="#1d4ed8").grid(row=1, column=1, sticky="w")

        tk.Label(status_frame, text="Guest clients:", anchor="w").grid(row=2, column=0, sticky="w")
        tk.Label(status_frame, textvariable=self.guest_count_var, anchor="w", fg="#7c3aed").grid(row=2, column=1, sticky="w")

        button_frame = tk.Frame(self.root)
        button_frame.pack(fill="x", pady=10)

        tk.Button(button_frame, text="Start Server", command=self.start_server, bg="#22c55e").pack(side="left", padx=10)
        tk.Button(button_frame, text="Stop Server", command=self.stop_server, bg="#ef4444").pack(side="left", padx=10)
        tk.Button(button_frame, text="Refresh", command=self.refresh_status).pack(side="left", padx=10)
        tk.Button(button_frame, text="Analyze Ports", command=self.auto_resolve_ports).pack(side="left", padx=10)

        info_frame = tk.LabelFrame(self.root, text="OBS Configuration", padx=10, pady=10)
        info_frame.pack(fill="x", padx=20, pady=5)
        tk.Label(info_frame, textvariable=self.instructions_var, justify="left", anchor="w").pack(fill="x")

        log_frame = tk.LabelFrame(self.root, text="Logs", padx=10, pady=10)
        log_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.log_text = tk.Text(log_frame, height=10, state="disabled")
        self.log_text.pack(fill="both", expand=True)

    def _update_instructions(self) -> None:
        host = self.env.get("OME_HOST_IP", "localhost")
        rtmp_port = self.env.get("OME_RTMP_PORT", "1935")
        app = self.env.get("OME_STREAM_APP", "app")
        stream_name = self.env.get("OME_STREAM_NAME", "stream")
        url = f"rtmp://{host}:{rtmp_port}/{app}"
        self.instructions_var.set(
            f"1. In OBS go to Settings → Stream.\n"
            f"2. Set Service to 'Custom...'.\n"
            f"3. Server URL: {url}\n"
            f"4. Stream Key: {stream_name}\n"
            f"Guests can open http://{host}:{self.env.get('GUEST_HTTP_PORT', '8088')} to join."
        )

    def _append_log(self, message: str) -> None:
        if not self.log_text:
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def start_server(self) -> None:
        try:
            result = run_compose_command(["up", "-d"])
            self.status_queue.put(result.stdout)
        except RuntimeError as exc:
            messagebox.showerror("Docker Compose", str(exc))
            self.status_queue.put(str(exc))
        except subprocess.CalledProcessError as exc:
            messagebox.showerror("Docker Compose", exc.stderr or str(exc))
            self.status_queue.put(exc.stderr or exc.stdout or str(exc))
        self.refresh_status()

    def stop_server(self) -> None:
        try:
            result = run_compose_command(["down"])
            self.status_queue.put(result.stdout)
        except RuntimeError as exc:
            messagebox.showerror("Docker Compose", str(exc))
            self.status_queue.put(str(exc))
        except subprocess.CalledProcessError as exc:
            messagebox.showerror("Docker Compose", exc.stderr or str(exc))
            self.status_queue.put(exc.stderr or exc.stdout or str(exc))
        self.refresh_status()

    def refresh_status(self) -> None:
        status = get_compose_status()
        self.server_status_var.set("Running" if status.running else "Stopped")
        stream_state = check_stream_availability(self.env)
        self.stream_status_var.set(stream_state)
        if not status.running:
            self.server_status_var.set("Stopped")
        guests = self.http_server.client_count
        if guests:
            elapsed = time.time() - self.http_server.last_ping
            if elapsed < 60:
                self.guest_count_var.set(f"{guests} active")
            else:
                self.guest_count_var.set(f"{guests} (idle)")
        else:
            self.guest_count_var.set("0")
        self._update_instructions()

    def auto_resolve_ports(self) -> None:
        updated = resolve_ports(self.env)
        if updated:
            message = "Updated ports:\n" + "\n".join(f"  {k}={v}" for k, v in updated.items())
            self.status_queue.put(message)
            messagebox.showinfo("Port Analyzer", message)
            self._update_instructions()
        else:
            messagebox.showinfo("Port Analyzer", "All configured ports are currently available.")

    def _poll_status_queue(self) -> None:
        try:
            while True:
                message = self.status_queue.get_nowait()
                for line in message.splitlines():
                    if line.strip():
                        self._append_log(line)
        except queue.Empty:
            pass
        self.root.after(500, self._poll_status_queue)

    def on_close(self) -> None:
        self.http_server.stop()
        self.root.destroy()


def main() -> None:
    StreamServerGUI()


if __name__ == "__main__":
    main()
