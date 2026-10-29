# Native Windows execution with mocked Task Scheduler cmdlets; never registers or starts OS tasks.
$ErrorActionPreference = 'Stop'
$global:bouquetMockTasks = @{}
$global:bouquetMockStopped = @()
$global:bouquetMockRemoved = @()
function Test-Path { param($LiteralPath) return $LiteralPath -like '*apps\api\.venv\Scripts\python.exe' }
function New-ScheduledTaskAction { param($Execute,$Argument,$WorkingDirectory) [pscustomobject]@{Execute=$Execute; Argument=$Argument; WorkingDirectory=$WorkingDirectory} }
function New-ScheduledTaskTrigger { param([switch]$AtLogOn,$User) [pscustomobject]@{AtLogOn=$AtLogOn; User=$User} }
function New-ScheduledTaskSettingsSet {
    param($MultipleInstances,$ExecutionTimeLimit,$RestartCount,$RestartInterval,[switch]$AllowStartIfOnBatteries,[switch]$DontStopIfGoingOnBatteries,[switch]$WakeToRun,[switch]$StartWhenAvailable)
    [pscustomobject]@{Enabled=$true; WakeToRun=[bool]$WakeToRun; StartWhenAvailable=[bool]$StartWhenAvailable; MultipleInstances=$MultipleInstances}
}
function New-ScheduledTaskPrincipal { param($UserId,$LogonType,$RunLevel) [pscustomobject]@{UserId=$UserId; LogonType=$LogonType; RunLevel=$RunLevel} }
function New-ScheduledTask { param($Action,$Trigger,$Settings,$Principal,$Description) [pscustomobject]@{Action=$Action; Trigger=$Trigger; Settings=$Settings; Principal=$Principal; Description=$Description; State='Disabled'} }
function Get-ScheduledTask { param($TaskName,$ErrorAction) return $global:bouquetMockTasks[$TaskName] }
function Register-ScheduledTask { param($TaskName,$InputObject,[switch]$Force) $global:bouquetMockTasks[$TaskName]=$InputObject }
function Stop-ScheduledTask { param($TaskName,$ErrorAction) $global:bouquetMockStopped += $TaskName }
function Disable-ScheduledTask { param($TaskName) $global:bouquetMockTasks[$TaskName].Settings.Enabled=$false }
function Unregister-ScheduledTask { param($TaskName,[switch]$Confirm) $global:bouquetMockRemoved += $TaskName; $global:bouquetMockTasks.Remove($TaskName) }
& (Join-Path $PSScriptRoot 'install-local-tasks.ps1')
if ($global:bouquetMockTasks.Count -ne 3) { throw 'Expected exactly three dedicated role tasks' }
foreach ($entry in $global:bouquetMockTasks.Values) {
    if ($entry.Settings.Enabled -or $entry.Settings.WakeToRun -or $entry.Settings.StartWhenAvailable) { throw 'Startup activation/catch-up must remain disabled' }
    if ($entry.Principal.RunLevel -ne 'Limited' -or $entry.Principal.LogonType -ne 'Interactive') { throw 'Unexpected elevated/password-based task principal' }
    if ($entry.Action.Argument -notmatch '-WindowStyle Hidden' -or $entry.Settings.MultipleInstances -ne 'IgnoreNew') { throw 'Task must be hidden and nonoverlapping' }
}
& (Join-Path $PSScriptRoot 'manage-local-tasks.ps1') -Action disable
if ($global:bouquetMockStopped.Count -ne 3) { throw 'Disable must stop all owned roles' }
& (Join-Path $PSScriptRoot 'manage-local-tasks.ps1') -Action uninstall
if ($global:bouquetMockTasks.Count -ne 0 -or $global:bouquetMockRemoved.Count -ne 3) { throw 'Uninstall left managed role tasks behind' }
$global:bouquetMockTasks['BouquetBrowse-offer']=[pscustomobject]@{Description='Unrelated user task'}
$refused=$false
try { & (Join-Path $PSScriptRoot 'install-local-tasks.ps1') } catch { $refused=$true }
if (-not $refused) { throw 'Installer overwrote an unrelated task' }
if ($global:bouquetMockTasks.Count -ne 1) { throw 'Ownership preflight must finish before any task mutation' }
Write-Output 'Native Windows startup/disable/uninstall mock lifecycle passed. No OS tasks were modified.'
