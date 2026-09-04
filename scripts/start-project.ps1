[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontendRoot = Join-Path $projectRoot "frontend"
$dataRoot = Join-Path $projectRoot "data"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$requirementsFile = Join-Path $projectRoot "backend\requirements.txt"
$viteScript = Join-Path $frontendRoot "node_modules\vite\bin\vite.js"
$backendPidFile = Join-Path $dataRoot "backend.pid"
$frontendPidFile = Join-Path $dataRoot "frontend.pid"
$backendUrl = "http://127.0.0.1:8000"
$frontendUrl = "http://127.0.0.1:5173"

function Test-BackendReady {
    try {
        $payload = Invoke-RestMethod -Uri "$backendUrl/openapi.json" -TimeoutSec 2
        return $payload.info.title -eq "agent-business"
    }
    catch {
        return $false
    }
}

function Test-FrontendReady {
    try {
        $page = Invoke-WebRequest -UseBasicParsing -Uri $frontendUrl -TimeoutSec 2
        $health = Invoke-RestMethod -Uri "$frontendUrl/api/health" -TimeoutSec 2
        return $page.Content.Contains('<div id="root"></div>') -and $health.status -eq "ok"
    }
    catch {
        return $false
    }
}

function Test-PortListening([int]$Port) {
    return $null -ne (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Wait-UntilReady {
    param(
        [scriptblock]$ReadyCheck,
        [System.Diagnostics.Process]$Process,
        [string]$ServiceName,
        [string]$ErrorLog
    )

    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (& $ReadyCheck) {
            return
        }
        if ($Process.HasExited) {
            $logTail = if (Test-Path -LiteralPath $ErrorLog) {
                (Get-Content -LiteralPath $ErrorLog -Tail 20 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
            }
            else {
                "No error log was generated."
            }
            throw "$ServiceName failed to start. Error log:`n$logTail"
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$ServiceName did not pass its health check within 60 seconds. See $ErrorLog."
}

function Import-DotEnv {
    $envFile = Join-Path $projectRoot ".env"
    if (-not (Test-Path -LiteralPath $envFile)) {
        return
    }

    foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        $separator = $trimmed.IndexOf("=")
        if ($separator -lt 1) {
            continue
        }
        $name = $trimmed.Substring(0, $separator).Trim()
        $value = $trimmed.Substring($separator + 1).Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
Import-DotEnv

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    throw "Python was not found. Install Python 3.11 or newer first."
}

$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCommand) {
    throw "Node.js was not found. Install Node.js 20 or newer first."
}

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    throw "npm.cmd was not found. Reinstall Node.js with npm."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "[1/5] Creating the .venv Python environment..."
    & $pythonCommand.Source -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the Python virtual environment."
    }
}

if (-not $SkipInstall) {
    Write-Host "[2/5] Installing backend dependencies..."
    & $venvPython -m pip install -r $requirementsFile
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install backend dependencies."
    }

    Write-Host "[3/5] Installing frontend dependencies..."
    Push-Location $frontendRoot
    try {
        & $npmCommand.Source install
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install frontend dependencies."
        }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "[2/5] Dependency installation skipped."
    Write-Host "[3/5] Checking existing dependencies..."
}

& $venvPython -c "import fastapi, uvicorn, multipart, pypdf, docx, reportlab, httpx"
if ($LASTEXITCODE -ne 0) {
    throw "Backend dependencies are incomplete. Run again without -SkipInstall."
}
if ($env:OS -eq "Windows_NT") {
    & $venvPython -c "import win32com.client"
    if ($LASTEXITCODE -ne 0) {
        throw "Windows PDF dependencies are incomplete. Run again without -SkipInstall."
    }
}
if (-not (Test-Path -LiteralPath $viteScript)) {
    throw "Frontend dependencies are incomplete. Run again without -SkipInstall."
}

$backendProcess = $null
if (Test-BackendReady) {
    Write-Host "[4/5] Reusing the backend already running at $backendUrl."
}
elseif (Test-PortListening 8000) {
    throw "Port 8000 is used by another process. Free it before retrying."
}
else {
    Write-Host "[4/5] Starting the FastAPI backend..."
    $backendProcess = Start-Process `
        -FilePath $venvPython `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--app-dir", "backend") `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput (Join-Path $dataRoot "backend.log") `
        -RedirectStandardError (Join-Path $dataRoot "backend-error.log") `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -LiteralPath $backendPidFile -Value $backendProcess.Id -Encoding ASCII
    Wait-UntilReady -ReadyCheck { Test-BackendReady } -Process $backendProcess -ServiceName "Backend" -ErrorLog (Join-Path $dataRoot "backend-error.log")
}

$frontendProcess = $null
if (Test-FrontendReady) {
    Write-Host "[5/5] Reusing the frontend already running at $frontendUrl."
}
elseif (Test-PortListening 5173) {
    throw "Port 5173 is used by another process. Free it before retrying."
}
else {
    Write-Host "[5/5] Starting the Vite frontend..."
    $frontendProcess = Start-Process `
        -FilePath $nodeCommand.Source `
        -ArgumentList @($viteScript, "--host", "127.0.0.1", "--port", "5173", "--strictPort") `
        -WorkingDirectory $frontendRoot `
        -RedirectStandardOutput (Join-Path $dataRoot "frontend.log") `
        -RedirectStandardError (Join-Path $dataRoot "frontend-error.log") `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -LiteralPath $frontendPidFile -Value $frontendProcess.Id -Encoding ASCII
    Wait-UntilReady -ReadyCheck { Test-FrontendReady } -Process $frontendProcess -ServiceName "Frontend" -ErrorLog (Join-Path $dataRoot "frontend-error.log")
}

Write-Host ""
Write-Host "agent-business is running:"
Write-Host "  Workbench: $frontendUrl"
Write-Host "  API docs: $backendUrl/docs"
Write-Host "  Health check: $backendUrl/api/health"
Write-Host "  Stop services: .\scripts\stop-project.ps1"

if (-not $NoBrowser) {
    Start-Process $frontendUrl
}
