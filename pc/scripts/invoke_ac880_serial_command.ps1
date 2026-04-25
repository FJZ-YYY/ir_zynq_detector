param(
  [string]$ComPort = "COM3",
  [int]$BaudRate = 115200,
  [string[]]$Commands,
  [int]$StartupDelayMs = 300,
  [int]$InterCommandDelayMs = 300,
  [int]$IdlePollMs = 200,
  [int]$IdleThresholdMs = 1000,
  [int]$MaxReadSeconds = 20
)

$ErrorActionPreference = "Stop"

if ($null -eq $Commands -or $Commands.Count -eq 0) {
  throw "At least one serial command must be provided."
}

$port = New-Object System.IO.Ports.SerialPort $ComPort, $BaudRate, 'None', 8, 'one'
$port.ReadTimeout = 500
$port.WriteTimeout = 500
$port.NewLine = "`n"

try {
  $port.Open()
  Start-Sleep -Milliseconds $StartupDelayMs
  $port.DiscardInBuffer()
  $port.Write("`r`n")
  Start-Sleep -Milliseconds $InterCommandDelayMs

  foreach ($command in $Commands) {
    $port.Write(($command + "`n"))
    Start-Sleep -Milliseconds $InterCommandDelayMs
  }

  $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
  $idleMs = 0
  $output = ""
  while ($stopwatch.Elapsed.TotalSeconds -lt $MaxReadSeconds) {
    $chunk = $port.ReadExisting()
    if (![string]::IsNullOrEmpty($chunk)) {
      $output += $chunk
      $idleMs = 0
    } else {
      $idleMs += $IdlePollMs
      if ($idleMs -ge $IdleThresholdMs) {
        break
      }
    }
    Start-Sleep -Milliseconds $IdlePollMs
  }

  Write-Output $output
} finally {
  if ($port.IsOpen) {
    $port.Close()
  }
}
