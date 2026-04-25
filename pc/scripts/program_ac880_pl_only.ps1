param(
  [string]$RepoRoot = "G:\FPGA\ir_zynq_detector",
  [string]$XsctBat = "F:\Xilinx\Vitis\2020.2\bin\xsct.bat"
)

$ErrorActionPreference = "Stop"

$tclScript = Join-Path $RepoRoot "vitis\program_pl_bitstream_only.tcl"

if (!(Test-Path $XsctBat)) { throw "xsct.bat not found: $XsctBat" }
if (!(Test-Path $tclScript)) { throw "Tcl script not found: $tclScript" }

Write-Host "Programming AC880 PL bitstream over JTAG..."
& $XsctBat $tclScript
if ($LASTEXITCODE -ne 0) {
  throw "program_pl_bitstream_only.tcl failed with exit code $LASTEXITCODE"
}

Write-Host "PL-only programming completed."
