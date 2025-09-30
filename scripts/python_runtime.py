"""Shared helpers for ensuring the correct Python runtime is used."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = REPO_ROOT / ".venv"
REQUIRED_PYTHON: Tuple[int, int] = (3, 12)
ENV_OVERRIDE = "WIFI_SILENT_DISCO_PYTHON"


def venv_python_path() -> Path:
    """Return the expected path to the project virtual environment Python."""
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _candidate_commands() -> Iterable[List[str]]:
    required_major, required_minor = REQUIRED_PYTHON
    candidates: List[List[str]] = []

    override = os.environ.get(ENV_OVERRIDE)
    if override:
        candidates.append([override])

    venv_python = venv_python_path()
    if venv_python.exists():
        candidates.append([str(venv_python)])

    version_specific = [
        f"python{required_major}.{required_minor}",
        f"python{required_major}{required_minor}",
        f"python{required_major}",
        "python3",
        "python",
    ]
    for name in version_specific:
        path = shutil.which(name)
        if path:
            candidates.append([path])

    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher:
            candidates.append([launcher, f"-{required_major}.{required_minor}"])

    seen: set[Tuple[str, ...]] = set()
    for command in candidates:
        key = tuple(command)
        if key in seen:
            continue
        seen.add(key)
        yield command


def _probe_python_version(command: Sequence[str]) -> Tuple[int, int, int] | None:
    try:
        completed = subprocess.run(
            [*command, "-c", "import json, sys; print(json.dumps(sys.version_info[:3]))"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    output = (completed.stdout or "").strip().splitlines()
    if not output:
        return None
    try:
        major, minor, micro = json.loads(output[-1])
    except json.JSONDecodeError:
        return None
    return int(major), int(minor), int(micro)


def _command_matches_current(command: Sequence[str]) -> bool:
    if not command:
        return False
    if len(command) == 1:
        try:
            return Path(command[0]).resolve() == Path(sys.executable).resolve()
        except FileNotFoundError:
            return False
    return False


def ensure_required_python() -> None:
    """Ensure the script is running under the required Python version.

    If a matching interpreter is available but not currently being used the
    process is re-executed using that interpreter.
    """

    current_major, current_minor = sys.version_info[:2]
    if (current_major, current_minor) == REQUIRED_PYTHON:
        return

    required_major, required_minor = REQUIRED_PYTHON
    for command in _candidate_commands():
        version = _probe_python_version(command)
        if version and version[:2] == REQUIRED_PYTHON:
            if _command_matches_current(command):
                return
            display = " ".join(command)
            print(
                "Detected Python",
                f"{current_major}.{current_minor}. Restarting with required interpreter '{display}'...",
            )
            os.execvpe(command[0], [*command, *sys.argv], os.environ)

    raise SystemExit(
        "WiFi Silent Disco tooling requires Python "
        f"{required_major}.{required_minor}. Install it or set the {ENV_OVERRIDE} "
        "environment variable to point at a compatible interpreter."
    )
