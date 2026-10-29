param([switch]$Enable)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$taskPython = Join-Path $taskRoot 'apps\api\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Install the locked Python environment first.' }
if ($Enable) {
    $env:PYTHONPATH = Join-Path $taskRoot 'apps\api'
    $taskReadiness = & $taskPython -m bouquetbrowse.cli operations-ready
    if ($LASTEXITCODE -ne 0 -or -not (($taskReadiness | ConvertFrom-Json).ready)) {
        throw 'Setup, explicit recurring configuration and both audited real-data gates must pass before enabling startup.'
    }
}
$taskUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
foreach ($taskRole in @('scheduler','browser','offer')) {
    $taskArguments = '-NoProfile -NonInteractive -WindowStyle Hidden -File "' + (Join-Path $PSScriptRoot 'run-local-role.ps1') + '" -Role ' + $taskRole
    $taskAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $taskArguments -WorkingDirectory $taskRoot
    $taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $taskUser
    $taskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    # StartWhenAvailable and WakeToRun deliberately remain false; the app records missed slots.
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
    $task = New-ScheduledTask -Action $taskAction -Trigger $taskTrigger -Settings $taskSettings -Principal $taskPrincipal
    if (-not $Enable) { $task.Settings.Enabled = $false }
    Register-ScheduledTask -TaskName "BouquetBrowse-$taskRole" -InputObject $task -Force | Out-Null
}
Write-Output $(if ($Enable) { 'Startup tasks registered for the next sign-in. No task was started now.' } else { 'Startup tasks registered disabled. Enable only after the separately commanded live validation.' })
