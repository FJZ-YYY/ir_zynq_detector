param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [string]$BoardHost = "auto",
  [string[]]$BoardHostCandidates = @("169.254.132.113", "192.168.0.233", "192.168.0.2"),
  [int]$Port = 22,
  [string]$User = "root",
  [string]$Password = "root",
  [string]$RemoteDir = "/home/root/irdet_demo",
  [string]$ComPort = "",
  [int]$BaudRate = 115200,
  [string[]]$Modes = @("gray8", "runtime_dw_pl_compare", "inpath_dw_cpu_full", "inpath_dw_pl_full"),
  [switch]$SkipPackageAll,
  [switch]$SkipArmBuild,
  [switch]$CleanRemote,
  [switch]$DeleteStale,
  [switch]$SkipSerialLinkPrep
)

$ErrorActionPreference = "Stop"

$validModes = @(
  "gray8",
  "runtime_dw_pl_compare",
  "inpath_dw_cpu_full",
  "inpath_dw_pl_full"
)

$runLinuxDemo = Join-Path $RepoRoot "pc\scripts\run_ac880_linux_demo.ps1"
if (!(Test-Path $runLinuxDemo)) { throw "Script not found: $runLinuxDemo" }

if ($Modes.Count -eq 0) {
  throw "Modes cannot be empty."
}

foreach ($mode in $Modes) {
  if ($validModes -notcontains $mode) {
    throw "Unsupported regression mode: $mode"
  }
}

for ($index = 0; $index -lt $Modes.Count; $index++) {
  $mode = $Modes[$index]
  $skipPackageThisRun = $SkipPackageAll.IsPresent -or ($index -gt 0)
  $args = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $runLinuxDemo,
    "-RepoRoot", $RepoRoot,
    "-BoardHost", $BoardHost,
    "-Port", $Port,
    "-User", $User,
    "-Password", $Password,
    "-RemoteDir", $RemoteDir,
    "-Mode", $mode
  )

  if (![string]::IsNullOrWhiteSpace($ComPort)) {
    $args += @("-ComPort", $ComPort)
  }
  if ($BaudRate -gt 0) {
    $args += @("-BaudRate", $BaudRate)
  }
  if ($skipPackageThisRun) {
    $args += "-SkipPackage"
  }
  if ($SkipArmBuild.IsPresent -and !$skipPackageThisRun) {
    $args += "-SkipArmBuild"
  }
  if ($CleanRemote.IsPresent -and $index -eq 0) {
    $args += "-CleanRemote"
  }
  if ($DeleteStale.IsPresent -and $index -eq 0) {
    $args += "-DeleteStale"
  }
  if ($SkipSerialLinkPrep.IsPresent) {
    $args += "-SkipSerialLinkPrep"
  }

  Write-Host ""
  Write-Host ("==== Regression {0}/{1}: mode={2} ====" -f ($index + 1), $Modes.Count, $mode)
  & powershell @args
  if ($LASTEXITCODE -ne 0) {
    throw "run_ac880_linux_demo.ps1 failed for mode=$mode with exit code $LASTEXITCODE"
  }
}

Write-Host ""
Write-Host "AC880 in-path regression PASS"
