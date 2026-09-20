$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$runtimePath = Join-Path $projectRoot '.runtime.json'
if (-not (Test-Path -LiteralPath $runtimePath)) { Write-Host 'No launcher-managed processes recorded.'; exit }
$recorded = Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json
function Stop-TaskProcessTree([int]$taskProcessId) {
    foreach ($child in (Get-CimInstance Win32_Process -Filter "ParentProcessId = $taskProcessId" -ErrorAction SilentlyContinue)) {
        Stop-TaskProcessTree -taskProcessId $child.ProcessId
    }
    Stop-Process -Id $taskProcessId -ErrorAction SilentlyContinue
}
foreach ($item in $recorded) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($item.id)" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine -and $process.CommandLine.Contains($projectRoot)) {
        Stop-TaskProcessTree -taskProcessId $item.id
        Write-Host "Stopped ThermaTrace $($item.kind)."
    }
}
Remove-Item -LiteralPath $runtimePath
