# Remove System Monitor from Windows startup
# This script removes the Windows Task Scheduler task

# Requires Administrator privileges
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "This script requires Administrator privileges!" -ForegroundColor Red
    Write-Host "Right-click and select 'Run as Administrator'" -ForegroundColor Yellow
    pause
    exit 1
}

$taskName = "SystemMonitor-AutoStart"

# Check if task exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    try {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "`n✅ Successfully removed '$taskName' from startup" -ForegroundColor Green
        Write-Host "System Monitor will no longer start automatically at login" -ForegroundColor Yellow
    } catch {
        Write-Host "`n❌ Failed to remove scheduled task:" -ForegroundColor Red
        Write-Host $_.Exception.Message
        exit 1
    }
} else {
    Write-Host "`n⚠️  Task '$taskName' not found" -ForegroundColor Yellow
    Write-Host "System Monitor is not configured for automatic startup" -ForegroundColor Gray
}

pause
