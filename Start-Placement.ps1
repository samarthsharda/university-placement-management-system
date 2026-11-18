param([int]$Port=8020,[switch]$NoBrowser,[switch]$SetupOnly)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $SetupOnly) {
    try {
        $runningDemo=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        if ($runningDemo.application -eq 'university-placement-management') {
            Write-Host "The placement app is already running at http://127.0.0.1:$Port"
            if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port" }
            exit 0
        }
    } catch { }
}
$venvPython=Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'Preparing the placement demo...'
    $placementCandidates=@()
    foreach ($commandName in @('python','python3')) {
        $placementCommand=Get-Command $commandName -ErrorAction SilentlyContinue
        if ($placementCommand -and $placementCommand.Source -notlike '*Microsoft\WindowsApps*') {
            $placementCandidates+=$placementCommand.Source
        }
    }
    if (Get-Command Get-AppxPackage -ErrorAction SilentlyContinue) {
        $placementPackages=Get-AppxPackage -Name 'OpenAI.CodexPrimaryRuntime*' | Sort-Object Version -Descending
        foreach ($placementPackage in $placementPackages) {
            $placementCandidates+=(Join-Path $placementPackage.InstallLocation 'dependencies/python/python.exe')
        }
    }
    $placementPython=$null
    foreach ($placementCandidate in $placementCandidates) {
        if (Test-Path -LiteralPath $placementCandidate) {
            & $placementCandidate -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
            if ($LASTEXITCODE -eq 0) { $placementPython=$placementCandidate; break }
        }
    }
    if ($placementPython) { & $placementPython -m venv .venv }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m venv .venv }
    else { throw 'Install Python 3.11 or newer from python.org, then run this launcher again.' }
    if ($LASTEXITCODE -ne 0) { throw 'Python setup failed. Install Python 3.11 or newer from python.org and try again.' }
}
& $venvPython -c 'import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(x) for x in sys.argv[1:]) else 1)' fastapi uvicorn
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing the required libraries. Internet access is needed on the first run.'
    & $venvPython -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Library installation failed. Check the internet connection and try again.' }
}
if ($SetupOnly) { Write-Host 'Setup complete.'; exit 0 }
Write-Host "Open http://127.0.0.1:$Port"
Write-Host 'Keep this window open. Press Ctrl+C here to stop the demo.'
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port" }
& $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port
