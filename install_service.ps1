# =============================================================================
# FLEETPULSE ENDPOINT AGENT - AUTOMATED SERVICE INSTALLER
# Run this script in PowerShell as Administrator
# =============================================================================

# Ensure running as Admin
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "[!] Error: Please run this script as Administrator!" -ForegroundColor Red
    Exit
}

$workDir = "C:\FleetPulse"
$pythonExe = "$workDir\venv\Scripts\python.exe"
$agentScript = "$workDir\agent.py"
$nssmExe = "$workDir\nssm.exe"

# 1. Download NSSM if not present
if (-not (Test-Path $nssmExe)) {
    Write-Host "[*] Downloading NSSM binary for Windows Service management..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile "$workDir\nssm.zip"
    Expand-Archive -Path "$workDir\nssm.zip" -DestinationPath "$workDir\nssm_temp" -Force
    Copy-Item "$workDir\nssm_temp\nssm-2.24\win64\nssm.exe" -Destination $nssmExe
    Remove-Item -Recurse -Force "$workDir\nssm.zip", "$workDir\nssm_temp"
}

# 2. Install Service
Write-Host "[*] Installing FleetPulseAgent Service..." -ForegroundColor Cyan
& $nssmExe install FleetPulseAgent $pythonExe $agentScript
& $nssmExe set FleetPulseAgent AppDirectory $workDir
& $nssmExe set FleetPulseAgent DisplayName "FleetPulse Endpoint Telemetry Agent"
& $nssmExe set FleetPulseAgent Description "Transmits OS compliance telemetry and executes remote remediation tasks for FleetPulse RMM."
& $nssmExe set FleetPulseAgent Start SERVICE_AUTO_START

# 3. Start Service
Write-Host "[*] Starting FleetPulseAgent Service..." -ForegroundColor Green
Start-Service FleetPulseAgent

Write-Host "[+] FleetPulseAgent successfully installed and running as a Windows Service!" -ForegroundColor Green