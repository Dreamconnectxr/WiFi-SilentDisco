<#
.SYNOPSIS
    One-click setup tool for OvenMediaEngine on Windows 11 with Docker.

.DESCRIPTION
    This script checks and installs prerequisites (WSL and Docker Desktop),
    then opens a simple GUI to start and stop an OvenMediaEngine Docker
    container. Ports are selected dynamically and the GUI displays OBS and VLC
    connection details.
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Log {
    param(
        [Parameter(Mandatory)][string]$Message,
        [switch]$IsError
    )

    $timestamp = (Get-Date).ToString('HH:mm:ss')
    $prefix = if ($IsError) { '[ERROR]' } else { '[INFO ]' }
    $line = "[$timestamp] $prefix $Message"
    Write-Host $line

    if ($script:UiControls -and $script:UiControls.LogBox) {
        $action = {
            param($box, $text)
            $box.AppendText($text + [Environment]::NewLine)
            $box.SelectionStart = $box.Text.Length
            $box.ScrollToCaret()
        }

        $logBox = $script:UiControls.LogBox
        if ($logBox.InvokeRequired) {
            $null = $logBox.BeginInvoke($action, $logBox, $line)
        }
        else {
            & $action $logBox $line
        }
    }
}

function Assert-Administrator {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
        Write-Log -Message 'Restarting this script with administrator privileges...'
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = 'powershell.exe'
        $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
        $psi.Verb = 'runas'
        try {
            [System.Diagnostics.Process]::Start($psi) | Out-Null
        }
        catch {
            Write-Log -Message 'Administrator elevation was cancelled.' -IsError
        }
        exit
    }
}

function Ensure-OptionalFeature {
    param(
        [Parameter(Mandatory)][string]$FeatureName,
        [Parameter(Mandatory)][string]$FriendlyName
    )

    $feature = Get-WindowsOptionalFeature -Online -FeatureName $FeatureName
    if ($feature.State -eq 'Enabled') {
        Write-Log -Message "$FriendlyName already enabled."
        return
    }

    Write-Log -Message "Enabling $FriendlyName..."
    $result = Enable-WindowsOptionalFeature -Online -FeatureName $FeatureName -All -NoRestart
    if ($result.RestartNeeded) {
        Write-Log -Message "$FriendlyName enabled. Please restart Windows and run this script again." -IsError
        Read-Host 'Press Enter to exit'
        exit
    }
    Write-Log -Message "$FriendlyName enabled."
}

function Ensure-WSL {
    Write-Log -Message 'Checking Windows Subsystem for Linux (WSL)...'
    Ensure-OptionalFeature -FeatureName 'Microsoft-Windows-Subsystem-Linux' -FriendlyName 'Windows Subsystem for Linux'
    Ensure-OptionalFeature -FeatureName 'VirtualMachinePlatform' -FriendlyName 'Virtual Machine Platform'

    try {
        $status = & wsl.exe --status 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Log -Message 'WSL is already configured.'
            return
        }
    }
    catch {
        # fall through to install
    }

    Write-Log -Message 'Installing WSL (this may take a few minutes)...'
    Start-Process -FilePath 'wsl.exe' -ArgumentList '--install','--no-distribution' -Verb runas -Wait
    Write-Log -Message 'WSL installation initiated. Please restart Windows to complete setup, then rerun this script.' -IsError
    Read-Host 'Press Enter to exit'
    exit
}

function Download-DockerDesktop {
    $uri = 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe'
    $destination = Join-Path -Path $env:TEMP -ChildPath 'DockerDesktopInstaller.exe'

    if (Test-Path $destination) {
        Write-Log -Message "Docker Desktop installer already downloaded at $destination"
        return $destination
    }

    Write-Log -Message 'Downloading Docker Desktop installer...'
    Invoke-WebRequest -Uri $uri -OutFile $destination
    Write-Log -Message 'Docker Desktop installer downloaded.'
    return $destination
}

function Ensure-DockerDesktop {
    Write-Log -Message 'Checking Docker Desktop...'
    $dockerCli = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerCli) {
        Write-Log -Message 'Docker CLI not found. Installing Docker Desktop...'
        $installer = Download-DockerDesktop
        Start-Process -FilePath $installer -ArgumentList 'install','--quiet' -Verb runas -Wait
        Write-Log -Message 'Docker Desktop installation completed. You may be prompted to log out; if so, please do and rerun the script.'
        $dockerCli = Get-Command docker -ErrorAction SilentlyContinue
        if (-not $dockerCli) {
            Write-Log -Message 'Docker CLI still not available. Please restart Windows and run the script again.' -IsError
            Read-Host 'Press Enter to exit'
            exit
        }
    }

    $dockerProcess = Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue
    if (-not $dockerProcess) {
        $dockerExePath = Join-Path -Path $env:ProgramFiles -ChildPath 'Docker\Docker\Docker Desktop.exe'
        if (-not (Test-Path $dockerExePath)) {
            Write-Log -Message 'Docker Desktop executable not found. Please ensure Docker Desktop is installed correctly.' -IsError
            Read-Host 'Press Enter to exit'
            exit
        }
        Write-Log -Message 'Starting Docker Desktop...'
        Start-Process -FilePath $dockerExePath | Out-Null
    }

    Write-Log -Message 'Waiting for Docker to become responsive...'
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        try {
            docker version --format '{{.Server.Version}}' | Out-Null
            Write-Log -Message 'Docker is ready.'
            break
        }
        catch {
            if ($stopwatch.Elapsed.TotalMinutes -ge 5) {
                Write-Log -Message 'Docker did not become ready within 5 minutes. Please check Docker Desktop manually.' -IsError
                Read-Host 'Press Enter to exit'
                exit
            }
            Start-Sleep -Seconds 5
        }
    }
}

function Get-FreeTcpPort {
    param([int[]]$Reserved = @())

    while ($true) {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
        $listener.Start()
        $port = ($listener.LocalEndpoint).Port
        $listener.Stop()
        if ($Reserved -notcontains $port) {
            return $port
        }
    }
}

function Get-FreeUdpPort {
    param([int[]]$Reserved = @())

    while ($true) {
        $client = [System.Net.Sockets.UdpClient]::new(0)
        $port = ($client.Client.LocalEndPoint).Port
        $client.Close()
        if ($Reserved -notcontains $port) {
            return $port
        }
    }
}

function Get-PrimaryIPv4 {
    $ip = Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -ne '127.0.0.1' } |
        Sort-Object InterfaceMetric |
        Select-Object -First 1

    if (-not $ip) {
        $ip = Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Manual -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -ne '127.0.0.1' } |
            Sort-Object InterfaceMetric |
            Select-Object -First 1
    }

    if ($ip) {
        return $ip.IPAddress
    }
    return '127.0.0.1'
}

function New-StreamKey {
    $chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
    $rng = New-Object System.Random
    $keyChars = for ($i = 0; $i -lt 12; $i++) { $chars[$rng.Next(0, $chars.Length)] }
    return -join $keyChars
}

$script:State = [ordered]@{
    ContainerName = 'ome_media_server'
    StreamKey     = New-StreamKey
    Ports         = $null
}

function Start-OmeContainer {
    if ($script:State.IsRunning) {
        Write-Log -Message 'OvenMediaEngine is already running.'
        return
    }

    try {
        Write-Log -Message 'Preparing dynamic port assignments...'
        $reserved = @()
        $httpPort = Get-FreeTcpPort -Reserved $reserved
        $reserved += $httpPort

        $httpsPort = Get-FreeTcpPort -Reserved $reserved
        $reserved += $httpsPort

        $rtmpPort = Get-FreeTcpPort -Reserved $reserved
        $reserved += $rtmpPort

        $webrtcSignaling = Get-FreeTcpPort -Reserved $reserved
        $reserved += $webrtcSignaling

        $stunPort = Get-FreeTcpPort -Reserved $reserved
        $reserved += $stunPort

        $turnTcpPort = Get-FreeTcpPort -Reserved $reserved
        $reserved += $turnTcpPort

        $udpReserved = @()
        $webrtcMedia = Get-FreeUdpPort -Reserved $udpReserved
        $udpReserved += $webrtcMedia

        $turnUdp = Get-FreeUdpPort -Reserved ($udpReserved + $reserved)
        $udpReserved += $turnUdp

        $script:State.Ports = [ordered]@{
            Http           = $httpPort
            Https          = $httpsPort
            Rtmp           = $rtmpPort
            WebRtcSignaling = $webrtcSignaling
            StunTcp        = $stunPort
            TurnTcp        = $turnTcpPort
            WebRtcMedia    = $webrtcMedia
            TurnUdp        = $turnUdp
        }

        $containerName = $script:State.ContainerName
        $existing = docker ps -a --filter "name=$containerName" --format '{{.ID}}'
        if ($existing) {
            Write-Log -Message 'Existing OvenMediaEngine container detected. Removing old container...'
            docker rm -f $containerName | Out-Null
        }

        Write-Log -Message 'Pulling the latest OvenMediaEngine image (if needed)...'
        docker pull airensoft/ovenmediaengine:latest | Out-Null

        Write-Log -Message 'Starting OvenMediaEngine container...'
        $args = @(
            'run','-d',
            "--name=$containerName",
            "-p", "${httpPort}:80",
            "-p", "${httpsPort}:443",
            "-p", "${rtmpPort}:1935",
            "-p", "${webrtcSignaling}:3333",
            "-p", "${stunPort}:3478",
            "-p", "${turnTcpPort}:3479",
            "-p", "${turnUdp}:3479/udp",
            "-p", "${webrtcMedia}:10000/udp",
            'airensoft/ovenmediaengine:latest'
        )

        docker @args | Out-Null
        $script:State.IsRunning = $true

        $localIp = Get-PrimaryIPv4
        $streamKey = $script:State.StreamKey

        $script:State.ConnectionInfo = @{
            ObsUrl       = "rtmp://$localIp:$rtmpPort/app"
            ObsStreamKey = $streamKey
            Vlcllhls     = "http://$localIp:$httpPort/app/$streamKey/llhls.m3u8"
            Vlchls       = "http://$localIp:$httpPort/app/$streamKey/playlist.m3u8"
        }

        Write-Log -Message 'OvenMediaEngine is running.'
        Write-Log -Message "OBS Server URL: $($script:State.ConnectionInfo.ObsUrl)"
        Write-Log -Message "OBS Stream Key: $streamKey"
        Write-Log -Message "VLC (Low-Latency HLS) URL: $($script:State.ConnectionInfo.Vlcllhls)"
        Write-Log -Message "VLC (Standard HLS) URL: $($script:State.ConnectionInfo.Vlchls)"
    }
    catch {
        $script:State.IsRunning = $false
        $script:State.Ports = $null
        $script:State.ConnectionInfo = $null
        Write-Log -Message "Failed to start OvenMediaEngine: $($_.Exception.Message)" -IsError
    }
    finally {
        Update-DetailsBox
    }
}

function Stop-OmeContainer {
    if (-not $script:State.IsRunning) {
        Write-Log -Message 'OvenMediaEngine is not currently running.'
        return
    }

    try {
        $containerName = $script:State.ContainerName
        Write-Log -Message 'Stopping OvenMediaEngine container...'
        docker rm -f $containerName | Out-Null
        Write-Log -Message 'OvenMediaEngine has been stopped.'
    }
    catch {
        Write-Log -Message "Failed to stop OvenMediaEngine: $($_.Exception.Message)" -IsError
    }
    finally {
        $script:State.IsRunning = $false
        $script:State.Ports = $null
        $script:State.ConnectionInfo = $null
        Update-DetailsBox
    }
}

function Update-DetailsBox {
    if (-not $script:UiControls.DetailsBox) { return }
    $detailsBox = $script:UiControls.DetailsBox

    $action = {
        param($box, $state)
        $box.Clear()
        if (-not $state.IsRunning) {
            $box.Text = "Server is not running. Click 'Start Server' to launch OvenMediaEngine.";
            return
        }

        $info = $state.ConnectionInfo
        $ports = $state.Ports
        $lines = @()
        $lines += 'Server Status: Running'
        $lines += ''
        $lines += 'OBS Configuration:'
        $lines += "  Server URL : $($info.ObsUrl)"
        $lines += "  Stream Key : $($info.ObsStreamKey)"
        $lines += ''
        $lines += 'VLC Playback:'
        $lines += "  Low-Latency HLS : $($info.Vlcllhls)"
        $lines += "  Standard HLS    : $($info.Vlchls)"
        $lines += ''
        $lines += 'Ports in Use:'
        $lines += "  HTTP  : $($ports.Http)"
        $lines += "  HTTPS : $($ports.Https)"
        $lines += "  RTMP  : $($ports.Rtmp)"
        $lines += "  WebRTC Signaling : $($ports.WebRtcSignaling)"
        $lines += "  STUN/TURN TCP    : $($ports.StunTcp), $($ports.TurnTcp)"
        $lines += "  STUN/TURN UDP    : $($ports.TurnUdp)"
        $lines += "  Media UDP        : $($ports.WebRtcMedia)"
        $lines += ''
        $lines += 'Tips:'
        $lines += '  • In OBS, choose the RTMP output mode and paste the URL and stream key above.'
        $lines += '  • In VLC, use Media → Open Network Stream and paste one of the URLs above.'
        $lines += '  • Share the HTTP URL with guests on the same network for playback.'
        $box.Lines = $lines
    }

    if ($detailsBox.InvokeRequired) {
        $null = $detailsBox.BeginInvoke($action, $detailsBox, $script:State)
    }
    else {
        & $action $detailsBox $script:State
    }
}

function Initialize-Gui {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'OvenMediaEngine Control Panel'
    $form.Size = New-Object System.Drawing.Size(700, 620)
    $form.StartPosition = 'CenterScreen'

    $startButton = New-Object System.Windows.Forms.Button
    $startButton.Text = 'Start Server'
    $startButton.Size = New-Object System.Drawing.Size(150, 35)
    $startButton.Location = New-Object System.Drawing.Point(20, 20)

    $stopButton = New-Object System.Windows.Forms.Button
    $stopButton.Text = 'Stop Server'
    $stopButton.Size = New-Object System.Drawing.Size(150, 35)
    $stopButton.Location = New-Object System.Drawing.Point(190, 20)

    $refreshButton = New-Object System.Windows.Forms.Button
    $refreshButton.Text = 'Refresh Details'
    $refreshButton.Size = New-Object System.Drawing.Size(150, 35)
    $refreshButton.Location = New-Object System.Drawing.Point(360, 20)

    $logLabel = New-Object System.Windows.Forms.Label
    $logLabel.Text = 'Activity Log:'
    $logLabel.Location = New-Object System.Drawing.Point(20, 70)
    $logLabel.AutoSize = $true

    $logBox = New-Object System.Windows.Forms.TextBox
    $logBox.Multiline = $true
    $logBox.ScrollBars = 'Vertical'
    $logBox.ReadOnly = $true
    $logBox.Location = New-Object System.Drawing.Point(20, 95)
    $logBox.Size = New-Object System.Drawing.Size(640, 220)

    $detailsLabel = New-Object System.Windows.Forms.Label
    $detailsLabel.Text = 'Connection Details:'
    $detailsLabel.Location = New-Object System.Drawing.Point(20, 325)
    $detailsLabel.AutoSize = $true

    $detailsBox = New-Object System.Windows.Forms.TextBox
    $detailsBox.Multiline = $true
    $detailsBox.ScrollBars = 'Vertical'
    $detailsBox.ReadOnly = $true
    $detailsBox.Location = New-Object System.Drawing.Point(20, 350)
    $detailsBox.Size = New-Object System.Drawing.Size(640, 200)

    $form.Controls.AddRange(@($startButton, $stopButton, $refreshButton, $logLabel, $logBox, $detailsLabel, $detailsBox))

    $script:UiControls = @{
        Form = $form
        StartButton = $startButton
        StopButton = $stopButton
        RefreshButton = $refreshButton
        LogBox = $logBox
        DetailsBox = $detailsBox
    }

    $startButton.Add_Click({
        $script:UiControls.StartButton.Enabled = $false
        $script:UiControls.StopButton.Enabled = $false
        $script:UiControls.RefreshButton.Enabled = $false
        $script:UiControls.StartButton.Text = 'Starting...'

        $worker = New-Object System.ComponentModel.BackgroundWorker
        $worker.DoWork += { Start-OmeContainer }
        $worker.RunWorkerCompleted += {
            param($sender, $event)
            if ($event.Error) {
                Write-Log -Message "Start operation failed: $($event.Error.Exception.Message)" -IsError
            }
            $script:UiControls.StartButton.Enabled = $true
            $script:UiControls.StopButton.Enabled = $true
            $script:UiControls.RefreshButton.Enabled = $true
            $script:UiControls.StartButton.Text = 'Start Server'
            Update-DetailsBox
        }
        $worker.RunWorkerAsync() | Out-Null
    })

    $stopButton.Add_Click({
        $script:UiControls.StartButton.Enabled = $false
        $script:UiControls.StopButton.Enabled = $false
        $script:UiControls.RefreshButton.Enabled = $false
        $script:UiControls.StopButton.Text = 'Stopping...'

        $worker = New-Object System.ComponentModel.BackgroundWorker
        $worker.DoWork += { Stop-OmeContainer }
        $worker.RunWorkerCompleted += {
            param($sender, $event)
            if ($event.Error) {
                Write-Log -Message "Stop operation failed: $($event.Error.Exception.Message)" -IsError
            }
            $script:UiControls.StartButton.Enabled = $true
            $script:UiControls.StopButton.Enabled = $true
            $script:UiControls.RefreshButton.Enabled = $true
            $script:UiControls.StopButton.Text = 'Stop Server'
            Update-DetailsBox
        }
        $worker.RunWorkerAsync() | Out-Null
    })

    $refreshButton.Add_Click({ Update-DetailsBox })

    $form.add_FormClosing({
        if ($script:State.IsRunning) {
            $result = [System.Windows.Forms.MessageBox]::Show(
                'The media server is still running. Do you want to stop it before exiting?',
                'Confirm Exit',
                [System.Windows.Forms.MessageBoxButtons]::YesNo,
                [System.Windows.Forms.MessageBoxIcon]::Question
            )
            if ($result -eq [System.Windows.Forms.DialogResult]::Yes) {
                try { Stop-OmeContainer }
                catch { Write-Log -Message "Failed to stop container: $($_.Exception.Message)" -IsError }
            }
        }
    })

    Update-DetailsBox
    [void][System.Windows.Forms.Application]::Run($form)
}

# --- Script entry point ---

Assert-Administrator
Write-Log -Message 'Starting OvenMediaEngine setup assistant...'
Ensure-WSL
Ensure-DockerDesktop
Write-Log -Message 'Prerequisites satisfied.'
Initialize-Gui
