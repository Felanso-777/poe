param(
    [switch]$InstallDependencies
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if ($InstallDependencies) {
    python -m pip install -r requirements.txt
}

Set-Location $PSScriptRoot
pyinstaller --clean --noconfirm production-agent.spec
Write-Output "Built: $((Join-Path $PSScriptRoot 'dist\ProofOfEffortMonitor.exe'))"
