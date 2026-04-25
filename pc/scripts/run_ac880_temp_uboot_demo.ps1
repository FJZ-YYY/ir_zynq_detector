param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [string]$ComPort = "COM3",
  [int]$BaudRate = 115200,
  [ValidateSet("gray8", "gray8_pl_probe", "gray8_pl_real_layer", "pl_selftest")]
  [string]$Mode = "gray8",
  [switch]$RunBootSelftest
)

$ErrorActionPreference = "Stop"

$bootScript = Join-Path $RepoRoot "pc\scripts\test_ac880_uboot_ir_boot.ps1"
$programPlScript = Join-Path $RepoRoot "pc\scripts\program_ac880_pl_only.ps1"
$serialDemoScript = Join-Path $RepoRoot "pc\scripts\run_ac880_linux_serial_demo.ps1"

if (!(Test-Path $bootScript)) { throw "Script not found: $bootScript" }
if (!(Test-Path $programPlScript)) { throw "Script not found: $programPlScript" }
if (!(Test-Path $serialDemoScript)) { throw "Script not found: $serialDemoScript" }

Write-Host "Step 1/2: temporary U-Boot boot using IR detector bitstream + DTB..."
$bootArgs = @(
  "-ExecutionPolicy", "Bypass",
  "-File", $bootScript,
  "-RepoRoot", $RepoRoot,
  "-ComPort", $ComPort,
  "-BaudRate", $BaudRate
)
if ($RunBootSelftest.IsPresent) {
  $bootArgs += "-RunPostBootSelftest"
}
& powershell @bootArgs
if ($LASTEXITCODE -ne 0) {
  throw "test_ac880_uboot_ir_boot.ps1 failed with exit code $LASTEXITCODE"
}

Write-Host "Step 2/3: programming current local PL bitstream over JTAG ..."
& powershell -ExecutionPolicy Bypass -File $programPlScript -RepoRoot $RepoRoot
if ($LASTEXITCODE -ne 0) {
  throw "program_ac880_pl_only.ps1 failed with exit code $LASTEXITCODE"
}

Write-Host "Step 3/3: running Linux serial demo mode=$Mode ..."
& powershell -ExecutionPolicy Bypass -File $serialDemoScript `
  -RepoRoot $RepoRoot `
  -ComPort $ComPort `
  -BaudRate $BaudRate `
  -Mode $Mode
if ($LASTEXITCODE -ne 0) {
  throw "run_ac880_linux_serial_demo.ps1 failed with exit code $LASTEXITCODE"
}
