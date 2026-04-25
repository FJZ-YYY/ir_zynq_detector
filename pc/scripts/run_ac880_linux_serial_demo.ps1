param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [string]$ComPort = "COM3",
  [int]$BaudRate = 115200,
  [string]$RemoteDir = "/home/root/irdet_demo",
  [ValidateSet("gray8", "gray8_pl_probe", "gray8_pl_real_layer", "pl_selftest", "full_demo")]
  [string]$Mode = "full_demo",
  [switch]$ProgramPl,
  [int]$PostProgramSettleSeconds = 3,
  [switch]$SilenceKernelConsole = $true
)

$ErrorActionPreference = "Stop"

$serialInvokeScript = Join-Path $RepoRoot "pc\scripts\invoke_ac880_serial_command.ps1"
$programPlScript = Join-Path $RepoRoot "pc\scripts\program_ac880_pl_only.ps1"

if (!(Test-Path $serialInvokeScript)) { throw "Script not found: $serialInvokeScript" }
if ($ProgramPl -and !(Test-Path $programPlScript)) { throw "Script not found: $programPlScript" }

if ($ProgramPl) {
  Write-Host "Programming PL bitstream before Linux serial demo..."
  & powershell -ExecutionPolicy Bypass -File $programPlScript -RepoRoot $RepoRoot
  if ($LASTEXITCODE -ne 0) {
    throw "program_ac880_pl_only.ps1 failed with exit code $LASTEXITCODE"
  }

  if ($PostProgramSettleSeconds -gt 0) {
    Write-Host "Waiting $PostProgramSettleSeconds second(s) for Linux serial output to settle..."
    Start-Sleep -Seconds $PostProgramSettleSeconds
  }

  Write-Host "Re-synchronizing Linux shell prompt over serial..."
  & $serialInvokeScript `
    -ComPort $ComPort `
    -BaudRate $BaudRate `
    -Commands @("echo SERIAL_LINK_READY") `
    -InterCommandDelayMs 500 `
    -IdleThresholdMs 1000 `
    -MaxReadSeconds 8 | Out-Null
}

$commands = @()
if ($SilenceKernelConsole) {
  $commands += "dmesg -n 1 >/dev/null 2>&1 || true"
}
$commands += "chmod +x $RemoteDir/run_demo_gray8.sh $RemoteDir/run_demo_gray8_with_pl_probe.sh $RemoteDir/run_demo_gray8_with_pl_real_layer.sh $RemoteDir/run_demo_tensor.sh $RemoteDir/run_pl_selftest.sh $RemoteDir/app/irdet_linux_ncnn_app $RemoteDir/app/irdet_linux_pl_dw3x3_tool $RemoteDir/lib/ld-linux-armhf.so.3 >/dev/null 2>&1 || true"

$commands += switch ($Mode) {
  "gray8" {
    @(
      "cd $RemoteDir",
      "./run_demo_gray8.sh"
    )
  }
  "gray8_pl_probe" {
    @(
      "cd $RemoteDir",
      "./run_demo_gray8_with_pl_probe.sh"
    )
  }
  "gray8_pl_real_layer" {
    @(
      "cd $RemoteDir",
      "./run_demo_gray8_with_pl_real_layer.sh"
    )
  }
  "pl_selftest" {
    @(
      "cd $RemoteDir",
      "./app/irdet_linux_pl_dw3x3_tool --all --skip-gpio"
    )
  }
  "full_demo" {
    @(
      "cd $RemoteDir",
      "./app/irdet_linux_pl_dw3x3_tool --all --skip-gpio",
      "./run_demo_gray8.sh"
    )
  }
}

switch ($Mode) {
  "gray8_pl_real_layer" {
    $IdleThresholdMs = 8000
    $MaxReadSeconds = 60
  }
  "gray8_pl_probe" {
    $IdleThresholdMs = 4000
    $MaxReadSeconds = 45
  }
  "pl_selftest" {
    $IdleThresholdMs = 4000
    $MaxReadSeconds = 45
  }
  default {
    $IdleThresholdMs = 1500
    $MaxReadSeconds = 30
  }
}

Write-Host "Running AC880 Linux serial demo mode=$Mode on $ComPort@$BaudRate ..."
& $serialInvokeScript `
  -ComPort $ComPort `
  -BaudRate $BaudRate `
  -Commands $commands `
  -InterCommandDelayMs 400 `
  -IdleThresholdMs $IdleThresholdMs `
  -MaxReadSeconds $MaxReadSeconds
