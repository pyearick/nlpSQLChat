$pidFile = "C:\Logs\server.pid"

if (Test-Path $pidFile) {
    $pid = Get-Content $pidFile
    if ($pid -match '^\d+$') {
        try {
            Write-Host "Stopping server process with PID $pid..."
            Stop-Process -Id $pid -Force
            Write-Host "Process $pid terminated."
            Remove-Item $pidFile
        }
        catch {
            $errMsg = $_.Exception.Message
            Write-Host "Failed to terminate process with PID $pid: $errMsg"
        }
    } else {
        Write-Host "PID file does not contain a valid PID: $pid"
    }
} else {
    Write-Host "PID file not found: $pidFile"
}
