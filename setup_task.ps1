[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = "TimebutlerAuto",
    [string]$PythonPath = "pythonw.exe",
    [switch]$IncludeWlanTrigger,
    [string[]]$EventIds = @("8001", "8002"),
    [string]$UserId = $env:USERNAME
)

# Stop on errors so a failed registration is not followed by success messages
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $projectRoot "timebutler_run.py"

if (-not (Test-Path $scriptPath)) {
    throw "timebutler_run.py wurde nicht gefunden unter $scriptPath"
}

$arguments = "`"$scriptPath`""

$actions = @(
    New-ScheduledTaskAction `
        -Execute $PythonPath `
        -Argument $arguments `
        -WorkingDirectory $projectRoot
)

$triggers = @(
    New-ScheduledTaskTrigger -AtLogOn
)

if ($IncludeWlanTrigger.IsPresent) {
    $eventFilter = ($EventIds | ForEach-Object { "*[System[EventID=$_]]" }) -join " or "
    $subscription = @"
<QueryList>
  <Query Id="0" Path="Microsoft-Windows-WLAN-AutoConfig/Operational">
    <Select Path="Microsoft-Windows-WLAN-AutoConfig/Operational">$eventFilter</Select>
  </Query>
</QueryList>
"@
    # Windows PowerShell 5.1 has no 'New-ScheduledTaskTrigger -OnEvent',
    # so the event trigger is built directly as a CIM instance.
    $eventTriggerClass = Get-CimClass -ClassName MSFT_TaskEventTrigger -Namespace Root/Microsoft/Windows/TaskScheduler
    $eventTrigger = New-CimInstance -CimClass $eventTriggerClass -ClientOnly
    $eventTrigger.Subscription = $subscription
    $eventTrigger.Enabled = $true
    $triggers += $eventTrigger
}

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 30)

$principal = New-ScheduledTaskPrincipal -UserId $UserId -RunLevel Highest -LogonType Interactive

$task = New-ScheduledTask -Action $actions -Trigger $triggers -Settings $settings -Principal $principal

if ($PSCmdlet.ShouldProcess($TaskName, "Register scheduled task")) {
    Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force
    Write-Host "Scheduled task '$TaskName' registriert."
    Write-Host "Aktion: $PythonPath $arguments"
    Write-Host "Trigger: Logon" -ForegroundColor Green
    if ($IncludeWlanTrigger) {
        Write-Host "Trigger: WLAN-Events ($($EventIds -join ', '))" -ForegroundColor Green
        Write-Host "Passe die EventIDs bei Bedarf mit -EventIds an (Get-WinEvent hilft bei der Analyse)."
    }
}
