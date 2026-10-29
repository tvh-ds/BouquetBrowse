param([Parameter(Mandatory=$true)][ValidateSet('scheduler','browser','offer')][string]$Role)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$taskPython = Join-Path $taskRoot 'apps\api\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Install the locked Python environment first.' }
$env:PYTHONPATH = Join-Path $taskRoot 'apps\api'
$env:PYTHONIOENCODING = 'utf-8'
$env:LANGSMITH_TRACING = 'false'
Set-Location -LiteralPath $taskRoot
# Task Scheduler supplies a hidden process. No Codex process or cookie copying is involved.
& $taskPython -m bouquetbrowse.worker --role $Role
exit $LASTEXITCODE
