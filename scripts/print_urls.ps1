function Get-LanIp {
    try {
        $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -notmatch '^127\.' -and $_.IPAddress -notmatch '^169\.254\.' } |
            Select-Object -ExpandProperty IPAddress
        if ($ips -and $ips.Count -gt 0) {
            return $ips[0]
        }
    } catch {
        # Ignore and try fallback
    }

    try {
        $ips = Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "IPEnabled = TRUE" |
            ForEach-Object { $_.IPAddress } |
            Where-Object { $_ -and $_ -notmatch ':' -and $_ -notmatch '^127\.' -and $_ -notmatch '^169\.254\.' }
        if ($ips -and $ips.Count -gt 0) {
            return $ips[0]
        }
    } catch {
        # Ignore and return loopback
    }

    return "127.0.0.1"
}

$HostIp = Get-LanIp

Write-Output "Detected LAN IP: $HostIp"
Write-Output ""
Write-Output "OBS RTMP Server: rtmp://$HostIp:1935/app"
Write-Output "OBS Stream Key: stream"
Write-Output "VLC (LL-HLS):   http://$HostIp:3333/app/stream/llhls.m3u8"
Write-Output "VLC (HLS-TS):   http://$HostIp:3333/app/stream/master.m3u8?format=ts"
Write-Output ""
Write-Output "docker compose up -d"
Write-Output "docker compose logs -f ovenmediaengine"
