param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [string]$BoardHost = "auto",
  [string[]]$BoardHostCandidates = @("169.254.132.113", "192.168.0.233", "192.168.0.2"),
  [int]$Port = 22,
  [string]$User = "root",
  [string]$Password = "root",
  [string]$RemoteDir = "/home/root/irdet_demo",
  [ValidateSet("gray8", "gray8_pl_probe", "gray8_pl_real_layer", "dump_runtime_dw_input", "runtime_dw_pl_compare", "inpath_dw_cpu_full", "inpath_dw_pl_full", "tensor", "pl_selftest", "full_demo", "none")]
  [string]$Mode = "gray8",
  [string]$ComPort = "",
  [int]$BaudRate = 115200,
  [switch]$SkipPackage,
  [switch]$SkipArmBuild,
  [switch]$CleanRemote,
  [switch]$DeleteStale,
  [switch]$SkipSerialLinkPrep
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
    if (Test-TcpPortQuick -HostName $RequestedHost -Port $Port) {
      return $RequestedHost
    }
    throw "Unable to reach requested AC880 host $RequestedHost`:$Port"
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
$prepareSerialLinkScript = Join-Path $RepoRoot "pc\scripts\prepare_ac880_ssh_link_over_serial.ps1"
$bundleDir = Join-Path $RepoRoot "build\zynq_linux_demo_bundle"
$venvPython = Join-Path $RepoRoot ".venv-train\Scripts\python.exe"

if (!(Test-Path $packageScript)) { throw "Script not found: $packageScript" }
if (!(Test-Path $deployScript)) { throw "Script not found: $deployScript" }
if (!(Test-Path $prepareSerialLinkScript)) { throw "Script not found: $prepareSerialLinkScript" }

if (Test-Path $venvPython) {
  $python = $venvPython
} else {
  $python = "python"
}

Write-Host "Checking paramiko using $python ..."
& $python -c "import paramiko" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Installing paramiko into the selected Python environment..."
  & $python -m pip install paramiko
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to install paramiko"
  }
}

$ResolvedBoardHost = $null
try {
  $ResolvedBoardHost = Resolve-BoardHost -RequestedHost $BoardHost -Candidates $BoardHostCandidates -Port $Port
} catch {
  if ($SkipSerialLinkPrep.IsPresent -or [string]::IsNullOrWhiteSpace($ComPort)) {
    throw
  }

  $PrepareHost = if (-not [string]::IsNullOrWhiteSpace($BoardHost) -and $BoardHost.ToLowerInvariant() -ne "auto") {
    $BoardHost
  } else {
    $BoardHostCandidates[0]
  }

  Write-Host "Board SSH is not reachable yet. Preparing a temporary network alias over serial on $ComPort ..."
  & $prepareSerialLinkScript `
    -RepoRoot $RepoRoot `
    -ComPort $ComPort `
    -BaudRate $BaudRate `
    -BoardHost $PrepareHost `
    -TcpPort $Port
  if ($LASTEXITCODE -ne 0) {
    throw "prepare_ac880_ssh_link_over_serial.ps1 failed with exit code $LASTEXITCODE"
  }

  $ResolvedBoardHost = Resolve-BoardHost -RequestedHost $BoardHost -Candidates $BoardHostCandidates -Port $Port
}

Write-Host "Resolved AC880 host: $ResolvedBoardHost"

if ($SkipPackage.IsPresent) {
  if (!(Test-Path $bundleDir)) {
    throw "Bundle directory not found: $bundleDir"
  }
  Write-Host "Skipping bundle packaging and reusing existing bundle at $bundleDir"
} else {
  Write-Host "Packaging AC880 Linux demo bundle..."
  $packageArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $packageScript,
    "-RepoRoot", $RepoRoot
  )
  if ($SkipArmBuild.IsPresent) {
    $packageArgs += "-SkipArmBuild"
  }
  & powershell @packageArgs
  if ($LASTEXITCODE -ne 0) {
    throw "package_zynq_linux_demo.ps1 failed with exit code $LASTEXITCODE"
  }
}

$deployArgs = @(
  $deployScript,
  "--bundle-dir", $bundleDir,
  "--host", $ResolvedBoardHost,
  "--port", $Port,
  "--user", $User,
  "--password", $Password,
  "--remote-dir", $RemoteDir,
  "--mode", $Mode
)
if ($CleanRemote.IsPresent) {
  $deployArgs += "--clean"
}
if ($DeleteStale.IsPresent) {
  $deployArgs += "--delete-stale"
}

Write-Host "Deploying bundle to $ResolvedBoardHost ..."
& $python @deployArgs
if ($LASTEXITCODE -ne 0) {
  throw "deploy_ac880_linux_demo.py failed with exit code $LASTEXITCODE"
}
