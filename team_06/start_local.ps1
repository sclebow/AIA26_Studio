$ErrorActionPreference = 'Stop'

$teamRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $teamRoot
$backendDir = Join-Path $teamRoot 'python'
$frontendDir = Join-Path $teamRoot 'frontend'
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $pythonExe)) {
  throw "Python virtual environment not found at $pythonExe"
}

if (-not (Test-Path (Join-Path $frontendDir 'package.json'))) {
  throw "Frontend package.json not found at $frontendDir"
}

$backendCommand = "Set-Location '$backendDir'; & '$pythonExe' main.py"
$frontendCommand = "Set-Location '$frontendDir'; npm run dev"

$reuseBackend = $false
try {
  $healthResponse = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2
  if ($healthResponse.Content -match '"ok"\s*:\s*true') {
    $reuseBackend = $true
  }
} catch {
  $reuseBackend = $false
}

if (-not $reuseBackend) {
  Start-Process powershell -ArgumentList @(
    '-NoExit',
    '-ExecutionPolicy', 'Bypass',
    '-Command', $backendCommand
  )
}

Start-Process powershell -ArgumentList @(
  '-NoExit',
  '-ExecutionPolicy', 'Bypass',
  '-Command', $frontendCommand
)

if ($reuseBackend) {
  Write-Host 'Reusing existing Team 06 backend on http://127.0.0.1:8000'
} else {
  Write-Host 'Started Team 06 backend on http://127.0.0.1:8000'
}
Write-Host 'Started Team 06 frontend in a separate PowerShell window.'
Write-Host 'Frontend: check the Vite URL shown in the new frontend window'