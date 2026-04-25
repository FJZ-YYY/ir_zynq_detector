param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [string]$BoardHost = "auto",
  [string[]]$BoardHostCandidates = @("169.254.132.113", "192.168.0.233", "192.168.0.2"),
  [int]$Port = 22,
  [string]$User = "root",
  [string]$Password = "root",
  [string]$RemoteDir = "/home/root/irdet_demo",
  [string]$Image,
  [string]$DatasetRoot,
  [string]$Match,
  [int]$Index = 0,
  [ValidateSet("first", "random")]
  [string]$Pick = "first",
  [switch]$RefreshBundle,
  [string]$ResultJson,
  [string]$AnnotatedOut,
  [switch]$WithGt
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

$python = "python"
$deployBundleScript = Join-Path $RepoRoot "pc\scripts\run_ac880_linux_demo.ps1"
$inferScript = Join-Path $RepoRoot "pc\scripts\infer_ac880_linux_image.py"

if (!(Test-Path $inferScript)) { throw "Script not found: $inferScript" }
if (!(Test-Path $deployBundleScript)) { throw "Script not found: $deployBundleScript" }

if ([string]::IsNullOrWhiteSpace($Image) -and [string]::IsNullOrWhiteSpace($DatasetRoot)) {
  throw "Either -Image or -DatasetRoot must be provided."
}
if (![string]::IsNullOrWhiteSpace($Image) -and ![string]::IsNullOrWhiteSpace($DatasetRoot)) {
  throw "Use either -Image or -DatasetRoot, not both."
}

Write-Host "Checking Python dependencies..."
& $python -c "import PIL, paramiko"
if ($LASTEXITCODE -ne 0) {
  Write-Host "Installing required Python packages..."
  & $python -m pip install --user pillow paramiko
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to install pillow/paramiko"
  }
}

$ResolvedBoardHost = Resolve-BoardHost -RequestedHost $BoardHost -Candidates $BoardHostCandidates -Port $Port
Write-Host "Resolved AC880 host: $ResolvedBoardHost"

if ($RefreshBundle) {
  Write-Host "Refreshing remote AC880 Linux demo bundle..."
  & powershell -ExecutionPolicy Bypass -File $deployBundleScript `
    -RepoRoot $RepoRoot `
    -BoardHost $ResolvedBoardHost `
    -Port $Port `
    -User $User `
    -Password $Password `
    -RemoteDir $RemoteDir `
    -Mode none
  if ($LASTEXITCODE -ne 0) {
    throw "run_ac880_linux_demo.ps1 failed with exit code $LASTEXITCODE"
  }
}

$args = @(
  $inferScript,
  "--host", $ResolvedBoardHost,
  "--port", $Port,
  "--user", $User,
  "--password", $Password,
  "--remote-dir", $RemoteDir,
  "--pick", $Pick,
  "--index", $Index
)

if (![string]::IsNullOrWhiteSpace($Image)) {
  $args += @("--image", $Image)
} else {
  $args += @("--dataset-root", $DatasetRoot)
  if (![string]::IsNullOrWhiteSpace($Match)) {
    $args += @("--match", $Match)
  }
}

if (![string]::IsNullOrWhiteSpace($ResultJson)) {
  $args += @("--result-json", $ResultJson)
}

if (![string]::IsNullOrWhiteSpace($AnnotatedOut)) {
  $args += @("--annotated-out", $AnnotatedOut)
}

if ($WithGt) {
  $args += "--with-gt"
}

Write-Host "Running remote image inference..."
& $python @args
if ($LASTEXITCODE -ne 0) {
  throw "infer_ac880_linux_image.py failed with exit code $LASTEXITCODE"
}
