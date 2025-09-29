# WiFi-SilentDisco

Silent Disco Solution via Wi-Fi on a local network. This repository now includes a one-click Windows helper that installs
prerequisites and manages an OvenMediaEngine (OME) Docker server. The initial goal is to validate the OBS → OME (RTMP) → VLC
(HLS/LL-HLS) pipeline on a LAN. Ultra-low-latency WebRTC playback and party-wide sync will be built on top of this foundation.

## Quick start on Windows 11

1. Open **PowerShell** as Administrator.
2. Allow script execution for the current process:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
   ```
3. Run the helper (from the repository root):
   ```powershell
   .\scripts\setup_ome_server.ps1
   ```
4. Follow on-screen guidance. The script will:
   - Verify and enable Windows Subsystem for Linux (WSL) features.
   - Download and install Docker Desktop if needed.
   - Launch a GUI to start/stop an OvenMediaEngine Docker container with smart port assignment.
   - Show the RTMP URL + stream key for OBS and the HLS/LL-HLS URLs for VLC.

### Streaming with OBS

- In OBS, go to **Settings → Stream** and choose **Custom** for the service.
- Copy the **Server URL** and **Stream Key** from the helper GUI into OBS.
- Start streaming.

### Playing in VLC

- On any device in the same network, open VLC → **Media → Open Network Stream**.
- Paste one of the playback URLs from the helper GUI (LL-HLS for lowest latency, standard HLS for compatibility).

## Troubleshooting tips

- If Windows requests a restart after enabling WSL features or installing Docker Desktop, reboot and run the script again.
- Ensure Docker Desktop shows as running before pressing **Start Server** in the GUI.
- When the container is active, the helper lists the ports in use so you can confirm they are not blocked by firewalls.

## Next steps

- Automate generation of a synchronized web client with WebRTC playback.
- Persist stream metadata so guests can join even if the host restarts the helper.
- Add observability (metrics, health checks) to monitor stream stability during events.
