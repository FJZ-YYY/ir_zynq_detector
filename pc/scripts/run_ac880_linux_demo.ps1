param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [string]$BoardHost = "auto",
  [string[]]$BoardHostCandidates = @("169.254.132.113", "192.168.0.233", "192.168.0.2"),
  [int]$Port = 22,
  [string]$User = "root",
  [string]$Password = "root",
  [string]$RemoteDir = "/home/root/irdet_demo",
  [ValidateSet("gray8", "tensor", "pl_selftest", "none")]
  [string]$Mode = "gray8"
)

$ErrorActionPreference = "Stop"

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

function Resolve-BoardHost {
  param(
    [Parameter(Mandatory = $true)][string]$RequestedHost,
    [Parameter(Mandatory = $true)][string[]]$Candidates,
    [Parameter(Mandatory = $true)][int]$Port
  )

  if (-not [string]::IsNullOrWhiteSpace($RequestedHost) -and $RequestedHost.ToLowerInvariant() -ne "auto") {
    return $RequestedHost
  }

  foreach ($candidate in $Candidates) {
    Write-Host "Probing AC880 host $candidate`:$Port ..."
    if (Test-TcpPortQuick -HostName $candidate -Port $Port) {
      return $candidate
    }
  }

  throw "Unable to reach AC880 Linux on any candidate hosts: $($Candidates -join ', ')"
}

$packageScript = Join-Path $RepoRoot "pc\scripts\package_zynq_linux_demo.ps1"
$deployScript = Join-Path $RepoRoot "pc\scripts\deploy_ac880_linux_demo.py"
$bundleDir = Join-Path $RepoRoot "build\zynq_linux_demo_bundle"

if (!(Test-Path $packageScript)) { throw "Script not found: $packageScript" }
if (!(Test-Path $deployScript)) { throw "Script not found: $deployScript" }

$python = "python"

Write-Host "Checking paramiko..."
& $python -c "import paramiko" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Installing paramiko into the current Python user environment..."
  & $python -m pip install --user paramiko
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to install paramiko"
  }
}

$ResolvedBoardHost = Resolve-BoardHost -RequestedHost $BoardHost -Candidates $BoardHostCandidates -Port $Port
Write-Host "Resolved AC880 host: $ResolvedBoardHost"

Write-Host "Packaging AC880 Linux demo bundle..."
& powershell -ExecutionPolicy Bypass -File $packageScript -RepoRoot $RepoRoot
if ($LASTEXITCODE -ne 0) {
  throw "package_zynq_linux_demo.ps1 failed with exit code $LASTEXITCODE"
}

Write-Host "Deploying bundle to $ResolvedBoardHost ..."
& $python $deployScript `
  --bundle-dir $bundleDir `
  --host $ResolvedBoardHost `
  --port $Port `
  --user $User `
  --password $Password `
  --remote-dir $RemoteDir `
  --mode $Mode
if ($LASTEXITCODE -ne 0) {
  throw "deploy_ac880_linux_demo.py failed with exit code $LASTEXITCODE"
}
