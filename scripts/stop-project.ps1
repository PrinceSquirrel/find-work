[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dataRoot = Join-Path $projectRoot "data"
$targets = @(
    @{ Name = "Frontend"; PidFile = (Join-Path $dataRoot "frontend.pid"); ProcessName = "node"; CommandMarker = "vite.js"; Port = 5173 },
    @{ Name = "Backend"; PidFile = (Join-Path $dataRoot "backend.pid"); ProcessName = "python"; CommandMarker = "app.main:app"; Port = 8000 }
)

function Get-DescendantProcessIds([int]$ParentId) {
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Get-DescendantProcessIds -ParentId $child.ProcessId
        $child.ProcessId
    }
}

foreach ($target in $targets) {
    if (-not (Test-Path -LiteralPath $target.PidFile)) {
        Write-Host "$($target.Name): no PID file was found; it may already be stopped."
        continue
    }

    $processId = [int](Get-Content -LiteralPath $target.PidFile -Raw).Trim()
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $process) {
        Remove-Item -LiteralPath $target.PidFile -Force
        Write-Host "$($target.Name): process was already stopped; the stale PID file was removed."
        continue
    }

    if ($process.ProcessName -ne $target.ProcessName) {
        throw "$($target.Name) PID $processId belongs to $($process.ProcessName); refusing to stop an unrelated process."
    }

    $processDetails = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
    if (-not $processDetails.CommandLine.Contains($projectRoot) -or -not $processDetails.CommandLine.Contains($target.CommandMarker)) {
        throw "$($target.Name) PID $processId does not match this project; refusing to stop an unrelated process."
    }

    foreach ($descendantId in @(Get-DescendantProcessIds -ParentId $processId)) {
        Stop-Process -Id $descendantId -Force -ErrorAction SilentlyContinue
    }
    Stop-Process -Id $processId -Force
    Remove-Item -LiteralPath $target.PidFile -Force

    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while ([DateTime]::UtcNow -lt $deadline) {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $target.Port -ErrorAction SilentlyContinue
        if (-not $listener) {
            break
        }
        Start-Sleep -Milliseconds 250
    }
    if (Get-NetTCPConnection -State Listen -LocalPort $target.Port -ErrorAction SilentlyContinue) {
        throw "$($target.Name) process stopped, but port $($target.Port) is still listening."
    }
    Write-Host "$($target.Name): stopped PID $processId."
}
