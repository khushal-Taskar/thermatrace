param([switch]$Production, [switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendDir = Join-Path $projectRoot 'backend'
$frontendDir = Join-Path $projectRoot 'frontend'
$pythonPath = Join-Path $backendDir '.venv/Scripts/python.exe'
$nextPath = Join-Path $frontendDir 'node_modules/next/dist/bin/next'
$logDir = Join-Path $projectRoot 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv (Join-Path $backendDir '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ is required.' }
}
& $pythonPath -c 'import fastapi, sqlalchemy, sklearn, pandas, uvicorn, alembic, reportlab, paho.mqtt, psycopg, multipart, faster_whisper, piper' 2>$null
if ($LASTEXITCODE -ne 0) {
    & $pythonPath -m pip install -r (Join-Path $backendDir 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
}
Push-Location $backendDir
try {
    & $pythonPath -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
} finally { Pop-Location }
if (-not (Test-Path -LiteralPath $nextPath)) {
    Push-Location $frontendDir
    try { npm ci; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' } }
    finally { Pop-Location }
}
if ($Production -and -not $SkipBuild) {
    Push-Location $frontendDir
    try { npm run build; if ($LASTEXITCODE -ne 0) { throw 'Production build failed.' } }
    finally { Pop-Location }
}

$created = @()
$backendListener = Get-NetTCPConnection -State Listen -LocalPort 8100 -ErrorAction SilentlyContinue
if (-not $backendListener) {
    $backendProcess = Start-Process -FilePath $pythonPath -ArgumentList '-m uvicorn app.main:app --host 127.0.0.1 --port 8100 --no-access-log' -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'backend.out.log') -RedirectStandardError (Join-Path $logDir 'backend.err.log')
    $created += @{ id = $backendProcess.Id; kind = 'backend' }
}
$frontendListener = Get-NetTCPConnection -State Listen -LocalPort 3100 -ErrorAction SilentlyContinue
if (-not $frontendListener) {
    $nextMode = if ($Production) { 'start' } else { 'dev' }
    $nodePath = (Get-Command node.exe).Source
    $frontendProcess = Start-Process -FilePath $nodePath -ArgumentList @('"' + $nextPath + '"', $nextMode, '-H', '127.0.0.1', '-p', '3100') -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'frontend.out.log') -RedirectStandardError (Join-Path $logDir 'frontend.err.log')
    $created += @{ id = $frontendProcess.Id; kind = 'frontend' }
}
if ($created.Count -gt 0) {
    $runtimePath = Join-Path $projectRoot '.runtime.json'
    $retained = @()
    if (Test-Path -LiteralPath $runtimePath) {
        foreach ($record in (Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json)) {
            $existingProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.id)" -ErrorAction SilentlyContinue
            if ($existingProcess -and $existingProcess.CommandLine -and $existingProcess.CommandLine.Contains($projectRoot)) { $retained += $record }
        }
    }
    ConvertTo-Json -InputObject @($retained + $created) | Set-Content -LiteralPath $runtimePath
}

$ready = $false
for ($attempt = 0; $attempt -lt 90; $attempt++) {
    try {
        $health = Invoke-RestMethod 'http://127.0.0.1:8100/api/health' -TimeoutSec 2
        $web = Invoke-WebRequest 'http://localhost:3100/login' -TimeoutSec 3 -UseBasicParsing
        if ($health.simulation -eq 'software' -and $web.Content.Contains('ThermaTrace')) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) { throw "Services did not become ready. Inspect $logDir. Ports 3100 and 8100 must be free or already serving ThermaTrace." }
Write-Host 'ThermaTrace is ready: http://localhost:3100'
Write-Host 'API documentation: http://127.0.0.1:8100/docs'
Write-Host 'Demo: admin@thermatrace.local / PharmaDemo!2026'
