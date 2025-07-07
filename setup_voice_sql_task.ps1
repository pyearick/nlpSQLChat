# setup_voice_sql_simple.ps1 - Simple robust setup avoiding VBScript issues
# Run as Administrator

param(
    [string]$ProjectPath = $PWD.Path,
    [string]$LogPath = "C:\Logs\VoiceSQL"
)

Write-Host "=== Voice SQL API Setup (Simple & Robust) ===" -ForegroundColor Green
Write-Host "Project: $ProjectPath" -ForegroundColor Yellow
Write-Host "Logs: $LogPath" -ForegroundColor Yellow

# Check admin privileges
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Error "❌ Must run as Administrator"
    exit 1
}

# Verify virtual environment
$venvPython = Join-Path $ProjectPath ".venv\Scripts\python.exe"
if (!(Test-Path $venvPython)) {
    Write-Error "❌ Virtual environment not found at: $venvPython"
    Write-Host "Full path checked: $venvPython"
    exit 1
}

$serverScript = Join-Path $ProjectPath "server_api.py"
if (!(Test-Path $serverScript)) {
    Write-Error "❌ server_api.py not found at: $serverScript"
    exit 1
}

Write-Host "✅ Found Python: $venvPython" -ForegroundColor Green
Write-Host "✅ Found Server: $serverScript" -ForegroundColor Green

# Create log directory
if (!(Test-Path $LogPath)) {
    New-Item -ItemType Directory -Path $LogPath -Force | Out-Null
    Write-Host "✅ Created log directory: $LogPath" -ForegroundColor Green
}

# Clean up any old scripts
$oldFiles = @("voice_sql_server.vbs", "voice_sql_manage.bat", "start_server.ps1")
foreach ($file in $oldFiles) {
    $filePath = Join-Path $ProjectPath $file
    if (Test-Path $filePath) {
        Remove-Item $filePath -Force
        Write-Host "🗑️ Removed old: $file" -ForegroundColor Yellow
    }
}

# SOLUTION: Use PowerShell script instead of VBScript
# This avoids all the path escaping issues with VBScript

$startupScript = @"
# start_server.ps1 - PowerShell startup script (no path issues)
Set-Location -Path "$ProjectPath"

# Log startup
`$logMsg = "[`$(Get-Date)] Starting Voice SQL API Server from: $ProjectPath"
Add-Content -Path "$LogPath\startup.log" -Value `$logMsg

# Start the server (hidden window)
`$processInfo = New-Object System.Diagnostics.ProcessStartInfo
`$processInfo.FileName = "$venvPython"
`$processInfo.Arguments = "server_api.py"
`$processInfo.WorkingDirectory = "$ProjectPath"
`$processInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
`$processInfo.CreateNoWindow = `$true

try {
    `$process = [System.Diagnostics.Process]::Start(`$processInfo)
    `$logMsg = "[`$(Get-Date)] Server started successfully. PID: `$(`$process.Id)"
    Add-Content -Path "$LogPath\startup.log" -Value `$logMsg
} catch {
    `$logMsg = "[`$(Get-Date)] Failed to start server: `$_"
    Add-Content -Path "$LogPath\startup.log" -Value `$logMsg
}
"@

$scriptPath = Join-Path $ProjectPath "start_server.ps1"
$startupScript | Out-File -FilePath $scriptPath -Encoding UTF8
Write-Host "✅ Created PowerShell startup script" -ForegroundColor Green

# Create management script
$managementScript = @"
@echo off
title Voice SQL Management
cls
echo ================================================================
echo                    Voice SQL API Management
echo ================================================================
echo.
echo Project Location: $ProjectPath
echo Log Directory:    $LogPath
echo.

echo Checking server status...
curl -s http://localhost:8000/health 2>nul
if %ERRORLEVEL% equ 0 (
    echo ✅ Server is responding on port 8000
    echo.
    echo Full server status:
    curl -s http://localhost:8000/health 2>nul | jq . 2>nul || curl -s http://localhost:8000/health
) else (
    echo ❌ Server is not responding on port 8000
)

echo.
echo ================================================================
echo Running Python processes:
tasklist /FI "IMAGENAME eq python.exe" /FO TABLE 2>nul

echo.
echo ================================================================
echo Recent startup log:
if exist "$LogPath\startup.log" (
    powershell "Get-Content '$LogPath\startup.log' -Tail 5 2>nul"
) else (
    echo No startup log found
)

echo.
echo Recent server log:
if exist "C:\Logs\voice_sql_api.log" (
    powershell "Get-Content 'C:\Logs\voice_sql_api.log' -Tail 5 2>nul"
) else (
    echo No server log found
)

echo.
echo ================================================================
echo Management Commands:
echo.
echo 1. Stop server:      taskkill /f /im python.exe
echo 2. Start task:       Start-ScheduledTask -TaskName "VoiceSQL API Server"
echo 3. Stop task:        Stop-ScheduledTask -TaskName "VoiceSQL API Server"
echo 4. Task status:      Get-ScheduledTask -TaskName "VoiceSQL API Server"
echo 5. Manual start:     powershell -File start_server.ps1
echo 6. View server log:  notepad C:\Logs\voice_sql_api.log
echo 7. View startup log: notepad $LogPath\startup.log
echo.
echo ================================================================
pause
"@

$managementPath = Join-Path $ProjectPath "voice_sql_manage.bat"
$managementScript | Out-File -FilePath $managementPath -Encoding UTF8
Write-Host "✅ Created management script" -ForegroundColor Green

# Get current user
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
Write-Host "Current user: $currentUser" -ForegroundColor Cyan

# Remove existing task
$taskName = "VoiceSQL API Server"
try {
    $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Write-Host "🗑️ Removing existing task..." -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
} catch {
    # Task didn't exist, that's fine
}

# Create scheduled task using PowerShell execution
Write-Host "Creating scheduled task..." -ForegroundColor Green

# Use PowerShell to execute our script (more reliable than VBScript)
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`"" -WorkingDirectory $ProjectPath
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 2)
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Highest

try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Voice SQL API server (PowerShell version)" -Force
    Write-Host "✅ Scheduled task created successfully" -ForegroundColor Green

    # Verify the task was created
    $task = Get-ScheduledTask -TaskName $taskName
    Write-Host "Task Status: $($task.State)" -ForegroundColor Cyan

} catch {
    Write-Error "❌ Failed to create scheduled task: $_"
    exit 1
}

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host "✅ Startup Script: start_server.ps1" -ForegroundColor Green
Write-Host "✅ Management: voice_sql_manage.bat" -ForegroundColor Green
Write-Host "✅ Scheduled Task: VoiceSQL API Server" -ForegroundColor Green
Write-Host "✅ Log Directory: $LogPath" -ForegroundColor Green
Write-Host "✅ Window Mode: Hidden (no visible windows)" -ForegroundColor Green

Write-Host ""
Write-Host "=== Quick Commands ===" -ForegroundColor Yellow
Write-Host "Manage Server:  .\voice_sql_manage.bat"
Write-Host "Start Task:     Start-ScheduledTask -TaskName 'VoiceSQL API Server'"
Write-Host "Stop Server:    taskkill /f /im python.exe"
Write-Host "Manual Test:    powershell -File start_server.ps1"

# Test the PowerShell script
Write-Host ""
$response = Read-Host "Test the PowerShell startup script now? (y/N)"
if ($response -eq 'y' -or $response -eq 'Y') {
    Write-Host "Testing PowerShell startup script..." -ForegroundColor Green

    # Run the PowerShell script
    Start-Process "powershell.exe" -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`"" -NoNewWindow

    Write-Host "Waiting 15 seconds for server to start..."
    for ($i = 15; $i -gt 0; $i--) {
        Write-Host "  $i..." -NoNewline
        Start-Sleep -Seconds 1
    }
    Write-Host ""

    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 10
        Write-Host "✅ SUCCESS! Server is responding" -ForegroundColor Green
        Write-Host "Status: $($health.status)" -ForegroundColor Green

        # Show some server info
        try {
            $status = Invoke-RestMethod -Uri "http://localhost:8000/status" -TimeoutSec 5
            Write-Host "Database: $($status.database.server_name)" -ForegroundColor Gray
            Write-Host "Security: $($status.database.security_mode)" -ForegroundColor Gray
        } catch {
            # Status endpoint might not be available
        }

        $stop = Read-Host "Stop test server? (Y/n)"
        if ($stop -ne 'n') {
            Stop-Process -Name "python" -Force -ErrorAction SilentlyContinue
            Write-Host "✅ Test server stopped" -ForegroundColor Green
        }
    } catch {
        Write-Warning "❌ Test failed: $_"
        Write-Host "Check logs: .\voice_sql_manage.bat" -ForegroundColor Yellow

        # Show recent logs
        if (Test-Path "$LogPath\startup.log") {
            Write-Host "Recent startup log:" -ForegroundColor Yellow
            Get-Content "$LogPath\startup.log" -Tail 3 | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
        }
    }
}

# Option to start the scheduled task
Write-Host ""
$response = Read-Host "Start the scheduled task now? (y/N)"
if ($response -eq 'y' -or $response -eq 'Y') {
    try {
        Start-ScheduledTask -TaskName $taskName
        Write-Host "✅ Scheduled task started!" -ForegroundColor Green
        Write-Host "Monitor with: .\voice_sql_manage.bat" -ForegroundColor Yellow
    } catch {
        Write-Warning "Failed to start scheduled task: $_"
    }
}

Write-Host ""
Write-Host "🎉 Setup Complete!" -ForegroundColor Green
Write-Host "The server will start automatically with Windows (hidden mode)" -ForegroundColor Green
Write-Host "Use .\voice_sql_manage.bat to monitor and manage the server" -ForegroundColor Green

Write-Host ""
Write-Host "=== Files Created ===" -ForegroundColor Cyan
Write-Host "• start_server.ps1 - PowerShell startup script (no path issues!)" -ForegroundColor Green
Write-Host "• voice_sql_manage.bat - Management and monitoring" -ForegroundColor Green
Write-Host "• Scheduled Task: VoiceSQL API Server" -ForegroundColor Green