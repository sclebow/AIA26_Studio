$ErrorActionPreference = 'Stop'

$teamRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $teamRoot
$backendDir = Join-Path $teamRoot 'python'
$frontendDir = Join-Path $teamRoot 'frontend'
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
$backendScript = Join-Path $backendDir 'main.py'
$backendPort = 8001
$frontendPort = 5173

if (-not (Test-Path $pythonExe)) {
  throw "Python virtual environment not found at $pythonExe"
}

if (-not (Test-Path (Join-Path $frontendDir 'package.json'))) {
  throw "Frontend package.json not found at $frontendDir"
}

$backendCommand = "Set-Location '$backendDir'; & '$pythonExe' '$backendScript' --serve --host 127.0.0.1 --port $backendPort"
$frontendCommand = "Set-Location '$frontendDir'; npm run dev -- --host 127.0.0.1 --port $frontendPort --strictPort"
$frontendUrl = 'http://127.0.0.1:5173'
$backendHealthUrl = "http://127.0.0.1:$backendPort/health"

function Stop-ListenerOnPort([int]$Port) {
  $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique

  foreach ($listenerPid in $listeners) {
    Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
  }
}

function Stop-BackendProcesses() {
  $backendProcesses = Get-CimInstance Win32_Process |
    Where-Object {
      $_.Name -match '^python(?:w)?\.exe$' -and (
        $_.CommandLine -like "*$backendScript*" -or
        $_.CommandLine -like "*team_06\\python*app:app*"
      )
    } |
    Select-Object -ExpandProperty ProcessId -Unique

  foreach ($backendPid in $backendProcesses) {
    Stop-Process -Id $backendPid -Force -ErrorAction SilentlyContinue
  }
}

$existingBackend = Get-NetTCPConnection -LocalPort $backendPort -State Listen -ErrorAction SilentlyContinue
$existingFrontend = Get-NetTCPConnection -LocalPort $frontendPort -State Listen -ErrorAction SilentlyContinue

if ($existingBackend) {
  Stop-BackendProcesses
  Stop-ListenerOnPort -Port $backendPort
  Start-Sleep -Milliseconds 500
}

if ($existingFrontend) {
  Stop-ListenerOnPort -Port $frontendPort
  Start-Sleep -Milliseconds 500
}

Start-Process powershell -ArgumentList @(
  '-NoExit',
  '-ExecutionPolicy', 'Bypass',
  '-Command', $backendCommand
)

Start-Process powershell -ArgumentList @(
  '-NoExit',
  '-ExecutionPolicy', 'Bypass',
  '-Command', $frontendCommand
)

for ($attempt = 0; $attempt -lt 20; $attempt++) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $backendHealthUrl -TimeoutSec 2
    if ($response.StatusCode -eq 200) {
      break
    }
  } catch {
    # Wait for the backend to finish booting.
  }
  Start-Sleep -Milliseconds 500
}

for ($attempt = 0; $attempt -lt 20; $attempt++) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $frontendUrl -TimeoutSec 2
    if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
      Start-Process $frontendUrl
      break
    }
  } catch {
    # Wait for Vite to finish booting.
  }
  Start-Sleep -Milliseconds 500
}

if ($existingBackend) {
  Write-Host "Restarted Team 06 backend on http://127.0.0.1:$backendPort"
} else {
  Write-Host "Started Team 06 backend on http://127.0.0.1:$backendPort"
}
if ($existingFrontend) {
  Write-Host 'Restarted Team 06 frontend on http://127.0.0.1:5173'
} else {
  Write-Host 'Started Team 06 frontend on http://127.0.0.1:5173'
}