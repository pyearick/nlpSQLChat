# start_server.ps1 - PowerShell startup script with port cleanup and log redirection
Set-Location -Path "C:\Users\pyearick.CRP\OneDrive - CRP Industries Inc\CRPAF\PycharmProjects\nlp-sql-in-a-box"

# Ensure log directory exists
$logDir = "C:/Logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

# Log startup
$logMsg = "[$(Get-Date)] Starting Voice SQL API Server from: $PWD"
Add-Content -Path "$logDir\startup.log" -Value $logMsg

# Clean up port 8000
try {
    $logMsg = "[$(Get-Date)] Checking for processes on port 8000..."
    Add-Content -Path "$logDir\startup.log" -Value $logMsg
    $netstatOutput = netstat -aon | Select-String ":8000.*LISTENING"
    if ($netstatOutput) {
        foreach ($line in $netstatOutput) {
            $processId = ($line -split "\s+")[-1]  # Use processId instead of PID
            $logMsg = "[$(Get-Date)] Terminating process with PID $processId on port 8000"
            Add-Content -Path "$logDir\startup.log" -Value $logMsg
            Stop-Process -Id $processId -Force -ErrorAction Stop
        }
    } else {
        $logMsg = "[$(Get-Date)] No processes found on port 8000"
        Add-Content -Path "$logDir\startup.log" -Value $logMsg
    }
} catch {
    $logMsg = "[$(Get-Date)] Failed to check or free port 8000: $_"
    Add-Content -Path "$logDir\startup.log" -Value $logMsg
}

# Start the server with log redirection
$processInfo = New-Object System.Diagnostics.ProcessStartInfo
$processInfo.FileName = "C:\Users\pyearick.CRP\OneDrive - CRP Industries Inc\CRPAF\PycharmProjects\nlp-sql-in-a-box\.venv\Scripts\python.exe"
$processInfo.Arguments = "server_api.py >> $logDir\voice_sql_api_task.log 2>&1"
$processInfo.WorkingDirectory = "C:\Users\pyearick.CRP\OneDrive - CRP Industries Inc\CRPAF\PycharmProjects\nlp-sql-in-a-box"
$processInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$processInfo.CreateNoWindow = $true

try {
    $process = [System.Diagnostics.Process]::Start($processInfo)
    $logMsg = "[$(Get-Date)] Server started successfully. PID: $($process.Id)"
    Add-Content -Path "$logDir\startup.log" -Value $logMsg
} catch {
    $logMsg = "[$(Get-Date)] Failed to start server: $_"
    Add-Content -Path "$logDir\startup.log" -Value $logMsg
}