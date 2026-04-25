param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [string]$ComPort = "COM3",
  [int]$BaudRate = 115200,
  [string]$BoardHost = "169.254.132.113",
  [string]$BoardInterface = "eth0",
  [int]$TcpPort = 22
)

$ErrorActionPreference = "Stop"

$serialInvokeScript = Join-Path $RepoRoot "pc\scripts\invoke_ac880_serial_command.ps1"
if (!(Test-Path $serialInvokeScript)) {
  throw "Script not found: $serialInvokeScript"
}

function Test-TcpPortQuick {
  param(
    [Parameter(Mandatory = $true)][string]$HostName,
    [Parameter(Mandatory = $true)][int]$Port,
    [int]$TimeoutMs = 1500
  )

  $client = $null
  $async = $null
  try {
    $client = New-Object System.Net.Sockets.TcpClient
    $async = $client.BeginConnect($HostName, $Port, $null, $null)
    if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
      return $false
    }
    $client.EndConnect($async) | Out-Null
    return $true
  } catch {
    return $false
  } finally {
    if ($async -and $async.AsyncWaitHandle) {
      $async.AsyncWaitHandle.Close()
    }
    if ($client) {
      $client.Close()
    }
  }
}

Write-Host "Preparing AC880 SSH link over serial on $ComPort@$BaudRate ..."
& $serialInvokeScript `
  -ComPort $ComPort `
  -BaudRate $BaudRate `
  -Commands @(
    "ip link set $BoardInterface up >/dev/null 2>&1 || true",
    "ip addr add $BoardHost/16 dev $BoardInterface 2>/dev/null || true",
    "ip addr show dev $BoardInterface",
    "ps | grep dropbear | grep -v grep || true"
  ) `
  -InterCommandDelayMs 500 `
  -IdleThresholdMs 3000 `
  -MaxReadSeconds 30
if ($LASTEXITCODE -ne 0) {
  throw "invoke_ac880_serial_command.ps1 failed with exit code $LASTEXITCODE"
}

Start-Sleep -Milliseconds 800
if (!(Test-TcpPortQuick -HostName $BoardHost -Port $TcpPort -TimeoutMs 3000)) {
  throw "AC880 SSH endpoint is still unreachable at $BoardHost`:$TcpPort after serial network preparation"
}

Write-Host "AC880 SSH link ready at $BoardHost`:$TcpPort"
