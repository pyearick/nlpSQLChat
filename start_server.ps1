# start_server.ps1 - PowerShell startup script with proper process management
Set-Location -Path "C:\Users\pyearick.CRP\OneDrive - CRP Industries Inc\CRPAF\PycharmProjects\nlp-sql-in-a-box"

# Ensure log directory exists
$logDir = "C:/Logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

# Log startup
$logMsg = "[$(Get-Date)] Starting Voice SQL API Server from: $PWD"
Add-Content -Path "$logDir\startup.log" -Value $logMsg

# Clean up port 8000 and any existing server processes
try {
    $logMsg = "[$(Get-Date)] Cleaning up existing processes..."
    Add-Content -Path "$logDir\startup.log" -Value $logMsg

    # Kill any existing server_api.py processes
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*server_api.py*"
    } | ForEach-Object {
        $logMsg = "[$(Get-Date)] Killing existing server_api.py process PID: $($_.Id)"
        Add-Content -Path "$logDir\startup.log" -Value $logMsg
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }

    # Also check by port
    $netstatOutput = netstat -aon | Select-String ":8000.*LISTENING"
    if ($netstatOutput) {
        foreach ($line in $netstatOutput) {
            $processId = ($line -split "\s+")[-1]
            $logMsg = "[$(Get-Date)] Terminating process with PID $processId on port 8000"
            Add-Content -Path "$logDir\startup.log" -Value $logMsg
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }

    # Wait for port to be released
    Start-Sleep -Seconds 3

} catch {
    $logMsg = "[$(Get-Date)] Error during cleanup: $_"
    Add-Content -Path "$logDir\startup.log" -Value $logMsg
}

# Store PID for cleanup later
$pidFile = "$logDir\voicesql_server.pid"

# Start the server
try {
    $logMsg = "[$(Get-Date)] Starting Python server..."
    Add-Content -Path "$logDir\startup.log" -Value $logMsg

    $pythonPath = "C:\Users\pyearick.CRP\OneDrive - CRP Industries Inc\CRPAF\PycharmProjects\nlp-sql-in-a-box\.venv\Scripts\python.exe"
    $serverScript = "server_api.py"
    $logFile = "$logDir\voice_sql_api_task.log"

    # Start the server process with tight parent-child relationship
    # Using -NoNewWindow -PassThru creates stronger process tree coupling
    $process = Start-Process -FilePath $pythonPath -ArgumentList $serverScript -WorkingDirectory $PWD -NoNewWindow -PassThru -RedirectStandardOutput "$logDir\server_output.log" -RedirectStandardError "$logDir\server_error.log"

    # Store the PID for later cleanup
    $process.Id | Set-Content -Path $pidFile

    # Wait and verify the server is responding
    Start-Sleep -Seconds 5

    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 10 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            $logMsg = "[$(Get-Date)] Server health check PASSED - server is responding"
            Add-Content -Path "$logDir\startup.log" -Value $logMsg
        }
    } catch {
        $logMsg = "[$(Get-Date)] Server health check FAILED: $_"
        Add-Content -Path "$logDir\startup.log" -Value $logMsg
    }

    # Set up cleanup handler for when PowerShell exits (removes complexity)
    Register-EngineEvent PowerShell.Exiting -Action {
        $pidFile = "C:\Logs\voicesql_server.pid"
        if (Test-Path $pidFile) {
            try {
                $serverPid = Get-Content $pidFile
                Stop-Process -Id $serverPid -Force -ErrorAction SilentlyContinue
                Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
            } catch {
                # Ignore cleanup errors
            }
        }
    } | Out-Null

    # Keep PowerShell alive to maintain process tree control
    # This ensures Task Scheduler can kill the entire tree
    $logMsg = "[$(Get-Date)] Monitoring server process (PID: $($process.Id))..."
    Add-Content -Path "$logDir\startup.log" -Value $logMsg

    # Simple monitoring loop - keeps script alive for proper Task Scheduler control
    try {
        while (!$process.HasExited) {
            Start-Sleep -Seconds 30

            # Quick health check (optional)
            if ((Get-Random -Maximum 10) -eq 0) {  # Only check occasionally
                try {
                    $null = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 3 -UseBasicParsing
                } catch {
                    $logMsg = "[$(Get-Date)] Health check failed - server may need attention"
                    Add-Content -Path "$logDir\startup.log" -Value $logMsg
                }
            }
        }
    } catch {
        # Handle any interruption (like Task Scheduler stop)
        $logMsg = "[$(Get-Date)] Monitoring interrupted - cleaning up..."
        Add-Content -Path "$logDir\startup.log" -Value $logMsg
    } finally {
        # Ensure cleanup when script exits
        if ($process -and !$process.HasExited) {
            $logMsg = "[$(Get-Date)] Force-killing server process..."
            Add-Content -Path "$logDir\startup.log" -Value $logMsg
            $process.Kill()
        }
    }

} catch {
    $logMsg = "[$(Get-Date)] Failed to start server: $_"
    Add-Content -Path "$logDir\startup.log" -Value $logMsg
} finally {
    # Cleanup PID file
    if (Test-Path $pidFile) {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}