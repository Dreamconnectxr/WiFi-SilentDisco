Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# Ensure the UI control map always exists before any logging attempts.
$script:UiControls = $null

# Track the log file path in script scope so multiple functions can reuse it.
$script:LogFilePath = Join-Path -Path $PSScriptRoot -ChildPath 'setup_ome_server.log'

function Initialize-Logging {
    [CmdletBinding()]
    param(
        [string]$LogPath
    )

    if ([string]::IsNullOrWhiteSpace($LogPath)) {
        return
    }

    $script:LogFilePath = $LogPath

    $directory = Split-Path -Path $script:LogFilePath -Parent
    if (-not (Test-Path -Path $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    if (-not (Test-Path -Path $script:LogFilePath)) {
        New-Item -ItemType File -Path $script:LogFilePath -Force | Out-Null
    }
}

function Write-Log {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet('INFO', 'WARN', 'ERROR')][string]$Level = 'INFO'
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $entry = "[$timestamp] [$Level] $Message"

    Write-Host $entry

    if ($script:LogFilePath) {
        Add-Content -Path $script:LogFilePath -Value $entry
    }

    $uiVariable = Get-Variable -Scope Script -Name UiControls -ErrorAction SilentlyContinue
    if ($null -ne $uiVariable) {
        $controls = $uiVariable.Value
        $logBox = $null

        if ($controls -is [System.Collections.IDictionary]) {
            if ($controls.Contains('LogBox')) {
                $logBox = $controls['LogBox']
            }
        } elseif ($null -ne $controls.PSObject.Properties['LogBox']) {
            $logBox = $controls.LogBox
        }

        if ($null -ne $logBox -and $logBox.PSObject.Methods.Name -contains 'AppendText') {
            $logBox.AppendText($entry + [Environment]::NewLine)
            if ($logBox.PSObject.Methods.Name -contains 'ScrollToCaret') {
                $logBox.ScrollToCaret()
            }
        }
    }
}

Initialize-Logging -LogPath $script:LogFilePath
Write-Log -Message 'Starting OME server setup process.' -Level 'INFO'
