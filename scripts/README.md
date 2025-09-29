# OvenMediaEngine helper script

`scripts/setup_ome_server.ps1` is a Windows PowerShell helper that sets up a local
OvenMediaEngine server using Docker Desktop. It performs prerequisite checks,
installs missing components, and offers a small GUI to start or stop the
container while showing connection details for OBS and VLC.

## Usage

```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
.\scripts\setup_ome_server.ps1
```

Run PowerShell as Administrator so the script can enable Windows features or
start Docker Desktop if needed.
