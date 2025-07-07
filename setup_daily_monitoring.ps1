# setup_daily_monitoring.ps1 - PowerShell script to create scheduled task

# Create the scheduled task for daily server monitoring
$TaskName = "VoiceSQL Daily Health Check"
$Description = "Daily health check for Voice SQL Server and Client"
$ScriptPath = "C:\path\to\your\project\run_tests.py"
$PythonPath = "C:\path\to\python.exe"  # Adjust to your Python installation
$LogPath = "C:\Logs\VoiceSQL\daily_monitoring.log"

# Create the action (what to run)
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$ScriptPath`" 2>&1 | Tee-Object -FilePath `"$LogPath`""

# Create the trigger (when to run) - Daily at 6:00 AM
$Trigger = New-ScheduledTaskTrigger -Daily -At "06:00"

# Create the principal (run as system/user)
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

# Create the settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Register the task
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description $Description

Write-Host "✅ Scheduled task created: $TaskName"
Write-Host "📅 Will run daily at 6:00 AM"
Write-Host "📝 Logs will be saved to: $LogPath"

# Alternative: Create via schtasks command (if PowerShell cmdlets not available)
# schtasks /create /tn "VoiceSQL Daily Health Check" /tr "python.exe C:\path\to\run_tests.py" /sc daily /st 06:00 /ru SYSTEM