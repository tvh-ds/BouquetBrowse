param([Parameter(Mandatory=$true)][ValidateSet('status','disable','uninstall')][string]$Action)
$ErrorActionPreference = 'Stop'
foreach ($taskRole in @('scheduler','browser','offer')) {
    $taskName = "BouquetBrowse-$taskRole"
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $task) { continue }
    if ($task.Description -ne 'BouquetBrowse local runtime v1') { throw "Refusing to manage an unowned task: $taskName" }
    if ($Action -eq 'status') {
        [pscustomobject]@{Name=$taskName; State=$task.State; Enabled=$task.Settings.Enabled}
    } else {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Disable-ScheduledTask -TaskName $taskName | Out-Null
        if ($Action -eq 'uninstall') { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
    }
}
