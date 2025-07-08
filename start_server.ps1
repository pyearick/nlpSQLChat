# start_server.ps1 - Simplified version that avoids stdout redirect conflicts
Set-Location -Path "C:\Users\pyearick.CRP\OneDrive - CRP Industries Inc\CRPAF\PycharmProjects\nlp-sql-in-a-box"

# Single unified log file
$logFile = "C:\Logs\VoiceSQLAPIServer.log"

# Ensure log directory exists
if (-not (Test-Path "C:\Logs")) {
    New-Item -ItemType Directory -Path "C:\Logs" | Out-Null
}

# Log startup
$logMsg = "[$(Get-Date)] ========== PowerShell Starting Voice SQL API Server =========="
Add-Content -Path $logFile -Value $logMsg
$logMsg = "[$(Get-Date)] Working Directory: $PWD"
Add-Content -Path $logFile -Value $logMsg

# Clean up existing processes
try {
    $logMsg = "[$(Get-Date)] Cleaning up existing processes..."
    Add-Content -Path $logFile -Value $logMsg

    # Kill any existing server processes
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*server_api.py*"
    } | ForEach-Object {
        $logMsg = "[$(Get-Date)] Killing existing server_api.py process PID: $($_.Id)"
        Add-Content -Path $logFile -Value $logMsg
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }

    # Also kill by port
    $netstatOutput = netstat -aon | Select-String ":8000.*LISTENING"
    if ($netstatOutput) {
        foreach ($line in $netstatOutput) {
            $processId = ($line -split "\s+")[-1]
            $logMsg = "[$(Get-Date)] Terminating process with PID $processId on port 8000"
            Add-Content -Path $logFile -Value $logMsg
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }

    Start-Sleep -Seconds 3
    $logMsg = "[$(Get-Date)] Cleanup completed"
    Add-Content -Path $logFile -Value $logMsg

} catch {
    $logMsg = "[$(Get-Date)] Error during cleanup: $_"
    Add-Content -Path $logFile -Value $logMsg
}

# Start the server
try {
    $pythonPath = "C:\Users\pyearick.CRP\OneDrive - CRP Industries Inc\CRPAF\PycharmProjects\nlp-sql-in-a-box\.venv\Scripts\python.exe"
    $serverScript = "server_api.py"

    $logMsg = "[$(Get-Date)] Starting Python server (no stdout redirect to avoid handle conflicts)..."
    Add-Content -Path $logFile -Value $logMsg

    # Start server WITHOUT redirecting stdout/stderr to avoid WinError 6
    # The Python script will handle its own logging to the same unified log file
    $process = Start-Process -FilePath $pythonPath -ArgumentList $serverScript -WorkingDirectory $PWD -WindowStyle Hidden -PassThru

    $logMsg = "[$(Get-Date)] Server started with PID: $($process.Id)"
    Add-Content -Path $logFile -Value $logMsg

    # Health check with retries
    $maxAttempts = 6
    $attempt = 1
    $serverReady = $false

    while ($attempt -le $maxAttempts -and !$serverReady) {
        Start-Sleep -Seconds 10

        $logMsg = "[$(Get-Date)] Health check attempt $attempt of $maxAttempts..."
        Add-Content -Path $logFile -Value $logMsg

        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 5 -UseBasicParsing
            if ($response.StatusCode -eq 200) {
                $logMsg = "[$(Get-Date)] ✅ Server health check PASSED - server is responding!"
                Add-Content -Path $logFile -Value $logMsg
                $serverReady = $true
            }
        } catch {
            if ($process.HasExited) {
                $logMsg = "[$(Get-Date)] 💥 ERROR: Server process exited! Exit code: $($process.ExitCode)"
                Add-Content -Path $logFile -Value $logMsg
                break
            } else {
                $logMsg = "[$(Get-Date)] 🔄 Health check failed, server still starting... ($_)"
                Add-Content -Path $logFile -Value $logMsg
            }
        }
        $attempt++
    }

    if ($serverReady) {
        $logMsg = "[$(Get-Date)] 🎉 Server startup completed successfully!"
        Add-Content -Path $logFile -Value $logMsg
    } else {
        $logMsg = "[$(Get-Date)] ⚠️ Server did not respond within 60 seconds"
        Add-Content -Path $logFile -Value $logMsg
    }

    # Monitor the server process
    $logMsg = "[$(Get-Date)] 👁️ Monitoring server process..."
    Add-Content -Path $logFile -Value $logMsg

    # Keep PowerShell alive to maintain process control
    while (!$process.HasExited) {
        Start-Sleep -Seconds 30
    }

    $logMsg = "[$(Get-Date)] 🛑 Server process has exited"
    Add-Content -Path $logFile -Value $logMsg

} catch {
    $logMsg = "[$(Get-Date)] 💥 Failed to start server: $_"
    Add-Content -Path $logFile -Value $logMsg
} finally {
    $logMsg = "[$(Get-Date)] ========== PowerShell script exiting =========="
    Add-Content -Path $logFile -Value $logMsg
}