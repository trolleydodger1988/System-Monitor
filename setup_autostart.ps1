# Setup System Monitor to run automatically at Windows startup
# This script creates a Windows Task Scheduler task

# Requires Administrator privileges
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "This script requires Administrator privileges!" -ForegroundColor Red
    Write-Host "Right-click and select 'Run as Administrator'" -ForegroundColor Yellow
    pause
    exit 1
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runScript = Join-Path $scriptDir "run_sysmon.ps1"

# Verify the run script exists
if (-not (Test-Path $runScript)) {
    Write-Host "Error: run_sysmon.ps1 not found at $runScript" -ForegroundColor Red
    exit 1
}

# Task details
$taskName = "SystemMonitor-AutoStart"
$taskDescription = "Automatically starts the System Monitor dashboard at login"
$taskAction = New-ScheduledTaskAction -Execute "PowerShell.exe" `
    -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runScript`""
$taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "Task '$taskName' already exists. Updating..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Register the new task
try {
    Register-ScheduledTask -TaskName $taskName `
        -Description $taskDescription `
        -Action $taskAction `
        -Trigger $taskTrigger `
        -Settings $taskSettings `
        -User $env:USERNAME `
        -RunLevel Highest `
        -Force | Out-Null
    
    Write-Host "`n✅ Success! System Monitor will now start automatically at login" -ForegroundColor Green
    Write-Host "`nTask Details:" -ForegroundColor Cyan
    Write-Host "  Name: $taskName"
    Write-Host "  Trigger: At user login ($env:USERNAME)"
    Write-Host "  Script: $runScript"
    Write-Host "`nTo manage this task:" -ForegroundColor Yellow
    Write-Host "  • Open Task Scheduler (taskschd.msc)"
    Write-Host "  • Look for '$taskName' in Task Scheduler Library"
    Write-Host "`nTo remove autostart, run:" -ForegroundColor Yellow
    Write-Host "  .\remove_autostart.ps1" -ForegroundColor White
} catch {
    Write-Host "`n❌ Failed to create scheduled task:" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}

pause
