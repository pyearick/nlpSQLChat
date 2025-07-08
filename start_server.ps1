Set-Location -Path "C:\Users\pyearick.CRP\OneDrive - CRP Industries Inc\CRPAF\PycharmProjects\nlp-sql-in-a-box"

# Unified log file
$logFile = "C:\Logs\VoiceSQLAPIServer.log"
$pidFile = "C:\Logs\server.pid"

# Ensure log directory exists
if (-not (Test-Path "C:\Logs")) {
    New-Item -ItemType Directory -Path "C:\Logs" | Out-Null
}

# Log startup
$logMsg = "[$(Get-Date)] ========== PowerShell Starting Voice SQL API Server =========="
Add-Content -Path $logFile -Value $logMsg

# Clean up existing server process if PID file exists
if (Test-Path $pidFile) {
    try {
        $existingPid = Get-Content $pidFile
        if ($existingPid) {
            $logMsg = "[$(Get-Date)] Found existing PID file with PID: $existingPid. Attempting to terminate..."
            Add-Content -Path $logFile -Value $logMsg
            Stop-Process -Id $existingPid -Force -ErrorAction SilentlyContinue
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
            $logMsg = "[$(Get-Date)] Existing process terminated and PID file removed."
            Add-Content -Path $logFile -Value $logMsg
        }
    } catch {
        $logMsg = "[$(Get-Date)] Warning: Failed to terminate existing process: $_"
        Add-Content -Path $logFile -Value $logMsg
    }
}

# Start the server
try {
    $pythonPath = "C:\Users\pyearick.CRP\OneDrive - CRP Industries Inc\CRPAF\PycharmProjects\nlp-sql-in-a-box\.venv\Scripts\python.exe"
    $serverScript = "server_api.py"

    $logMsg = "[$(Get-Date)] Starting Python server..."
    Add-Content -Path $logFile -Value $logMsg

    $process = Start-Process -FilePath $pythonPath -ArgumentList $serverScript -WorkingDirectory $PWD -WindowStyle Hidden -PassThru

    $logMsg = "[$(Get-Date)] Server started with PID: $($process.Id)"
    Add-Content -Path $logFile -Value $logMsg

    # Wait for server to initialize
    Start-Sleep -Seconds 10

    # Monitor the server process
    while (-not $process.HasExited) {
        Start-Sleep -Seconds 30
    }

    $logMsg = "[$(Get-Date)] 🛑 Server process has exited"
    Add-Content -Path $logFile -Value $logMsg

} catch {
    $logMsg = "[$(Get-Date)] 💥 Failed to start server: $_"
    Add-Content -Path $logFile -Value $logMsg
} finally {
    # Cleanup PID file if it exists
    if (Test-Path $pidFile) {
        try {
            Remove-Item $pidFile -Force
            $logMsg = "[$(Get-Date)] PID file removed during cleanup."
            Add-Content -Path $logFile -Value $logMsg
        } catch {
            $logMsg = "[$(Get-Date)] Warning: Failed to remove PID file: $_"
            Add-Content -Path $logFile -Value $logMsg
        }
    }

    $logMsg = "[$(Get-Date)] ========== PowerShell script exiting =========="
    Add-Content -Path $logFile -Value $logMsg
}