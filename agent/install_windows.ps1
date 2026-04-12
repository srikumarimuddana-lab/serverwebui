# agent/install_windows.ps1
#Requires -RunAsAdministrator

$INSTALL_DIR = "C:\ProgramData\server-agent"
$CONFIG_DIR = "C:\ProgramData\server-agent"
$CERT_DIR = "C:\ProgramData\server-agent\certs"

Write-Host "=== Server Agent Installer (Windows) ==="

# Create directories
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $CERT_DIR | Out-Null

# Copy files
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Copy-Item -Path "$ScriptDir\*" -Destination $INSTALL_DIR -Recurse -Force

# Create venv and install deps
python -m venv "$INSTALL_DIR\venv"
& "$INSTALL_DIR\venv\Scripts\pip.exe" install --upgrade pip
& "$INSTALL_DIR\venv\Scripts\pip.exe" install -r "$INSTALL_DIR\requirements.txt"

# Config
$ConfigPath = "$CONFIG_DIR\config.yaml"
if (-not (Test-Path $ConfigPath)) {
    Copy-Item "$INSTALL_DIR\config.example.yaml" $ConfigPath
    Write-Host "Config created at $ConfigPath - edit before starting"
}

# Restrict cert directory permissions
$acl = Get-Acl $CERT_DIR
$acl.SetAccessRuleProtection($true, $false)
$adminRule = New-Object System.Security.AccessControl.FileSystemAccessRule("BUILTIN\Administrators", "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
$acl.AddAccessRule($adminRule)
Set-Acl $CERT_DIR $acl

# Install as Windows Service using NSSM (must be on PATH)
$NssmPath = Get-Command nssm -ErrorAction SilentlyContinue
if ($NssmPath) {
    nssm install ServerAgent "$INSTALL_DIR\venv\Scripts\uvicorn.exe" "agent.app.main:app --host 0.0.0.0 --port 8420"
    nssm set ServerAgent AppDirectory $INSTALL_DIR
    nssm set ServerAgent Description "Server Agent for WebUI"
    nssm set ServerAgent Start SERVICE_AUTO_START
    Write-Host "Windows Service 'ServerAgent' installed"
} else {
    Write-Host "WARNING: NSSM not found. Install NSSM to run as a Windows Service."
    Write-Host "Manual start: $INSTALL_DIR\venv\Scripts\uvicorn.exe agent.app.main:app --host 0.0.0.0 --port 8420"
}

Write-Host ""
Write-Host "=== Installation complete ==="
Write-Host "1. Edit config: $ConfigPath"
Write-Host "2. Place certificates in: $CERT_DIR"
Write-Host "3. Start service: nssm start ServerAgent"
