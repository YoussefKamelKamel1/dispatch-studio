param([int]$Port = 8012)
$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$workspacePython = Join-Path (Split-Path $PSScriptRoot) '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $projectPython) { $dispatchPython = $projectPython }
elseif (Test-Path -LiteralPath $workspacePython) { $dispatchPython = $workspacePython }
else { $dispatchPython = 'python' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'frontend\dist\index.html'))) {
  throw 'Build the interface first: cd frontend; npm ci; npm run build'
}
Write-Host "Dispatch: http://127.0.0.1:$Port"
& $dispatchPython (Join-Path $PSScriptRoot 'run.py') --port $Port
exit $LASTEXITCODE
