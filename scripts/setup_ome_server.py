#!/usr/bin/env python3
"""Setup helper for the WiFi Silent Disco OvenMediaEngine stack."""
from __future__ import annotations

import argparse
import shlex
import shutil
import socket
import subprocess
import sys
import venv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from python_runtime import (
    REPO_ROOT,
    REQUIRED_PYTHON,
    VENV_DIR,
    ensure_required_python,
    venv_python_path,
)

ensure_required_python()

ENV_PATH = REPO_ROOT / ".env"
ENV_TEMPLATE_PATH = REPO_ROOT / ".env.example"
REQUIREMENTS_FILE = REPO_ROOT / "requirements.txt"

EXPECTED_MAJOR, EXPECTED_MINOR = REQUIRED_PYTHON

REQUIRED_COMMANDS = {
    "docker": "Docker is required to run OvenMediaEngine. Install Docker Desktop (Windows/macOS) or Docker Engine (Linux) and rerun this script.",
    "docker compose": "Docker Compose V2 is required. On Linux ensure you installed the docker-compose-plugin package. On macOS/Windows it ships with Docker Desktop.",
}

PYTHON_MODULE_REQUIREMENTS = {
    "tkinter": (
        "Tkinter is required for the GUI controller. On Windows rerun the official Python installer and enable the "
        '"tcl/tk and IDLE" optional feature. On Debian/Ubuntu install the python3-tk package.'
    ),
}


@dataclass
class SetupReport:
    """Collects actions, warnings, and errors to present at the end of the run."""

    actions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def add_action(self, message: str) -> None:
        self.actions.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def print_summary(self) -> None:
        print("\n===== Setup Summary =====")
        if self.actions:
            print("\nCompleted actions:")
            for line in self.actions:
                print(f"  • {line}")
        if self.warnings:
            print("\nWarnings:")
            for line in self.warnings:
                print(f"  • {line}")
        if self.errors:
            print("\nErrors:")
            for line in self.errors:
                print(f"  • {line}")
        if not any([self.actions, self.warnings, self.errors]):
            print("No changes were necessary.")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command and return the completed process."""
    print(f"$ {' '.join(shlex.quote(part) for part in cmd)}")
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def docker_daemon_ready(report: SetupReport) -> bool:
    try:
        run(["docker", "info"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        report.add_error(
            "Docker command not found. Install Docker Desktop (Windows/macOS) or Docker Engine (Linux) and rerun the setup."
        )
        return False
    except subprocess.CalledProcessError as exc:
        report.add_error(
            "Docker is installed but not running. Start Docker Desktop / Engine and ensure WSL integration is enabled on Windows."
        )
        if exc.stdout:
            print(exc.stdout)
        return False
    return True


def command_available(command: str, message: str, report: SetupReport) -> bool:
    parts = shlex.split(command)
    executable = shutil.which(parts[0])
    if not executable:
        report.add_error(message)
        return False
    try:
        subprocess.run(parts + ["--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as exc:
        report.add_error(
            f"{parts[0]} is installed but failed when checking the version. Output was:\n{exc.stdout or exc.stderr or 'No output provided.'}"
        )
        return False
    return True


def ensure_requirements(report: SetupReport) -> bool:
    all_present = True
    for command, message in REQUIRED_COMMANDS.items():
        if not command_available(command, message, report):
            all_present = False
    if not all_present:
        return False
    return docker_daemon_ready(report)


def check_python_version(report: SetupReport) -> bool:
    major, minor, micro = sys.version_info[:3]
    if major != EXPECTED_MAJOR or minor != EXPECTED_MINOR:
        report.add_error(
            "Unsupported Python version detected. "
            f"Found {major}.{minor}.{micro}. Install Python {EXPECTED_MAJOR}.{EXPECTED_MINOR} and rerun the setup."
        )
        return False
    report.add_action(f"Python version {major}.{minor}.{micro} is supported.")
    return True


def check_python_modules(report: SetupReport) -> None:
    for module, guidance in PYTHON_MODULE_REQUIREMENTS.items():
        try:
            __import__(module)
            report.add_action(f"Verified availability of Python module '{module}'.")
        except ImportError:
            report.add_error(f"Missing Python module '{module}'. {guidance}")


def _read_pyvenv_cfg(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    cfg_path = path / "pyvenv.cfg"
    if not cfg_path.exists():
        return data
    for line in cfg_path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip().lower()] = value.strip()
    return data


def ensure_virtualenv(report: SetupReport) -> Path | None:
    recreate = False
    if VENV_DIR.exists():
        cfg = _read_pyvenv_cfg(VENV_DIR)
        version = cfg.get("version")
        if version and not version.startswith(f"{EXPECTED_MAJOR}.{EXPECTED_MINOR}"):
            report.add_warning(
                "Existing virtual environment was created with a different Python version and will be recreated."
            )
            recreate = True
    if recreate and VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)
    if not VENV_DIR.exists():
        builder = venv.EnvBuilder(with_pip=True, clear=False)
        try:
            builder.create(VENV_DIR)
            report.add_action(f"Created Python virtual environment at {VENV_DIR}.")
        except Exception as exc:  # pragma: no cover - depends on host system
            report.add_error(f"Failed to create virtual environment: {exc}")
            return None
    else:
        report.add_action("Python virtual environment already exists.")
    python_exec = venv_python_path()
    if not python_exec.exists():
        report.add_error("Virtual environment python executable is missing. Try deleting the .venv folder and rerun the setup.")
        return None
    return python_exec


def install_python_dependencies(python_exec: Path | None, report: SetupReport) -> None:
    if python_exec is None:
        return
    try:
        run([str(python_exec), "-m", "pip", "install", "--upgrade", "pip"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        report.add_action("Upgraded pip inside the virtual environment.")
    except subprocess.CalledProcessError as exc:
        report.add_warning(
            "Unable to upgrade pip in the virtual environment. You can upgrade manually with 'python -m pip install --upgrade pip'."
        )
        print(exc.stdout or exc.stderr or "No pip output provided.")
    if not REQUIREMENTS_FILE.exists():
        report.add_warning("requirements.txt not found. Skipping Python package installation.")
        return
    try:
        run([str(python_exec), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)])
        report.add_action("Installed Python dependencies from requirements.txt.")
    except subprocess.CalledProcessError as exc:
        report.add_error(
            "Failed to install Python dependencies. Review the pip output above and resolve the issues before rerunning the setup."
        )
        print(exc.stdout or exc.stderr or "No pip output provided.")


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


def ensure_env_file(report: SetupReport, force: bool = False) -> Dict[str, str]:
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
            report.add_action("Refreshed .env with updated values.")
        return current

    ip = detect_host_ip()
    template.setdefault("OME_HOST_IP", ip)
    if template.get("OME_HOST_IP", "").lower() in {"auto", ""}:
        template["OME_HOST_IP"] = ip
    write_env_file(template)
    report.add_action("Created .env from template.")
    return template


def pull_images(report: SetupReport) -> None:
    try:
        run(["docker", "pull", "airensoft/ovenmediaengine:latest"])
        report.add_action("Ensured the OvenMediaEngine Docker image is up to date.")
    except subprocess.CalledProcessError as exc:
        report.add_warning(
            "Failed to pull OvenMediaEngine image automatically. You can retry later with 'docker pull airensoft/ovenmediaengine:latest'."
        )
        print(exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare the WiFi Silent Disco streaming stack")
    parser.add_argument("--force-env", action="store_true", help="Overwrite the existing .env file with defaults")
    parser.add_argument("--skip-pull", action="store_true", help="Skip pulling the Docker images")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = SetupReport()

    python_ok = check_python_version(report)
    check_python_modules(report)

    venv_python = None
    if python_ok:
        venv_python = ensure_virtualenv(report)
        install_python_dependencies(venv_python, report)
    else:
        report.add_warning(
            "Skipped virtual environment provisioning because the current Python version is not supported."
        )

    docker_ready = ensure_requirements(report)

    env_values: Dict[str, str] = {}
    try:
        env_values = ensure_env_file(report, force=args.force_env)
    except FileNotFoundError as exc:
        report.add_error(str(exc))

    if env_values:
        print("[✓] Environment values:")
        for key, value in env_values.items():
            print(f"    {key}={value}")

    compose_file = REPO_ROOT / "docker-compose.yml"
    if not compose_file.exists():
        report.add_error("docker-compose.yml is missing. Verify the repository clone.")

    if not args.skip_pull:
        if docker_ready:
            pull_images(report)
        else:
            report.add_warning(
                "Skipped pulling Docker images because Docker requirements were not satisfied."
            )

    report.print_summary()
    if report.errors:
        print("\nResolve the errors listed above and rerun the setup once addressed.")
    else:
        print("\nSetup complete. Run scripts/start_stream_server.py to start the stack.")

    try:
        input("\nPress Enter to close this window...")
    except EOFError:
        pass

    if report.errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
