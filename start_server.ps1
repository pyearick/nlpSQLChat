# start_server.ps1 - PowerShell startup script with proper process management
Set-Location -Path "C:\Users\pyearick.CRP\OneDrive - CRP Industries Inc\CRPAF\PycharmProjects\nlp-sql-in-a-box"

# Ensure log directory exists
$logDir = "C:/Logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

# Single unified log file
$logFile = "$logDir\VoiceSQLAPIServer.log"

# Log startup
$logMsg = "[$(Get-Date)] ========== Starting Voice SQL API Server =========="
Add-Content -Path $logFile -Value $logMsg
$logMsg = "[$(Get-Date)] Working Directory: $PWD"
Add-Content -Path $logFile -Value $logMsg

# Clean up port 8000 and any existing server processes
try {
    $logMsg = "[$(Get-Date)] Cleaning up existing processes..."
    Add-Content -Path $logFile -Value $logMsg

    # Kill any existing server_api.py processes
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*server_api.py*"
    } | ForEach-Object {
        $logMsg = "[$(Get-Date)] Killing existing server_api.py process PID: $($_.Id)"
        Add-Content -Path $logFile -Value $logMsg
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }

    # Also check by port
    $netstatOutput = netstat -aon | Select-String ":8000.*LISTENING"
    if ($netstatOutput) {
        foreach ($line in $netstatOutput) {
            $processId = ($line -split "\s+")[-1]
            $logMsg = "[$(Get-Date)] Terminating process with PID $processId on port 8000"
            Add-Content -Path $logFile -Value $logMsg
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }

    # Wait for port to be released
    Start-Sleep -Seconds 3
    $logMsg = "[$(Get-Date)] Cleanup completed, waiting 3 seconds for port release"
    Add-Content -Path $logFile -Value $logMsg

} catch {
    $logMsg = "[$(Get-Date)] Error during cleanup: $_"
    Add-Content -Path $logFile -Value $logMsg
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

    # Wait longer for server initialization (Azure credentials can be slow)
    $logMsg = "[$(Get-Date)] Waiting for server initialization..."
    Add-Content -Path $logFile -Value $logMsg

    # Progressive health checking with retries
    $maxAttempts = 6
    $attempt = 1
    $serverReady = $false

    while ($attempt -le $maxAttempts -and !$serverReady) {
        Start-Sleep -Seconds 10  # Wait 10 seconds between attempts

        $logMsg = "[$(Get-Date)] Health check attempt $attempt of $maxAttempts..."
        Add-Content -Path $logFile -Value $logMsg

        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 5 -UseBasicParsing
            if ($response.StatusCode -eq 200) {
                $logMsg = "[$(Get-Date)] ✅ Server health check PASSED - server is responding (attempt $attempt)"
                Add-Content -Path $logFile -Value $logMsg
                $serverReady = $true
            }
        } catch {
            $logMsg = "[$(Get-Date)] ❌ Health check attempt $attempt failed: $_"
            Add-Content -Path $logFile -Value $logMsg

            # Check if process is still alive
            if ($process.HasExited) {
                $logMsg = "[$(Get-Date)] 💥 ERROR: Server process has exited during startup! Exit code: $($process.ExitCode)"
                Add-Content -Path $logFile -Value $logMsg
                break
            } else {
                $logMsg = "[$(Get-Date)] 🔄 Server process still running (PID: $($process.Id)), will retry..."
                Add-Content -Path $logFile -Value $logMsg
            }
        }
        $attempt++
    }

    if (!$serverReady) {
        $logMsg = "[$(Get-Date)] ⚠️ WARNING: Server did not respond to health checks within 60 seconds"
        Add-Content -Path $logFile -Value $logMsg

        # Check port status
        $portCheck = netstat -aon | Select-String ":8000.*LISTENING"
        if ($portCheck) {
            $logMsg = "[$(Get-Date)] 🔍 Port 8000 is bound, server may still be starting up..."
            Add-Content -Path $logFile -Value $logMsg
        } else {
            $logMsg = "[$(Get-Date)] 🚫 Port 8000 is not bound - server startup failed"
            Add-Content -Path $logFile -Value $logMsg
        }
    }

    # Set up cleanup handler for when PowerShell exits (removes complexity)
    Register-EngineEvent PowerShell.Exiting -Action {
        $pidFile = "C:\Logs\voicesql_server.pid"
        $logFile = "C:\Logs\VoiceSQLAPIServer.log"
        if (Test-Path $pidFile) {
            try {
                $serverPid = Get-Content $pidFile
                $logMsg = "[$(Get-Date)] 🛑 PowerShell exiting - cleaning up server PID: $serverPid"
                Add-Content -Path $logFile -Value $logMsg
                Stop-Process -Id $serverPid -Force -ErrorAction SilentlyContinue
                Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
            } catch {
                # Ignore cleanup errors
            }
        }
    } | Out-Null

    # Keep PowerShell alive to maintain process tree control
    # This ensures Task Scheduler can kill the entire tree
    $logMsg = "[$(Get-Date)] 👁️ Monitoring server process (PID: $($process.Id))..."
    Add-Content -Path $logFile -Value $logMsg

    # Simple monitoring loop - keeps script alive for proper Task Scheduler control
    try {
        while (!$process.HasExited) {
            Start-Sleep -Seconds 30

            # Quick health check (optional) - only occasionally to reduce log noise
            if ((Get-Random -Maximum 10) -eq 0) {  # Only check occasionally
                try {
                    $null = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 3 -UseBasicParsing
                } catch {
                    $logMsg = "[$(Get-Date)] 🚨 Health check failed - server may need attention"
                    Add-Content -Path $logFile -Value $logMsg
                }
            }
        }
    } catch {
        # Handle any interruption (like Task Scheduler stop)
        $logMsg = "[$(Get-Date)] 🛑 Monitoring interrupted - cleaning up..."
        Add-Content -Path $logFile -Value $logMsg
    } finally {
        # Ensure cleanup when script exits
        if ($process -and !$process.HasExited) {
            $logMsg = "[$(Get-Date)] 💀 Force-killing server process..."
            Add-Content -Path $logFile -Value $logMsg
            $process.Kill()
        }
        $logMsg = "[$(Get-Date)] ========== PowerShell script exiting =========="
        Add-Content -Path $logFile -Value $logMsg
    }

} catch {
    $logMsg = "[$(Get-Date)] 💥 Failed to start server: $_"
    Add-Content -Path $logFile -Value $logMsg
} finally {
    # Cleanup PID file
    if (Test-Path $pidFile) {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}